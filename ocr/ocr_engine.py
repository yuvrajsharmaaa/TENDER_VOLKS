from pathlib import Path

import numpy as np
from PIL import Image
from paddleocr import PaddleOCR

from backend.app.models.models import TextBlock


class OcrEngine:
    """
    Line-level OCR using PaddleOCR.

    Output shape (`TextBlock` list) matches the previous Tesseract-based
    implementation, so downstream layout detection and field extraction
    are unaffected.
    """

    # Class-level cache to share raw OCR results and avoid double-processing in layout detection
    _cache: dict[str, list] = {}

    # Class-level model cache — PaddleOCR model loading is expensive (seconds),
    # so load once per language and reuse across all OcrEngine instances.
    _models: dict[str, PaddleOCR] = {}

    def __init__(self, lang: str = "en"):
        self.lang = lang
        if lang not in OcrEngine._models:
            OcrEngine._models[lang] = PaddleOCR(
                use_angle_cls=True,  # handles rotated/skewed scanned text
                lang=lang,
                use_gpu=False,
                show_log=False,
            )
        self.ocr = OcrEngine._models[lang]

    def run(self, image_path: Path) -> list[TextBlock]:
        cache_key = f"{image_path}:{self.lang}"
        if cache_key in OcrEngine._cache:
            raw_lines = OcrEngine._cache[cache_key]
        else:
            img = np.array(Image.open(image_path).convert("RGB"))
            result = self.ocr.ocr(img, cls=True)
            raw_lines = result[0] if result and result[0] else []
            OcrEngine._cache[cache_key] = raw_lines

        text_blocks = []
        for idx, line in enumerate(raw_lines):
            box_points, (text, confidence) = line
            if not text.strip():
                continue
            xs = [p[0] for p in box_points]
            ys = [p[1] for p in box_points]
            text_blocks.append(TextBlock(
                block_id=f"blk_{idx+1:04d}",
                text=text,
                confidence=round(float(confidence), 4),
                bounding_box={
                    "x1": int(min(xs)), "y1": int(min(ys)),
                    "x2": int(max(xs)), "y2": int(max(ys)),
                },
                language_hint=self.lang,
            ))
        return text_blocks