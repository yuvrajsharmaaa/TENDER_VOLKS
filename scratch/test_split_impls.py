import fitz
import sys
sys.stdout.reconfigure(encoding='utf-8')
from backend.app.services.pdf_text_extractor import extract_pdf_text_hybrid
from pathlib import Path
from backend.app.models.models import TextBlock

pdf_path = r"backend/app/storage/jobs/78e7a091-f1aa-4556-bb42-3d386d14583f/GAIL NiCd Barauni.pdf"
pages_dir = Path("scratch/barauni_pages")

results = extract_pdf_text_hybrid(pdf_path, pages_dir)

def try_detect(text_blocks):
    total_orig = len(text_blocks)
    if total_orig == 0:
        return 300
        
    # Filter out blocks that span too wide (e.g. full width text/paragraphs)
    # We estimate page width from max coordinate
    max_x = max(b.bounding_box["x2"] for b in text_blocks)
    min_x = min(b.bounding_box["x1"] for b in text_blocks)
    page_width = max_x - min_x or 1
    
    filtered_blocks = [
        b for b in text_blocks
        if (b.bounding_box["x2"] - b.bounding_box["x1"]) < 0.5 * page_width
    ]
    
    total = len(filtered_blocks)
    if total == 0:
        filtered_blocks = text_blocks
        total = len(filtered_blocks)
        
    bins = {}
    for b in filtered_blocks:
        key = b.bounding_box["x1"] // 20
        bins[key] = bins.get(key, 0) + 1
        
    sorted_bins = sorted(bins.items(), key=lambda kv: kv[1], reverse=True)
    
    if len(sorted_bins) >= 2:
        top2 = sorted(sorted_bins[:2], key=lambda kv: kv[0])
        bin1, bin2 = top2[0][0], top2[1][0]
        if bin2 - bin1 >= 4:
            mid_bin_x = (bin1 + bin2) * 10
            left_col_blocks = [b for b in filtered_blocks if b.bounding_box["x1"] < mid_bin_x]
            right_col_blocks = [b for b in filtered_blocks if b.bounding_box["x1"] >= mid_bin_x]

            max_left_x2 = max(b.bounding_box["x2"] for b in left_col_blocks) if left_col_blocks else (bin1 * 20 + 20)
            min_right_x1 = min(b.bounding_box["x1"] for b in right_col_blocks) if right_col_blocks else (bin2 * 20)

            col_split = (max_left_x2 + min_right_x1) // 2
            
            # Balance guard
            n_left = sum(1 for b in text_blocks if b.bounding_box["x1"] < col_split)
            n_right = total_orig - n_left
            minority = min(n_left, n_right)
            if minority / total_orig >= 0.15:
                return int(col_split)
                
    # Fallback
    x1_positions = sorted(set(b.bounding_box["x1"] for b in filtered_blocks))
    if len(x1_positions) < 2:
        return 300
    gaps = [(x1_positions[i+1] - x1_positions[i], x1_positions[i])
            for i in range(len(x1_positions) - 1)]
    page_width = x1_positions[-1] - x1_positions[0] or 1
    
    valid_gaps = []
    for gap_size, gap_start in gaps:
        split = gap_start + gap_size // 2
        n_left = sum(1 for b in text_blocks if b.bounding_box["x1"] < split)
        n_right = total_orig - n_left
        minority = min(n_left, n_right)
        if minority / total_orig >= 0.15:
            valid_gaps.append((gap_size, gap_start))
            
    if valid_gaps:
        best_gap = max(valid_gaps, key=lambda g: g[0])
        return best_gap[1] + best_gap[0] // 2
        
    best_gap = max(gaps, key=lambda g: g[0])
    return best_gap[1] + best_gap[0] // 2

for p in results:
    blocks = []
    for idx, b in enumerate(p['blocks']):
        bbox = b.get('bounding_box')
        blocks.append(TextBlock(
            block_id=str(idx),
            text=b.get('text', ''),
            confidence=1.0,
            bounding_box=bbox,
            language_hint='en'
        ))
    print(f"Page {p['page']} split boundary: {try_detect(blocks)}")
