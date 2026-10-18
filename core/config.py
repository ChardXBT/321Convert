"""Runtime tunables, read once from the environment at import.

Tests monkeypatch these attributes, so callers must read them as
``config.NAME`` at call time, never ``from core.config import NAME``.
"""

import os

MIB = 1024 * 1024


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _str(name: str, default: str) -> str:
    return os.getenv(name, default)


def _bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


MAX_UPLOAD_BYTES = _int("MAX_UPLOAD_BYTES", 25 * MIB)
MAX_OUTPUT_BYTES = _int("MAX_OUTPUT_BYTES", 75 * MIB)
MAX_ARCHIVE_BYTES = _int("MAX_ARCHIVE_BYTES", 100 * MIB)
MAX_ARCHIVE_FILES = _int("MAX_ARCHIVE_FILES", 500)

RATE_LIMIT_REQUESTS = _int("RATE_LIMIT_REQUESTS", 60)
RATE_LIMIT_WINDOW = _int("RATE_LIMIT_WINDOW", 600)

CONVERSION_TIMEOUT = _float("CONVERSION_TIMEOUT", 90.0)
CONVERSION_ISOLATION = _str("CONVERSION_ISOLATION", "process")
MAX_CONCURRENT_CONVERSIONS = _int("MAX_CONCURRENT_CONVERSIONS", 2)
BUSY_WAIT_SECONDS = _float("BUSY_WAIT_SECONDS", 20.0)

MAX_IMAGE_PIXELS = _int("MAX_IMAGE_PIXELS", 40_000_000)
MAX_FRAMES = _int("MAX_FRAMES", 300)
MAX_ANIMATION_PIXELS = _int("MAX_ANIMATION_PIXELS", 120_000_000)

MAX_PDF_PAGES = _int("MAX_PDF_PAGES", 300)
MAX_PDF_RENDER_PAGES = _int("MAX_PDF_RENDER_PAGES", 50)
PDF_RENDER_SCALE = _float("PDF_RENDER_SCALE", 2.0)

MAX_SPREADSHEET_CELLS = _int("MAX_SPREADSHEET_CELLS", 500_000)
MAX_PDF_TABLE_ROWS = _int("MAX_PDF_TABLE_ROWS", 2000)

MAX_HTML_BYTES = _int("MAX_HTML_BYTES", 3 * MIB)
MAX_EMBEDDED_IMAGE_BYTES = _int("MAX_EMBEDDED_IMAGE_BYTES", 8 * MIB)
MAX_EMBEDDED_IMAGES = _int("MAX_EMBEDDED_IMAGES", 60)

TRUST_PROXY = _bool("TRUST_PROXY", False)
LOG_LEVEL = _str("LOG_LEVEL", "INFO")
