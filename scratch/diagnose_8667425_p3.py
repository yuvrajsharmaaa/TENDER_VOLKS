import sys
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path
from backend.app.services.pdf_text_extractor import extract_pdf_text_hybrid
from backend.app.models.models import TextBlock
from ocr.extractors.gem_field_extractor import (
    detect_column_split, merge_into_cells, pair_cells_by_row, match_field
)

pdf_path = "backend/app/storage/jobs/6b266bb1-6cd4-4db8-96b2-61d488f66122/GeM-Bidding-8667425.pdf_1765009740_1937252.pdf"
pages_dir = Path("scratch/pdf8667425_pages")

results = extract_pdf_text_hybrid(pdf_path, pages_dir)

# Page 3 — PBG fields live here but are not extracted
p = results[2]  # Page 3 (0-indexed)
blocks = [TextBlock(
    block_id=str(idx), text=b.get('text',''), confidence=1.0,
    bounding_box=b.get('bounding_box'), language_hint='en'
) for idx, b in enumerate(p['blocks'])]

print("=== PAGE 3 ALL BLOCKS ===")
for b in blocks:
    print(f"  x1={b.bounding_box['x1']:3d}, x2={b.bounding_box['x2']:3d}, text={repr(b.text)}")

split = detect_column_split(blocks)
print(f"\nColumn split: {split}")
left_blocks = [b for b in blocks if b.bounding_box["x1"] < split]
right_blocks = [b for b in blocks if b.bounding_box["x1"] >= split]
print(f"Left: {len(left_blocks)}, Right: {len(right_blocks)}")

left_cells = merge_into_cells(left_blocks)
right_cells = merge_into_cells(right_blocks)
pairs = pair_cells_by_row(left_cells, right_cells)
print(f"\nPairs ({len(pairs)}):")
for lc, rc in pairs:
    print(f"  '{lc['text']}' --> '{rc['text']}'")

# Also check: are left blocks crossing the split line?
print("\nLeft cells:")
for c in left_cells:
    print(f"  y1={c['bbox']['y1']}, x2={c['bbox']['x2']}, text={repr(c['text'])}")

print("\nRight cells:")
for c in right_cells:
    print(f"  y1={c['bbox']['y1']}, x1={c['bbox']['x1']}, text={repr(c['text'])}")
