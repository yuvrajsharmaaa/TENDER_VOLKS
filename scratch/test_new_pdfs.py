import sys
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path
from backend.app.services.pdf_parent_ingest import ingest_parent_tender_pdf

# Test two different new GeM PDFs that haven't been fixed yet
test_jobs = [
    ("6b266bb1-6cd4-4db8-96b2-61d488f66122", "GeM-Bidding-8667425.pdf_1765009740_1937252.pdf"),
    ("6e007511-7837-407a-85ef-83b48aead20f", "GeM-Bidding-7724454.pdf_1748685463_3605671.pdf"),
]

FIELDS_OF_INTEREST = [
    "EMD Amount", "EMD Required", "PBG Percentage", "PBG Duration (Months)",
    "Bid Validity Period", "Reverse Auction Applicable", "Reference ID / NIT No",
    "Organisation", "Commercial Evaluation Type"
]

for job_id, filename in test_jobs:
    pdf_path = Path(f"backend/app/storage/jobs/{job_id}/{filename}")
    if not pdf_path.exists():
        print(f"\n[SKIP] PDF not found: {pdf_path}")
        continue
    
    print(f"\n{'='*60}")
    print(f"JOB: {job_id}")
    print(f"PDF: {filename}")
    print(f"{'='*60}")
    
    try:
        res = ingest_parent_tender_pdf(
            job_id=f"test-{job_id[:8]}",
            pdf_path=pdf_path,
            original_filename=filename
        )
        sections = res.get("infoSheetSections", [])
        for sec in sections:
            for f in sec.get("fields", []):
                if f['label'] in FIELDS_OF_INTEREST:
                    status_icon = "✓" if f['status'] == "extracted" else "✗"
                    print(f"  {status_icon} {f['label']}: {f['value']} ({f['status']})")
    except Exception as e:
        print(f"  ERROR: {e}")
