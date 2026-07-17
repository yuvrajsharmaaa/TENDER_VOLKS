import sys
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path
from backend.app.services.pdf_parent_ingest import ingest_parent_tender_pdf
import json

job_id = "6b266bb1-6cd4-4db8-96b2-61d488f66122"
pdf_path = Path(f"backend/app/storage/jobs/{job_id}/GeM-Bidding-8667425.pdf_1765009740_1937252.pdf")
res = ingest_parent_tender_pdf(job_id=job_id, pdf_path=pdf_path, original_filename=pdf_path.name)

print("TENDER RESOLVED KEYS:")
for k, v in res.items():
    if k not in ["rawTextPages", "infoSheetSections"]:
        print(f"  {k}: {repr(v)}")

print("\nINFOSHEET SECTIONS & FIELDS:")
for sec in res.get("infoSheetSections", []):
    print(f"=== Section: {sec.get('name')} ===")
    for f in sec.get("fields", []):
        print(f"  Label: {f['label']:<35} | Value: {repr(f['value']):<30} | Status: {f['status']:<10} | Review: {f.get('needs_review')}")
