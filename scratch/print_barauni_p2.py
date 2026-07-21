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
for idx, b in enumerate(blocks):
    print(f"Block {idx:2d}: bbox=[{b['bounding_box']['x1']:.1f}, {b['bounding_box']['y1']:.1f}, {b['bounding_box']['x2']:.1f}, {b['bounding_box']['y2']:.1f}], text={repr(b['text'])}")
