"""Pinned OCR assets, fetched and verified at build time, never during uploads."""

import hashlib
import logging
from importlib.util import find_spec
from pathlib import Path

# RapidOCR 3.10.0's model manifest. Keep filenames and checksums explicit so a
# dependency update cannot silently change the deployed models or memory use.
MODELS = {
    "Det": (
        "PP-OCRv6/det/PP-OCRv6_det_small.onnx",
        "090f04abcd9d9a7498bc4ebf677e4cb9bdce1fe4197ddb7e529f1ef44e1ff94f",
    ),
    "Cls": (
        "PP-OCRv4/cls/ch_ppocr_mobile_v2.0_cls_mobile.onnx",
        "e47acedf663230f8863ff1ab0e64dd2d82b838fceb5957146dab185a89d6215c",
    ),
    "Rec": (
        "PP-OCRv6/rec/PP-OCRv6_rec_small.onnx",
        "6f327246b50388f3c176ae304bd95767ea6dc0c9ae92153ef8cbe210b3c14884",
    ),
}
BASE_URL = "https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.10.0/onnx/"


def model_directory() -> Path:
    spec = find_spec("rapidocr")
    if spec is None or spec.origin is None:
        raise RuntimeError("RapidOCR is not installed.")
    return Path(spec.origin).parent / "models"


def model_paths() -> dict[str, str]:
    directory = model_directory()
    paths = {}
    for section, (relative, _) in MODELS.items():
        path = directory / Path(relative).name
        if not path.is_file():
            raise RuntimeError("OCR models are missing; run python -m conversions.ocr_models.")
        paths[f"{section}.model_path"] = str(path)
    return paths


def prepare() -> None:
    from rapidocr.utils.download_file import DownloadFile, DownloadFileInput

    directory = model_directory()
    for relative, digest in MODELS.values():
        path = directory / Path(relative).name
        DownloadFile.run(
            DownloadFileInput(
                file_url=BASE_URL + relative,
                save_path=path,
                sha256=digest,
                logger=logging.getLogger(__name__),
                verbose=False,
            )
        )
        with path.open("rb") as source:
            if hashlib.file_digest(source, "sha256").hexdigest() != digest:
                path.unlink()
                raise RuntimeError("OCR model checksum verification failed.")


if __name__ == "__main__":
    prepare()
