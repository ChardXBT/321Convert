"""Upload handling: filename sanitising, content sniffing, Office archive
checks and text decoding. Everything here runs in the parent process before a
conversion is handed to the runner.
"""

import re
import zipfile
from dataclasses import dataclass
from pathlib import Path

from core import config, registry
from core.errors import RequestValidationError

_TEXT_EXTENSIONS = {"txt", "html", "htm", "md", "markdown", "csv"}
_OFFICE_REQUIRED = {
    "xlsx": ("xl/workbook.xml", "The file is not a valid Excel workbook."),
    "docx": ("word/document.xml", "The file is not a valid Word document."),
}

_UNSAFE_CHARS = re.compile(r'[\x00-\x1f\x7f<>:"/\\|?*]')
_WHITESPACE = re.compile(r"\s+")


def sanitize_stem(filename: str) -> str:
    """A safe, Unicode-aware filename stem for the download name."""
    name = re.split(r"[/\\]", filename or "")[-1]
    stem = Path(name).stem
    stem = _UNSAFE_CHARS.sub("", stem)
    stem = _WHITESPACE.sub(" ", stem).strip(" .")
    return stem[:80] or "file"


def extension_of(filename: str) -> str:
    return Path(filename).suffix.lower().lstrip(".")


@dataclass
class UploadInfo:
    path: Path
    extension: str
    family: registry.Family
    stem: str


def save_upload(storage, directory) -> UploadInfo:
    """Validate and store an uploaded file as ``input.<ext>`` in *directory*."""
    if storage is None or not storage.filename:
        raise RequestValidationError("Choose a file to convert.")
    extension = extension_of(storage.filename)
    if not extension:
        raise RequestValidationError("The file has no extension.")
    family = registry.family_for_extension(extension)
    if family is None:
        raise RequestValidationError(f"Files of type .{extension} are not supported.")

    path = Path(directory, f"input.{extension}")
    storage.save(path)
    if not path.is_file() or path.stat().st_size == 0:
        raise RequestValidationError("The uploaded file is empty.")

    sniff(path, extension)
    return UploadInfo(path, extension, family, sanitize_stem(storage.filename))


def sniff(path: Path, extension: str) -> None:
    """Reject files that cannot possibly be what their extension claims."""
    if extension == "pdf":
        with path.open("rb") as handle:
            if b"%PDF-" not in handle.read(1024):
                raise RequestValidationError("The file is not a valid PDF.")
    elif extension in _OFFICE_REQUIRED:
        with path.open("rb") as handle:
            if handle.read(4) != b"PK\x03\x04":
                raise RequestValidationError(_OFFICE_REQUIRED[extension][1])
        validate_office_archive(path, extension)
    elif extension in _TEXT_EXTENSIONS:
        with path.open("rb") as handle:
            if b"\x00" in handle.read(8192):
                raise RequestValidationError("The file does not look like a text file.")
    # Images are sniffed in the child process: Pillow's formats= allowlist
    # both validates the container and decodes it.


def validate_office_archive(path: Path, extension: str) -> None:
    """An .xlsx/.docx is a ZIP: bound it and check its structure first."""
    required_member, invalid_message = _OFFICE_REQUIRED[extension]
    try:
        with zipfile.ZipFile(path) as archive:
            members = archive.infolist()
            if (
                len(members) > config.MAX_ARCHIVE_FILES
                or sum(member.file_size for member in members) > config.MAX_ARCHIVE_BYTES
            ):
                raise RequestValidationError("The document expands beyond the processing limit.")
            for member in members:
                if member.filename.startswith(("/", "\\")) or ".." in Path(member.filename).parts:
                    raise RequestValidationError("The document contains unsafe archive paths.")
            names = set(archive.namelist())
            if "[Content_Types].xml" not in names or required_member not in names:
                raise RequestValidationError(invalid_message)
    except zipfile.BadZipFile as exc:
        raise RequestValidationError(invalid_message) from exc


def read_text(path: Path) -> str:
    """Decode a text upload: UTF-8 (with BOM) or cp1252; LF line endings."""
    data = Path(path).read_bytes()
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        # cp1252 has five undefined bytes (0x81/0x8D/0x8F/0x90/0x9D); they must
        # not make an otherwise readable file fail.
        text = data.decode("cp1252", errors="replace")
    return text.replace("\r\n", "\n").replace("\r", "\n")
