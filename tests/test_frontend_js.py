"""Runs the frontend state-machine tests (tests/js/*.test.mjs) under Node.

The browser tests stay optional (``pytest -m e2e``); these drive the same
static/app.js logic through a DOM stub so they run everywhere Node exists.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
JS_TESTS = sorted((REPO / "tests" / "js").glob("*.test.mjs"))
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")


def test_frontend_file_lifecycle():
    result = subprocess.run(  # noqa: S603 -- fixed interpreter, repo-local files
        [NODE, "--test", *[str(p) for p in JS_TESTS]],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
