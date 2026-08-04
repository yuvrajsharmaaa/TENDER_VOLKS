import sys
import re
import json
from pathlib import Path
import fitz

# Add project root and backend to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from backend.app.services.tender_mapper import build_infosheet_data
from backend.app.services.normalizer import parse_money

def safe_str(s):
    return str(s).encode("ascii", "ignore").decode("ascii")

noida_pdf = Path("backend/app/storage/objects/tender-pdfs/a6a5034c-efe2-4d5f-b0a9-3d278b3f8188/GAIL Split Noida.pdf")
doc = fitz.open(str(noida_pdf))
pages_text = [{"page": idx + 1, "text": page.get_text()} for idx, page in enumerate(doc)]
full_text = "\n".join([p["text"] for p in pages_text])

report = []
report.append("=== NOIDA ANOMALY DETAILED DIAGNOSTIC REPORT ===")

# EMD Amount
tag_e_match = re.search(
    r"\(E\)\s*BID\s*SECURITY\s*/?\s*EARNEST\s*MONEY\s*DEPOSIT\s*\(EMD\)(.*?)(?=\([A-Z0-9]{1,3}\)|\Z)",
    full_text, re.IGNORECASE | re.DOTALL
)
if tag_e_match:
    e_text = tag_e_match.group(1)
    report.append("\n[EMD Tag E Match]:")
    report.append(safe_str(repr(e_text[:400])))
    amt_match = re.search(r"Amount[:\-\s]+Rs\.?\s*([\d,]+(?:\.\d+)?)", e_text, re.IGNORECASE)
    if amt_match:
        report.append(f"Tag E amt match: {amt_match.group(1)} -> parsed: {parse_money(amt_match.group(1))}")

report.append("\n[EMD / Money matches in text]:")
for line_idx, line in enumerate(full_text.split("\n")):
    if any(k in line.lower() for k in ["emd", "bid security", "2,00,000", "200000", "5,00,00", "500000"]):
        report.append(f"Line {line_idx+1}: {safe_str(line.strip())}")

info = build_infosheet_data([], pages_text)
report.append("\n[Mapper Extracted Fields]:")
report.append(f"EMD Amount Display: {safe_str(info.get('emd_amount_display'))}")
report.append(f"Work Order 1 Display: {safe_str(info.get('order_value_1_display'))}")
report.append(f"Work Order 2 Display: {safe_str(info.get('order_value_2_display'))}")
report.append(f"Work Order 3 Display: {safe_str(info.get('order_value_3_display'))}")
report.append(f"Payment Terms Installation: {safe_str(repr(info.get('payment_terms_installation_display')))}")
report.append(f"Working Capital Type: {safe_str(repr(info.get('working_capital_type_display')))}")
report.append(f"Working Capital Value: {safe_str(repr(info.get('working_capital_value_display')))}")

report.append("\n[Payment Terms Installation Clause Extracted Text]:")
for idx, line in enumerate(full_text.split("\n")):
    if "supplied sor items" in line.lower():
        report.append(f"Line {idx+1}: {safe_str(line.strip())}")

report.append("\n[Working Capital Clause Extracted Text]:")
for idx, line in enumerate(full_text.split("\n")):
    if "working capital of the bidder" in line.lower() or "shall be at least" in line.lower():
        report.append(f"Line {idx+1}: {safe_str(line.strip())}")

Path("scratch/noida_report.txt").write_text("\n".join(report), encoding="utf-8")
print("Wrote scratch/noida_report.txt successfully.")
