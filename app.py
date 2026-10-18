"""Flask app: routes, validation, security headers. See docs/ARCHITECTURE.md."""

import hashlib
import io
import json
import logging
import os
import secrets
import tempfile
import threading
import time
from collections import defaultdict, deque
from pathlib import Path
from urllib.parse import urlsplit

from flask import Flask, g, jsonify, render_template, request, send_file
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.middleware.proxy_fix import ProxyFix

from core import config, registry, runner, uploads
from core.errors import (
    ConversionCrashed,
    ConversionError,
    ConversionTimeout,
    ConverterBusy,
    RequestValidationError,
)

logging.basicConfig(level=config.LOG_LEVEL)
logger = logging.getLogger(__name__)
for name in ("pypdf", "xhtml2pdf", "xhtml2pdf.parser", "reportlab", "PIL"):
    logging.getLogger(name).setLevel(logging.CRITICAL)

app = Flask(__name__)
app.config.update(
    MAX_CONTENT_LENGTH=config.MAX_UPLOAD_BYTES,
    MAX_FORM_MEMORY_SIZE=config.MAX_UPLOAD_BYTES,
    MAX_FORM_PARTS=20,
)
if config.TRUST_PROXY:
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

APP_VERSION = (os.getenv("RENDER_GIT_COMMIT") or "dev")[:7]


def _asset_version() -> str:
    digest = hashlib.sha1()  # noqa: S324 -- cache-buster, not a security hash
    static = Path(__file__).parent / "static"
    for name in ("app.js", "styles.css", "favicon.svg"):
        path = static / name
        if path.is_file():
            digest.update(path.read_bytes())
    return digest.hexdigest()[:10]


ASSET_VERSION = _asset_version()

rate_limit_lock = threading.Lock()
rate_limit_hits = defaultdict(deque)

_warmed = threading.Event()

LEGACY_DOCUMENT_CONVERSIONS = {
    "html_to_pdf": "pdf",
    "excel_to_pdf": "pdf",
    "pdf_to_docx": "docx",
    "create_csv_from_excel": "csv",
    "text_to_html": "html",
}


def error_response(message, status=400):
    return jsonify({"success": False, "error": message}), status


def _rate_limited():
    """True when this client is over the limit; also returns Retry-After."""
    now = time.monotonic()
    window = config.RATE_LIMIT_WINDOW
    client = request.remote_addr or "unknown"
    with rate_limit_lock:
        if len(rate_limit_hits) >= 10_000 and client not in rate_limit_hits:
            for key, old_hits in list(rate_limit_hits.items())[:1000]:
                while old_hits and old_hits[0] <= now - window:
                    old_hits.popleft()
                if not old_hits:
                    rate_limit_hits.pop(key, None)
            if len(rate_limit_hits) >= 10_000:
                return True, window
        hits = rate_limit_hits[client]
        while hits and hits[0] <= now - window:
            hits.popleft()
        if len(hits) >= config.RATE_LIMIT_REQUESTS:
            return True, max(1, int(hits[0] + window - now))
        hits.append(now)
    return False, 0


def _cross_origin():
    if request.headers.get("Sec-Fetch-Site") == "cross-site":
        return True
    origin = request.headers.get("Origin")
    if not origin:
        return False
    parsed = urlsplit(origin)
    return parsed.scheme not in {"http", "https"} or parsed.netloc != request.host


@app.before_request
def protect():
    _warm_once()
    g.csp_nonce = secrets.token_urlsafe(16)
    if request.method != "POST":
        return None
    if _cross_origin():
        return error_response("Cross-origin requests are not allowed.", 403)
    limited, retry_after = _rate_limited()
    if limited:
        response, status = error_response(
            "Too many conversions. Please wait a few minutes and try again.", 429
        )
        response.headers["Retry-After"] = str(retry_after)
        return response, status
    return None


def _warm_once():
    if config.CONVERSION_ISOLATION == "process" and not _warmed.is_set():
        _warmed.set()
        threading.Thread(target=runner.warm_up, daemon=True).start()


@app.after_request
def secure_headers(response):
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; img-src 'self' blob:; style-src 'self'; "
        f"script-src 'self' 'nonce-{getattr(g, 'csp_nonce', '')}'; "
        "connect-src 'self'; font-src 'self'; object-src 'none'; "
        "base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
    )
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=()"
    response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    if request.path.startswith("/static/"):
        if request.args.get("v"):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        else:
            response.headers["Cache-Control"] = "public, max-age=3600"
    else:
        response.headers["Cache-Control"] = "no-store"
    if request.is_secure:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


@app.errorhandler(RequestEntityTooLarge)
def upload_too_large(_error):
    return error_response(
        f"Files must be smaller than {config.MAX_UPLOAD_BYTES // (1024 * 1024)} MB.",
        413,
    )


@app.errorhandler(404)
def not_found(_error):
    return error_response("Not found.", 404)


@app.errorhandler(405)
def method_not_allowed(_error):
    return error_response("Method not allowed.", 405)


@app.errorhandler(500)
def internal_error(_error):
    return error_response("Something went wrong.", 500)


@app.route("/")
def index():
    return render_template(
        "index.html",
        max_upload_mb=config.MAX_UPLOAD_BYTES // (1024 * 1024),
        registry_data=registry.describe(),
        csp_nonce=getattr(g, "csp_nonce", ""),
        asset_version=ASSET_VERSION,
        app_version=APP_VERSION,
    )


@app.route("/robots.txt")
def robots():
    return app.response_class("User-agent: *\nAllow: /\n", mimetype="text/plain")


@app.route("/health")
def health():
    try:
        with tempfile.NamedTemporaryFile(mode="w", dir=tempfile.gettempdir(), delete=True):
            pass
    except OSError:
        return jsonify({"status": "degraded"}), 503
    return jsonify({"status": "ok", "version": APP_VERSION})


@app.route("/api/formats")
def api_formats():
    return jsonify(registry.describe())


@app.route("/api/convert", methods=["POST"])
def api_convert():
    return _convert("file", request.form.get("target", ""), request.form)


@app.route("/convert", methods=["POST"])
def legacy_convert_image():
    return _convert("image", request.form.get("output_format", ""), request.form)


@app.route("/document/convert", methods=["POST"])
def legacy_convert_document():
    conversion = request.form.get("conversion_type", "")
    target = LEGACY_DOCUMENT_CONVERSIONS.get(conversion)
    if target is None:
        return error_response("Choose a supported conversion.", 400)
    return _convert("file", target, request.form)


def _convert(file_key, target, form):
    started = time.monotonic()
    family_id = "?"
    try:
        with tempfile.TemporaryDirectory(prefix="321convert-") as directory:
            info = uploads.save_upload(request.files.get(file_key), directory)
            family_id = info.family.id
            target = target.lower().lstrip(".")
            if target not in info.family.outputs:
                label = (
                    registry.output_format(target).label
                    if target in registry.OUTPUT_FORMATS
                    else target.upper()
                )
                raise RequestValidationError(f"{info.family.label} files cannot be converted to {label}.")
            options = registry.validate_options(family_id, target, form)
            options["_stem"] = info.stem

            output_path = Path(directory, f"output.{target}")
            in_size = info.path.stat().st_size
            result = runner.run(family_id, target, info.path, output_path, options)
            result_path = Path(result.path)
            if not result_path.is_file():
                raise ConversionCrashed("NoOutput")
            if result_path.stat().st_size > config.MAX_OUTPUT_BYTES:
                return error_response("The converted file is too large to return safely.", 422)
            data = result_path.read_bytes()
            if len(data) > config.MAX_OUTPUT_BYTES:
                return error_response("The converted file is too large to return safely.", 422)

        download_name = f"{info.stem}.{result.extension}"
        if result.extension == info.extension:
            download_name = f"{info.stem}-converted.{result.extension}"
        logger.info(
            "conversion ok family=%s target=%s ms=%d in=%d out=%d",
            family_id,
            target,
            int((time.monotonic() - started) * 1000),
            in_size,
            len(data),
        )
        response = send_file(
            io.BytesIO(data),
            mimetype=registry.output_format(result.extension).mimetype,
            as_attachment=True,
            download_name=download_name,
            max_age=0,
        )
        response.headers["X-Conversion-Notes"] = json.dumps(result.notes, ensure_ascii=True)
        return response
    except RequestValidationError as exc:
        return error_response(str(exc), 400)
    except ConversionError as exc:
        return error_response(str(exc), 422)
    except ConversionTimeout:
        return error_response("The conversion took too long and was stopped. Try a smaller file.", 504)
    except ConverterBusy:
        response, status = error_response(
            "The converter is busy right now. Please try again in a moment.", 503
        )
        response.headers["Retry-After"] = "15"
        return response, status
    except RequestEntityTooLarge:
        raise
    except ConversionCrashed as exc:
        logger.warning(
            "conversion failed family=%s target=%s error=%s",
            family_id,
            target,
            exc.args[0] if exc.args else "unknown",
        )
        return error_response("The file could not be converted. It may be damaged or unsupported.", 422)
    except Exception as exc:
        logger.warning(
            "conversion failed family=%s target=%s error=%s",
            family_id,
            target,
            type(exc).__name__,
        )
        return error_response("The file could not be converted. It may be damaged or unsupported.", 422)


if __name__ == "__main__":
    runner.warm_up()
    app.run(host="127.0.0.1", port=int(os.getenv("PORT", 5000)), debug=False)
