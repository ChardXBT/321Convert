"""OCR coverage: scanned PDFs via pdf->txt/docx and images via image->txt.

These exercise the real RapidOCR engine (inline isolation) so they take a few
seconds each; they stay in the default suite on purpose.
"""

import io
import json
from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFont

from core import config
from tests import samples

FONT_PATH = Path(__file__).resolve().parent.parent / "conversions" / "fonts" / "DejaVuSans.ttf"

LINES = [
    "INVOICE TOTAL 1234 USD",
    "Scanned document line two",
    "Another row of text here",
    "Reference number 987654",
    "Final scanned line five",
]


def _scanned_page() -> Image.Image:
    image = Image.new("RGB", (1240, 1754), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(str(FONT_PATH), 30)
    for index, line in enumerate(LINES):
        draw.text((80, 120 + index * 80), line, fill="black", font=font)
    return image


def _scanned_png() -> io.BytesIO:
    buffer = io.BytesIO()
    _scanned_page().save(buffer, "PNG")
    buffer.seek(0)
    return buffer


def _scanned_pdf(pages: int = 1) -> io.BytesIO:
    images = [_scanned_page() for _ in range(pages)]
    buffer = io.BytesIO()
    images[0].save(buffer, "PDF", save_all=pages > 1, append_images=images[1:])
    buffer.seek(0)
    return buffer


def _notes(response) -> list[str]:
    return json.loads(response.headers.get("X-Conversion-Notes", "[]"))


def _collapsed(text: str) -> str:
    return " ".join(text.upper().split())


pytestmark = pytest.mark.ocr


def test_pdf_to_txt_ocr(client):
    response = samples.convert(client, "scan.pdf", _scanned_pdf(), "txt")
    assert response.status_code == 200
    assert response.mimetype == "text/plain"
    assert "INVOICE" in _collapsed(response.data.decode("utf-8"))
    assert any("recognised with OCR" in note for note in _notes(response))


def test_pdf_to_docx_ocr(client):
    response = samples.convert(client, "scan.pdf", _scanned_pdf(), "docx")
    assert response.status_code == 200
    from docx import Document

    document = Document(io.BytesIO(response.data))
    text = _collapsed("\n".join(paragraph.text for paragraph in document.paragraphs))
    assert "INVOICE" in text


def test_ocr_page_cap(client, monkeypatch):
    monkeypatch.setattr(config, "OCR_MAX_PAGES", 1)
    response = samples.convert(client, "scan.pdf", _scanned_pdf(pages=2), "txt")
    assert response.status_code == 200
    text = _collapsed(response.data.decode("utf-8"))
    notes = _notes(response)
    assert "INVOICE" in text
    assert any("stopped after 1 page(s)" in note for note in notes)
    assert any("recognised with OCR" in note for note in notes)


def test_ocr_time_budget_zero(client, monkeypatch):
    monkeypatch.setattr(config, "OCR_TIME_BUDGET", 0)
    response = samples.convert(client, "scan.pdf", _scanned_pdf(), "txt")
    assert response.status_code == 200
    notes = _notes(response)
    assert any("stopped after 0 page(s)" in note for note in notes)
    assert not any("recognised with OCR" in note for note in notes)


def test_ocr_budget_predictive(client, monkeypatch):
    import time as time_module

    from conversions import ocr

    monkeypatch.setattr(config, "OCR_TIME_BUDGET", 0.4)
    calls = []

    def slow_recognize(image):
        calls.append(1)
        time_module.sleep(0.3)
        return "pretend recognised text"

    monkeypatch.setattr(ocr, "recognize", slow_recognize)
    response = samples.convert(client, "scan.pdf", _scanned_pdf(pages=3), "txt")
    assert response.status_code == 200
    assert len(calls) == 1
    assert any("stopped after 1 page(s)" in note for note in _notes(response))


def test_image_to_txt(client):
    response = samples.convert(client, "scan.png", _scanned_png(), "txt")
    assert response.status_code == 200
    assert response.mimetype == "text/plain"
    assert "INVOICE" in _collapsed(response.data.decode("utf-8"))
    assert "Text was recognised with OCR; check it for errors." in _notes(response)


def test_selectable_pdf_skips_ocr(client, monkeypatch):
    from conversions import ocr

    def _boom(image):
        raise AssertionError("OCR must not run for pages with selectable text")

    monkeypatch.setattr(ocr, "recognize", _boom)
    response = samples.convert(client, "text.pdf", samples.pdf_text(["selectable words"]), "txt")
    assert response.status_code == 200
    assert "selectable words" in response.data.decode("utf-8")
