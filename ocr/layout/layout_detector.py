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
        cache_key = str(image_path)
        from ocr.ocr_engine import OcrEngine
        if cache_key in OcrEngine._cache:
            data = OcrEngine._cache[cache_key]
        else:
            img = Image.open(image_path).convert("RGB")
            data = pytesseract.image_to_data(
                img, lang=self.lang, output_type=pytesseract.Output.DICT
            )
            OcrEngine._cache[cache_key] = data

        paragraphs: dict[tuple, dict] = {}
        paragraph_words: dict[tuple, list[dict]] = {}
        
        n = len(data["text"])
        for i in range(n):
            text = data["text"][i].strip()
            if not text:
                continue
            key = (data["block_num"][i], data["par_num"][i])
            x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
            
            para = paragraphs.setdefault(key, {"x1": x, "y1": y, "x2": x + w, "y2": y + h})
            para["x1"] = min(para["x1"], x)
            para["y1"] = min(para["y1"], y)
            para["x2"] = max(para["x2"], x + w)
            para["y2"] = max(para["y2"], y + h)

            p_words = paragraph_words.setdefault(key, [])
            p_words.append({
                "text": text,
                "x1": x,
                "y1": y,
                "x2": x + w,
                "y2": y + h,
                "line_num": data["line_num"][i]
            })

        regions = []
        for idx, (key, box) in enumerate(sorted(paragraphs.items())):
            region_type = "paragraph"
            words_in_para = paragraph_words.get(key, [])
            
            if words_in_para:
                # Group words in this paragraph by line_num
                lines: dict[int, list[dict]] = {}
                for w in words_in_para:
                    lines.setdefault(w["line_num"], []).append(w)
                
                multi_column_lines_count = 0
                total_lines_count = len(lines)
                
                for line_num, line_words in lines.items():
                    # Sort words left-to-right
                    sorted_line_words = sorted(line_words, key=lambda w: w["x1"])
                    cols = []
                    if sorted_line_words:
                        current_col = [sorted_line_words[0]]
                        for w in sorted_line_words[1:]:
                            gap = w["x1"] - current_col[-1]["x2"]
                            if gap > 40:  # Column gap threshold (in pixels)
                                cols.append(current_col)
                                current_col = [w]
                            else:
                                current_col.append(w)
                        cols.append(current_col)
                    
                    if len(cols) >= 2:
                        multi_column_lines_count += 1
                
                # If at least 30% of lines are multi-column, or if we have multiple lines
                # that consistently form at least 2 columns, classify as a table.
                if total_lines_count >= 1:
                    ratio = multi_column_lines_count / total_lines_count
                    if ratio >= 0.35 or (total_lines_count >= 2 and multi_column_lines_count >= 2):
                        region_type = "table"

            regions.append(LayoutRegion(
                region_id=f"reg_{idx+1:04d}",
                region_type=region_type,
                bounding_box={"x1": box["x1"], "y1": box["y1"], "x2": box["x2"], "y2": box["y2"]},
                contained_block_ids=[],
                table_structure=None,
            ))
        return regions

