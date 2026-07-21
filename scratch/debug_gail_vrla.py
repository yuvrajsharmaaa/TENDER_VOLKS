import fitz
import sys
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path
from backend.app.services.pdf_text_extractor import extract_pdf_text_hybrid, cluster_words_into_cells
from backend.app.models.models import PageResult, TextBlock
from ocr.extractors.gem_field_extractor import GemFieldExtractor, match_field, FIELD_ANCHORS

pdf_path = 'backend/app/storage/jobs/35580348-246b-49f7-86a0-175c1bfd64ca/GAIL VRLA Jamnagar.pdf'
pages_dir = Path('backend/app/storage/jobs/35580348-246b-49f7-86a0-175c1bfd64ca/pages')

results = extract_pdf_text_hybrid(pdf_path, pages_dir)
mock_results = []
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
    mock_results.append(PageResult(
        job_id="test",
        page_number=p['page'],
        image_path="",
        image_width_px=600,
        image_height_px=800,
        processing_time_seconds=0.0,
        text_blocks=blocks,
        layout_regions=[]
    ))

# Let's inspect the same-block matches and spatial pairs
extractor = GemFieldExtractor()

# Let's run a custom loop to print candidates for department_name
print("=== DEBGUING CANDIDATES ===")
# We'll run the extract_fields logic but print candidates
for page in mock_results:
    # 1. Same-block
    for block in page.text_blocks:
        text = block.text.strip()
        parts = text.split(":", 1)
        if len(parts) == 2 and parts[0].strip() and parts[1].strip():
            l_text, r_text = parts[0].strip(), parts[1].strip()
            field_name = match_field(l_text, None)
            if field_name == "department_name":
                print(f"Same-block colon match: label='{l_text}', value='{r_text}', text='{text}'")
        
        for field_name, spec in FIELD_ANCHORS.items():
            if field_name == "department_name":
                for anchor in spec["anchors"]:
                    clean_anchor = anchor.lower()
                    import re
                    # strip devanagari from text
                    from ocr.extractors.gem_field_extractor import strip_devanagari
                    clean_text = strip_devanagari(text).lower()
                    if clean_text.startswith(clean_anchor):
                        suffix = text[len(anchor):].strip()
                        suffix = re.sub(r"^[:\-/\s\u0930\u093e\u093f\u0940\u0941\u0942\u0947\u0948\u094b\u094c\u0902]+", "", suffix).strip()
                        print(f"Same-block prefix match: anchor='{anchor}', suffix='{suffix}', text='{text}'")

    # 2. Spatial pairing candidates
    from ocr.extractors.gem_field_extractor import segment_by_schedule, detect_column_split, merge_into_cells, pair_cells_by_row
    segments = segment_by_schedule(page.layout_regions, page.text_blocks)
    for seg_num, seg_blocks in segments.items():
        col_split = detect_column_split(seg_blocks)
        left_blocks = [b for b in seg_blocks if b.bounding_box["x1"] < col_split]
        right_blocks = [b for b in seg_blocks if b.bounding_box["x1"] >= col_split]
        left_cells = merge_into_cells(left_blocks)
        right_cells = merge_into_cells(right_blocks)
        pairs = pair_cells_by_row(left_cells, right_cells)
        for lc, rc in pairs:
            field_name = match_field(lc["text"], None)
            if field_name == "department_name":
                print(f"Spatial match: left='{lc['text']}', right='{rc['text']}'")
