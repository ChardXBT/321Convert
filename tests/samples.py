"""Sample file builders for the test suite. Every function returns BytesIO
positioned at 0, holding a complete file."""

import io
import struct
import zlib
from datetime import datetime


def _bytes(data: bytes) -> io.BytesIO:
    return io.BytesIO(data)


def png(size=(20, 10), mode="RGB", color=(200, 30, 40)) -> io.BytesIO:
    from PIL import Image

    buffer = io.BytesIO()
    Image.new(mode, size, color).save(buffer, "PNG")
    buffer.seek(0)
    return buffer


def bmp() -> io.BytesIO:
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), (1, 2, 3)).save(buffer, "BMP")
    buffer.seek(0)
    return buffer


def ico() -> io.BytesIO:
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGBA", (48, 48), (0, 200, 0, 255)).save(buffer, "ICO", sizes=[(16, 16), (32, 32), (48, 48)])
    buffer.seek(0)
    return buffer


def jpeg_cmyk() -> io.BytesIO:
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("CMYK", (16, 16), (0, 128, 255, 0)).save(buffer, "JPEG")
    buffer.seek(0)
    return buffer


def jpeg_with_exif_orientation(orientation=6, size=(40, 20)) -> io.BytesIO:
    from PIL import Image

    image = Image.new("RGB", size, (10, 20, 30))
    exif = Image.Exif()
    exif[0x0112] = orientation
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", exif=exif.tobytes())
    buffer.seek(0)
    return buffer


def gif_animated(frames=3) -> io.BytesIO:
    from PIL import Image

    colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0), (0, 255, 255)]
    images = [Image.new("RGB", (32, 32), colors[i % len(colors)]) for i in range(frames)]
    buffer = io.BytesIO()
    images[0].save(
        buffer,
        "GIF",
        save_all=True,
        append_images=images[1:],
        duration=80,
        loop=0,
    )
    buffer.seek(0)
    return buffer


def webp_animated(frames=3) -> io.BytesIO:
    from PIL import Image

    colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255)]
    images = [Image.new("RGB", (32, 32), colors[i % len(colors)]) for i in range(frames)]
    buffer = io.BytesIO()
    images[0].save(
        buffer,
        "WEBP",
        save_all=True,
        append_images=images[1:],
        duration=80,
        loop=0,
    )
    buffer.seek(0)
    return buffer


def png_palette_transparent() -> io.BytesIO:
    """P-mode PNG with a transparent palette entry; pixel (0,0) transparent."""
    from PIL import Image

    image = Image.new("P", (8, 8))
    palette = [255, 0, 0] + [0] * (768 - 3)
    image.putpalette(palette)
    image.info["transparency"] = 0
    image.putpixel((0, 0), 0)
    for x in range(1, 8):
        for y in range(8):
            image.putpixel((x, y), 0 if x == y else 0)
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    buffer.seek(0)
    return buffer


def png_la() -> io.BytesIO:
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("LA", (10, 10), (200, 128)).save(buffer, "PNG")
    buffer.seek(0)
    return buffer


def png_i16() -> io.BytesIO:
    """I;16 gradient PNG."""
    from PIL import Image

    image = Image.new("I;16", (16, 4))
    image.putdata([x * 4096 for x in range(64)])
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    buffer.seek(0)
    return buffer


def tiff_multipage(pages=2) -> io.BytesIO:
    from PIL import Image

    images = [Image.new("RGB", (16, 16), (i * 60, 0, 0)) for i in range(pages)]
    buffer = io.BytesIO()
    images[0].save(buffer, "TIFF", save_all=True, append_images=images[1:])
    buffer.seek(0)
    return buffer


def heic() -> io.BytesIO:
    from PIL import Image
    from pillow_heif import register_heif_opener

    register_heif_opener()
    buffer = io.BytesIO()
    Image.new("RGB", (16, 16), (10, 200, 10)).save(buffer, "HEIF")
    buffer.seek(0)
    return buffer


def avif() -> io.BytesIO:
    from PIL import Image
    from pillow_heif import register_heif_opener

    register_heif_opener()
    buffer = io.BytesIO()
    Image.new("RGB", (16, 16), (200, 10, 200)).save(buffer, "AVIF")
    buffer.seek(0)
    return buffer


def png_with_icc() -> io.BytesIO:
    from PIL import Image, ImageCms

    profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB"))
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), (5, 5, 200)).save(buffer, "PNG", icc_profile=profile.tobytes())
    buffer.seek(0)
    return buffer


def bomb_png() -> io.BytesIO:
    """A PNG whose IHDR declares 30000x30000 pixels."""

    def chunk(kind: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + kind
            + payload
            + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", 30000, 30000, 8, 2, 0, 0, 0)
    data = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IEND", b"")
    return io.BytesIO(data)


def truncated_jpeg() -> io.BytesIO:
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (64, 64), (30, 30, 30)).save(buffer, "JPEG")
    data = buffer.getvalue()[: len(buffer.getvalue()) // 2]
    return io.BytesIO(data)


def psd_as_png() -> io.BytesIO:
    return io.BytesIO(b"8BPS" + b"\x00" * 100)


def jpeg_named_png() -> io.BytesIO:
    """A real JPEG that will be uploaded with a .png name."""
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), (9, 9, 9)).save(buffer, "JPEG")
    buffer.seek(0)
    return buffer


def _xlsx_with(sheet_rows: dict) -> io.BytesIO:
    from openpyxl import Workbook

    workbook = Workbook()
    first = True
    for name, rows in sheet_rows.items():
        sheet = workbook.active if first else workbook.create_sheet()
        first = False
        sheet.title = name
        for row in rows:
            sheet.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    buffer.seek(0)
    return buffer


def xlsx() -> io.BytesIO:
    return _xlsx_with(
        {
            "Data": [
                ["name", "value", "flag", "when", "stamp", "empty"],
                ["a", 3.0, True, datetime(2024, 1, 5), datetime(2024, 1, 5, 13, 30), None],
                ["b", 2.5, False, None, None, None],
            ]
        }
    )


def xlsx_two_sheets() -> io.BytesIO:
    return _xlsx_with({"First": [["k"], ["one"]], "Second": [["k"], ["two"]]})


def xlsx_formulas() -> io.BytesIO:
    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Data"
    sheet.append(["v"])
    for value in ("=cmd", "-5", "+1 (555)", "@handle"):
        cell = sheet.cell(row=sheet.max_row + 1, column=1)
        cell.value = value
        cell.data_type = "s"  # keep "=cmd" as literal text, not a formula
    buffer = io.BytesIO()
    workbook.save(buffer)
    buffer.seek(0)
    return buffer


def xlsx_empty_sheet() -> io.BytesIO:
    return _xlsx_with({"Blank": [[None, None]]})


def csv_text(delim=",", rows=None) -> io.BytesIO:
    rows = rows or [["a", "b"], ["1", "2.5"], ["x", "=1+1"], ["", "3."]]
    text = "\r\n".join(delim.join(row) for row in rows)
    return io.BytesIO(text.encode("utf-8"))


def text(content="Hello plain text.\nSecond line.") -> io.BytesIO:
    return io.BytesIO(content.encode("utf-8"))


def text_cp1252() -> io.BytesIO:
    return io.BytesIO("Café — naïve".encode("cp1252"))


def binary_as_txt() -> io.BytesIO:
    return io.BytesIO(b"\x00\x01\x02binary")


def html(content=None) -> io.BytesIO:
    body = content or "<h1>Title</h1><p>Hello</p>"
    return io.BytesIO(
        f"<!doctype html><html><head><title>Page</title></head><body>{body}</body></html>".encode()
    )


def markdown(content=None) -> io.BytesIO:
    body = content or "# Heading One\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n```\ncode\n```\n"
    return io.BytesIO(body.encode("utf-8"))


def docx() -> io.BytesIO:
    from docx import Document
    from docx.enum.text import WD_BREAK

    document = Document()
    document.add_heading("Main Heading", level=1)
    paragraph = document.add_paragraph()
    run = paragraph.add_run("bold words")
    run.bold = True
    document.add_paragraph("item one", style="List Bullet")
    document.add_paragraph("item two", style="List Bullet")
    table = document.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "cell-a"
    table.cell(0, 1).text = "cell-b"
    table.cell(1, 0).text = "cell-c"
    table.cell(1, 1).text = "cell-d"
    # Embedded image inside a run.
    paragraph = document.add_paragraph()
    paragraph.add_run().add_picture(png((8, 8)))
    document.add_paragraph("before break").add_run().add_break(WD_BREAK.PAGE)
    document.add_paragraph("after break")
    document.core_properties.title = "Doc Title"
    buffer = io.BytesIO()
    document.save(buffer)
    buffer.seek(0)
    return buffer


def damaged_docx() -> io.BytesIO:
    """Valid zip with the required members, but garbage document.xml."""
    import zipfile

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", "<x/>")
        archive.writestr("word/document.xml", "<not-xml")
    buffer.seek(0)
    return buffer


def pdf_text(pages=None) -> io.BytesIO:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    pages = pages or ["first page text", "second page text"]
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    for index, line in enumerate(pages):
        pdf.drawString(72, 720, line)
        if index < len(pages) - 1:
            pdf.showPage()
    pdf.showPage()
    pdf.save()
    buffer.seek(0)
    return buffer


def pdf_huge_page() -> io.BytesIO:
    """One page declared 14400x14400 pt (200x200 in) — renderer must cap it."""
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=(14400, 14400))
    pdf.drawString(72, 14200, "huge page")
    pdf.showPage()
    pdf.save()
    buffer.seek(0)
    return buffer


def pdf_blank() -> io.BytesIO:
    from pypdf import PdfWriter

    buffer = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.write(buffer)
    buffer.seek(0)
    return buffer


def pdf_with_image() -> io.BytesIO:
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=(200, 200))
    pdf.drawString(20, 180, "image page text")
    pdf.drawImage(ImageReader(png((8, 8))), 20, 20, 8, 8)
    pdf.showPage()
    pdf.save()
    buffer.seek(0)
    return buffer


def pdf_encrypted(user_pw="userpw", owner_pw="ownerpw") -> io.BytesIO:
    from pypdf import PdfReader, PdfWriter

    writer = PdfWriter()
    writer.append(PdfReader(io.BytesIO(pdf_text(["secret"]).getvalue())))
    writer.encrypt(user_password=user_pw, owner_password=owner_pw)
    buffer = io.BytesIO()
    writer.write(buffer)
    buffer.seek(0)
    return buffer


def pdf_owner_only() -> io.BytesIO:
    return pdf_encrypted(user_pw="", owner_pw="ownerpw")


def zip_slip_xlsx() -> io.BytesIO:
    import zipfile

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("../escape", "bad")
    buffer.seek(0)
    return buffer


def zip_not_office() -> io.BytesIO:
    import zipfile

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("readme.txt", "hello")
    buffer.seek(0)
    return buffer


def convert(client, filename, data, target, **options):
    """POST one file to /api/convert."""
    form = {"file": (data, filename), "target": target}
    form.update({key: str(value) for key, value in options.items()})
    return client.post("/api/convert", data=form, content_type="multipart/form-data")
