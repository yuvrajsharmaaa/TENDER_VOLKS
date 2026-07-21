import sys
sys.stdout.reconfigure(encoding='utf-8')
import re
from pathlib import Path
from backend.app.services.pdf_text_extractor import extract_pdf_text_hybrid
from backend.app.models.models import TextBlock
from ocr.extractors.gem_field_extractor import (
    detect_column_split, merge_into_cells, strip_devanagari, FIELD_ANCHORS
)

pdf_path = "backend/app/storage/jobs/6b266bb1-6cd4-4db8-96b2-61d488f66122/GeM-Bidding-8667425.pdf_1765009740_1937252.pdf"
pages_dir = Path("scratch/pdf8667425_pages")

results = extract_pdf_text_hybrid(pdf_path, pages_dir)
p = results[2]  # Page 3

blocks = [TextBlock(
    block_id=str(idx), text=b.get('text',''), confidence=1.0,
    bounding_box=b.get('bounding_box'), language_hint='en'
) for idx, b in enumerate(p['blocks'])]

print("=== Raw Blocks matches on page 3 ===")
for b in blocks:
    clean_text = strip_devanagari(b.text).lower()
    for field_name, spec in FIELD_ANCHORS.items():
        if field_name != "pbg_percentage":
            continue
        for anchor in spec["anchors"]:
            clean_anchor = anchor.lower()
            if clean_anchor in clean_text:
                idx = b.text.lower().find(anchor.lower())
                print(f"Match raw block: {repr(b.text)}")
                print(f"  clean_text: {repr(clean_text)}")
                print(f"  anchor: {repr(anchor)}")
                if idx != -1:
                    suffix = b.text[idx + len(anchor):].strip()
                    suffix = re.sub(r"^[:\-/\s\u0900-\u097F]+", "", suffix).strip()
                    print(f"  extracted suffix: {repr(suffix)}")
