import io
import json

import pytest
from PIL import Image
from pypdf import PdfReader

from core import config
from tests import samples


def samples_jpeg():
    from PIL import Image as I

    buffer = io.BytesIO()
    I.new("RGB", (16, 16), (10, 200, 60)).save(buffer, "JPEG")
    buffer.seek(0)
    return buffer


INPUTS = {
    "png": ("in.png", samples.png),
    "jpeg": ("in.jpg", samples_jpeg),
    "cmyk_jpg": ("in.jpg", samples.jpeg_cmyk),
    "gif_anim": ("in.gif", samples.gif_animated),
    "webp_anim": ("in.webp", samples.webp_animated),
    "p_transparent": ("in.png", samples.png_palette_transparent),
    "la_png": ("in.png", samples.png_la),
    "i16_png": ("in.png", samples.png_i16),
    "tiff_multi": ("in.tiff", samples.tiff_multipage),
    "heic": ("in.heic", samples.heic),
    "avif": ("in.avif", samples.avif),
    "bmp": ("in.bmp", samples.bmp),
    "ico": ("in.ico", samples.ico),
}

OUTPUTS = ["jpg", "png", "webp", "gif", "bmp", "tiff", "avif", "heic", "ico", "pdf"]

EXPECTED_FORMAT = {
    "jpg": "JPEG",
    "png": "PNG",
    "webp": "WEBP",
    "gif": "GIF",
    "bmp": "BMP",
    "tiff": "TIFF",
    "avif": "AVIF",
    "heic": "HEIF",
    "ico": "ICO",
}


def notes_of(response):
    return json.loads(response.headers.get("X-Conversion-Notes", "[]"))


@pytest.mark.parametrize("output", OUTPUTS)
@pytest.mark.parametrize("kind", sorted(INPUTS))
def test_image_matrix(client, kind, output):
    filename, builder = INPUTS[kind]
    response = samples.convert(client, filename, builder(), output)
    assert response.status_code == 200, (kind, output, response.data[:200])
    if output == "pdf":
        assert response.mimetype == "application/pdf"
        assert len(PdfReader(io.BytesIO(response.data)).pages) >= 1
    else:
        image = Image.open(io.BytesIO(response.data))
        image.load()
        assert image.format == EXPECTED_FORMAT[output]


def test_cmyk_to_png_bmp_gif_ico(client):
    for output in ("png", "bmp", "gif", "ico"):
        response = samples.convert(client, "c.jpg", samples.jpeg_cmyk(), output)
        assert response.status_code == 200, output
        Image.open(io.BytesIO(response.data)).load()


def test_palette_transparent_to_jpg_flattens_white(client):
    response = samples.convert(client, "t.png", samples.png_palette_transparent(), "jpg")
    assert response.status_code == 200
    image = Image.open(io.BytesIO(response.data)).convert("RGB")
    assert image.getpixel((0, 0)) == (255, 255, 255)
    assert "flattened to white" in " ".join(notes_of(response))


def test_la_to_jpg_and_bmp(client):
    for output in ("jpg", "bmp"):
        response = samples.convert(client, "la.png", samples.png_la(), output)
        assert response.status_code == 200, output


def test_i16_to_jpg_and_bmp_keeps_gradient(client):
    for output in ("jpg", "bmp"):
        response = samples.convert(client, "g.png", samples.png_i16(), output)
        assert response.status_code == 200, output
        image = Image.open(io.BytesIO(response.data)).convert("L")
        values = {image.getpixel((x, 0)) for x in range(image.width)}
        assert len(values) > 1, output


def test_exif_orientation_rotates_and_strips_exif(client):
    response = samples.convert(client, "rot.jpg", samples.jpeg_with_exif_orientation(6), "png")
    assert response.status_code == 200
    image = Image.open(io.BytesIO(response.data))
    assert image.size == (20, 40)

    response = samples.convert(client, "rot.jpg", samples.jpeg_with_exif_orientation(6), "jpg")
    image = Image.open(io.BytesIO(response.data))
    assert not image.info.get("exif")


def test_icc_preserved_png_to_webp_not_cmyk(client):
    response = samples.convert(client, "icc.png", samples.png_with_icc(), "webp")
    assert response.status_code == 200
    assert Image.open(io.BytesIO(response.data)).info.get("icc_profile")

    response = samples.convert(client, "c.jpg", samples.jpeg_cmyk(), "jpg")
    image = Image.open(io.BytesIO(response.data))
    assert not image.info.get("icc_profile")


def test_animated_gif_frames_preserved(client):
    for output in ("gif", "webp", "tiff"):
        response = samples.convert(client, "a.gif", samples.gif_animated(3), output)
        assert response.status_code == 200, output
        image = Image.open(io.BytesIO(response.data))
        assert getattr(image, "n_frames", 1) == 3


def test_animated_gif_to_pdf_pages(client):
    response = samples.convert(client, "a.gif", samples.gif_animated(3), "pdf")
    assert response.status_code == 200
    assert len(PdfReader(io.BytesIO(response.data)).pages) == 3


def test_animated_to_png_first_frame_note(client):
    response = samples.convert(client, "a.gif", samples.gif_animated(3), "png")
    assert response.status_code == 200
    assert getattr(Image.open(io.BytesIO(response.data)), "n_frames", 1) == 1
    assert any("first frame" in note for note in notes_of(response))


def test_animation_too_large_keeps_first_frame(client, monkeypatch):
    monkeypatch.setattr(config, "MAX_FRAMES", 2)
    response = samples.convert(client, "a.gif", samples.gif_animated(3), "gif")
    assert response.status_code == 200
    assert getattr(Image.open(io.BytesIO(response.data)), "n_frames", 1) == 1
    assert any("too large" in note for note in notes_of(response))


def test_max_dimension_resize(client):
    response = samples.convert(client, "x.png", samples.png((40, 20)), "jpg", max_dimension=16)
    image = Image.open(io.BytesIO(response.data))
    assert image.size == (16, 8)
    assert any("Resized to 16x8" in note for note in notes_of(response))


def test_max_dimension_larger_than_image_no_resize(client):
    response = samples.convert(client, "x.png", samples.png((20, 10)), "png", max_dimension=500)
    assert Image.open(io.BytesIO(response.data)).size == (20, 10)
    assert notes_of(response) == []


def test_max_dimension_below_minimum_rejected(client):
    response = samples.convert(client, "x.png", samples.png(), "png", max_dimension=5)
    assert response.status_code == 400


def test_heic_output_rgb_and_rgba(client):
    response = samples.convert(client, "a.png", samples.png(size=(32, 24)), "heic")
    assert response.status_code == 200
    assert response.mimetype == "image/heif"
    image = Image.open(io.BytesIO(response.data))
    image.load()
    assert image.format == "HEIF"
    assert image.size == (32, 24)
    assert image.mode == "RGB"

    rgba = io.BytesIO()
    Image.new("RGBA", (16, 16), (0, 100, 200, 128)).save(rgba, "PNG")
    rgba.seek(0)
    response = samples.convert(client, "a.png", rgba, "heic")
    assert response.status_code == 200
    image = Image.open(io.BytesIO(response.data))
    image.load()
    assert image.mode == "RGBA"


def test_heic_quality_changes_size(client):
    noisy = io.BytesIO()
    image = Image.new("RGB", (64, 64))
    image.putdata(
        [
            ((x * 37 + y * 11) % 256, (x * 13 + y * 53) % 256, (x * y) % 256)
            for y in range(64)
            for x in range(64)
        ]
    )
    image.save(noisy, "PNG")
    noisy.seek(0)
    small = samples.convert(client, "q.png", io.BytesIO(noisy.getvalue()), "heic", quality=20)
    big = samples.convert(client, "q.png", noisy, "heic", quality=95)
    assert small.status_code == 200 and big.status_code == 200
    assert len(small.data) != len(big.data)


def test_heic_to_heic_uses_converted_name(client):
    response = samples.convert(client, "photo.heic", samples.heic(), "heic")
    assert response.status_code == 200
    assert "photo-converted" in (response.headers.get("Content-Disposition") or "")


def test_ico_downscale_and_sizes(client):
    response = samples.convert(client, "big.png", samples.png((512, 512)), "ico")
    assert response.status_code == 200
    image = Image.open(io.BytesIO(response.data))
    assert max(image.size) <= 256
    assert any("256" in note for note in notes_of(response))


def test_bomb_png_rejected(client):
    response = samples.convert(client, "bomb.png", samples.bomb_png(), "png")
    assert response.status_code == 422
    assert b"Traceback" not in response.data


def test_jpeg_named_png_still_converts(client):
    response = samples.convert(client, "lie.png", samples.jpeg_named_png(), "png")
    assert response.status_code == 200
    assert Image.open(io.BytesIO(response.data)).format == "PNG"


def test_psd_rejected(client):
    response = samples.convert(client, "fake.png", samples.psd_as_png(), "jpg")
    assert response.status_code == 422
    assert b"could not be read" in response.data or b"could not be converted" in response.data


def test_truncated_jpeg_rejected(client):
    response = samples.convert(client, "cut.jpg", samples.truncated_jpeg(), "png")
    assert response.status_code == 422


def test_quality_validation(client):
    for quality in ("0", "101", "abc"):
        response = samples.convert(client, "x.png", samples.png(), "jpg", quality=quality)
        assert response.status_code == 400, quality


def test_zip_never_from_images(client):
    # Multi-page PDF->images returns zip; image inputs never do.
    response = samples.convert(client, "m.tiff", samples.tiff_multipage(2), "png")
    assert response.status_code == 200
    assert response.mimetype == "image/png"
