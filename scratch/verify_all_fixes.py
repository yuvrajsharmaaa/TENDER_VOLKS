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

pdf_noida = Path("backend/app/storage/objects/tender-pdfs/a6a5034c-efe2-4d5f-b0a9-3d278b3f8188/GAIL Split Noida.pdf")
pdf_rajahmundry = Path("backend/app/storage/objects/tender-pdfs/05f9096e-26e9-4c57-9937-34b222e8ea41/GAIL Rajahmundry NiCd (1).pdf")
pdf_visakhapatnam = Path("backend/app/storage/objects/tender-pdfs/8cf1c0c8-6c43-4224-9907-ec57a51cb3e1/GAIL Visakhapatnam B&BC VRLA.pdf")

def get_extracted_fields(p: Path):
    doc = fitz.open(str(p))
    pages_text = [{"page": idx + 1, "text": page.get_text()} for idx, page in enumerate(doc)]
    info = build_infosheet_data([], pages_text)
    return {
        "emd": info.get("emd_amount_display"),
        "ov1": info.get("order_value_1_display"),
        "ov2": info.get("order_value_2_display"),
        "ov3": info.get("order_value_3_display"),
        "wc": info.get("working_capital_value_display"),
        "pti": info.get("payment_terms_installation_display"),
        "sch1": info.get("schedule_1_details_display"),
    }

noida_res = get_extracted_fields(pdf_noida)
raj_res = get_extracted_fields(pdf_rajahmundry)
viz_res = get_extracted_fields(pdf_visakhapatnam)

print("\n==========================================================================")
print("COMPREHENSIVE AFTER-FIX VERIFICATION RESULTS TABLE")
print("==========================================================================")

tenders = [
    ("GAIL Split Noida (GEM/2025/B/7017046)", noida_res),
    ("GAIL Rajahmundry NiCd (GEM/2026/B/7783843)", raj_res),
    ("GAIL Visakhapatnam B&BC VRLA", viz_res),
]

for title, res in tenders:
    print(f"\n{title}:")
    print(f"  EMD Amount:                 {safe_str(res['emd'])}")
    print(f"  Work Order 1:               {safe_str(res['ov1'])}")
    print(f"  Work Order 2:               {safe_str(res['ov2'])}")
    print(f"  Work Order 3:               {safe_str(res['ov3'])}")
    print(f"  Working Capital Value:      {safe_str(res['wc'])}")
    print(f"  Payment Terms Installation: {safe_str(res['pti'])}")
    print(f"  Schedule Details:           {safe_str(res['sch1'])}")
