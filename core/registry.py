"""Families, outputs and options: the single source of truth for
"what converts to what". Kept in sync with docs/ARCHITECTURE.md.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from core import config
from core.errors import RequestValidationError


@dataclass(frozen=True)
class OutputFormat:
    ext: str
    label: str
    mimetype: str


@dataclass(frozen=True)
class Option:
    id: str
    label: str
    type: str  # "int" | "str"
    default: Any = None
    minimum: int | None = None
    maximum: int | None = None
    max_length: int | None = None
    help: str = ""
    outputs: frozenset | None = None
    families: frozenset | None = None


@dataclass(frozen=True)
class Family:
    id: str
    label: str
    extensions: frozenset
    outputs: tuple[str, ...]


MIMETYPES = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
    "gif": "image/gif",
    "bmp": "image/bmp",
    "tif": "image/tiff",
    "tiff": "image/tiff",
    "heic": "image/heif",
    "heif": "image/heif",
    "avif": "image/avif",
    "ico": "image/x-icon",
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "txt": "text/plain",
    "csv": "text/csv",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "html": "text/html",
    "htm": "text/html",
    "md": "text/markdown",
    "markdown": "text/markdown",
    "zip": "application/zip",
}

OUTPUT_FORMATS = {
    "jpg": OutputFormat("jpg", "JPG", MIMETYPES["jpg"]),
    "png": OutputFormat("png", "PNG", MIMETYPES["png"]),
    "webp": OutputFormat("webp", "WebP", MIMETYPES["webp"]),
    "gif": OutputFormat("gif", "GIF", MIMETYPES["gif"]),
    "bmp": OutputFormat("bmp", "BMP", MIMETYPES["bmp"]),
    "tiff": OutputFormat("tiff", "TIFF", MIMETYPES["tiff"]),
    "avif": OutputFormat("avif", "AVIF", MIMETYPES["avif"]),
    "ico": OutputFormat("ico", "ICO", MIMETYPES["ico"]),
    "pdf": OutputFormat("pdf", "PDF", MIMETYPES["pdf"]),
    "docx": OutputFormat("docx", "DOCX", MIMETYPES["docx"]),
    "txt": OutputFormat("txt", "TXT", MIMETYPES["txt"]),
    "csv": OutputFormat("csv", "CSV", MIMETYPES["csv"]),
    "xlsx": OutputFormat("xlsx", "XLSX", MIMETYPES["xlsx"]),
    "html": OutputFormat("html", "HTML", MIMETYPES["html"]),
    "zip": OutputFormat("zip", "ZIP", MIMETYPES["zip"]),
}

IMAGE_EXTENSIONS = frozenset(
    {"jpg", "jpeg", "png", "webp", "gif", "bmp", "tif", "tiff", "heic", "heif", "avif", "ico"}
)

FAMILIES = (
    Family(
        "image",
        "Image",
        IMAGE_EXTENSIONS,
        ("jpg", "png", "webp", "gif", "bmp", "tiff", "avif", "ico", "pdf"),
    ),
    Family("pdf", "PDF", frozenset({"pdf"}), ("docx", "txt", "png", "jpg")),
    Family("spreadsheet", "Spreadsheet", frozenset({"xlsx"}), ("csv", "pdf")),
    Family("csv", "CSV", frozenset({"csv"}), ("xlsx",)),
    Family("docx", "Word document", frozenset({"docx"}), ("pdf", "txt", "html")),
    Family("html", "HTML", frozenset({"html", "htm"}), ("pdf",)),
    Family("text", "Plain text", frozenset({"txt"}), ("pdf", "html")),
    Family("markdown", "Markdown", frozenset({"md", "markdown"}), ("html", "pdf")),
)

_FAMILY_BY_ID = {family.id: family for family in FAMILIES}
_FAMILY_BY_EXT = {ext: family for family in FAMILIES for ext in sorted(family.extensions)}

OPTIONS = (
    Option(
        id="quality",
        label="Quality",
        type="int",
        default=82,
        minimum=1,
        maximum=100,
        help="Higher keeps more detail and makes a larger file.",
        outputs=frozenset({"jpg", "webp", "avif"}),
    ),
    Option(
        id="max_dimension",
        label="Maximum dimension",
        type="int",
        minimum=16,
        maximum=10000,
        help="Shrink so the longest side is at most this many pixels. Never enlarges.",
        families=frozenset({"image"}),
    ),
    Option(
        id="sheet_name",
        label="Sheet name",
        type="str",
        max_length=100,
        help="Name of a single sheet; leave empty for the default.",
        families=frozenset({"spreadsheet"}),
    ),
    Option(
        id="title",
        label="Document title",
        type="str",
        max_length=120,
        help="Title used for the generated page.",
        families=frozenset({"text", "markdown"}),
        outputs=frozenset({"html"}),
    ),
)

_OPTION_BY_ID = {option.id: option for option in OPTIONS}

_CONTROL_CHARS = dict.fromkeys(range(0x20), None) | {0x7F: None}


def family_for_extension(ext: str) -> Family | None:
    return _FAMILY_BY_EXT.get(ext.lower().lstrip("."))


def output_format(ext: str) -> OutputFormat:
    return OUTPUT_FORMATS[ext.lower().lstrip(".")]


def options_for(family_id: str, output_ext: str) -> list[Option]:
    result = []
    for option in OPTIONS:
        if option.outputs is not None and output_ext not in option.outputs:
            continue
        if option.families is not None and family_id not in option.families:
            continue
        result.append(option)
    return result


def _clean_str(value: str, max_length: int | None) -> str:
    value = value.translate(_CONTROL_CHARS).strip()
    if max_length is not None:
        value = value[:max_length]
    return value


def validate_options(family_id: str, output_ext: str, form: Mapping[str, str]) -> dict:
    """Coerce the submitted options for this (family, output) pair.

    Only options applicable to the pair are returned; options left blank fall
    back to their default and options with no default are omitted. Unknown form
    fields are ignored, including ``_stem`` -- the route injects the sanitised
    filename stem under that key itself, after this function runs.
    """
    values = {}
    for option in options_for(family_id, output_ext):
        raw = form.get(option.id)
        if option.type == "int":
            if raw is None or raw.strip() == "":
                if option.default is not None:
                    values[option.id] = option.default
                continue
            try:
                number = int(raw.strip())
            except ValueError as exc:
                raise RequestValidationError(
                    f"{option.label} must be a whole number between {option.minimum} and {option.maximum}."
                ) from exc
            if not (option.minimum <= number <= option.maximum):
                raise RequestValidationError(
                    f"{option.label} must be a whole number between {option.minimum} and {option.maximum}."
                )
            values[option.id] = number
        else:
            if raw is None:
                if option.default is not None:
                    values[option.id] = option.default
                continue
            text = _clean_str(raw, option.max_length)
            if not text:
                if option.default is not None:
                    values[option.id] = option.default
                continue
            values[option.id] = text
    return values


def describe() -> dict:
    accept = ",".join(f".{ext}" for ext in sorted(_FAMILY_BY_EXT))
    return {
        "max_upload_mb": config.MAX_UPLOAD_BYTES // (1024 * 1024),
        "accept": accept,
        "families": [
            {
                "id": family.id,
                "label": family.label,
                "extensions": sorted(family.extensions),
                "outputs": [{"ext": ext, "label": OUTPUT_FORMATS[ext].label} for ext in family.outputs],
                "options": [option.id for option in OPTIONS if _applies_to_family(option, family.id)],
            }
            for family in FAMILIES
        ],
        "options": {
            option.id: {
                "label": option.label,
                "type": option.type,
                "default": option.default,
                "minimum": option.minimum,
                "maximum": option.maximum,
                "max_length": option.max_length,
                "help": option.help,
                "outputs": sorted(option.outputs) if option.outputs else None,
                "families": sorted(option.families) if option.families else None,
            }
            for option in OPTIONS
        },
    }


def _applies_to_family(option: Option, family_id: str) -> bool:
    if option.families is not None:
        return family_id in option.families
    family = _FAMILY_BY_ID[family_id]
    return option.outputs is None or any(ext in family.outputs for ext in option.outputs)
