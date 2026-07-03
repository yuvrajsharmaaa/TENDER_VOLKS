from paddleocr import PaddleOCR
from pathlib import Path
from backend.app.models.models import TextBlock
import numpy as np
from PIL import Image

class OcrEngine:
    def __init__(self, lang: str = "en"):
        self.ocr = PaddleOCR(
            use_angle_cls=True,
            lang=lang,
            use_gpu=False,
            show_log=False,
        )

    def run(self, image_path: Path) -> list[TextBlock]:
        img = np.array(Image.open(image_path).convert("RGB"))
        result = self.ocr.ocr(img, cls=True)

        text_blocks = []
        if not result or result[0] is None:
            return text_blocks

        for idx, line in enumerate(result[0]):
            box_points, (text, confidence) = line
            xs = [p[0] for p in box_points]
            ys = [p[1] for p in box_points]
            text_blocks.append(TextBlock(
                block_id=f"blk_{idx+1:04d}",
                text=text,
                confidence=round(float(confidence), 4),
                bounding_box={"x1": int(min(xs)), "y1": int(min(ys)),
                              "x2": int(max(xs)), "y2": int(max(ys))},
                language_hint="en"
            ))
        return text_blocks
