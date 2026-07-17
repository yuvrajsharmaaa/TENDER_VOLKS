import sys
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path
from backend.app.services.pdf_text_extractor import extract_pdf_text_hybrid

pdf_path = "backend/app/storage/jobs/6b266bb1-6cd4-4db8-96b2-61d488f66122/GeM-Bidding-8667425.pdf_1765009740_1937252.pdf"
pages_dir = Path("scratch/pdf8667425_pages")

results = extract_pdf_text_hybrid(pdf_path, pages_dir)
p = results[2]  # Page 3

print("=== All Blocks on Page 3 containing relevant substrings ===")
for idx, b in enumerate(p['blocks']):
    txt = b.get('text', '')
    if any(kw in txt for kw in ['3.00', 'Percentage', '9ितशत', '3.0']):
        print(f"idx={idx:2d}, text={repr(txt)}, bbox={b.get('bounding_box')}")
