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
    imports) to start; for spawn there is nothing to pre-start, so the heavy
    imports are warmed in this process instead. Never raises.
    """
    try:
        if config.CONVERSION_ISOLATION != "process":
            return
        context = _mp_context()
        if "forkserver" in multiprocessing.get_all_start_methods():
            proc = context.Process(target=_noop, daemon=True)
            proc.start()
            proc.join(30)
        else:
            import conversions

            conversions.preload()
    except Exception:
        logger.warning("converter warm-up failed", exc_info=True)


def _child_main(conn, family_id, output_ext, input_path, output_path, options):
    """Child entry point. Never lets an exception escape."""
    try:
        try:
            import resource

            limit = math.ceil(config.CONVERSION_TIMEOUT) + 10
            resource.setrlimit(resource.RLIMIT_CPU, (limit, limit + 5))
        except Exception:  # noqa: S110 -- non-Linux, or rlimits unavailable
            pass

        import conversions

        converter = conversions.CONVERTERS[(family_id, output_ext)]
        result = converter(Path(input_path), Path(output_path), options)
        conn.send({"ok": True, "result": asdict(result)})
    except ConversionError as exc:
        try:
            conn.send(
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
            conn.send(
                {
                    "ok": False,
                    "user_message": None,
                    "error_type": type(exc).__name__,
                }
            )
        except Exception:  # noqa: S110 -- the parent treats a silent child as a crash
            pass
    finally:
        conn.close()


def _run_process(family_id, output_ext, input_path, output_path, options):
    context = _mp_context()
    parent_conn, child_conn = context.Pipe(duplex=False)
    proc = context.Process(
        target=_child_main,
        args=(child_conn, family_id, output_ext, str(input_path), str(output_path), options),
        daemon=True,
    )
    proc.start()
    child_conn.close()
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
