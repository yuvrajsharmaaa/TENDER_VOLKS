import fitz
import re
import json
from pathlib import Path
import sys

# Add project root and backend to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from backend.app.services.tender_mapper import build_infosheet_data

pdf_noida = Path("backend/app/storage/objects/tender-pdfs/a6a5034c-efe2-4d5f-b0a9-3d278b3f8188/GAIL Split Noida.pdf")
doc = fitz.open(str(pdf_noida))
pages_text = [{"page": idx + 1, "text": page.get_text()} for idx, page in enumerate(doc)]

# Call build_infosheet_data
info = build_infosheet_data([], pages_text)

print("Schedule 1 details:", repr(info.get("schedule_1_details_display")))
print("Schedule 2 details:", repr(info.get("schedule_2_details_display")))
print("Schedule 3 details:", repr(info.get("schedule_3_details_display")))
