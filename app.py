import io
import logging
import os
import tempfile
import threading
import time
import zipfile
from collections import defaultdict, deque
from pathlib import Path
from urllib.parse import urlsplit

from flask import Flask, jsonify, render_template, request, send_file
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.utils import secure_filename

import conversions  # noqa: F401
from core.converter_factory import ConverterFactory


logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)
logging.getLogger("pypdf").setLevel(logging.CRITICAL)
logging.getLogger("pypdf._reader").setLevel(logging.CRITICAL)

MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", 25 * 1024 * 1024))
MAX_OUTPUT_BYTES = int(os.getenv("MAX_OUTPUT_BYTES", 75 * 1024 * 1024))
MAX_ARCHIVE_BYTES = int(os.getenv("MAX_ARCHIVE_BYTES", 100 * 1024 * 1024))
MAX_ARCHIVE_FILES = int(os.getenv("MAX_ARCHIVE_FILES", 500))
RATE_LIMIT_REQUESTS = int(os.getenv("RATE_LIMIT_REQUESTS", 20))
RATE_LIMIT_WINDOW = int(os.getenv("RATE_LIMIT_WINDOW", 600))

IMAGE_FORMATS = {"jpg", "jpeg", "png", "webp", "gif", "bmp", "tif", "tiff"}
IMAGE_OUTPUTS = {"jpg": "JPEG", "jpeg": "JPEG", "png": "PNG", "webp": "WEBP", "gif": "GIF", "bmp": "BMP", "tif": "TIFF", "tiff": "TIFF"}
DOCUMENT_CONVERSIONS = {
    "html_to_pdf": ({"html", "htm"}, "pdf"),
    "excel_to_pdf": ({"xlsx"}, "pdf"),
    "pdf_to_docx": ({"pdf"}, "docx"),
    "create_csv_from_excel": ({"xlsx"}, "csv"),
    "text_to_html": ({"txt"}, "html"),
}
MIME_TYPES = {
    "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp",
    "gif": "image/gif", "bmp": "image/bmp", "tif": "image/tiff", "tiff": "image/tiff",
    "pdf": "application/pdf", "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "csv": "text/csv", "html": "text/html", "txt": "text/plain",
}

app = Flask(__name__)
app.config.update(MAX_CONTENT_LENGTH=MAX_UPLOAD_BYTES, MAX_FORM_MEMORY_SIZE=MAX_UPLOAD_BYTES, MAX_FORM_PARTS=20)
if os.getenv("TRUST_PROXY", "false").lower() == "true":
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

rate_limit_lock = threading.Lock()
rate_limit_hits = defaultdict(deque)


class RequestValidationError(ValueError):
    pass


def error_response(message, status=400):
    return jsonify({"success": False, "error": message}), status


def get_extension(filename):
    return Path(filename).suffix.lower().lstrip(".")


def safe_upload(file_key, directory, allowed_extensions):
    upload = request.files.get(file_key)
    if not upload or not upload.filename:
        raise RequestValidationError("Choose a file to convert.")
    extension = get_extension(upload.filename)
    if extension not in allowed_extensions:
        raise RequestValidationError(f"This conversion does not accept .{extension or 'unknown'} files.")
    safe_name = secure_filename(upload.filename)
    safe_stem = Path(safe_name).stem[:100] if safe_name else "upload"
    name = f"{safe_stem}.{extension}"
    path = Path(directory, f"source_{name}")
    upload.save(path)
    if not path.is_file() or path.stat().st_size == 0:
        raise RequestValidationError("The uploaded file is empty.")
    if extension == "pdf":
        with path.open("rb") as pdf_file:
            if pdf_file.read(5) != b"%PDF-":
                raise RequestValidationError("The uploaded file is not a valid PDF.")
    validate_archive(path)
    return path


def validate_archive(path):
    if path.suffix.lower() not in {".xlsx", ".docx"}:
        return
    try:
        with zipfile.ZipFile(path) as archive:
            members = archive.infolist()
            total_size = sum(member.file_size for member in members)
            if len(members) > MAX_ARCHIVE_FILES or total_size > MAX_ARCHIVE_BYTES:
                raise RequestValidationError("The document expands beyond the processing limit.")
            if any(member.filename.startswith(("/", "\\")) or ".." in Path(member.filename).parts for member in members):
                raise RequestValidationError("The document contains unsafe archive paths.")
    except zipfile.BadZipFile as exc:
        raise RequestValidationError("The document is not a valid Office file.") from exc


def validate_number(value, name, minimum, maximum, default):
    try:
        number = int(value if value is not None else default)
    except (TypeError, ValueError) as exc:
        raise RequestValidationError(f"{name} must be a number.") from exc
    if not minimum <= number <= maximum:
        raise RequestValidationError(f"{name} must be between {minimum} and {maximum}.")
    return number


def file_response(path, download_name):
    path = Path(path)
    if not path.is_file():
        raise RuntimeError("The conversion did not create an output file.")
    if path.stat().st_size > MAX_OUTPUT_BYTES:
        raise RequestValidationError("The converted file is too large to return safely.")
    data = io.BytesIO(path.read_bytes())
    return send_file(data, mimetype=MIME_TYPES.get(get_extension(download_name), "application/octet-stream"),
                     as_attachment=True, download_name=download_name, max_age=0)


def limited():
    now = time.monotonic()
    client = request.remote_addr or "unknown"
    with rate_limit_lock:
        if len(rate_limit_hits) >= 10_000 and client not in rate_limit_hits:
            for key, old_hits in list(rate_limit_hits.items())[:1000]:
                while old_hits and old_hits[0] <= now - RATE_LIMIT_WINDOW:
                    old_hits.popleft()
                if not old_hits:
                    rate_limit_hits.pop(key, None)
            if len(rate_limit_hits) >= 10_000:
                return True
        hits = rate_limit_hits[client]
        while hits and hits[0] <= now - RATE_LIMIT_WINDOW:
            hits.popleft()
        if len(hits) >= RATE_LIMIT_REQUESTS:
            return True
        hits.append(now)
    return False


def cross_origin_request():
    origin = request.headers.get("Origin")
    if not origin:
        return False
    parsed = urlsplit(origin)
    return parsed.scheme not in {"http", "https"} or parsed.netloc != request.host


@app.before_request
def protect_conversion_routes():
    if request.method == "POST":
        if cross_origin_request():
            return error_response("Cross-origin conversion requests are not allowed.", 403)
        if limited():
            return error_response("Too many conversions. Please wait a few minutes and try again.", 429)


@app.after_request
def secure_headers(response):
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; img-src 'self' blob:; style-src 'self'; script-src 'self'; "
        "object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
    )
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=()"
    response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    if request.path.startswith("/static/"):
        response.headers["Cache-Control"] = "public, max-age=86400"
    else:
        response.headers["Cache-Control"] = "no-store"
    if request.is_secure:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


@app.errorhandler(RequestEntityTooLarge)
def upload_too_large(_error):
    return error_response(f"Files must be smaller than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.", 413)


@app.route("/")
def index():
    return render_template("index.html", max_upload_mb=MAX_UPLOAD_BYTES // (1024 * 1024))


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/convert", methods=["POST"])
def convert_image_route():
    try:
        output_extension = request.form.get("output_format", "").lower()
        if output_extension not in IMAGE_OUTPUTS:
            return error_response("Choose a supported output format.")
        quality = validate_number(request.form.get("quality"), "Quality", 1, 100, 82)
        with tempfile.TemporaryDirectory(prefix="321convert-") as directory:
            source = safe_upload("image", directory, IMAGE_FORMATS)
            result = ConverterFactory.convert(
                "convert_image", str(source), output_format=IMAGE_OUTPUTS[output_extension], quality=quality
            )
            return file_response(result, f"{source.stem.removeprefix('source_')}_converted.{output_extension}")
    except RequestValidationError as exc:
        return error_response(str(exc))
    except RequestEntityTooLarge:
        raise
    except Exception as exc:
        logger.warning("Image conversion failed (%s)", type(exc).__name__)
        return error_response("The image could not be converted. It may be damaged or unsupported.", 422)


@app.route("/document/convert", methods=["POST"])
def convert_document_route():
    conversion = request.form.get("conversion_type", "")
    if conversion not in DOCUMENT_CONVERSIONS:
        return error_response("Choose a supported conversion.")
    allowed_extensions, output_extension = DOCUMENT_CONVERSIONS[conversion]
    try:
        with tempfile.TemporaryDirectory(prefix="321convert-") as directory:
            source = safe_upload("file", directory, allowed_extensions)
            output = Path(directory, f"converted.{output_extension}")
            params = {"output_path": str(output)}
            if conversion in {"excel_to_pdf", "create_csv_from_excel"}:
                sheet_name = request.form.get("sheet_name", "").strip()
                if sheet_name:
                    params["sheet_name"] = sheet_name[:100]
            elif conversion == "text_to_html":
                params["title"] = request.form.get("title", "Converted Document").strip()[:120]
            result = ConverterFactory.convert(conversion, str(source), **params)
            if isinstance(result, str) and Path(result).is_file():
                output = Path(result)
            base = source.stem.removeprefix("source_")
            return file_response(output, f"{base}_converted.{output_extension}")
    except RequestValidationError as exc:
        return error_response(str(exc), 422)
    except RequestEntityTooLarge:
        raise
    except Exception as exc:
        logger.warning("Document conversion failed: %s (%s)", conversion, type(exc).__name__)
        return error_response("The document could not be converted. It may be damaged or unsupported.", 422)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.getenv("PORT", 5000)), debug=False)
