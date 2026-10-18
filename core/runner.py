"""Runs one conversion in an isolated child process with a hard timeout.

The child sends exactly one message back through a pipe; anything else --
timeout, crash, missing message -- maps to ConversionTimeout or
ConversionCrashed. Messages in exceptions never contain filenames or file
content. ``CONVERSION_ISOLATION=inline`` skips the child entirely (tests).
"""

import logging
import math
import multiprocessing
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path

from core import config
from core.errors import (
    ConversionCrashed,
    ConversionError,
    ConversionTimeout,
    ConverterBusy,
)

logger = logging.getLogger(__name__)


@dataclass
class ConversionResult:
    path: str
    extension: str
    notes: list[str] = field(default_factory=list)


_SEMAPHORE = threading.BoundedSemaphore(config.MAX_CONCURRENT_CONVERSIONS)
_MP_CONTEXT = None


def _mp_context():
    global _MP_CONTEXT
    if _MP_CONTEXT is None:
        start_method = "forkserver" if "forkserver" in multiprocessing.get_all_start_methods() else "spawn"
        context = multiprocessing.get_context(start_method)
        if start_method == "forkserver":
            context.set_forkserver_preload(["conversions.warm"])
        _MP_CONTEXT = context
    return _MP_CONTEXT


def _noop() -> None:
    pass


def warm_up() -> None:
    """Start the child machinery early so the first conversion is not slow.

    For forkserver this forces the server process (with its preloaded heavy
    imports) to start; for spawn an idle worker is pre-spawned so the heavy
    imports never land in this (web) process. Never raises.
    """
    try:
        if config.CONVERSION_ISOLATION != "process":
            return
        context = _mp_context()
        if context._name == "forkserver":
            proc = context.Process(target=_noop, daemon=True)
            proc.start()
            proc.join(30)
        else:
            _replenish_idle()
    except Exception:
        logger.warning("converter warm-up failed", exc_info=True)


def _worker_main(job_conn, result_conn):
    """Idle worker: warm heavy imports, take one job, run it, report, exit."""
    try:
        import conversions

        conversions.preload()
    except Exception:  # noqa: S110 -- the job path imports again and reports properly
        pass
    try:
        job = job_conn.recv()
    except (EOFError, OSError):
        job_conn.close()
        result_conn.close()
        return
    job_conn.close()
    try:
        try:
            import resource

            limit = math.ceil(config.CONVERSION_TIMEOUT) + 10
            resource.setrlimit(resource.RLIMIT_CPU, (limit, limit + 5))
        except Exception:  # noqa: S110 -- non-Linux, or rlimits unavailable
            pass

        import conversions

        family_id, output_ext, input_path, output_path, options = job
        converter = conversions.CONVERTERS[(family_id, output_ext)]
        result = converter(Path(input_path), Path(output_path), options)
        result_conn.send({"ok": True, "result": asdict(result)})
    except ConversionError as exc:
        try:
            result_conn.send(
                {
                    "ok": False,
                    "user_message": str(exc),
                    "error_type": type(exc).__name__,
                }
            )
        except Exception:  # noqa: S110 -- the parent treats a silent child as a crash
            pass
    except BaseException as exc:
        try:
            result_conn.send(
                {
                    "ok": False,
                    "user_message": None,
                    "error_type": type(exc).__name__,
                }
            )
        except Exception:  # noqa: S110 -- the parent treats a silent child as a crash
            pass
    finally:
        result_conn.close()


@dataclass
class _Worker:
    proc: object
    job_conn: object
    result_conn: object


_IDLE = None
_IDLE_LOCK = threading.Lock()


def _close_worker(worker) -> None:
    for conn in (worker.job_conn, worker.result_conn):
        try:
            conn.close()
        except Exception:  # noqa: S110 -- already closed/broken
            pass


def _start_worker() -> _Worker:
    # Pipe(duplex=False) yields (read end, write end): jobs flow parent->child,
    # results flow child->parent.
    context = _mp_context()
    job_read, job_write = context.Pipe(duplex=False)
    result_read, result_write = context.Pipe(duplex=False)
    proc = context.Process(
        target=_worker_main,
        args=(job_read, result_write),
        daemon=True,
    )
    proc.start()
    job_read.close()
    result_write.close()
    return _Worker(proc, job_write, result_read)


def _take_idle():
    global _IDLE
    with _IDLE_LOCK:
        worker = _IDLE
        _IDLE = None
    if worker is None:
        return None
    if not worker.proc.is_alive():
        _close_worker(worker)
        worker.proc.join(1)
        return None
    return worker


def _replenish_idle() -> None:
    """Keep one pre-spawned idle worker waiting on spawn platforms only."""
    global _IDLE
    if _mp_context()._name != "spawn":
        return
    with _IDLE_LOCK:
        if _IDLE is not None:
            if _IDLE.proc.is_alive():
                return
            _close_worker(_IDLE)
            _IDLE = None
        try:
            _IDLE = _start_worker()
        except Exception:
            _IDLE = None
            logger.warning("idle conversion worker could not be started", exc_info=True)


def _stop_idle() -> None:
    global _IDLE
    with _IDLE_LOCK:
        worker = _IDLE
        _IDLE = None
    if worker is not None:
        _close_worker(worker)
        worker.proc.join(5)
        if worker.proc.is_alive():
            worker.proc.kill()
            worker.proc.join(5)


def _run_process(family_id, output_ext, input_path, output_path, options):
    worker = _take_idle() or _start_worker()
    job = (family_id, output_ext, str(input_path), str(output_path), options)
    try:
        worker.job_conn.send(job)
    except (EOFError, OSError):
        _close_worker(worker)
        worker.proc.join(1)
        worker = _start_worker()
        worker.job_conn.send(job)
    worker.job_conn.close()
    # Respawning the idle worker is slow on spawn platforms (~0.5 s to create
    # the process), so it happens off the request path; the lock keeps it to
    # at most one waiting worker.
    threading.Thread(target=_replenish_idle, name="idle-worker-respawn", daemon=True).start()
    parent_conn = worker.result_conn
    proc = worker.proc
    try:
        if parent_conn.poll(config.CONVERSION_TIMEOUT):
            try:
                message = parent_conn.recv()
            except EOFError as exc:
                proc.join(10)
                raise ConversionCrashed("EOFError") from exc
        else:
            proc.kill()
            proc.join(5)
            raise ConversionTimeout()
        proc.join(10)
        if proc.is_alive():
            proc.kill()
            proc.join(5)
        if not isinstance(message, dict) or "ok" not in message:
            raise ConversionCrashed("BadMessage")
        if message["ok"]:
            result = message["result"]
            return ConversionResult(
                path=result["path"],
                extension=result["extension"],
                notes=list(result.get("notes") or []),
            )
        if message.get("user_message"):
            raise ConversionError(message["user_message"])
        raise ConversionCrashed(message.get("error_type") or "UnknownError")
    finally:
        parent_conn.close()


def _run_inline(family_id, output_ext, input_path, output_path, options):
    import conversions

    try:
        return conversions.CONVERTERS[(family_id, output_ext)](Path(input_path), Path(output_path), options)
    except ConversionError:
        raise
    except Exception as exc:
        raise ConversionCrashed(type(exc).__name__) from exc


def run(
    family_id: str,
    output_ext: str,
    input_path: Path,
    output_path: Path,
    options: dict,
) -> ConversionResult:
    if not _SEMAPHORE.acquire(timeout=config.BUSY_WAIT_SECONDS):
        raise ConverterBusy()
    try:
        if config.CONVERSION_ISOLATION == "inline":
            return _run_inline(family_id, output_ext, input_path, output_path, options)
        return _run_process(family_id, output_ext, input_path, output_path, options)
    finally:
        _SEMAPHORE.release()
