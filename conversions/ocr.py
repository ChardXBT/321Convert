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
                    from rapidocr.utils.typings import ModelType, OCRVersion

                    from conversions.ocr_models import model_paths
                except Exception as exc:
                    raise ConversionError("Text recognition is unavailable right now.") from exc
                threads = config.OCR_THREADS
                try:
                    params = {
                        **model_paths(),
                        "EngineConfig.onnxruntime.intra_op_num_threads": threads,
                        "EngineConfig.onnxruntime.inter_op_num_threads": threads,
                        "EngineConfig.onnxruntime.enable_cpu_mem_arena": False,
                        "Det.limit_type": "max",
                        "Det.limit_side_len": 736,
                        "Det.model_type": ModelType.SMALL,
                        "Det.ocr_version": OCRVersion.PPOCRV6,
                        "Rec.model_type": ModelType.SMALL,
                        "Rec.ocr_version": OCRVersion.PPOCRV6,
                        "Rec.rec_batch_num": 1,
                        "Cls.cls_batch_num": 1,
                        "Global.log_level": "critical",
                    }
                    import cv2

                    cv2.setNumThreads(threads)
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


def _memory_error(exc: Exception) -> bool:
    """Recognize Python allocation errors and RapidOCR's wrapped native errors."""
    cause = exc.__cause__ or exc
    if isinstance(exc, MemoryError) or isinstance(cause, MemoryError):
        return True
    try:
        from onnxruntime.capi import onnxruntime_pybind11_state as ort
    except Exception:
        return False
    native_types = tuple(getattr(ort, name) for name in ("Fail", "RuntimeException") if hasattr(ort, name))
    return isinstance(cause, native_types) and any(
        marker in str(cause) for marker in ("std::bad_alloc", "Failed to allocate memory")
    )


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
        if _memory_error(exc):
            raise ConversionError("The conversion needs too much memory. Try a smaller file.") from exc
        if _model_error(exc.__cause__ or exc):
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
        image = Image.open(input_path, formats=INPUT_FORMATS)
    except (UnidentifiedImageError, OSError) as exc:
        raise ConversionError(
            "The image could not be read. It may be damaged or not a supported image."
        ) from exc
    # Shrink while decoding (JPEG draft is a cheap integer downsample) so the
    # RGB copy fed to the engine is already near the recognition size.
    frame = None
    try:
        image.draft("RGB", (MAX_OCR_SIDE, MAX_OCR_SIDE))
        if max(image.size) > MAX_OCR_SIDE:
            image.thumbnail((MAX_OCR_SIDE, MAX_OCR_SIDE))
        transposed = ImageOps.exif_transpose(image)
        try:
            frame = transposed.convert("RGB")
        finally:
            transposed.close()
    finally:
        image.close()
    try:
        text = recognize(frame)
    finally:
        if frame is not None:
            frame.close()
    notes = ["Text was recognised with OCR; check it for errors."]
    if not text.strip():
        notes.append("No text could be recognised in the image.")
    output_path.write_text(text.strip() + ("\n" if text.strip() else ""), encoding="utf-8")
    return ConversionResult(str(output_path), "txt", notes)
