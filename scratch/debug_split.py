import fitz
import sys
sys.stdout.reconfigure(encoding='utf-8')
from backend.app.services.pdf_text_extractor import extract_pdf_text_hybrid
from pathlib import Path

pdf_path = r"backend/app/storage/jobs/78e7a091-f1aa-4556-bb42-3d386d14583f/GAIL NiCd Barauni.pdf"
pages_dir = Path("scratch/barauni_pages")

results = extract_pdf_text_hybrid(pdf_path, pages_dir)
p2 = results[1]  # Page 2
blocks = p2['blocks']

# Let's run detect_column_split logic step-by-step
text_blocks = []
for idx, b in enumerate(blocks):
    from backend.app.models.models import TextBlock
    text_blocks.append(TextBlock(
        block_id=str(idx),
        text=b.get('text', ''),
        confidence=1.0,
        bounding_box=b.get('bounding_box'),
        language_hint='en'
    ))

total = len(text_blocks)
bins = {}
for b in text_blocks:
    key = b.bounding_box["x1"] // 20
    bins[key] = bins.get(key, 0) + 1

sorted_bins = sorted(bins.items(), key=lambda kv: kv[1], reverse=True)
print("sorted_bins:", sorted_bins)

if len(sorted_bins) >= 2:
    top2 = sorted(sorted_bins[:2], key=lambda kv: kv[0])
    bin1, bin2 = top2[0][0], top2[1][0]
    print(f"bin1={bin1}, bin2={bin2}")
    if bin2 - bin1 >= 4:
        mid_bin_x = (bin1 + bin2) * 10
        left_col_blocks = [b for b in text_blocks if b.bounding_box["x1"] < mid_bin_x]
        right_col_blocks = [b for b in text_blocks if b.bounding_box["x1"] >= mid_bin_x]

        max_left_x2 = max(b.bounding_box["x2"] for b in left_col_blocks) if left_col_blocks else (bin1 * 20 + 20)
        min_right_x1 = min(b.bounding_box["x1"] for b in right_col_blocks) if right_col_blocks else (bin2 * 20)

        col_split = (max_left_x2 + min_right_x1) // 2
        print(f"max_left_x2={max_left_x2}, min_right_x1={min_right_x1}, col_split={col_split}")

        n_left = sum(1 for b in text_blocks if b.bounding_box["x1"] < col_split)
        n_right = total - n_left
        minority = min(n_left, n_right)
        print(f"n_left={n_left}, n_right={n_right}, minority={minority}, ratio={minority/total:.3f}")
        if minority / total >= 0.15:
            print("Passed balance guard with:", col_split)
        else:
            print("Failed balance guard!")

# Let's look at gap-based fallback
x1_positions = sorted(set(b.bounding_box["x1"] for b in text_blocks))
print("x1_positions:", x1_positions)
gaps = [(x1_positions[i+1] - x1_positions[i], x1_positions[i])
        for i in range(len(x1_positions) - 1)]
page_width = x1_positions[-1] - x1_positions[0] or 1
print("page_width:", page_width)
candidate_gaps = [
    g for g in gaps
    if 0.15 * page_width < (g[1] - x1_positions[0]) < 0.85 * page_width
]
print("candidate_gaps:", candidate_gaps)
best_gap = max(candidate_gaps or gaps, key=lambda g: g[0])
fallback_split = best_gap[1] + best_gap[0] // 2
print("fallback_split:", fallback_split)
