import sys
import logging
from pathlib import Path

sys.path.insert(0, ".")
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')

from backend.app.services.pdf_parent_ingest import ingest_parent_tender_pdf

pdf_path = Path("backend/app/storage/jobs/7d129d6b-d232-44c1-bffc-d71435ce3319/GAIL Jaipur MI-CD Tender.pdf")
print("Starting end-to-end ingest for:", pdf_path)

if pdf_path.exists():
    result = ingest_parent_tender_pdf("test_job_jaipur", pdf_path, pdf_path.name)
    print("\n--- INGEST RESULT SUMMARY ---")
    print("Tender Title:", result.get("title"))
    print("Confidence:", result.get("confidence"))
    print("Extracted Sections Count:", len(result.get("sections", [])))
