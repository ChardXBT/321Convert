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


def test_engine_thread_and_detector_limits(client):
    """After a real OCR run the engine must keep the settled resource caps."""
    response = samples.convert(client, "scan.png", _scanned_png(), "txt")
    assert response.status_code == 200

    from conversions import ocr

    detector = ocr._get_engine().text_det
    session_options = detector.session.session.get_session_options()
    assert session_options.intra_op_num_threads == 1
    assert session_options.inter_op_num_threads == 1
    assert detector.limit_type == "max"
    assert detector.limit_side_len == 736


def test_missing_models_fail_before_network(tmp_path, monkeypatch):
    """model_paths() must raise before any download attempt."""
    import requests

    from conversions import ocr_models

    monkeypatch.setattr(ocr_models, "model_directory", lambda: tmp_path)
    network_calls = []
    monkeypatch.setattr(requests, "get", lambda *a, **k: network_calls.append((a, k)))

    with pytest.raises(RuntimeError, match="OCR models are missing"):
        ocr_models.model_paths()
    assert network_calls == []


def test_image_to_txt_exif_rotation(client):
    """An EXIF-rotated scan must be recognised after orientation is applied."""
    rotated = _scanned_page().rotate(90, expand=True)
    exif = Image.Exif()
    exif[0x0112] = 6  # Orientation: display rotated 90 degrees CW
    buffer = io.BytesIO()
    rotated.save(buffer, "PNG", exif=exif)
    buffer.seek(0)

    response = samples.convert(client, "scan.png", buffer, "txt")
    assert response.status_code == 200
    assert "INVOICE" in _collapsed(response.data.decode("utf-8"))


@pytest.mark.parametrize("error_kind", ["python", "onnx-alloc", "onnx-arena"])
def test_ocr_memory_error_is_safe_and_actionable(client, monkeypatch, error_kind):
    from onnxruntime.capi import onnxruntime_pybind11_state as ort
    from rapidocr.inference_engine.onnxruntime.main import ONNXRuntimeError

    from conversions import ocr

    def failing_engine(_image):
        if error_kind == "python":
            raise MemoryError("synthetic-private-marker")
        cause = (
            ort.Fail("std::bad_alloc synthetic-private-marker")
            if error_kind == "onnx-alloc"
            else ort.RuntimeException("Failed to allocate memory synthetic-private-marker")
        )
        raise ONNXRuntimeError("synthetic-private-marker") from cause

    monkeypatch.setattr(ocr, "_get_engine", lambda: failing_engine)
    response = samples.convert(client, "scan.png", _scanned_png(), "txt")
    assert response.status_code == 422
    assert response.get_json()["error"] == ("The conversion needs too much memory. Try a smaller file.")
    assert b"synthetic-private-marker" not in response.data


def test_non_native_ocr_error_is_not_misclassified(client, monkeypatch):
    from conversions import ocr

    def failing_engine(_image):
        raise ValueError("std::bad_alloc synthetic-private-marker")

    monkeypatch.setattr(ocr, "_get_engine", lambda: failing_engine)
    response = samples.convert(client, "scan.png", _scanned_png(), "txt")
    assert response.status_code == 422
    assert response.get_json()["error"] == (
        "The file could not be converted. It may be damaged or unsupported."
    )
    assert b"synthetic-private-marker" not in response.data
