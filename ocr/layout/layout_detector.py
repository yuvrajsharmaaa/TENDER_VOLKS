from paddleocr import PPStructure
from pathlib import Path
from backend.app.models.models import LayoutRegion
import numpy as np
from PIL import Image

class LayoutDetector:
    def __init__(self):
        self.structure = PPStructure(
            table=True,
            ocr=False,
            show_log=False,
            use_gpu=False,
        )

    def detect(self, image_path: Path) -> list[LayoutRegion]:
        img = np.array(Image.open(image_path).convert("RGB"))
        result = self.structure(img)

        regions = []
        for idx, region in enumerate(result):
            region_type = region.get("type", "unknown").lower()
            bbox = region.get("bbox", [0, 0, 0, 0])

            table_structure = None
            if region_type == "table" and "res" in region:
                table_structure = region["res"] # In real scenario, parse html

            regions.append(LayoutRegion(
                region_id=f"reg_{idx+1:04d}",
                region_type=region_type,
                bounding_box={"x1": bbox[0], "y1": bbox[1],
                              "x2": bbox[2], "y2": bbox[3]},
                contained_block_ids=[],
                table_structure=table_structure
            ))
        return regions
