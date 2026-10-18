import io
import socket

from pypdf import PdfReader

from core import config
from tests import samples


def pdf_text_of(data: bytes) -> str:
    return "".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(data)).pages)


def test_docx_to_html_blocks(client):
    response = samples.convert(client, "doc.docx", samples.docx(), "html")
    assert response.status_code == 200
    body = response.data.decode()
    assert "<h1>Main Heading</h1>" in body
    assert "<b>bold words</b>" in body
    assert "<table>" in body and "cell-a" in body
    assert '<img src="data:image/png' in body
    assert "<ul>" in body and "<li>item one</li>" in body
    assert "<hr>" in body  # page break maps to hr in HTML output


def test_docx_to_txt(client):
    response = samples.convert(client, "doc.docx", samples.docx(), "txt")
    assert response.status_code == 200
    text = response.data.decode()
    assert "Main Heading" in text
    assert "- item one" in text
    assert "cell-a\tcell-b" in text


def test_docx_to_pdf(client):
    response = samples.convert(client, "doc.docx", samples.docx(), "pdf")
    assert response.status_code == 200
    text = pdf_text_of(response.data)
    assert "Main Heading" in text
    assert "cell-a" in text
    assert len(PdfReader(io.BytesIO(response.data)).pages) >= 2  # page break


def test_damaged_docx_rejected(client):
    response = samples.convert(client, "bad.docx", samples.damaged_docx(), "pdf")
    assert response.status_code == 422


def test_html_to_pdf_no_network_no_scripts(client, monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("network!")

    monkeypatch.setattr(socket, "getaddrinfo", boom)
    monkeypatch.setattr(socket, "create_connection", boom)
    payload = (
        "<script>alert(1)</script><iframe src='http://x'></iframe>"
        "<img src='http://127.0.0.1/x'>"
        "<p style='background:url(http://x);color:red'>styled</p>"
    )
    response = samples.convert(client, "page.html", samples.html(payload), "pdf")
    assert response.status_code == 200, response.data[:300]
    assert response.mimetype == "application/pdf"
    assert "styled" in pdf_text_of(response.data)


def test_html_to_pdf_data_image_ok(client):
    pixel = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    payload = f'<img src="data:image/png;base64,{pixel}">'
    response = samples.convert(client, "img.html", samples.html(payload), "pdf")
    assert response.status_code == 200


def test_html_size_limit(client, monkeypatch):
    monkeypatch.setattr(config, "MAX_HTML_BYTES", 100)
    big = samples.html("<p>" + "x" * 500 + "</p>")
    response = samples.convert(client, "big.html", big, "pdf")
    assert response.status_code == 422
    assert b"3 MB" in response.data or b"limited" in response.data


def test_unicode_text_to_pdf_font_embedded(client):
    response = samples.convert(client, "uni.txt", samples.text("Привет мир — Ωmega €"), "pdf")
    assert response.status_code == 200
    assert "Привет мир" in pdf_text_of(response.data)


def test_html_title_becomes_pdf_metadata(client):
    response = samples.convert(client, "t.html", samples.html(), "pdf")
    assert response.status_code == 200
    assert PdfReader(io.BytesIO(response.data)).metadata.title == "Page"


def test_html_title_not_in_pdf_body(client):
    payload = "<html><head><title>Secret Title</title></head><body><h1>Hi</h1></body></html>"
    response = samples.convert(client, "t.html", io.BytesIO(payload.encode()), "pdf")
    assert response.status_code == 200
    reader = PdfReader(io.BytesIO(response.data))
    assert reader.metadata.title == "Secret Title"
    page_text = reader.pages[0].extract_text() or ""
    assert "Secret Title" not in page_text
    assert "Hi" in page_text


def test_markdown_to_html(client):
    response = samples.convert(client, "doc.md", samples.markdown(), "html")
    assert response.status_code == 200
    body = response.data.decode()
    assert "<table>" in body
    assert "<code>" in body or "<pre>" in body
    assert "<title>Heading One</title>" in body


def test_markdown_script_removed(client):
    response = samples.convert(
        client, "doc.md", samples.markdown("# T\n\n<script>alert(1)</script>\n"), "html"
    )
    assert b"<script>" not in response.data


def test_markdown_to_pdf(client):
    response = samples.convert(client, "doc.md", samples.markdown(), "pdf")
    assert response.status_code == 200
    assert "Heading One" in pdf_text_of(response.data)


def test_text_to_html_escapes_and_titles(client):
    response = samples.convert(
        client, "note.txt", samples.text("<script>x</script>"), "html", title="My <b> T"
    )
    assert response.status_code == 200
    body = response.data.decode()
    assert "&lt;script&gt;" in body
    assert "My &lt;b&gt; T" in body
    assert "<title>My &lt;b&gt; T</title>" in body


def test_text_to_html_default_title_is_stem(client):
    response = samples.convert(client, "notes.txt", samples.text("hi"), "html")
    assert "<title>notes</title>" in response.data.decode()


def test_text_to_pdf(client):
    response = samples.convert(client, "n.txt", samples.text("plain words"), "pdf")
    assert response.status_code == 200
    assert "plain words" in pdf_text_of(response.data)


def test_cp1252_text_decodes(client):
    response = samples.convert(client, "c.txt", samples.text_cp1252(), "html")
    assert response.status_code == 200
    assert "Café" in response.data.decode()


def test_cp1252_undefined_byte_replaced(client):
    # 0x81 is undefined in cp1252 and must not fail the decode.
    data = io.BytesIO(b"caf\xe9 \x81 ok")
    response = samples.convert(client, "c.txt", data, "html")
    assert response.status_code == 200
    assert "café" in response.data.decode()


def test_markdown_remote_image_kept_in_html(client):
    source = samples.markdown("# T\n\n![x](https://example.com/a.png)\n")
    response = samples.convert(client, "doc.md", source, "html")
    assert response.status_code == 200
    assert 'src="https://example.com/a.png"' in response.data.decode()


def test_markdown_remote_image_pdf_no_network(client, monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("network!")

    monkeypatch.setattr(socket, "getaddrinfo", boom)
    monkeypatch.setattr(socket, "create_connection", boom)
    source = samples.markdown("# T\n\n![x](https://example.com/a.png)\n")
    response = samples.convert(client, "doc.md", source, "pdf")
    assert response.status_code == 200


def test_binary_text_rejected(client):
    response = samples.convert(client, "b.txt", samples.binary_as_txt(), "html")
    assert response.status_code == 400
    assert b"text file" in response.data
