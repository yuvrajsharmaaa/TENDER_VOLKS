import sys
import os
import re
import json
from pathlib import Path
import fitz  # PyMuPDF

# Add project root and backend to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from backend.app.services.tender_mapper import build_infosheet_data
from backend.app.services.llm_field_resolver import LLMFieldResolver

def extract_pdf_text(pdf_path: Path) -> str:
    doc = fitz.open(str(pdf_path))
    pages_text = []
    for page in doc:
        pages_text.append(page.get_text())
    return "\n".join(pages_text)

# Find GAIL Rajahmundry and another tender PDF
rajahmundry_pdf = None
visakhapatnam_pdf = None

for p in Path("backend/app/storage").rglob("*.pdf"):
    if "Rajahmundry" in p.name and rajahmundry_pdf is None:
        rajahmundry_pdf = p
    elif "Visakhapatnam" in p.name and visakhapatnam_pdf is None:
        visakhapatnam_pdf = p

print(f"Rajahmundry PDF: {rajahmundry_pdf}")
print(f"Visakhapatnam PDF: {visakhapatnam_pdf}")

def check_fc_regex(full_text: str):
    normalized_full_text = re.sub(r"\s+", " ", full_text).lower()
    m_fc_exempt = re.search(
        r"financial\s+criteria\b(?:(?!financial\s+criteria).){0,150}?not\s+applicable",
        normalized_full_text,
        re.DOTALL,
    )
    if m_fc_exempt:
        return True, m_fc_exempt.group(0)[:150]
    return False, "NO MATCH"

resolver = LLMFieldResolver()

tenders = [
    ("GEM/2026/B/7783843 (GAIL Rajahmundry NiCd)", rajahmundry_pdf),
    ("GAIL Visakhapatnam B&BC VRLA", visakhapatnam_pdf),
]

for name, pdf_p in tenders:
    if not pdf_p or not pdf_p.exists():
        print(f"Skipping {name} (file not found)")
        continue
        
    text = extract_pdf_text(pdf_p)
    fc_matched, fc_window = check_fc_regex(text)
    
    page_texts = [{"page": idx + 1, "text": page_txt} for idx, page_txt in enumerate(text.split("\f"))]
    info = build_infosheet_data([], page_texts)
    
    missing_keys = ["custom_eligibility_criteria_display"]
    heuristic_res = resolver._resolve_local_heuristics(text, missing_keys)
    custom_elig = heuristic_res.get("custom_eligibility_criteria_display", {}).get("value")
    
    print(f"\n============================================================")
    print(f"TENDER: {name}")
    print(f"FC Exempt Regex Matched: {fc_matched}")
    print(f"FC Match Window (150 chars max): {fc_window!r}")
    print(f"Avg Annual Turnover Type: {info.get('avg_annual_turnover_type_display')}")
    print(f"Avg Annual Turnover Value: {info.get('avg_annual_turnover_value_display')}")
    print(f"Working Capital Type: {info.get('working_capital_type_display')}")
    print(f"Working Capital Value: {info.get('working_capital_value_display')}")
    print(f"Solvency Certificate Type: {info.get('solvency_certificate_type_display')}")
    print(f"Solvency Certificate Value: {info.get('solvency_certificate_value_display')}")
    print(f"Net Worth Type: {info.get('net_worth_type_display')}")
    print(f"Net Worth Value: {info.get('net_worth_value_display')}")
    print(f"Custom Eligibility Criteria (Mapper): {info.get('custom_eligibility_criteria_display')}")
    print(f"Custom Eligibility Criteria (Heuristic Fallback): {custom_elig}")
