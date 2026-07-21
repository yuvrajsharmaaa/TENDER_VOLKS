from pathlib import Path

import pytesseract
from PIL import Image

from backend.app.models.models import TextBlock


class OcrEngine:
    """
    Line-level OCR using Tesseract (via pytesseract).

    Executes line-level character recognition and extracts word/line bounding
    boxes into standardized TextBlock outputs for layout detection and field extraction.
    """

    # Class-level cache to share raw OCR results and avoid double-processing in layout detection
    _cache: dict[str, dict] = {}

    def __init__(self, lang: str = "eng"):
        self.lang = lang

    def run(self, image_path: Path) -> list[TextBlock]:
        cache_key = str(image_path)
        if cache_key in OcrEngine._cache:
            data = OcrEngine._cache[cache_key]
        else:
            img = Image.open(image_path).convert("RGB")
            data = pytesseract.image_to_data(
                img, lang=self.lang, output_type=pytesseract.Output.DICT
            )
            OcrEngine._cache[cache_key] = data


        # Group Tesseract's word-level boxes into line-level blocks (grouped
        # by block/paragraph/line index) so downstream anchor/regex matching
        # in ocr/extractors/field_extractor.py sees whole lines, matching the
        # granularity the rest of the pipeline expects.
        lines: dict[tuple, dict] = {}
        n = len(data["text"])
        for i in range(n):
            text = data["text"][i].strip()
            if not text:
                continue
            key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
            x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
            conf_raw = data["conf"][i]
            try:
                conf = max(float(conf_raw), 0.0) / 100.0
            except (TypeError, ValueError):
                conf = 0.0

            line = lines.setdefault(key, {
                "words": [], "confs": [], "x1": x, "y1": y, "x2": x + w, "y2": y + h
            })
            line["words"].append(text)
            line["confs"].append(conf)
            line["x1"] = min(line["x1"], x)
            line["y1"] = min(line["y1"], y)
            line["x2"] = max(line["x2"], x + w)
            line["y2"] = max(line["y2"], y + h)

        text_blocks = []
        for idx, (key, line) in enumerate(sorted(lines.items())):
            avg_conf = sum(line["confs"]) / len(line["confs"]) if line["confs"] else 0.0
            text_blocks.append(TextBlock(
                block_id=f"blk_{idx+1:04d}",
                text=" ".join(line["words"]),
                confidence=round(avg_conf, 4),
                bounding_box={"x1": line["x1"], "y1": line["y1"], "x2": line["x2"], "y2": line["y2"]},
                language_hint=self.lang,
            ))
        return text_blocks
