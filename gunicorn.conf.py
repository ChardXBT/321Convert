"""Gunicorn server configuration.

Loaded automatically by gunicorn even when the start command only names the
app (``gunicorn app:app``), so deployment does not depend on the platform
syncing a modified build command.
"""

import subprocess
import sys


def on_starting(server):
    # Startup-only subprocess keeps model downloads/imports out of web workers.
    # Missing/corrupt models fail readiness, before accepting any uploads.
    subprocess.run(  # noqa: S603 -- fixed argv, no shell, no user input
        [sys.executable, "-m", "conversions.ocr_models"], check=True, timeout=180
    )
