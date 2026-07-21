import sys
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path
from backend.app.services.pdf_parent_ingest import ingest_parent_tender_pdf

pdf_path = Path("backend/app/storage/jobs/78e7a091-f1aa-4556-bb42-3d386d14583f/GAIL NiCd Barauni.pdf")
res = ingest_parent_tender_pdf(
    job_id="test-barauni-extraction",
    pdf_path=pdf_path,
    original_filename="GAIL NiCd Barauni.pdf"
)

sections = res.get("infoSheetSections", [])
print("=== EXTRACTED SECTIONS AND FIELDS FOR BARAUNI ===")
for sec in sections:
    print(f"\nSection: {sec['title']}")
    for f in sec.get("fields", []):
        print(f"  {f['label']}: {f['value']} (Status: {f['status']}, Conf: {f['confidence']})")
