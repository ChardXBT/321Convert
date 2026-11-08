"""Worker result protocol: the child->parent message must decode into a
declared outcome. Malformed messages are crashes, never KeyError/TypeError.
"""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from core import runner
from core.errors import ConversionCrashed, ConversionError


def _worker_with_message(monkeypatch, message):
    worker = runner._Worker(
        proc=Mock(is_alive=Mock(return_value=True)),
        job_conn=Mock(),
        result_conn=Mock(),
    )
    worker.result_conn.poll.return_value = True
    worker.result_conn.recv.return_value = message
    monkeypatch.setattr(runner, "_take_idle", lambda: worker)
    monkeypatch.setattr(runner, "_mp_context", lambda: SimpleNamespace(_name="forkserver"))
    return worker


def _run():
    return runner._run_process("image", "jpg", "in.png", "out.jpg", {})


@pytest.mark.parametrize(
    "message",
    [
        {"ok": True},  # missing "result": used to die as KeyError at runner.py:257
        {"ok": True, "result": None},
        {"ok": True, "result": "out.jpg"},
        {"ok": True, "result": {"path": "out.jpg"}},  # missing "extension"
        {"ok": "yes", "result": {"path": "out.jpg", "extension": "jpg"}},  # non-bool ok
        {"ok": 1, "result": {"path": "out.jpg", "extension": "jpg"}},
        {"ok": False, "user_message": 0, "error_type": None},  # falsy both -> crash
    ],
)
def test_malformed_worker_messages_decode_to_crashed(monkeypatch, message):
    _worker_with_message(monkeypatch, message)
    with pytest.raises(ConversionCrashed):
        _run()


def test_success_message_decodes_to_result(monkeypatch):
    _worker_with_message(
        monkeypatch,
        {"ok": True, "result": {"path": "out.jpg", "extension": "jpg", "notes": ["n1"]}},
    )
    result = _run()
    assert result.path == "out.jpg"
    assert result.extension == "jpg"
    assert result.notes == ["n1"]


def test_user_error_message_surfaces_and_keeps_error_type(monkeypatch, caplog):
    _worker_with_message(
        monkeypatch,
        {"ok": False, "user_message": "password-protected", "error_type": "ConversionError"},
    )
    with pytest.raises(ConversionError, match="password-protected"):
        _run()


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ({"ok": False}, "UnknownError"),
        ({"ok": False, "user_message": None, "error_type": None}, "UnknownError"),
        ({"ok": False, "error_type": "KeyError"}, "KeyError"),
        ("not-a-dict", "BadMessage"),
        ({"ok": None}, "BadMessage"),
    ],
)
def test_crash_and_bad_messages_decode(monkeypatch, message, expected):
    _worker_with_message(monkeypatch, message)
    with pytest.raises(ConversionCrashed, match=expected):
        _run()
