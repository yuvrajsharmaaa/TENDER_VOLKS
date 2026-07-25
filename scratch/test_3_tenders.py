import sys
import os
import logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding='utf-8')

# Quiet noisy loggers
logging.getLogger("ocr").setLevel(logging.WARNING)
logging.getLogger("tender_ocr").setLevel(logging.WARNING)
logging.getLogger("backend").setLevel(logging.WARNING)

from pathlib import Path
from backend.app.services.pdf_parent_ingest import ingest_parent_tender_pdf

tenders = [
    ("Visakhapatnam", "b385b369-0f80-4ec1-a28a-651ae88b546f", "GAIL Visakhapatnam B&BC VRLA.pdf"),
    ("Ranchi", "3b8770e5-6453-48f6-bf8c-2f3b49999d74", "GAIL Ranchi SMF (1).pdf"),
    ("Jaipur", "0c9996e2-3c51-4041-b159-fd5505894f05", "GAIL Jaipur AMC.pdf")
]

fields_to_check = [
    "maf_required_display",
    "processing_fee_amount_display",
    "processing_fee_mode_display",
    "tender_fee_amount_display",
    "tender_fee_mode_display",
    "emd_required_display",
    "emd_amount_display",
    "emd_mode_display",
    "payment_terms_supply_display",
    "payment_terms_installation_display",
    "commercial_evaluation_display",
    "reverse_auction_applicable_display",
    "delivery_time_supply_display",
    "delivery_time_installation_display",
    "pbg_required_display",
    "pbg_mode_display",
    "pbg_percentage_display",
    "pbg_duration_display",
    "sd_percentage_display",
    "sd_mode_display",
    "sd_duration_display",
    "ld_percentage_display",
    "max_ld_percentage_display",
    "custom_eligibility_criteria_display",
    "avg_annual_turnover_value_display",
    "avg_annual_turnover_type_display",
    "working_capital_value_display",
    "working_capital_type_display",
    "solvency_certificate_value_display",
    "solvency_certificate_type_display",
    "net_worth_value_display",
    "net_worth_type_display",
    "courier_address_display",
    "physical_docs_required_display",
    "physical_docs_deadline_display",
    "client_name_1_display",
    "client_phone_1_display",
    "client_email_1_display"
]

def run_test():
    results = {}
    for name, jid, filename in tenders:
        pdf_path = Path(f"backend/app/storage/jobs/{jid}/{filename}")
        print(f"\n========================================================")
        print(f"TENDER: {name} (Job: {jid})")
        print(f"========================================================")
        try:
            res = ingest_parent_tender_pdf(job_id=jid, pdf_path=pdf_path, original_filename=filename)
            sections = res.get("infoSheetSections", [])
            page_texts = res.get("rawTextPages", [])
            from backend.app.services.tender_mapper import build_infosheet_data
            info_data = build_infosheet_data(sections, page_texts, job_id=jid)
            
            results[name] = info_data
            for fk in fields_to_check:
                val = info_data.get(fk, "MISSING_KEY")
                src = info_data.get("_info_sheet_sources", {}).get(fk, "unknown")
                print(f"  {fk:38s}: {str(val):45s} (src: {src})")
        except Exception as e:
            print(f"ERROR processing {name}: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    run_test()
