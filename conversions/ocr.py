"""OCR via RapidOCR (ONNX Runtime). Imported lazily everywhere: the engine
pulls in onnxruntime and OpenCV, which are far too heavy to load for requests
that never need text recognition."""

import threading
from pathlib import Path

import conversions
from core import config
from core.errors import ConversionError
from core.runner import ConversionResult

MAX_OCR_SIDE = 1800

_engine = None
_engine_lock = threading.Lock()


def _get_engine():
    global _engine
    if _engine is None:
        with _engine_lock:
            if _engine is None:
                try:
                    from rapidocr import RapidOCR
                except Exception as exc:
                    raise ConversionError("Text recognition is unavailable right now.") from exc
                threads = config.OCR_THREADS
                params = {}
                for section in ("Det", "Cls", "Rec"):
                    params[f"{section}.intra_op_num_threads"] = threads
                    params[f"{section}.inter_op_num_threads"] = threads
                try:
                    _engine = RapidOCR(params=params)
                except Exception as exc:
                    raise ConversionError("Text recognition is unavailable right now.") from exc
    return _engine


def _model_error(exc: Exception) -> bool:
    """True only for onnxruntime model/session load failures."""
    try:
        from onnxruntime.capi import onnxruntime_pybind11_state as ort
    except Exception:
        return False
    names = ("Fail", "InvalidArgument", "InvalidGraph", "InvalidProtobuf", "NoSuchFile")
    return isinstance(exc, tuple(getattr(ort, name) for name in names if hasattr(ort, name)))


def recognize(image) -> str:
    """OCR one PIL image; returns recognised lines joined with newlines."""
    import numpy as np

    if max(image.size) > MAX_OCR_SIDE:
        scaled = image.copy()
        scaled.thumbnail((MAX_OCR_SIDE, MAX_OCR_SIDE))
        image = scaled
    engine = _get_engine()
    try:
        result = engine(np.asarray(image.convert("RGB")))
    except Exception as exc:
        # Model/session failures get the friendly message; anything else
        # propagates so the API maps it to the generic 422.
        if _model_error(exc):
            raise ConversionError("Text recognition is unavailable right now.") from exc
        raise
    txts = getattr(result, "txts", None)
    scores = getattr(result, "scores", None) or []
    if not txts:
        return ""
    lines = []
    for index, text in enumerate(txts):
        if index < len(scores) and scores[index] < 0.5:
            continue
        lines.append(text)
    return "\n".join(lines)


def image_to_text(input_path: Path, output_path: Path, options: dict) -> ConversionResult:
    """image -> txt converter entry point."""
    from PIL import ImageOps, UnidentifiedImageError

    from conversions.images import INPUT_FORMATS

    Image = conversions._pillow()
    try:
        with Image.open(input_path, formats=INPUT_FORMATS):
            pass
        image = Image.open(input_path, formats=INPUT_FORMATS)
    except (UnidentifiedImageError, OSError) as exc:
        raise ConversionError(
            "The image could not be read. It may be damaged or not a supported image."
        ) from exc
    with image:
        frame = ImageOps.exif_transpose(image.convert("RGB"))
    text = recognize(frame)
    notes = ["Text was recognised with OCR; check it for errors."]
    if not text.strip():
        notes.append("No text could be recognised in the image.")
    output_path.write_text(text.strip() + ("\n" if text.strip() else ""), encoding="utf-8")
    return ConversionResult(str(output_path), "txt", notes)
