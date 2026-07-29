import json
import sys
from pathlib import Path
from backend.app.services.pdf_parent_ingest import ingest_parent_tender_pdf
from backend.app.services.tender_mapper import build_infosheet_data

sys.stdout.reconfigure(encoding='utf-8')

job_id = "526f4449-2e3b-4e7a-9c53-9a91d4c1b617"
job_dir = Path(fr"c:\Users\Asus\Desktop\Tender_Volks\main\backend\app\storage\jobs\{job_id}")
pdf_path = job_dir / "original.pdf"

# Run ingest_parent_tender_pdf to re-process with fixed ATC selection and mapping
result = ingest_parent_tender_pdf(
    job_id=job_id,
    pdf_path=pdf_path,
    original_filename="GAIL NiCd Ranchi.pdf"
)

sections = result.get("infoSheetSections", [])
pages = result.get("rawTextPages", [])

infosheet_data = build_infosheet_data(sections, pages, job_id=job_id)

print("\n--- REPROCESSED RANCHI INFOSHEET DATA FIELDS ---")
fields_to_check = [
    "pbg_mode_display", "pbg_percentage_display", "pbg_required_display",
    "sd_mode_display", "sd_percentage_display", "sd_required_display",
    "payment_terms_supply_display", "payment_terms_installation_display",
    "courier_address_display", "client_name_1_display", "client_name_2_display",
    "order_value_1_display", "order_value_2_display", "order_value_3_display",
    "custom_eligibility_criteria_display"
]

for k in fields_to_check:
    print(f"  {k}: {infosheet_data.get(k)!r}")
