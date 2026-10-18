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
    runner._stop_idle()
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

    # One pre-spawned idle worker may legitimately remain on spawn platforms.
    def survivors():
        idle_proc = runner._IDLE.proc if runner._IDLE else None
        return [child for child in multiprocessing.active_children() if child is not idle_proc]

    deadline = time.monotonic() + 10
    while survivors() and time.monotonic() < deadline:
        time.sleep(0.05)
    assert not survivors()
    monkeypatch.setattr(config, "CONVERSION_TIMEOUT", 30.0)
    result = runner.run("image", "jpg", _png(tmp_path), tmp_path / "out2.jpg", {})
    assert result.extension == "jpg"


def _spawn_platform() -> bool:
    return runner._mp_context()._name == "spawn"


def _wait_for_idle(timeout=15.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if runner._IDLE is not None and runner._IDLE.proc.is_alive():
            return runner._IDLE
        time.sleep(0.1)
    return None


def test_idle_worker_spawned(process_mode, tmp_path):
    result = runner.run("image", "jpg", _png(tmp_path), tmp_path / "out.jpg", {})
    assert result.extension == "jpg"
    if _spawn_platform():
        assert _wait_for_idle() is not None
    else:
        assert runner._IDLE is None


def test_idle_worker_warm_conversion(process_mode, tmp_path):
    if not _spawn_platform():
        pytest.skip("pre-spawned idle workers only exist on spawn platforms")
    runner.run("image", "jpg", _png(tmp_path), tmp_path / "a.jpg", {})
    assert _wait_for_idle() is not None
    time.sleep(1.0)  # let the worker reach its blocking recv()
    start = time.monotonic()
    result = runner.run("image", "jpg", _png(tmp_path), tmp_path / "b.jpg", {})
    elapsed = time.monotonic() - start
    assert result.extension == "jpg"
    assert elapsed < 1.0


def test_idle_worker_exits_on_closed_pipe(process_mode):
    if not _spawn_platform():
        pytest.skip("pre-spawned idle workers only exist on spawn platforms")
    runner._replenish_idle()
    worker = _wait_for_idle()
    assert worker is not None
    with runner._IDLE_LOCK:
        runner._IDLE = None
    runner._close_worker(worker)
    worker.proc.join(5)
    assert not worker.proc.is_alive()
    assert worker.proc.exitcode == 0


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
