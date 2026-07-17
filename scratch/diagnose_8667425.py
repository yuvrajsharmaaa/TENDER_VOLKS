import sys
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path
from backend.app.services.pdf_text_extractor import extract_pdf_text_hybrid
from backend.app.models.models import TextBlock
from ocr.extractors.gem_field_extractor import (
    detect_column_split, merge_into_cells, pair_cells_by_row,
    segment_by_schedule, match_field, strip_devanagari, FIELD_ANCHORS
)
import re

pdf_path = "backend/app/storage/jobs/6b266bb1-6cd4-4db8-96b2-61d488f66122/GeM-Bidding-8667425.pdf_1765009740_1937252.pdf"
pages_dir = Path("scratch/pdf8667425_pages")

results = extract_pdf_text_hybrid(pdf_path, pages_dir)

for p in results:
    blocks = [TextBlock(
        block_id=str(idx), text=b.get('text',''), confidence=1.0,
        bounding_box=b.get('bounding_box'), language_hint='en'
    ) for idx, b in enumerate(p['blocks'])]
    
    # Search for PBG-related text on any page
    page_text = " ".join(b.text for b in blocks).lower()
    if "pbg" in page_text or "epbg" in page_text or "percentage" in page_text:
        print(f"\n=== PAGE {p['page']} - Has ePBG content ===")
        split = detect_column_split(blocks)
        print(f"  Column split: {split}")
        left_blocks = [b for b in blocks if b.bounding_box["x1"] < split]
        right_blocks = [b for b in blocks if b.bounding_box["x1"] >= split]
        left_cells = merge_into_cells(left_blocks)
        right_cells = merge_into_cells(right_blocks)
        pairs = pair_cells_by_row(left_cells, right_cells)
        
        print(f"  Left blocks: {len(left_blocks)}, Right blocks: {len(right_blocks)}")
        print(f"  Pairs: {len(pairs)}")
        
        for lc, rc in pairs:
            ltext = lc['text']
            rtext = rc['text']
            if any(kw in ltext.lower() for kw in ["pbg", "epbg", "percentage", "duration"]):
                print(f"  PAIR: '{ltext}' --> '{rtext}'")
        
        # Also look at raw blocks for PBG content
        print(f"\n  Raw blocks containing 'pbg' or 'epbg':")
        for b in blocks:
            if any(kw in b.text.lower() for kw in ["pbg", "epbg", "percentage", "duration"]):
                print(f"    x1={b.bounding_box['x1']}, text={repr(b.text)}")
