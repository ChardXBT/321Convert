import multiprocessing
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
from PIL import Image

from core import config, resources, runner
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
    # The worker may still be in its spawn-time preload before reaching recv().
    worker.proc.join(20)
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
    # Independent of the host's cgroup memory limit.
    monkeypatch.setattr(runner, "_SEMAPHORE", threading.BoundedSemaphore(2))
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
    monkeypatch.setattr(runner, "_SEMAPHORE", threading.BoundedSemaphore(2))
    runner._SEMAPHORE.acquire()
    runner._SEMAPHORE.acquire()
    try:
        response = samples.convert(client, "x.png", samples.png(), "jpg")
    finally:
        runner._SEMAPHORE.release()
        runner._SEMAPHORE.release()
    assert response.status_code == 503
    assert response.headers["Retry-After"] == "15"


def _fake_cgroup_files(monkeypatch, values):
    """Patch Path.read_text so only the cgroup memory files are faked."""
    real_read_text = Path.read_text

    def fake_read_text(self, *args, **kwargs):
        name = str(self).replace("\\", "/")
        for suffix, value in values.items():
            if name.endswith(suffix):
                if value is None:
                    raise OSError("missing")
                return value
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", fake_read_text)


def test_memory_limit_cgroup_v2(monkeypatch):
    _fake_cgroup_files(monkeypatch, {"memory.max": "536870912\n"})
    assert resources.memory_limit() == 536870912


def test_memory_limit_unlimited_marker(monkeypatch):
    _fake_cgroup_files(monkeypatch, {"memory.max": "max\n", "memory.limit_in_bytes": None})
    assert resources.memory_limit() is None


def test_memory_limit_v1_fallback(monkeypatch):
    _fake_cgroup_files(monkeypatch, {"memory.max": None, "memory.limit_in_bytes": "1073741824\n"})
    assert resources.memory_limit() == 1073741824


@pytest.mark.parametrize(
    ("memory_bytes", "requested", "expected"),
    [
        (None, 2, 2),  # no cgroup limit: requested concurrency stands
        (512 * config.MIB, 2, 1),  # 512MiB instance: reserve leaves room for one
        (1024 * config.MIB, 2, 2),  # 1GiB: requested concurrency fits
        (None, 0, 1),  # requested zero is raised to one
    ],
)
def test_concurrency_limit(monkeypatch, memory_bytes, requested, expected):
    monkeypatch.setattr(resources, "memory_limit", lambda: memory_bytes)
    monkeypatch.setattr(config, "MAX_CONCURRENT_CONVERSIONS", requested)
    assert resources.concurrency_limit() == expected


@pytest.mark.skipif(sys.platform != "linux", reason="RLIMIT_DATA setup only runs on Linux")
def test_limit_memory_bounds_allocation():
    # Runs in a subprocess so the test process itself never allocates the
    # oversized buffer or gets a lowered rlimit.
    script = (
        "from core import config, resources\n"
        "config.CONVERSION_MEMORY_BYTES = 32 * config.MIB\n"
        "resources.limit_memory()\n"
        "try:\n"
        "    bytearray(128 * config.MIB)\n"
        "except MemoryError:\n"
        "    print('memory-error', flush=True)\n"
        "    raise SystemExit(0)\n"
        "print('no-limit', flush=True)\n"
        "raise SystemExit(2)\n"
    )
    result = subprocess.run(  # noqa: S603 -- fixed interpreter, literal script
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parent.parent,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "memory-error" in result.stdout


def _mock_worker():
    from unittest.mock import Mock

    return runner._Worker(
        proc=Mock(is_alive=Mock(return_value=True)),
        job_conn=Mock(),
        result_conn=Mock(),
    )


def test_run_process_send_retry_failure_cleans_both_workers(monkeypatch):
    """Both job sends failing must not leak either worker."""
    first = _mock_worker()
    second = _mock_worker()
    first.job_conn.send.side_effect = BrokenPipeError
    second.job_conn.send.side_effect = BrokenPipeError
    from unittest.mock import Mock

    monkeypatch.setattr(runner, "_take_idle", lambda: None)
    monkeypatch.setattr(runner, "_start_worker", Mock(side_effect=[first, second]))

    with pytest.raises(BrokenPipeError):
        runner._run_process("image", "jpg", "in.png", "out.jpg", {})

    for worker in (first, second):
        worker.proc.kill.assert_called_once()
        worker.proc.join.assert_called()
        worker.job_conn.close.assert_called()
        worker.result_conn.close.assert_called()


def test_run_process_poll_error_cleans_worker(monkeypatch, tmp_path):
    """A poll() failure must still kill and reap the child and close pipes."""
    from types import SimpleNamespace

    worker = _mock_worker()
    worker.result_conn.poll.side_effect = OSError("pipe broke")
    monkeypatch.setattr(runner, "_take_idle", lambda: worker)
    monkeypatch.setattr(runner, "_mp_context", lambda: SimpleNamespace(_name="forkserver"))

    with pytest.raises(OSError, match="pipe broke"):
        runner._run_process("image", "jpg", "in.png", "out.jpg", {})

    worker.proc.kill.assert_called_once()
    worker.proc.join.assert_called()
    worker.job_conn.close.assert_called()
    worker.result_conn.close.assert_called()
