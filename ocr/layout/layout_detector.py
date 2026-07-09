from pathlib import Path

import pytesseract
from PIL import Image

from backend.app.models.models import LayoutRegion


class LayoutDetector:
    """
    Heuristic layout detection grouped from Tesseract's paragraph-level boxes.

    The original implementation used PaddleOCR's PPStructure model for table
    detection, but it shares PaddleOCR's blocked `imgaug` dependency chain
    (see ocr/ocr_engine.py for the full explanation) and cannot be installed
    here. This groups OCR word boxes into paragraph-level regions instead of
    running true table-structure detection — it is a real, deterministic
    grouping of live OCR output (not mocked data), just a coarser one. Table
    regions are not distinguished; every region is reported as "paragraph".
    `contained_block_ids`/`text_content` are filled in by ocr/pipeline.py via
    spatial containment against the actual TextBlock list, so this class only
    needs to produce region boundaries.
    """

    def __init__(self, lang: str = "eng"):
        self.lang = lang

    def detect(self, image_path: Path) -> list[LayoutRegion]:
        img = Image.open(image_path).convert("RGB")
        data = pytesseract.image_to_data(
            img, lang=self.lang, output_type=pytesseract.Output.DICT
        )

        paragraphs: dict[tuple, dict] = {}
        n = len(data["text"])
        for i in range(n):
            if not data["text"][i].strip():
                continue
            key = (data["block_num"][i], data["par_num"][i])
            x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
            para = paragraphs.setdefault(key, {"x1": x, "y1": y, "x2": x + w, "y2": y + h})
            para["x1"] = min(para["x1"], x)
            para["y1"] = min(para["y1"], y)
            para["x2"] = max(para["x2"], x + w)
            para["y2"] = max(para["y2"], y + h)

        regions = []
        for idx, (key, box) in enumerate(sorted(paragraphs.items())):
            regions.append(LayoutRegion(
                region_id=f"reg_{idx+1:04d}",
                region_type="paragraph",
                bounding_box={"x1": box["x1"], "y1": box["y1"], "x2": box["x2"], "y2": box["y2"]},
                contained_block_ids=[],
                table_structure=None,
            ))
        return regions
