
import fitz
import sys
sys.stdout.reconfigure(encoding='utf-8')
from backend.app.services.pdf_text_extractor import cluster_words_into_cells

doc = fitz.open('backend/app/storage/jobs/35580348-246b-49f7-86a0-175c1bfd64ca/GAIL VRLA Jamnagar.pdf')
page = doc.load_page(0)
native_words = page.get_text("words")
blocks = cluster_words_into_cells(native_words)

print(f"{'Cell Text':<60} | x1={round(min(b['bounding_box']['x1'] for b in blocks)):.0f}, x2={round(max(b['bounding_box']['x2'] for b in blocks)):.0f}")
print("-" * 80)
for idx, b in enumerate(blocks):
    bbox = b['bounding_box']
    print(f"{idx:02d}: {b['text']:<55} | x1={bbox['x1']:3d}, y1={bbox['y1']:3d}, x2={bbox['x2']:3d}, y2={bbox['y2']:3d}")
