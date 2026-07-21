import sys
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path
from backend.app.services.pdf_parent_ingest import ingest_parent_tender_pdf

pdf_path = Path("backend/app/storage/jobs/35580348-246b-49f7-86a0-175c1bfd64ca/GAIL VRLA Jamnagar.pdf")
res = ingest_parent_tender_pdf(
    job_id="test-jamnagar-extraction",
    pdf_path=pdf_path,
    original_filename="GAIL VRLA Jamnagar.pdf"
)

sections = res.get("infoSheetSections", [])
print("=== EXTRACTED SECTIONS AND FIELDS FOR JAMNAGAR ===")
for sec in sections:
    print(f"\nSection: {sec['title']}")
    for f in sec.get("fields", []):
        if f['label'] in ["EMD Amount", "EMD Required", "PBG Percentage", "PBG Duration (Months)", "Bid Validity Period", "Reverse Auction Applicable", "Reference ID / NIT No", "Organisation"]:
            print(f"  {f['label']}: {f['value']} (Status: {f['status']}, Conf: {f['confidence']})")
