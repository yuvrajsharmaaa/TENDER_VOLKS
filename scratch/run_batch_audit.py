import sys
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path
from backend.app.services.pdf_parent_ingest import ingest_parent_tender_pdf
import json

jobs_dir = Path("backend/app/storage/jobs")
job_ids = [d.name for d in jobs_dir.iterdir() if d.is_dir() and d.name not in ["extracted_children", "pages"]]

# Fields we expect to be extracted
EXPECTED_FIELDS = [
    "tender_id", "emd_amount", "emd_required", "pbg_percentage", "pbg_duration_months",
    "bid_validity_days", "reverse_auction_enabled", "evaluation_method", "organization_name"
]

total_docs = 0
zero_failure_docs = 0
silent_missing_docs = 0
flagged_review_docs = 0
failed_fields_count = {}

print("=== STARTING BATCH AUDIT ===")
for jid in job_ids:
    pdf_files = list(jobs_dir.glob(f"{jid}/*.pdf"))
    pdf_files = [p for p in pdf_files if p.name != "original.pdf"]
    if not pdf_files:
        continue
    
    pdf_path = pdf_files[0]
    total_docs += 1
    print(f"\nAudit Document Job: {jid} | Name: {pdf_path.name}")
    
    try:
        res = ingest_parent_tender_pdf(job_id=jid, pdf_path=pdf_path, original_filename=pdf_path.name)
        sections = res.get("infoSheetSections", [])
        
        extracted_fields = {}
        missing_fields = []
        review_fields = []
        
        for sec in sections:
            for f in sec.get("fields", []):
                label = f.get("field_name", f.get("label"))
                val = f.get("value")
                status = f.get("status")
                needs_review = f.get("needs_review", False)
                
                # Check status
                if val in [None, "None", "NA", ""]:
                    missing_fields.append(label)
                    failed_fields_count[label] = failed_fields_count.get(label, 0) + 1
                elif needs_review:
                    review_fields.append(label)
                
                extracted_fields[label] = val
                
        print(f"  Missing Fields: {missing_fields}")
        print(f"  Needs Review: {review_fields}")
        
        if not missing_fields and not review_fields:
            zero_failure_docs += 1
        if missing_fields:
            silent_missing_docs += 1
        if review_fields:
            flagged_review_docs += 1
            
    except Exception as e:
        print(f"  Ingest failed: {e}")

print("\n=== AGGREGATE SUMMARY ===")
print(f"Total documents: {total_docs}")
print(f"Documents with zero extraction failures: {zero_failure_docs}")
print(f"Documents with >=1 silent missing value: {silent_missing_docs}")
print(f"Documents with >=1 flagged low-confidence value: {flagged_review_docs}")
print(f"Pattern failures per field count: {failed_fields_count}")
