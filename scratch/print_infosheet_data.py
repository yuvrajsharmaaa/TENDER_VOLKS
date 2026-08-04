import sys
import logging
from pathlib import Path

getattr(sys.stdout, 'reconfigure')(encoding='utf-8')
sys.path.insert(0, ".")
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')

from backend.app.services.pdf_parent_ingest import ingest_parent_tender_pdf
from backend.app.services.tender_mapper import build_infosheet_data

pdf_path = Path("backend/app/storage/jobs/43474eaf-b191-4dab-aacb-4465917bf45d/GAIL Rajahmundry NiCd (1).pdf")
job_id = "rajahmundry_nicd_ingest_test"

# Run ingest
result = ingest_parent_tender_pdf(job_id, pdf_path, pdf_path.name)

# Extract sections
sections = result.get("sections", [])
all_pages = result.get("pages", [])

# Build infosheet data
infosheet_data = build_infosheet_data(sections, all_pages, job_id=job_id)

print("\n" + "="*95)
print("REGENERATED EXCEL INFOSHEET DATA FOR GEM/2026/B/7783843 (Rajahmundry NiCd)")
print("="*95)

keys_to_show = [
    ("Tender Title", "tender_title_display"),
    ("Reference ID / NIT No", "reference_id_display"),
    ("Authority Agency", "authority_agency_display"),
    ("EMD Amount", "emd_amount_display"),
    ("EMD Mode", "emd_mode_display"),
    ("Payment Terms Supply (%)", "payment_terms_supply_display"),
    ("Payment Terms Installation (%)", "payment_terms_installation_display"),
    ("LD Percentage per Week (%)", "ld_percentage_display"),
    ("Max LD Percentage (%)", "max_ld_percentage_display"),
    ("Courier Contact Address", "courier_address_display"),
    ("Client Contact Person (Nodal)", "client_name_1_display"),
    ("Client Contact Person (Secondary)", "client_name_2_display"),
    ("PBG Percentage (%)", "pbg_percentage_display"),
    ("PBG Duration (Months)", "pbg_duration_display"),
    ("Delivery Time Supply (Days)", "delivery_time_supply_display")
]

statuses = infosheet_data.get("_info_sheet_statuses", {})  
sources = infosheet_data.get("_info_sheet_sources", {})  

for label, key in keys_to_show:
    val = str(infosheet_data.get(key, ""))
    st = str(statuses.get(key, "N/A"))
    src = str(sources.get(key, "N/A"))
    print(f"  - {label:<35}: {val:<45} | Status: {st:<12} | Source: {src}")
