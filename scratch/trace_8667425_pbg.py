import sys
sys.stdout.reconfigure(encoding='utf-8')
import re
from pathlib import Path
from backend.app.services.pdf_text_extractor import extract_pdf_text_hybrid
from backend.app.models.models import TextBlock
from ocr.extractors.gem_field_extractor import (
    detect_column_split, merge_into_cells, segment_by_schedule,
    strip_devanagari, FIELD_ANCHORS
)

pdf_path = "backend/app/storage/jobs/6b266bb1-6cd4-4db8-96b2-61d488f66122/GeM-Bidding-8667425.pdf_1765009740_1937252.pdf"
pages_dir = Path("scratch/pdf8667425_pages")

results = extract_pdf_text_hybrid(pdf_path, pages_dir)

# Check page 3 where ePBG blocks live
p = results[2]

# Build a mock PageResult to pass to segment_by_schedule
from backend.app.models.models import PageResult
blocks = [TextBlock(
    block_id=str(idx), text=b.get('text',''), confidence=1.0,
    bounding_box=b.get('bounding_box'), language_hint='en'
) for idx, b in enumerate(p['blocks'])]

page = PageResult(
    job_id="debug", page_number=3, image_path="",
    image_width_px=600, image_height_px=800,
    processing_time_seconds=0.0, text_blocks=blocks, layout_regions=[]
)

print(f"=== PAGE 3 SEGMENTS ===")
segments = segment_by_schedule(page.layout_regions, page.text_blocks)
print(f"Number of segments: {len(segments)}, keys: {list(segments.keys())}")

for seg_num, seg_blocks in segments.items():
    print(f"\nSegment {seg_num}: {len(seg_blocks)} blocks")
    col_split = detect_column_split(seg_blocks)
    left_blocks = [b for b in seg_blocks if b.bounding_box["x1"] < col_split]
    right_blocks = [b for b in seg_blocks if b.bounding_box["x1"] >= col_split]
    left_cells = merge_into_cells(left_blocks)
    right_cells = merge_into_cells(right_blocks)
    
    print(f"  col_split={col_split}, left_cells={len(left_cells)}, right_cells={len(right_cells)}")
    
    print(f"\n  === Running same-cell contains check on all cells ===")
    for cell in left_cells + right_cells:
        cell_text = cell["text"].strip()
        clean_text = strip_devanagari(cell_text).lower()
        for field_name, spec in FIELD_ANCHORS.items():
            if field_name not in ["pbg_percentage", "pbg_duration_months", "pbg_advisory_bank"]:
                continue
            for anchor in spec["anchors"]:
                clean_anchor = anchor.lower()
                if clean_anchor in clean_text:
                    idx = cell_text.lower().find(anchor.lower())
                    if idx != -1:
                        suffix = cell_text[idx + len(anchor):].strip()
                        suffix = re.sub(r"^[:\-/\s\u0900-\u097F]+", "", suffix).strip()
                        print(f"  HIT: field={field_name}, anchor={repr(anchor)}")
                        print(f"    cell_text={repr(cell_text)}")
                        print(f"    suffix={repr(suffix)}, len={len(suffix)}")
                        print(f"    Will emit: {len(suffix) < 200}")
