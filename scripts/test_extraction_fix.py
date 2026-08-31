import os, sys, ast
sys.path.insert(0, os.getcwd())
from pathlib import Path
import pandas as pd
from dotenv import load_dotenv


load_dotenv(".env.dev")

from backend.app.services.pdf_parent_ingest import ingest_parent_tender_pdf
from backend.app.services.normalizer import parse_money, parse_int, parse_float

df_master = pd.read_csv("master-tenders.csv").set_index("tender_no")

test_tenders = [
    "2025_AAI_251587_1",
    "02/SEE/NGP/CCW/NIT/2026-27",
    "02252518B",
    "0326D0043A",
    "GEM/2024/B/4523113",
    "2025_UPTCL_1060055_1",
    "2025_ONGC_257559_1",
    "2026_AAI_267728_1",
    "2025_CRIS_ELECT_11",
    "2024_IPGCL_266724_1"
]

print("=" * 80)
print("TESTING EXTRACTION FIX ACROSS TEST TENDERS")
print("=" * 80)

for t in test_tenders:
    if t not in df_master.index:
        continue
    row = df_master.loc[t]
    sf_raw = str(row["source_files"])
    folder = str(row["folder_path"]) if str(row["folder_path"]) != "nan" else "tender-documents"
    files = ast.literal_eval(sf_raw) if sf_raw.startswith("[") else [sf_raw]
    pdfs = [f for f in files if str(f).lower().endswith('.pdf')]
    if not pdfs:
        continue
    p_file = pdfs[0]
    p_path = Path(folder) / p_file
    if not p_path.exists():
        continue
        
    print(f"\n--- Tender: {t} ({p_file}) ---")
    res = ingest_parent_tender_pdf(
        job_id=f"test-fix-{t[:10]}",
        pdf_path=p_path,
        original_filename=p_path.name
    )
    
    extracted_features = {}
    for sec in res.get("infoSheetSections", []):
        for f in sec.get("fields", []):
            lbl = f.get("label", "")
            val = f.get("value")
            if any(k in lbl.lower() for k in ["turnover", "experience", "pbg", "security", "period", "tender value", "emd"]):
                extracted_features[lbl] = val
                
    for k, v in extracted_features.items():
        if v and str(v).lower() not in ("not found", "out of scope (stage 1)", "none"):
            clean_k = str(k).encode("ascii", "replace").decode("ascii")
            clean_v = str(v).encode("ascii", "replace").decode("ascii")
            print(f"  [FOUND] {clean_k}: {clean_v}")

