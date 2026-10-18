"""Raster image conversion via Pillow (+ pillow-heif for HEIC/AVIF)."""

from pathlib import Path

import conversions
from core import config
from core.errors import ConversionError
from core.runner import ConversionResult

INPUT_FORMATS = ["JPEG", "PNG", "WEBP", "GIF", "BMP", "TIFF", "HEIF", "AVIF", "ICO"]

ANIMATED_OUTPUTS = {"gif", "webp", "tiff", "pdf"}
_ALPHA_MODES = {"RGBA", "LA", "PA", "RGBa"}
_NON_RGB_MODES = {"CMYK", "YCbCr", "LAB", "HSV"}
_ICC_SOURCE_MODES = {"RGB", "RGBA", "L", "LA"}
_ICC_OUTPUTS = {"jpg", "png", "webp", "avif", "tiff"}

_UNREADABLE = "The image could not be read. It may be damaged or not a supported image."


def _has_alpha(image) -> bool:
    return image.mode in _ALPHA_MODES or (image.mode == "P" and "transparency" in image.info)


def _to_8bit_l(image):
    """Scale an I;16 / I / F image to 8-bit L."""
    from PIL import ImageOps

    try:
        if image.mode.startswith("I;16"):
            return image.convert("I").point(lambda v: v * (255 / 65535)).convert("L")
        return image.point(lambda v: v * (255 / 65535)).convert("L")
    except Exception:
        return ImageOps.autocontrast(image.convert("I")).convert("L")


def _flatten_white(image):
    """Composite an image that may have alpha over a white RGB background."""
    Image = conversions._pillow()
    if image.mode != "RGBA":
        image = image.convert("RGBA")
    background = Image.new("RGB", image.size, "white")
    background.paste(image, mask=image.getchannel("A"))
    return background


def _normalise(frame, output_ext, notes):
    """Return the frame in a mode the target writer accepts."""
    mode = frame.mode
    has_alpha = _has_alpha(frame)

    if output_ext == "jpg":
        if has_alpha:
            frame = _flatten_white(frame)
            if "Transparent areas were flattened to white." not in notes:
                notes.append("Transparent areas were flattened to white.")
        elif mode in _NON_RGB_MODES or mode == "P":
            frame = frame.convert("RGB")
        elif mode.startswith("I;16") or mode in {"I", "F"}:
            frame = _to_8bit_l(frame)
        elif mode not in {"1", "L", "RGB"}:
            frame = frame.convert("RGB")
    elif output_ext == "png":
        if mode in _NON_RGB_MODES:
            frame = frame.convert("RGB")
        elif mode in {"I", "F"}:
            frame = _to_8bit_l(frame)
        # I;16 is kept: PNG supports it natively.
    elif output_ext in {"webp", "avif"}:
        wanted = "RGBA" if has_alpha else "RGB"
        if mode != wanted:
            frame = frame.convert(wanted)
    elif output_ext == "gif":
        if mode in _NON_RGB_MODES or mode.startswith("I;16") or mode in {"I", "F"}:
            frame = frame.convert("RGB")
        # The GIF writer quantises RGB/RGBA/LA/P itself.
    elif output_ext == "bmp":
        if has_alpha:
            frame = frame.convert("RGBA")
        elif mode in _NON_RGB_MODES or mode == "P":
            frame = frame.convert("RGB")
        elif mode.startswith("I;16") or mode in {"I", "F"}:
            frame = _to_8bit_l(frame)
        elif mode == "LA":
            frame = frame.convert("RGBA")
        elif mode not in {"1", "L", "RGB", "RGBA"}:
            frame = frame.convert("RGB")
    elif output_ext == "tiff":
        if mode in {"YCbCr", "LAB", "HSV"}:
            frame = frame.convert("RGB")
        # TIFF accepts CMYK, I;16, RGBA, P and LA as they are.
    elif output_ext == "ico":
        frame = frame.convert("RGBA")
    elif output_ext == "pdf":
        if has_alpha:
            frame = _flatten_white(frame)
        elif mode != "RGB":
            frame = frame.convert("RGB")
    return frame


def _save_pdf(frames, output_path, stem):
    """Draw one image per A4 page, centred inside 36pt margins."""
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    pdf = canvas.Canvas(str(output_path))
    if stem:
        pdf.setTitle(stem)
    margin = 36
    for frame in frames:
        page_w, page_h = A4 if frame.height >= frame.width else landscape(A4)
        avail_w, avail_h = page_w - 2 * margin, page_h - 2 * margin
        scale = min(avail_w / frame.width, avail_h / frame.height, 1.0)
        draw_w, draw_h = frame.width * scale, frame.height * scale
        pdf.drawImage(
            ImageReader(frame.convert("RGB")),
            (page_w - draw_w) / 2,
            (page_h - draw_h) / 2,
            draw_w,
            draw_h,
        )
        pdf.showPage()
    pdf.save()


def _save_ico(frame, output_path, notes):
    Image = conversions._pillow()
    longest = max(frame.size)
    if longest > 256:
        frame.thumbnail((256, 256), Image.Resampling.LANCZOS)
        notes.append("ICO output is limited to 256×256 pixels.")
        longest = max(frame.size)
    # Pillow drops entries larger than the image's smaller side, and an
    # all-dropped sizes list produces an empty 6-byte ICO.
    shortest = min(frame.size)
    sizes = [(s, s) for s in (16, 32, 48, 64, 128, 256) if s <= shortest]
    if not sizes:
        sizes = [frame.size]
    frame.save(output_path, "ICO", sizes=sizes)


def convert(input_path: Path, output_path: Path, options: dict) -> ConversionResult:
    Image = conversions._pillow()
    from PIL import ImageOps, ImageSequence, UnidentifiedImageError

    ext = output_path.suffix.lower().lstrip(".")
    quality = options.get("quality", 82)
    max_dimension = options.get("max_dimension")
    stem = options.get("_stem", "")
    notes = []

    try:
        with Image.open(input_path, formats=INPUT_FORMATS) as probe:
            probe.verify()
        image = Image.open(input_path, formats=INPUT_FORMATS)
    except (UnidentifiedImageError, OSError) as exc:
        raise ConversionError(_UNREADABLE) from exc

    try:
        n_frames = getattr(image, "n_frames", 1) or 1
        animated_source = n_frames > 1
        preserve = animated_source and ext in ANIMATED_OUTPUTS
        if animated_source:
            too_large = (
                n_frames > config.MAX_FRAMES
                or n_frames * image.width * image.height > config.MAX_ANIMATION_PIXELS
            )
            if too_large:
                preserve = False
                notes.append("Only the first frame was kept because the animation is too large.")
            elif not preserve:
                notes.append("Only the first frame of the animation was converted.")

        frames = []
        durations = []
        limit = n_frames if preserve else 1
        for index, raw in enumerate(ImageSequence.Iterator(image)):
            if index >= limit:
                break
            durations.append(raw.info.get("duration", 100))
            frame = ImageOps.exif_transpose(raw.copy())
            if max_dimension and max(frame.size) > max_dimension:
                frame.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)
                if index == 0:
                    notes.append(f"Resized to {frame.width}x{frame.height}.")
            frames.append(_normalise(frame, ext, notes))

        first = frames[0]
        save_kwargs = {}
        if ext in _ICC_OUTPUTS and image.mode in _ICC_SOURCE_MODES and image.info.get("icc_profile"):
            save_kwargs["icc_profile"] = image.info["icc_profile"]
        # EXIF is never copied: it can carry location and device data.

        if ext == "pdf":
            _save_pdf(frames, output_path, stem)
        elif ext == "ico":
            _save_ico(first, output_path, notes)
        elif preserve and len(frames) > 1:
            rest = frames[1:]
            if ext == "gif":
                save_kwargs.update(
                    save_all=True,
                    append_images=rest,
                    duration=durations,
                    loop=0,
                    disposal=2,
                    optimize=True,
                )
            elif ext == "webp":
                save_kwargs.update(
                    save_all=True,
                    append_images=rest,
                    duration=durations,
                    loop=0,
                    quality=quality,
                    method=4,
                )
            else:  # tiff
                save_kwargs.update(save_all=True, append_images=rest, compression="tiff_lzw")
            first.save(output_path, _pillow_format(ext), **save_kwargs)
        else:
            if ext == "jpg":
                save_kwargs.update(quality=quality, optimize=True)
            elif ext == "webp":
                save_kwargs.update(quality=quality, method=4)
            elif ext == "avif":
                save_kwargs["quality"] = quality
            elif ext == "png":
                save_kwargs.update(optimize=False, compress_level=6)
            elif ext == "gif":
                save_kwargs["optimize"] = True
            elif ext == "tiff":
                save_kwargs["compression"] = "tiff_lzw"
            first.save(output_path, _pillow_format(ext), **save_kwargs)
    finally:
        image.close()

    return ConversionResult(str(output_path), ext, notes)


def _pillow_format(ext: str) -> str:
    return {
        "jpg": "JPEG",
        "png": "PNG",
        "webp": "WEBP",
        "gif": "GIF",
        "bmp": "BMP",
        "tiff": "TIFF",
        "avif": "AVIF",
    }[ext]
