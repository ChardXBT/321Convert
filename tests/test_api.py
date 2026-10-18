import io
import json

from core import config
from tests import samples


def test_api_formats_shape(client):
    response = client.get("/api/formats")
    assert response.status_code == 200
    data = response.get_json()
    assert {"max_upload_mb", "accept", "families", "options"} <= set(data)
    assert isinstance(data["families"], list) and data["families"]
    family = data["families"][0]
    assert {"id", "label", "extensions", "outputs", "options"} <= set(family)


def test_missing_file_400(client):
    response = client.post("/api/convert", data={"target": "jpg"})
    assert response.status_code == 400
    assert "Choose a file" in response.get_json()["error"]


def test_unsupported_extension_400(client):
    response = samples.convert(client, "a.exe", io.BytesIO(b"x"), "jpg")
    assert response.status_code == 400
    assert "not supported" in response.get_json()["error"]


def test_no_extension_400(client):
    response = samples.convert(client, "noext", io.BytesIO(b"x"), "jpg")
    assert response.status_code == 400


def test_target_not_allowed_for_family(client):
    response = samples.convert(client, "d.xlsx", samples.xlsx(), "jpg")
    assert response.status_code == 400
    assert "Spreadsheet files cannot be converted to JPG" in response.get_json()["error"]


def test_unicode_filename_rfc5987(client):
    response = samples.convert(client, "Résumé 2024.png", samples.png(), "jpg")
    assert response.status_code == 200
    disposition = response.headers["Content-Disposition"]
    assert "R%C3%A9sum%C3%A9%202024.jpg" in disposition
    assert ".." not in disposition and "/" not in disposition.split("filename")[0]


def test_long_filename_truncated(client):
    name = "a" * 500 + ".png"
    response = samples.convert(client, name, samples.png(), "jpg")
    assert response.status_code == 200
    assert len(response.headers["Content-Disposition"]) < 200


def test_same_extension_gets_converted_suffix(client):
    response = samples.convert(client, "photo.png", samples.png(), "png")
    assert "photo-converted.png" in response.headers["Content-Disposition"]


def test_notes_header_is_json_list(client):
    response = samples.convert(client, "a.gif", samples.gif_animated(3), "png")
    notes = json.loads(response.headers["X-Conversion-Notes"])
    assert isinstance(notes, list)


def test_legacy_convert_image(client):
    response = client.post(
        "/convert",
        data={"image": (samples.png(), "pic.png"), "output_format": "jpg", "quality": "80"},
        content_type="multipart/form-data",
    )
    assert response.status_code == 200
    assert response.mimetype == "image/jpeg"


def test_legacy_document_conversions(client):
    cases = [
        ("html_to_pdf", "p.html", samples.html(), "application/pdf"),
        ("excel_to_pdf", "d.xlsx", samples.xlsx(), "application/pdf"),
        (
            "pdf_to_docx",
            "d.pdf",
            samples.pdf_text(["hi"]),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ),
        ("create_csv_from_excel", "d.xlsx", samples.xlsx(), "text/csv"),
        ("text_to_html", "n.txt", samples.text(), "text/html"),
    ]
    for conversion, filename, data, mimetype in cases:
        response = client.post(
            "/document/convert",
            data={"file": (data, filename), "conversion_type": conversion},
            content_type="multipart/form-data",
        )
        assert response.status_code == 200, conversion
        assert response.mimetype == mimetype, conversion


def test_legacy_unknown_conversion_400(client):
    response = client.post(
        "/document/convert",
        data={"file": (samples.text(), "n.txt"), "conversion_type": "nope"},
        content_type="multipart/form-data",
    )
    assert response.status_code == 400


def test_404_and_405_json(client):
    assert client.get("/nope").status_code == 404
    assert client.get("/nope").get_json()["success"] is False
    assert client.post("/health").status_code == 405


def test_health_version(client):
    data = client.get("/health").get_json()
    assert data["status"] == "ok" and "version" in data


def test_output_size_cap(client, monkeypatch):
    monkeypatch.setattr(config, "MAX_OUTPUT_BYTES", 10)
    response = samples.convert(client, "x.png", samples.png(), "jpg")
    assert response.status_code == 422
    assert "too large" in response.get_json()["error"]


def test_output_size_rejected_before_read(client, monkeypatch, tmp_path):
    """An oversized output must be refused from stat(), before read_bytes()."""
    from pathlib import Path

    from core import runner as runner_module
    from core.runner import ConversionResult

    monkeypatch.setattr(config, "MAX_OUTPUT_BYTES", 16)
    oversized = tmp_path / "out.jpg"
    oversized.write_bytes(b"x" * 17)
    monkeypatch.setattr(
        runner_module,
        "run",
        lambda *args, **kwargs: ConversionResult(oversized, "jpg", []),
    )

    real_read_bytes = Path.read_bytes
    forbidden_reads = []

    def fake_read_bytes(self, *args, **kwargs):
        if self == oversized:
            forbidden_reads.append(self)
            raise AssertionError("read_bytes must not run for an oversized output")
        return real_read_bytes(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_bytes", fake_read_bytes)

    response = samples.convert(client, "x.png", samples.png(), "jpg")
    assert response.status_code == 422
    assert "too large" in response.get_json()["error"]
    assert forbidden_reads == []
