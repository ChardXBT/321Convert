import multiprocessing
import time

import pytest
from PIL import Image

from core import config, runner
from core.errors import (
    ConversionCrashed,
    ConversionError,
    ConversionTimeout,
    ConverterBusy,
)
from tests import samples


@pytest.fixture()
def process_mode(monkeypatch):
    monkeypatch.setattr(config, "CONVERSION_ISOLATION", "process")
    yield
    for child in multiprocessing.active_children():
        child.kill()
        child.join(2)


def _png(tmp_path):
    path = tmp_path / "in.png"
    path.write_bytes(samples.png().read())
    return path


def test_process_png_to_jpg(process_mode, tmp_path):
    source = _png(tmp_path)
    output = tmp_path / "out.jpg"
    result = runner.run("image", "jpg", source, output, {})
    assert result.extension == "jpg"
    assert Image.open(result.path).format == "JPEG"


def test_timeout_kills_child(process_mode, monkeypatch, tmp_path):
    monkeypatch.setattr(config, "CONVERSION_TIMEOUT", 0.001)
    source = _png(tmp_path)
    with pytest.raises(ConversionTimeout):
        runner.run("image", "jpg", source, tmp_path / "out.jpg", {})
    deadline = time.monotonic() + 10
    while multiprocessing.active_children() and time.monotonic() < deadline:
        time.sleep(0.05)
    assert not multiprocessing.active_children()


def test_child_conversion_error_surfaces(process_mode, tmp_path):
    source = tmp_path / "locked.pdf"
    source.write_bytes(samples.pdf_encrypted().read())
    with pytest.raises(ConversionError, match="password-protected"):
        runner.run("pdf", "txt", source, tmp_path / "out.txt", {})


def test_child_crash_maps_to_crashed(process_mode, tmp_path):
    # An unmapped (family, output) raises KeyError in the child: an ordinary
    # exception there must come back as ConversionCrashed, not ConversionError.
    source = _png(tmp_path)
    with pytest.raises(ConversionCrashed):
        runner.run("image", "xyz", source, tmp_path / "out.xyz", {})


def test_busy_semaphore(process_mode, monkeypatch, tmp_path):
    monkeypatch.setattr(config, "BUSY_WAIT_SECONDS", 0.05)
    runner._SEMAPHORE.acquire()
    runner._SEMAPHORE.acquire()
    try:
        with pytest.raises(ConverterBusy):
            runner.run("image", "jpg", _png(tmp_path), tmp_path / "out.jpg", {})
    finally:
        runner._SEMAPHORE.release()
        runner._SEMAPHORE.release()


def test_busy_http_503(process_mode, client, monkeypatch, tmp_path):
    monkeypatch.setattr(config, "BUSY_WAIT_SECONDS", 0.05)
    runner._SEMAPHORE.acquire()
    runner._SEMAPHORE.acquire()
    try:
        response = samples.convert(client, "x.png", samples.png(), "jpg")
    finally:
        runner._SEMAPHORE.release()
        runner._SEMAPHORE.release()
    assert response.status_code == 503
    assert response.headers["Retry-After"] == "15"
