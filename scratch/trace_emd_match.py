import fitz
import re
from pathlib import Path
import sys

def safe_str(s):
    return str(s).encode("ascii", "ignore").decode("ascii")

# Add project root and backend to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from backend.app.services.tender_mapper import build_infosheet_data
from backend.app.services.normalizer import parse_money

pdf_noida = Path("backend/app/storage/objects/tender-pdfs/a6a5034c-efe2-4d5f-b0a9-3d278b3f8188/GAIL Split Noida.pdf")
doc = fitz.open(str(pdf_noida))
full_text = "\n".join([p.get_text() for p in doc])

print("=== TRACING EXACT REGEX MATCH FOR EMD IN NOIDA PDF ===")

print("\nAll occurrences of 'EMD Amount' in full_text:")
for m in re.finditer(r"EMD\s+Amount[^\n]*", full_text, re.IGNORECASE):
    print(f"  Pos {m.start()}: {safe_str(repr(m.group(0)))}")
    substr = full_text[m.start():m.start()+250]
    print(f"    Subsequent text: {safe_str(repr(substr))}")

print("\n--- CHECKING HOW EMD AMOUNT WAS DERIVED IN POSTGRES DB ---")
# Let's inspect the database row for Noida in postgres!
import psycopg2
db_url_local = "postgresql://postgres:postgres@127.0.0.1:5433/tender_db"
try:
    conn = psycopg2.connect(db_url_local)
    cursor = conn.cursor()
    cursor.execute("SELECT id, emd_amount, tender_value, estimated_cost FROM public.tender_information WHERE tender_id = 99 OR id = 6")
    row = cursor.fetchone()
    print("DB Row for ID 6:", row)
    
    # Check all rows in tender_information with emd_amount > 0
    cursor.execute("SELECT id, tender_id, emd_amount, tender_value FROM public.tender_information WHERE emd_amount > 0")
    print("All rows with emd_amount > 0:", cursor.fetchall())
    conn.close()
except Exception as e:
    print("Error querying DB:", e)
