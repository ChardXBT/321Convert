import io
import tempfile
import unittest
import zipfile
from pathlib import Path

from openpyxl import Workbook
from PIL import Image
from pypdf import PdfWriter

import app as app_module


app = app_module.app


def png_file():
    data = io.BytesIO()
    Image.new("RGB", (4, 4), "orange").save(data, "PNG")
    data.seek(0)
    return data


def xlsx_file(value=321):
    data = io.BytesIO()
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["name", "value"])
    sheet.append(["private", value])
    workbook.save(data)
    data.seek(0)
    return data


def pdf_file():
    data = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.write(data)
    data.seek(0)
    return data


def unsafe_xlsx():
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as archive:
        archive.writestr("../escape", "bad")
    data.seek(0)
    return data


class ConverterAppTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True, MAX_CONTENT_LENGTH=app_module.MAX_UPLOAD_BYTES)
        app_module.RATE_LIMIT_REQUESTS = 20
        app_module.rate_limit_hits.clear()
        self.client = app.test_client()

    def tearDown(self):
        app_module.RATE_LIMIT_REQUESTS = 20
        app.config["MAX_CONTENT_LENGTH"] = app_module.MAX_UPLOAD_BYTES
        app_module.rate_limit_hits.clear()

    def test_home_has_security_headers(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("object-src 'none'", response.headers["Content-Security-Policy"])
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertIn(b"Terms", response.data)
        self.assertIn(b"MIT License", response.data)
        self.assertIn(b"https://github.com/ChardXBT/321Convert", response.data)

    def test_https_has_hsts_and_static_files_are_cacheable(self):
        secure = self.client.get("/", base_url="https://example.test")
        static = self.client.get("/static/app.js")
        self.assertIn("max-age=31536000", secure.headers["Strict-Transport-Security"])
        self.assertEqual(static.headers["Cache-Control"], "public, max-age=86400")
        static.close()

    def test_image_conversion_returns_private_attachment(self):
        before = set(Path(tempfile.gettempdir()).glob("321convert-*"))
        response = self.client.post(
            "/convert",
            data={"image": (png_file(), "sample.png"), "output_format": "jpg", "quality": "80"},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "image/jpeg")
        self.assertIn("attachment", response.headers["Content-Disposition"])
        self.assertEqual(set(Path(tempfile.gettempdir()).glob("321convert-*")), before)

    def test_all_advertised_image_outputs_work(self):
        mime_types = {
            "jpg": "image/jpeg", "png": "image/png", "webp": "image/webp",
            "gif": "image/gif", "bmp": "image/bmp", "tiff": "image/tiff",
        }
        for output, mime_type in mime_types.items():
            with self.subTest(output=output):
                response = self.client.post(
                    "/convert",
                    data={"image": (png_file(), "sample.png"), "output_format": output, "quality": "80"},
                    content_type="multipart/form-data",
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.mimetype, mime_type)

    def test_malformed_image_does_not_leak_parser_error(self):
        response = self.client.post(
            "/convert",
            data={"image": (io.BytesIO(b"secret-parser-detail"), "fake.png"), "output_format": "jpg"},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 422)
        self.assertNotIn(b"secret-parser-detail", response.data)
        self.assertIn(b"could not be converted", response.data)

    def test_image_quality_boundaries_are_enforced(self):
        for quality in ("0", "101", "not-a-number"):
            with self.subTest(quality=quality):
                response = self.client.post(
                    "/convert",
                    data={"image": (png_file(), "sample.png"), "output_format": "jpg", "quality": quality},
                    content_type="multipart/form-data",
                )
                self.assertEqual(response.status_code, 400)

    def test_rejects_extension_not_allowed_for_conversion(self):
        response = self.client.post(
            "/document/convert",
            data={"file": (io.BytesIO(b"not a pdf"), "attack.exe"), "conversion_type": "pdf_to_docx"},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 422)
        self.assertNotIn(b"Traceback", response.data)

    def test_rejects_empty_and_missing_uploads(self):
        empty = self.client.post(
            "/convert",
            data={"image": (io.BytesIO(b""), "empty.png"), "output_format": "jpg"},
            content_type="multipart/form-data",
        )
        missing = self.client.post("/convert", data={"output_format": "jpg"})
        self.assertEqual(empty.status_code, 400)
        self.assertEqual(missing.status_code, 400)

    def test_filename_is_sanitized(self):
        response = self.client.post(
            "/convert",
            data={"image": (png_file(), "../../private image.png"), "output_format": "jpg"},
            content_type="multipart/form-data",
        )
        disposition = response.headers["Content-Disposition"]
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("..", disposition)
        self.assertNotIn("/", disposition)

    def test_extremely_long_filename_is_safely_truncated(self):
        response = self.client.post(
            "/convert",
            data={"image": (png_file(), f"{'a' * 500}.png"), "output_format": "jpg"},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 200)
        self.assertLess(len(response.headers["Content-Disposition"]), 200)

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

    def test_spreadsheet_formula_payload_is_neutralized_in_csv(self):
        response = self.client.post(
            "/document/convert",
            data={"file": (xlsx_file("@SUM(1+1)"), "data.xlsx"), "conversion_type": "create_csv_from_excel"},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"'@SUM(1+1)", response.data)

    def test_spreadsheet_to_pdf(self):
        response = self.client.post(
            "/document/convert",
            data={"file": (xlsx_file(), "data.xlsx"), "conversion_type": "excel_to_pdf"},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "application/pdf")

    def test_pdf_to_docx(self):
        response = self.client.post(
            "/document/convert",
            data={"file": (pdf_file(), "blank.pdf"), "conversion_type": "pdf_to_docx"},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.mimetype,
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )

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

    def test_malformed_and_unsafe_office_archives_are_rejected(self):
        malformed = self.client.post(
            "/document/convert",
            data={"file": (io.BytesIO(b"not-a-zip"), "bad.xlsx"), "conversion_type": "create_csv_from_excel"},
            content_type="multipart/form-data",
        )
        unsafe = self.client.post(
            "/document/convert",
            data={"file": (unsafe_xlsx(), "unsafe.xlsx"), "conversion_type": "create_csv_from_excel"},
            content_type="multipart/form-data",
        )
        self.assertEqual(malformed.status_code, 422)
        self.assertEqual(unsafe.status_code, 422)
        self.assertIn(b"unsafe archive paths", unsafe.data)

    def test_damaged_pdf_does_not_leak_parser_details(self):
        with self.assertNoLogs("pypdf", level="WARNING"), self.assertLogs("app", level="WARNING") as logs:
            response = self.client.post(
                "/document/convert",
                data={"file": (io.BytesIO(b"%PDF-private parser detail"), "damaged.pdf"), "conversion_type": "pdf_to_docx"},
                content_type="multipart/form-data",
            )
        self.assertEqual(response.status_code, 422)
        self.assertNotIn(b"private parser detail", response.data)
        self.assertIn(b"could not be converted", response.data)
        self.assertNotIn("damaged.pdf", " ".join(logs.output))
        self.assertNotIn("private parser detail", " ".join(logs.output))

    def test_cross_origin_post_is_rejected(self):
        response = self.client.post(
            "/convert",
            headers={"Origin": "https://attacker.example"},
            data={"image": (png_file(), "sample.png"), "output_format": "jpg"},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 403)

    def test_same_origin_post_is_allowed(self):
        response = self.client.post(
            "/convert",
            headers={"Origin": "http://localhost"},
            data={"image": (png_file(), "sample.png"), "output_format": "jpg"},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 200)

    def test_rate_limit_is_enforced(self):
        app_module.RATE_LIMIT_REQUESTS = 1
        first = self.client.post("/convert", data={"output_format": "jpg"})
        second = self.client.post("/convert", data={"output_format": "jpg"})
        self.assertEqual(first.status_code, 400)
        self.assertEqual(second.status_code, 429)

    def test_rate_limit_state_is_not_cleared_when_client_map_is_full(self):
        for number in range(10_000):
            app_module.rate_limit_hits[f"client-{number}"].append(float("inf"))
        with app.test_request_context("/", environ_base={"REMOTE_ADDR": "new-client"}):
            self.assertTrue(app_module.limited())
        self.assertEqual(len(app_module.rate_limit_hits), 10_000)

    def test_oversized_request_is_rejected(self):
        app.config["MAX_CONTENT_LENGTH"] = 32
        response = self.client.post(
            "/convert",
            data={"image": (io.BytesIO(b"x" * 100), "large.png"), "output_format": "jpg"},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 413)

    def test_old_public_file_routes_do_not_exist(self):
        self.assertEqual(self.client.get("/downloads/secret.txt").status_code, 404)
        self.assertEqual(self.client.get("/previews/secret.txt").status_code, 404)

    def test_unknown_conversion_is_rejected(self):
        response = self.client.post(
            "/document/convert",
            data={"file": (io.BytesIO(b"x"), "note.txt"), "conversion_type": "does_not_exist"},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
