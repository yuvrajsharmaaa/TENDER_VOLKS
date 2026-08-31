import os
import sys
sys.path.insert(0, os.getcwd())

from dotenv import load_dotenv
load_dotenv(".env.dev")

from backend.app.services.pdf_parent_ingest import ingest_parent_tender_pdf

from backend.app.services.tender_mapper import map_extraction_to_tender_information
from backend.app.services.normalizer import parse_money

from pathlib import Path

pdf_path = Path("tender-documents/1779357063078_1_gen_terms___condition_hvac.pdf")
res = ingest_parent_tender_pdf(
    job_id="test-clean-extract",
    pdf_path=pdf_path,
    original_filename=pdf_path.name
)


print("Top level resolved tenderValue:", res.get("tenderValue"))
print("Top level resolved emdAmount:", res.get("emdAmount"))
print("Top level resolved tenderFee:", res.get("tenderFee"))

for sec in res.get("infoSheetSections", []):
    for f in sec.get("fields", []):
        lbl = f.get("label", "")
        if any(k in lbl.lower() for k in ["value", "emd", "fee", "turnover", "period"]):
            print(f"  - {lbl}: {f.get('value')} (status: {f.get('status')})")
