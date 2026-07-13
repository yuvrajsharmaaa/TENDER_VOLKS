from typing import Dict, Any, Optional
from backend.app.models.tender_information import TenderInformation

def map_extracted_fields_to_tender_info(
    tender_project_id: str,
    document_id: str,
    extracted_data: Dict[str, Any],
    tender_name: Optional[str] = None
) -> TenderInformation:
    """
    Maps extracted OCR field results (from extracted_fields.json) to the
    TenderInformation database model.
    """
    fields_list = extracted_data.get("extracted_fields", [])
    fields_map = {f["field_name"]: f["value"] for f in fields_list}
    confidence_map = {f["field_name"]: f.get("confidence", 0.0) for f in fields_list}
    
    # Helper to get field value if present and not "Not Found"
    def get_val(key: str) -> Optional[str]:
        val = fields_map.get(key)
        if val == "Not Found":
            return None
        return val

    def compute_parse_confidence() -> float:
        """
        Transparent fallback confidence: mean confidence across fields that
        were actually found (value != "Not Found"), weighted by how many of
        the total rule-based fields were successfully extracted. This avoids
        a hardcoded constant while remaining simple enough for an MVP.
        """
        if not fields_list:
            return 0.0
        found = [f for f in fields_list if f.get("value") != "Not Found"]
        if not found:
            return 0.0
        avg_conf = sum(f.get("confidence", 0.0) for f in found) / len(found)
        coverage = len(found) / len(fields_list)
        return round(avg_conf * coverage, 4)

    # 1. Directly extractable fields
    emd = get_val("EMD")
    fee = get_val("Tender Fee")
    est_cost = get_val("Tender Value")
    
    start_date = get_val("Bid Submission Start Date")
    end_date = get_val("bid_end_datetime") or get_val("Bid Submission End Date")
    opening_date = get_val("bid_open_datetime") or get_val("Bid Opening Date")
    prebid_date = get_val("Pre-Bid Meeting Date")
    pub_date = get_val("tender_date") or get_val("Bid Submission Start Date") # fallback
    
    nit = get_val("bid_number") or get_val("NIT No")
    t_id = get_val("bid_number") or get_val("NIT No")
    buyer_email = get_val("buyer_email")
    
    org = get_val("organisation_name") or get_val("Organisation")
    dept = get_val("department_name")
    client_name = get_val("office_name") or get_val("ministry_name")
    
    # 2. Derived fields
    past_exp_req = get_val("past_experience_required")
    past_exp_years = get_val("years_of_past_experience")
    
    tech_exp = None
    if past_exp_req or past_exp_years:
        tech_exp = f"Past Experience Required: {past_exp_req or 'N/A'}. Years of experience: {past_exp_years or 'N/A'}."

    # 3. Product / item extraction summary
    products = extracted_data.get("extracted_products", []) or []
    required_products_summary = None
    if products:
        lines = []
        for p in products:
            qty = f"{p['quantity']} {p['unit']}".strip() if p.get("quantity") else "qty unknown"
            lines.append(f"{p['product_name']} ({qty}) - {p['raw_text'][:100]}")
        required_products_summary = "; ".join(lines)

    # 4. Manual-review fields (initialized to None)
    # These fields are currently not confidently extractable by raw OCR rules
    # and will be reviewed manually later.
    security_deposit = None
    certifications_required = None
    oem_authorization = None
    technical_specifications_summary = None
    required_products_quantities = required_products_summary
    compliance_schedule = None
    pan_card_proof = None
    gst_registration_certificate = None
    turnover_audited_balance_sheets = None
    experience_certificates = None
    contact_person = None
    phone = None
    address = None
    work_delivery_location = None
    physical_submission_address = None
    liquidated_damages_percentage = None
    maximum_ld_cap = None
    warranty_period = None
    blacklisting_clauses = None

    return TenderInformation(
        tender_project_id=tender_project_id,
        document_id=document_id,
        tender_name=tender_name,
        tender_id=t_id,
        parse_confidence=compute_parse_confidence(),
        nit_number=nit,
        client=client_name,
        department=dept,
        organization=org,
        publish_date=pub_date,
        pre_bid_meeting_date=prebid_date,
        bid_submission_start_date=start_date,
        bid_submission_end_date=end_date,
        bid_opening_date=opening_date,
        emd_amount=emd,
        tender_fee=fee,
        estimated_cost=est_cost,
        security_deposit=security_deposit,
        technical_experience=tech_exp,
        financial_turnover=get_val("minimum_average_annual_turnover"),
        certifications_required=certifications_required,
        oem_authorization=oem_authorization,
        technical_specifications_summary=technical_specifications_summary,
        required_products_quantities=required_products_quantities,
        compliance_schedule=compliance_schedule,
        pan_card_proof=pan_card_proof,
        gst_registration_certificate=gst_registration_certificate,
        turnover_audited_balance_sheets=turnover_audited_balance_sheets,
        experience_certificates=experience_certificates,
        contact_person=contact_person,
        email=buyer_email,
        phone=phone,
        address=address,
        work_delivery_location=work_delivery_location,
        physical_submission_address=physical_submission_address,
        liquidated_damages_percentage=liquidated_damages_percentage,
        maximum_ld_cap=maximum_ld_cap,
        warranty_period=warranty_period,
        blacklisting_clauses=blacklisting_clauses
    )
