import fitz
import sys
from pathlib import Path
from backend.app.services.pdf_text_extractor import extract_pdf_text_hybrid, cluster_words_into_cells
from backend.app.models.models import PageResult, TextBlock
from ocr.extractors.gem_field_extractor import GemFieldExtractor, detect_column_split

pdf_path = r"backend/app/storage/jobs/78e7a091-f1aa-4556-bb42-3d386d14583f/GAIL NiCd Barauni.pdf"
pages_dir = Path("scratch/barauni_pages")

results = extract_pdf_text_hybrid(pdf_path, pages_dir)
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
    
    # Let's see what detect_column_split returns for each page
    split = detect_column_split(blocks)
    print(f"Page {p['page']} split boundary: {split}")
    # Print blocks distribution around split
    left = [b for b in blocks if b.bounding_box["x1"] < split]
    right = [b for b in blocks if b.bounding_box["x1"] >= split]
    print(f"  Blocks count: total={len(blocks)}, left={len(left)}, right={len(right)}")
