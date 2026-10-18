"""Converter registry. Modules here must stay import-light: heavy libraries
(Pillow, openpyxl, python-docx, pypdf, pypdfium2, xhtml2pdf, nh3, Markdown) are
imported inside functions, or eagerly in ``preload()`` which the forkserver
loads ahead of time via ``conversions.warm``.
"""

import warnings

# Modules are import-light, so importing them here is cheap.
from conversions import documents, images, ocr, pdf, spreadsheets
from core import config

CONVERTERS = {
    ("image", "jpg"): images.convert,
    ("image", "png"): images.convert,
    ("image", "webp"): images.convert,
    ("image", "gif"): images.convert,
    ("image", "bmp"): images.convert,
    ("image", "tiff"): images.convert,
    ("image", "avif"): images.convert,
    ("image", "heic"): images.convert,
    ("image", "ico"): images.convert,
    ("image", "pdf"): images.convert,
    ("image", "txt"): ocr.image_to_text,
    ("pdf", "docx"): pdf.to_docx,
    ("pdf", "txt"): pdf.to_txt,
    ("pdf", "png"): pdf.to_images,
    ("pdf", "jpg"): pdf.to_images,
    ("spreadsheet", "csv"): spreadsheets.to_csv,
    ("spreadsheet", "pdf"): spreadsheets.to_pdf,
    ("csv", "xlsx"): spreadsheets.csv_to_xlsx,
    ("docx", "pdf"): documents.docx_to_pdf,
    ("docx", "txt"): documents.docx_to_txt,
    ("docx", "html"): documents.docx_to_html,
    ("html", "pdf"): documents.html_to_pdf,
    ("text", "html"): documents.text_to_html,
    ("text", "pdf"): documents.text_to_pdf,
    ("markdown", "html"): documents.markdown_to_html,
    ("markdown", "pdf"): documents.markdown_to_pdf,
}

_HEIF_REGISTERED = False


def _pillow():
    """Return the Pillow ``Image`` module with hardened limits applied.

    Idempotent: sets the decompression-bomb ceiling, turns the warning into an
    error and registers pillow-heif's opener once.
    """
    global _HEIF_REGISTERED
    from PIL import Image

    Image.MAX_IMAGE_PIXELS = config.MAX_IMAGE_PIXELS
    warnings.simplefilter("error", Image.DecompressionBombWarning)
    if not _HEIF_REGISTERED:
        try:
            from pillow_heif import register_heif_opener

            register_heif_opener()
        except Exception:  # noqa: S110 -- HEIC/AVIF support is optional
            pass
        _HEIF_REGISTERED = True
    return Image


def preload() -> None:
    """Import every heavy dependency once, ahead of forking."""
    _pillow()
    import markdown  # noqa: F401
    import nh3  # noqa: F401
    import openpyxl  # noqa: F401
    import pypdf  # noqa: F401
    import pypdfium2  # noqa: F401
    from docx import Document  # noqa: F401

    from conversions import pdf_render  # noqa: F401  (imports xhtml2pdf)
