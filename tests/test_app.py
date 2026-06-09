import io
import unittest

from openpyxl import Workbook
from PIL import Image

from app import app, rate_limit_hits


def png_file():
    data = io.BytesIO()
    Image.new("RGB", (4, 4), "orange").save(data, "PNG")
    data.seek(0)
    return data


def xlsx_file():
    data = io.BytesIO()
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["name", "value"])
    sheet.append(["private", 321])
    workbook.save(data)
    data.seek(0)
    return data


class ConverterAppTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True)
        rate_limit_hits.clear()
        self.client = app.test_client()

    def test_home_has_security_headers(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("object-src 'none'", response.headers["Content-Security-Policy"])
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(response.headers["Cache-Control"], "no-store")

    def test_image_conversion_returns_private_attachment(self):
        response = self.client.post(
            "/convert",
            data={"image": (png_file(), "sample.png"), "output_format": "jpg", "quality": "80"},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "image/jpeg")
        self.assertIn("attachment", response.headers["Content-Disposition"])

    def test_rejects_extension_not_allowed_for_conversion(self):
        response = self.client.post(
            "/document/convert",
            data={"file": (io.BytesIO(b"not a pdf"), "attack.exe"), "conversion_type": "pdf_to_docx"},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 422)
        self.assertNotIn(b"Traceback", response.data)

    def test_text_to_html_escapes_active_content(self):
        response = self.client.post(
            "/document/convert",
            data={
                "file": (io.BytesIO(b"<script>alert(1)</script>"), "note.txt"),
                "conversion_type": "text_to_html",
                "title": "<img src=x onerror=alert(1)>",
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(b"<script>", response.data)
        self.assertNotIn(b"<img src=x", response.data)
        self.assertIn(b"&lt;script&gt;", response.data)

    def test_spreadsheet_to_csv(self):
        response = self.client.post(
            "/document/convert",
            data={"file": (xlsx_file(), "data.xlsx"), "conversion_type": "create_csv_from_excel"},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "text/csv")
        self.assertIn(b"private,321", response.data)

    def test_html_to_pdf_does_not_fetch_or_execute_html(self):
        response = self.client.post(
            "/document/convert",
            data={
                "file": (io.BytesIO(b'<img src="http://127.0.0.1/private"><script>alert(1)</script>'), "page.html"),
                "conversion_type": "html_to_pdf",
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "application/pdf")

    def test_unknown_conversion_is_rejected(self):
        response = self.client.post(
            "/document/convert",
            data={"file": (io.BytesIO(b"x"), "note.txt"), "conversion_type": "does_not_exist"},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
