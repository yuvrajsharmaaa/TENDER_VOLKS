import sys
from pathlib import Path

# Add project directories to path
sys.path.insert(0, str(Path(r"c:\Users\Asus\Desktop\Tender_Volks\main").resolve()))

from backend.app.services.pdf_text_extractor import extract_pdf_text_hybrid
from ocr.extractors.gem_field_extractor import GemFieldExtractor, pair_labels_to_values, match_field
from backend.app.models.models import PageResult, TextBlock

pdf_path = r"c:\Users\Asus\Desktop\Tender_Volks\main\backend\app\storage\jobs\0a77f878-21d2-4024-86e7-e22b6fe720e3\GAIL VRLA Jamnagar.pdf"
pages_dir = Path(r"c:\Users\Asus\Desktop\Tender_Volks\main\scratch\pages_debug")

page_texts = extract_pdf_text_hybrid(pdf_path, pages_dir)

# Build PageResult objects
mock_results = []
for p in page_texts:
    blocks = []
    blocks_data = p.get("blocks", [])
    for idx, b in enumerate(blocks_data):
        bbox = b.get("bounding_box", {"x1": 0, "y1": 0, "x2": 0, "y2": 0})
        blocks.append(TextBlock(
            block_id=str(b.get("block_id", idx)),
            text=b.get("text", ""),
            confidence=b.get("confidence", 1.0),
            language_hint="en",
            bounding_box=bbox
        ))
    mock_results.append(PageResult(
        job_id="debug",
        page_number=p.get("page", 1),
        image_path="",
        image_width_px=600,
        image_height_px=800,
        processing_time_seconds=0.0,
        text_blocks=blocks,
        layout_regions=[]
    ))

with open(r"c:\Users\Asus\Desktop\Tender_Volks\main\scratch\debug_extraction_output.txt", "w", encoding="utf-8") as out:
    out.write("--- DEBUGGING PAGE 2 BLOCKS & CELL PAIRING ---\n")
    p2 = mock_results[1]  # Page 2 (index 1)
    out.write(f"Page 2 has {len(p2.text_blocks)} blocks.\n")
    pairs = pair_labels_to_values(p2.text_blocks)
    out.write(f"Total paired cells on Page 2: {len(pairs)}\n")
    for l_c, r_c in pairs:
        out.write(f"  Label: {repr(l_c['text'])}\n")
        out.write(f"  Value: {repr(r_c['text'])}\n")
        field = match_field(l_c['text'], None)
        if field:
             out.write(f"    --> Matched field: {field}\n")
        out.write("-" * 30 + "\n")

    out.write("\n--- RUNNING EXTRACTOR ---\n")
    extractor = GemFieldExtractor()
    extracted = extractor.extract_fields(mock_results)
    out.write(f"Extracted {len(extracted)} fields.\n")
    for f in extracted:
        if f.value is not None or f.confidence > 0:
            out.write(f"Field: {f.field_name}, Value: {repr(f.value)} (Conf: {f.confidence})\n")
            
print("Done writing to scratch/debug_extraction_output.txt")
