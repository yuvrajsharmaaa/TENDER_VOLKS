import csv
from pathlib import Path
from backend.app.models.tender_information import TenderInformation

CSV_COLUMNS = [
    # 1. Basic Information
    "tender_name",
    "tender_id",
    "nit_number",
    "client",
    "department",
    "organization",
    # 2. Dates and Timeline
    "publish_date",
    "pre_bid_meeting_date",
    "bid_submission_start_date",
    "bid_submission_end_date",
    "bid_opening_date",
    # 3. Pricing
    "emd_amount",
    "tender_fee",
    "estimated_cost",
    "security_deposit",
    # 4. Eligibility
    "technical_experience",
    "financial_turnover",
    "certifications_required",
    "oem_authorization",
    # 5. Technical Requirements
    "technical_specifications_summary",
    "required_products_quantities",
    "compliance_schedule",
    # 6. Checklist Documents
    "pan_card_proof",
    "gst_registration_certificate",
    "turnover_audited_balance_sheets",
    "experience_certificates",
    # 7. Contacts
    "contact_person",
    "email",
    "phone",
    "address",
    # 8. Delivery and Address
    "work_delivery_location",
    "physical_submission_address",
    # 9. Risk / Commercial Terms
    "liquidated_damages_percentage",
    "maximum_ld_cap",
    "warranty_period",
    "blacklisting_clauses"
]

def export_tender_info_to_csv(info: TenderInformation, filepath: Path) -> None:
    """
    Exports a TenderInformation database model record into a CSV file
    preserving the exact column order matching target field inventory.
    """
    filepath.parent.mkdir(parents=True, exist_ok=True)
    
    # Prepare row data
    row_data = {}
    for col in CSV_COLUMNS:
        row_data[col] = getattr(info, col, None)
        
    with open(filepath, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerow(row_data)
