import fitz
import sys
sys.stdout.reconfigure(encoding='utf-8')
from backend.app.services.pdf_text_extractor import cluster_words_into_cells
from backend.app.models.models import PageResult, TextBlock
from ocr.extractors.gem_field_extractor import segment_by_schedule, merge_into_cells, pair_cells_by_row

def detect_column_split_v3(text_blocks):
    bins = {}
    for b in text_blocks:
        x1 = b.bounding_box["x1"]
        bin_idx = x1 // 20
        bins[bin_idx] = bins.get(bin_idx, 0) + 1
    
    sorted_bins = sorted(bins.items(), key=lambda item: item[1], reverse=True)
    if len(sorted_bins) >= 2:
        bin1_x = sorted_bins[0][0] * 20 + 10
        bin2_x = sorted_bins[1][0] * 20 + 10
        split = (bin1_x + bin2_x) // 2
        return split
    return 300  # fallback

doc = fitz.open('backend/app/storage/jobs/35580348-246b-49f7-86a0-175c1bfd64ca/GAIL VRLA Jamnagar.pdf')
page = doc.load_page(0)
native_words = page.get_text("words")
blocks = cluster_words_into_cells(native_words)

tb_list = []
for idx, b in enumerate(blocks):
    tb_list.append(TextBlock(
        block_id=str(idx),
        text=b.get('text', ''),
        confidence=1.0,
        bounding_box=b.get('bounding_box'),
        language_hint='en'
    ))

col_split = detect_column_split_v3(tb_list)
print("Detected column split V3:", col_split)

left_blocks = [b for b in tb_list if b.bounding_box["x1"] < col_split]
right_blocks = [b for b in tb_list if b.bounding_box["x1"] >= col_split]

left_cells = merge_into_cells(left_blocks, y_gap_tolerance=5)
right_cells = merge_into_cells(right_blocks, y_gap_tolerance=5)

print("\nMerged Left Cells:")
for c in left_cells:
    bbox = c['bbox']
    print(f"  {c['text']} (x1={bbox['x1']}, y1={bbox['y1']}, x2={bbox['x2']}, y2={bbox['y2']})")

print("\nMerged Right Cells:")
for c in right_cells:
    bbox = c['bbox']
    print(f"  {c['text']} (x1={bbox['x1']}, y1={bbox['y1']}, x2={bbox['x2']}, y2={bbox['y2']})")

pairs = pair_cells_by_row(left_cells, right_cells)
print("\nPaired Cells:")
for lc, rc in pairs:
    print(f"  Left: '{lc['text']}'  <--->  Right: '{rc['text']}'")
