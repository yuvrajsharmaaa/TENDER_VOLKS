import sys
import logging
from pathlib import Path

sys.path.insert(0, ".")
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')

from backend.app.services.pdf_parent_ingest import ingest_parent_tender_pdf
from backend.app.services.tender_mapper import map_extraction_to_internal_schema

pdf_path = Path("backend/app/storage/jobs/43474eaf-b191-4dab-aacb-4465917bf45d/GAIL Rajahmundry NiCd (1).pdf")
job_id = "rajahmundry_nicd_ingest_test"
result = ingest_parent_tender_pdf(job_id, pdf_path, pdf_path.name)

# Map to internal schema
mapped_data = map_extraction_to_internal_schema(result)

print("\n" + "="*80)
print("FINAL REGENERATED EXCEL INFOSHEET FIELDS FOR RAJAHMUNDRY (GEM/2026/B/7783843)")
print("="*80)
target_keys = [
    "tender_id",
    "reference_id",
    "authority_agency",
    "emd_amount_display",
    "emd_mode_display",
    "payment_terms_supply_display",
    "payment_terms_installation_display",
    "ld_percentage_display",
    "max_ld_percentage_display",
    "courier_address_display",
    "client_name_1_display",
    "client_name_2_display",
    "pbg_percentage_display",
    "pbg_duration_display",
    "delivery_time_supply_display"
]

for k in target_keys:
    val = mapped_data.get(k)
    status = mapped_data.get("_info_sheet_statuses", {}).get(k, "N/A")
    source = mapped_data.get("_info_sheet_sources", {}).get(k, "N/A")
    print(f"  - {k:<35}: {val!r} | status={status} | source={source}")
