import logging
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple
from backend.app.services.normalizer import (
    parse_money,
    parse_int,
    parse_float,
    parse_yes_no,
    parse_bool,
    parse_datetime,
    normalize_text,
    split_multi_value_field,
    parse_address_components,
    derive_presence_flag,
    detect_tender_type
)
from backend.app.services.csv_schema import CSV_COLUMNS, EVIDENCE_COLUMNS
from backend.app.services.evidence_collector import resolve_best_value, compile_evidence_log

logger = logging.getLogger(__name__)

# Field category mappings for the page scorer
FIELD_CATEGORIES = {
    "tender_id": "identity",
    "tender_value": "identity",
    "bid_validity_days": "identity",
    "physical_docs_deadline": "timing",
    "emd_amount": "emd",
    "emd_mode": "emd",
    "tender_fee_amount": "fee",
    "tender_fee_mode": "fee",
    "processing_fee_amount": "fee",
    "processing_fee_mode": "fee",
    "pbg_percentage": "guarantees",
    "pbg_duration": "guarantees",
    "sd_percentage": "guarantees",
    "sd_duration": "guarantees",
    "maf_required": "eligibility",
    "avg_annual_turnover_value": "eligibility",
    "technical_eligibility_age": "eligibility",
    "order_value_1": "eligibility",
    "order_value_2": "eligibility",
    "order_value_3": "eligibility",
    "delivery_time_supply": "delivery",
    "courier_address": "courier",
    "courier_name": "courier",
    "courier_phone": "courier"
}

def map_extraction_to_internal_schema(extracted: dict) -> dict:
    """
    Step 7A: Standardizes OCR/LLM raw extraction dict or page-aware occurrences
    into a normalized internal schema dictionary.
    """
    normalized = {}
    occurrences = extracted.get("occurrences", [])
    total_pages = extracted.get("total_pages", 16)
    
    # 1. Page-Aware Occurrences Resolution Logic
    if occurrences:
        # Group raw occurrences by field name
        by_field = {}
        for occ in occurrences:
            fn = occ.get("field_name")
            if fn:
                by_field.setdefault(fn, []).append(occ)
                
        resolved_vals = {}
        evidence_summaries = []
        normalized_occs = []
        
        for field_name, field_occs in by_field.items():
            field_type = FIELD_CATEGORIES.get(field_name, "general")
            best_occ = resolve_best_value(field_occs, field_type, total_pages)
            
            if best_occ:
                raw_val = best_occ.get("value_raw")
                # Parse raw value into standard type
                if field_name in ["tender_value", "emd_amount", "tender_fee_amount", "processing_fee_amount", "order_value_1", "order_value_2", "order_value_3", "avg_annual_turnover_value"]:
                    norm_val = parse_money(raw_val)
                elif field_name in ["bid_validity_days", "technical_eligibility_age", "pbg_duration", "sd_duration", "delivery_time_supply", "delivery_time_installation_days"]:
                    norm_val = parse_int(raw_val)
                elif field_name in ["pbg_percentage", "sd_percentage", "ld_percentage_per_week", "max_ld_percentage"]:
                    norm_val = parse_float(raw_val)
                elif field_name in ["physical_docs_deadline"]:
                    norm_val = parse_datetime(raw_val)
                elif field_name in ["delivery_time_installation_inclusive"]:
                    norm_val = parse_bool(raw_val)
                else:
                    norm_val = raw_val
                    
                resolved_vals[field_name] = norm_val
                evidence_summaries.append(f"{field_name}:p{best_occ.get('page', 1)}")
                
                # Attach normalized value for the Layer 2 log
                for occ in field_occs:
                    occ["normalized_value"] = norm_val
                    normalized_occs.append(occ)
                    
        # Update raw values with resolved normalized values
        extracted = {**extracted, **resolved_vals}
        normalized["occurrences"] = normalized_occs
        normalized["source_page_evidence_summary"] = "|".join(evidence_summaries)
    else:
        # Fallback to key-value maps
        normalized["occurrences"] = []
        normalized["source_page_evidence_summary"] = ""

    # 2. Key Mapping & Normalization
    # Alternate list formats
    if "extracted_fields" in extracted and isinstance(extracted["extracted_fields"], list):
        flat_data = {}
        for field in extracted["extracted_fields"]:
            if isinstance(field, dict) and "field_name" in field and "value" in field:
                flat_data[field["field_name"]] = field["value"]
        if "EMD" in flat_data: flat_data["emd_amount"] = flat_data["EMD"]
        if "Tender Fee" in flat_data: flat_data["tender_fee_amount"] = flat_data["Tender Fee"]
        if "Tender Value" in flat_data: flat_data["tender_value"] = flat_data["Tender Value"]
        if "Bid Submission End Date" in flat_data: flat_data["physical_docs_deadline"] = flat_data["Bid Submission End Date"]
        extracted = {**extracted, **flat_data}

    # Standardize values
    normalized["bid_number"] = extracted.get("bid_number") or extracted.get("tender_id")
    normalized["tender_value"] = parse_money(extracted.get("tender_value") or extracted.get("estimated_value"))
    normalized["bid_validity_days"] = parse_int(extracted.get("bid_validity_days"))
    normalized["deadline_dt"] = parse_datetime(
        extracted.get("physical_docs_deadline") or 
        extracted.get("bid_end_datetime") or 
        extracted.get("bid_end_date")
    )
    
    # EMD Details
    normalized["emd_amount"] = parse_money(extracted.get("emd_amount"))
    normalized["emd_mode_raw"] = extracted.get("emd_mode_text") or extracted.get("emd_mode")
    
    # Tender Fee Details
    normalized["fee_amount"] = parse_money(extracted.get("tender_fee_amount") or extracted.get("tender_fee"))
    normalized["fee_mode_raw"] = extracted.get("tender_fee_mode_text") or extracted.get("tender_fee_mode")
    
    # Processing Fee Details
    normalized["processing_fee_amount"] = parse_money(extracted.get("processing_fee_amount") or extracted.get("processing_fee"))
    normalized["processing_fee_mode_raw"] = extracted.get("processing_fee_mode_text") or extracted.get("processing_fee_mode")
    
    # PBG / Security Deposit Details
    normalized["pbg_pct"] = parse_float(extracted.get("pbg_percentage"))
    normalized["pbg_dur"] = parse_int(extracted.get("pbg_duration"))
    normalized["pbg_mode"] = extracted.get("pbg_mode")
    normalized["sd_pct"] = parse_float(extracted.get("sd_percentage"))
    normalized["sd_dur"] = parse_int(extracted.get("sd_duration"))
    normalized["sd_mode"] = extracted.get("sd_mode")
    
    # Liquidated Damages Details
    normalized["ld_pct_week"] = parse_float(extracted.get("ld_percentage_per_week"))
    normalized["max_ld_pct"] = parse_float(extracted.get("max_ld_percentage"))
    
    # Eligibility Details
    normalized["maf_req_raw"] = extracted.get("maf_required")
    normalized["experience_years"] = parse_int(extracted.get("technical_eligibility_age"))
    normalized["oem_experience"] = extracted.get("oem_experience")
    normalized["turnover_val"] = parse_money(extracted.get("avg_annual_turnover_value") or extracted.get("turnover"))
    normalized["turnover_type"] = extracted.get("avg_annual_turnover_type")
    
    normalized["working_capital_value"] = parse_money(extracted.get("working_capital_value"))
    normalized["working_capital_type"] = extracted.get("working_capital_type")
    normalized["solvency_certificate_value"] = parse_money(extracted.get("solvency_certificate_value"))
    normalized["solvency_certificate_type"] = extracted.get("solvency_certificate_type")
    normalized["net_worth_value"] = parse_money(extracted.get("net_worth_value"))
    normalized["net_worth_type"] = extracted.get("net_worth_type")
    
    normalized["order_value_1"] = parse_money(extracted.get("order_value_1"))
    normalized["order_value_2"] = parse_money(extracted.get("order_value_2"))
    normalized["order_value_3"] = parse_money(extracted.get("order_value_3"))
    normalized["work_value_type"] = extracted.get("work_value_type")
    normalized["custom_rules"] = normalize_text(extracted.get("custom_eligibility_criteria"))
    
    # Delivery Details
    normalized["delivery_time_supply"] = parse_int(extracted.get("delivery_time_supply"))
    normalized["delivery_time_installation_days"] = parse_int(extracted.get("delivery_time_installation_days"))
    normalized["delivery_time_installation_inclusive"] = parse_bool(extracted.get("delivery_time_installation_inclusive"))
    normalized["payment_terms_supply"] = parse_money(extracted.get("payment_terms_supply"))
    normalized["payment_terms_installation"] = parse_money(extracted.get("payment_terms_installation"))
    
    # Courier Details
    normalized["courier_address"] = extracted.get("courier_address")
    normalized["courier_name"] = extracted.get("courier_name")
    normalized["courier_phone"] = extracted.get("courier_phone")
    normalized["org_name"] = extracted.get("organization_name") or extracted.get("authority_name")
    normalized["ra_status"] = extracted.get("reverse_auction_applicable")
    
    return normalized

def map_internal_to_db_payload(data: dict, tender_id: int) -> dict:
    """
    Step 7B: Maps internal schema fields dict into a database-ready payload.
    """
    emd_req = "Yes" if data.get("emd_amount") and data.get("emd_amount") > 0 else derive_presence_flag(data.get("emd_amount"))
    fee_req = "Yes" if data.get("fee_amount") and data.get("fee_amount") > 0 else derive_presence_flag(data.get("fee_amount"))
    proc_req = "Yes" if data.get("processing_fee_amount") and data.get("processing_fee_amount") > 0 else derive_presence_flag(data.get("processing_fee_amount"))
    
    pbg_req = "Yes" if data.get("pbg_pct") and data.get("pbg_pct") > 0 else derive_presence_flag(data.get("pbg_pct"))
    sd_req = "Yes" if data.get("sd_pct") and data.get("sd_pct") > 0 else derive_presence_flag(data.get("sd_pct"))
    ld_req = "Yes" if data.get("max_ld_pct") and data.get("max_ld_pct") > 0 else derive_presence_flag(data.get("max_ld_pct"))
    
    maf_req = parse_yes_no(data.get("custom_rules"), ["OEM authorization", "maf", "manufacturer authorization"]) if data.get("custom_rules") else "No"
    if data.get("maf_req_raw"):
        maf_req = parse_yes_no(str(data.get("maf_req_raw")), ["yes", "required", "true", "req"])
        
    addr1, addr2, pin = parse_address_components(data.get("courier_address"))
    
    db_payload = {
        "tender_id": tender_id,
        "tender_value": data.get("tender_value"),
        "emd_required": emd_req,
        "emd_amount": data.get("emd_amount"),
        "emd_mode": split_multi_value_field(data.get("emd_mode_raw")),
        "tender_fee_required": fee_req,
        "tender_fee_amount": data.get("fee_amount"),
        "tender_fee_mode": split_multi_value_field(data.get("fee_mode_raw")),
        "processing_fee_required": proc_req,
        "processing_fee_amount": data.get("processing_fee_amount"),
        "processing_fee_mode": split_multi_value_field(data.get("processing_fee_mode_raw")),
        "bid_validity_days": data.get("bid_validity_days"),
        "physical_docs_deadline": data.get("deadline_dt"),
        "physical_docs_required": derive_presence_flag(data.get("deadline_dt")),
        
        # Security Deposit & Performance Guarantee
        "pbg_required": pbg_req,
        "pbg_percentage": data.get("pbg_pct"),
        "pbg_duration": data.get("pbg_dur"),
        "pbg_mode": data.get("pbg_mode"),
        "sd_required": sd_req,
        "sd_percentage": data.get("sd_pct"),
        "sd_duration": data.get("sd_dur"),
        "sd_mode": data.get("sd_mode"),
        
        # Liquidated Damages (LD)
        "ld_required": ld_req,
        "ld_percentage_per_week": data.get("ld_pct_week"),
        "max_ld_percentage": data.get("max_ld_pct"),
        
        # Eligibility
        "maf_required": maf_req,
        "technical_eligibility_age": data.get("experience_years"),
        "oem_experience": data.get("oem_experience"),
        "avg_annual_turnover_value": data.get("turnover_val"),
        "avg_annual_turnover_type": data.get("turnover_type") or "Bidder",
        
        "working_capital_value": data.get("working_capital_value"),
        "working_capital_type": data.get("working_capital_type"),
        "solvency_certificate_value": data.get("solvency_certificate_value"),
        "solvency_certificate_type": data.get("solvency_certificate_type"),
        "net_worth_value": data.get("net_worth_value"),
        "net_worth_type": data.get("net_worth_type"),
        
        "order_value_1": data.get("order_value_1"),
        "order_value_2": data.get("order_value_2"),
        "order_value_3": data.get("order_value_3"),
        "work_value_type": data.get("work_value_type"),
        "custom_eligibility_criteria": data.get("custom_rules"),
        
        # Delivery & Timeline
        "delivery_time_supply": data.get("delivery_time_supply"),
        "delivery_time_installation_days": data.get("delivery_time_installation_days"),
        "delivery_time_installation_inclusive": data.get("delivery_time_installation_inclusive"),
        "payment_terms_supply": data.get("payment_terms_supply"),
        "payment_terms_installation": data.get("payment_terms_installation"),
        
        # Courier Details
        "courier_name": data.get("courier_name"),
        "courier_phone": data.get("courier_phone"),
        "courier_address": data.get("courier_address"),
        "courier_address_line_1": addr1,
        "courier_address_line_2": addr2,
        "courier_pincode": pin,
        
        # Presence flags
        "client_details_present": derive_presence_flag(data.get("org_name")),
        "courier_details_present": derive_presence_flag(data.get("courier_address")),
        "reverse_auction_applicable": data.get("ra_status"),
        
        # Technical Evaluation / manual fields default to None (stamp later)
        "te_recommendation": None,
        "te_rejection_reason": None,
        "te_rejection_remarks": None,
        "te_rejection_proof": None,
        "te_final_remark": None,
        "customer_in_contact": None,
        "commercial_evaluation": None,
        "physical_doc_type": None,
        "physical_docs_type": None,
        "courier_city": None,
        "courier_state": None,
        
        "source_page_evidence_summary": data.get("source_page_evidence_summary")
    }
    
    return db_payload

def map_internal_to_summary_csv_row(data: dict) -> dict:
    """
    Step 7C: Serializes DB payload values into flat string mappings matching
    the exact ordered fields CSV_COLUMNS list.
    """
    csv_row = {}
    for col in CSV_COLUMNS:
        val = data.get(col)
        if isinstance(val, str) and val.startswith('[') and val.endswith(']'):
            import ast
            try:
                val = ast.literal_eval(val)
            except BaseException:
                pass
                
        if val is None:
            csv_row[col] = ""
        elif isinstance(val, list):
            csv_row[col] = "|".join([str(item) for item in val if item])
        else:
            csv_row[col] = str(val)
    return csv_row

def map_internal_to_evidence_rows(data: dict) -> List[dict]:
    """
    Step 7D: Converts occurrences logged inside the internal dictionary
    into Layer 2 evidence rows list formatted for DictWriter.
    """
    raw_occurrences = data.get("occurrences", [])
    tender_id = data.get("bid_number") or data.get("tender_id") or "unknown"
    return compile_evidence_log(raw_occurrences, tender_id)

def map_occurrences_to_tender_payloads(
    occurrences: List[Dict[str, Any]], 
    tender_id: int, 
    total_pages: int = 16
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """
    Groups raw occurrences by field_name, resolves the best weighted occurrence,
    and returns db_payload and evidence rows.
    """
    extracted_data = {
        "occurrences": occurrences,
        "total_pages": total_pages,
        "tender_id": tender_id
    }
    internal = map_extraction_to_internal_schema(extracted_data)
    db_payload = map_internal_to_db_payload(internal, tender_id)
    evidence_rows = map_internal_to_evidence_rows(internal)
    return db_payload, evidence_rows

def map_extraction_to_tender_information(extracted: dict, tender_id: int) -> dict:
    """
    Combined old entry point for backward compatibility.
    """
    normalized = map_extraction_to_internal_schema(extracted)
    return map_internal_to_db_payload(normalized, tender_id)


def build_infosheet_data(sections: List[Dict[str, Any]], page_texts: List[Dict[str, Any]] = None) -> Dict[str, str]:
    """
    Flattens the extracted sections and runs regex match fallbacks on the raw page texts
    to resolve all Visual Layout variables defined in INFOSHEET_DATA_KEYS.
    """
    field_lookup = {}
    for sec in sections:
        for f in sec.get("fields", []):
            label = f.get("label", "").strip()
            val = f.get("value", "")
            status = f.get("status", "")
            if status != "missing" and val is not None and val != "":
                field_lookup[label] = str(val).strip()

    # Get full text if page_texts is provided
    full_text = ""
    if page_texts:
        full_text = "\n".join([p.get("text", "") for p in page_texts])

    # Helper to extract using regex from full_text
    import re
    def extract_regex(pattern, default="NA"):
        if not full_text:
            return default
            
        # Intercept legacy pattern and rewrite to robust tabular pattern
        suffix = r"[:\-\s]+([^\n]+)"
        if pattern.endswith(suffix):
            label = pattern[:-len(suffix)]
            # Match inline with colon/dash OR at most 2 spaces, stopping at large gaps
            # If there's a colon/dash, we allow any character. If only spaces, the value must start with alphanumeric.
            m1 = re.search(rf"{label}[ \t]*[:\-][ \t]*((?:(?!\s{{2,}})[^\n])+)", full_text, re.IGNORECASE)
            if not m1:
                m1 = re.search(rf"{label}[ \t]{{1,2}}([A-Za-z0-9₹Rs](?:(?!\s{{2,}})[^\n]){{0,24}})(?:\s{{2,}}|\n|$)", full_text, re.IGNORECASE)
            if m1:
                return m1.group(1).strip()
            # Match next line ONLY if label is the only thing on the line
            m2 = re.search(rf"^[ \t]*{label}[ \t]*\n[ \t]*((?:(?!\s{{2,}})[^\n])+)", full_text, re.IGNORECASE | re.MULTILINE)
            if m2:
                return m2.group(1).strip()
            return default
                
        # Fallback to original
        m = re.search(pattern, full_text, re.IGNORECASE)
        if m:
            return m.group(1).strip()
        return default

    def resolve_field(keys, regex_pattern, default="NA"):
        if isinstance(keys, str):
            keys = [keys]
        for key in keys:
            val = field_lookup.get(key)
            if val and val != "NA" and val != "Not Found":
                return val
        return extract_regex(regex_pattern, default)

    # 1. Organization
    organization = resolve_field(["Authority Agency", "Organisation"], r"Organization[:\-\s]+([^\n]+)")
    if not organization or organization == "NA":
        organization = extract_regex(r"Organisation Name[:\-\s]+([^\n]+)")

    # 2. Tender Name
    tender_name = resolve_field("Tender Name / Title", r"Tender Name[:\-\s]+([^\n]+)")

    # 3. Tender ID
    tender_id_display = resolve_field("Reference ID / NIT No", r"Tender No[:\-\s]+([^\n]+)")

    # 4. Website
    website = resolve_field("Website", r"Website[:\-\s]+([^\n]+)")

    # 5. Bid Due Date and Time
    bid_due_date_time = resolve_field("Bid Submission Deadline", r"Due Date & Time[:\-\s]+([^\n]+)")

    # 6. Recommendation by TE
    te_recommendation_display = resolve_field("Recommendation by TE", r"Recommendation[:\-\s]+([^\n]+)")
    if te_recommendation_display == "Yes — Recommended":
        te_recommendation_display = "YES"
    elif te_recommendation_display == "No — Rejected":
        te_recommendation_display = "NO"

    # 7. Reason
    te_rejection_reason_display = resolve_field("Reason", r"Reason[:\-\s]+([^\n]+)")

    # 8. Processing Fees
    processing_fee_amount_display = resolve_field("Processing Fee Amount", r"Processing Fee Amount[:\-\s]+([^\n]+)")
    # 9. Processing Fees (in form of)
    processing_fee_mode_display = resolve_field("Processing Fee Mode", r"Processing Fee Mode[:\-\s]+([^\n]+)")

    # 10. Tender Fees
    tender_fee_amount_display = field_lookup.get("Tender Fee")
    if not tender_fee_amount_display or tender_fee_amount_display == "NA":
        tender_fee_amount_display = extract_regex(r"Tender Fee Amount[:\-\s]+([^\n]+)")
    if not tender_fee_amount_display or tender_fee_amount_display == "NA":
        tender_fee_amount_display = extract_regex(r"Tender Fee[:\-\s]+([^\n]+)")
    if tender_fee_amount_display != "NA" and not re.search(r"\d|no|nil|exempt", tender_fee_amount_display, re.IGNORECASE):
        tender_fee_amount_display = "NA"

    # 11. Tender Fees (in form of)
    tender_fee_mode_display = resolve_field("Tender Fee Mode", r"Tender Fee Mode[:\-\s]+([^\n]+)")

    # 12. EMD
    emd_amount_display = field_lookup.get("EMD Amount")
    if not emd_amount_display or emd_amount_display == "NA":
        emd_amount_display = extract_regex(r"EMD Amount[:\-\s]+([^\n]+)")
    if not emd_amount_display or emd_amount_display == "NA":
        emd_amount_display = extract_regex(r"EMD[:\-\s]+([^\n]+)")
    if emd_amount_display != "NA" and not re.search(r"\d|no|nil|exempt", emd_amount_display, re.IGNORECASE):
        emd_amount_display = "NA"

    # 13. EMD required
    emd_required_display = resolve_field("EMD Required", r"EMD Required[:\-\s]+([^\n]+)")

    # 14. Tender Value (GST Inclusive)
    tender_value_display = resolve_field("Estimated Tender Value", r"Tender Value \(GST Inclusive\)[:\-\s]+([^\n]+)")

    # 15. EMD (in form of)
    emd_mode_display = resolve_field("EMD Mode", r"EMD Mode[:\-\s]+([^\n]+)")

    # 16. Bid Validity
    bid_validity_days_display = resolve_field("Bid Validity Period", r"Bid Validity \(Days\)[:\-\s]+([^\n]+)")
    if bid_validity_days_display and bid_validity_days_display != "NA":
        clean_num = re.sub(r"\D", "", str(bid_validity_days_display))
        if clean_num:
            bid_validity_days_display = f"{clean_num} Days"

    # 17. Commercial Evaluation
    commercial_evaluation_display = resolve_field(["Commercial Evaluation", "Commercial Evaluation Type"], r"Commercial Evaluation Type[:\-\s]+([^\n]+)")

    # 18. RA Applicable
    reverse_auction_applicable_display = resolve_field("Reverse Auction Applicable", r"Reverse Auction Applicable[:\-\s]+([^\n]+)")

    # 19. MAF required
    maf_required_display = resolve_field("MAF Required", r"MAF Required[:\-\s]+([^\n]+)")

    # 20. Delivery Time (Supply/Total)
    delivery_time_supply_display = resolve_field(["Delivery Time Supply (Days)", "Period of Work"], r"Delivery Time Supply \(Days\)[:\-\s]+([^\n]+)")

    # 21. Delivery Time (Installation)
    delivery_time_installation_display = resolve_field("Delivery Time Installation (Days)", r"Delivery Time Installation \(Days\)[:\-\s]+([^\n]+)")

    # 22. PBG (in form of)
    pbg_mode_display = resolve_field("PBG Mode", r"PBG Mode[:\-\s]+([^\n]+)")

    # 23. Payment Terms (Supply)
    payment_terms_supply_display = resolve_field("Payment Terms Supply", r"Payment Terms Supply \((?:%|\w+)\)[:\-\s]+([^\n]+)")
    if payment_terms_supply_display == "NA":
        payment_terms_supply_display = extract_regex(r"Payment Terms Supply[:\-\s]+([^\n]+)")

    # 24. Payment Terms (Installation)
    payment_terms_installation_display = resolve_field("Payment Terms Installation", r"Payment Terms Installation \((?:%|\w+)\)[:\-\s]+([^\n]+)")
    if payment_terms_installation_display == "NA":
        payment_terms_installation_display = extract_regex(r"Payment Terms Installation[:\-\s]+([^\n]+)")

    # 25. SD (in form of)
    sd_mode_display = resolve_field("Security Deposit Mode", r"Security Deposit Mode[:\-\s]+([^\n]+)")

    # 26. LD/PRS %age (per week)
    ld_percentage_display = resolve_field("LD Percentage Per Week", r"LD Percentage Per Week[:\-\s]+([^\n]+)")

    # 27. Max LD %age
    max_ld_percentage_display = resolve_field("Max LD Percentage", r"Max LD Percentage[:\-\s]+([^\n]+)")

    # 28. PBG %age
    pbg_percentage_display = resolve_field("PBG Percentage", r"PBG Percentage[:\-\s]+([^\n]+)")

    # 29. Security Deposit
    sd_percentage_display = resolve_field("Security Deposit %", r"Security Deposit %[:\-\s]+([^\n]+)")

    # 30. PBG Duration
    pbg_duration_display = resolve_field("PBG Duration (Months)", r"PBG Duration \(Months\)[:\-\s]+([^\n]+)")

    # 31. SD Duration
    sd_duration_display = resolve_field("SD Duration (Months)", r"SD Duration \(Months\)[:\-\s]+([^\n]+)")

    # 32. Physical Docs Submission Required
    physical_docs_required_display = resolve_field("Physical Docs Required", r"Physical Docs Required[:\-\s]+([^\n]+)")

    # 33. Physical Docs Submission Deadline
    physical_docs_deadline_display = resolve_field("Physical Docs Deadline", r"Physical Docs Deadline[:\-\s]+([^\n]+)")

    # 34. Age (in yrs)
    experience_years_val = field_lookup.get("Minimum Experience (Years)")
    if experience_years_val and experience_years_val != "NA":
        age_in_yrs = experience_years_val
    else:
        age_in_yrs = extract_regex(r"Eligibility Criterion \(Years\)[:\-\s]+([^\n]+)")

    # 35. 3 Works Value
    order_value_1_display = resolve_field("3 Works Value", r"3 Works Value[:\-\s]+([^\n]+)")

    # 36. Annual Avg Turnover
    avg_annual_turnover_type_display = resolve_field("Avg Annual Turnover Type", r"Avg Annual Turnover Type[:\-\s]+([^\n]+)")
    avg_annual_turnover_value_display = field_lookup.get("Annual Turnover Limit") or field_lookup.get("Annual Avg Turnover")
    if not avg_annual_turnover_value_display or avg_annual_turnover_value_display == "NA":
        avg_annual_turnover_value_display = extract_regex(r"Avg Annual Turnover Value[:\-\s]+([^\n]+)")

    # 37. 2 Works Value
    order_value_2_display = resolve_field("2 Works Value", r"2 Works Value[:\-\s]+([^\n]+)")

    # 38. Working Capital
    working_capital_type_display = resolve_field("Working Capital Type", r"Working Capital Type[:\-\s]+([^\n]+)")
    working_capital_value_display = resolve_field(["Working Capital Value", "Working Capital"], r"Working Capital Value[:\-\s]+([^\n]+)")

    # 39. 1 work Value
    order_value_3_display = resolve_field("1 work Value", r"1 work Value[:\-\s]+([^\n]+)")

    # 40. Net Worth
    net_worth_type_display = resolve_field("Net Worth Type", r"Net Worth Type[:\-\s]+([^\n]+)")
    net_worth_value_display = resolve_field(["Net Worth Value", "Net Worth"], r"Net Worth Value[:\-\s]+([^\n]+)")

    # 41. PO selected for Technical Eligibility
    po_selected_documents_display = resolve_field("PO selected for Technical Eligibility", r"PO selected for Technical Eligibility[:\-\s]+([^\n]+)")

    # 42. Solvency Certificate
    solvency_certificate_type_display = resolve_field("Solvency Certificate Type", r"Solvency Certificate Type[:\-\s]+([^\n]+)")
    solvency_certificate_value_display = resolve_field(["Solvency Certificate Value", "Solvency Certificate"], r"Solvency Certificate Value[:\-\s]+([^\n]+)")

    # Page 2
    # 43. PQC Documents
    pqc_docs = extract_regex(r"PQR Selection[:\-\s]+([^\n]+)")
    if pqc_docs == "—" or pqc_docs == "NA":
        pqc_matches = []
        for line in full_text.split("\n"):
            if any(k in line.lower() for k in ["leoch", "ve turnover", "ve all generic"]):
                pqc_matches.append(line.strip())
        if pqc_matches:
            pqc_docs = ", ".join(pqc_matches)
    pqc_documents_display = pqc_docs

    # 44. Documents for Commercial Eligibility
    commercial_eligibility_documents_display = extract_regex(r"Documents for Commercial Eligibility[:\-\s]+([^\n]+)")

    # 45. Client details
    client_match = re.search(r"Requested Details[:\-\s]+([^\n]+)[:\-\s]+([^\n]+)[:\-\s]+([^\n]+)", full_text, re.IGNORECASE)
    if client_match:
        client_name_1_display = client_match.group(1).strip()
        client_email_1_display = client_match.group(3).strip()
        client_phone_1_display = client_match.group(2).strip()
    else:
        client_name_1_display = "NA"
        client_email_1_display = "NA"
        client_phone_1_display = "NA"

    client_name_2_display = "NA"
    client_email_2_display = "NA"
    client_phone_2_display = "NA"
    client_name_3_display = "NA"
    client_email_3_display = "NA"
    client_phone_3_display = "NA"

    # 46. Docs Submitted
    doc_1_display = "NA"
    doc_2_display = "NA"
    doc_3_display = "NA"
    doc_4_display = "NA"
    doc_5_display = "NA"
    doc_6_display = "NA"
    doc_7_display = "NA"
    doc_8_display = "NA"
    doc_9_display = "NA"

    extra_docs_match = re.search(r"Extra Documents \(\d+\)[:\-\s]+([^\n]+)(?:\n\s*([^\n]+))?(?:\n\s*([^\n]+))?(?:\n\s*([^\n]+))?(?:\n\s*([^\n]+))?(?:\n\s*([^\n]+))?", full_text, re.IGNORECASE)
    if extra_docs_match:
        doc_1_display = extra_docs_match.group(1).strip() if extra_docs_match.group(1) else "NA"
        doc_2_display = extra_docs_match.group(2).strip() if extra_docs_match.group(2) else "NA"
        doc_3_display = extra_docs_match.group(3).strip() if extra_docs_match.group(3) else "NA"
        doc_4_display = extra_docs_match.group(4).strip() if extra_docs_match.group(4) else "NA"
        doc_5_display = extra_docs_match.group(5).strip() if extra_docs_match.group(5) else "NA"
        doc_6_display = extra_docs_match.group(6).strip() if extra_docs_match.group(6) else "NA"

    # Courier Delivery Address
    courier_addr_match = re.search(r"Address \(Legacy\)[:\-\s]+([^\n]+(?:\n\s*[^\n]+)?)[:\-\s]+(?:Physical Docs Required|Physical Docs Submission)", full_text, re.IGNORECASE)
    if courier_addr_match:
        courier_address_display = courier_addr_match.group(1).strip().replace("\n", " ")
    else:
        courier_address_display = "NA"

    courier_provider_display = "NA"
    courier_docket_no_display = "NA"
    courier_delivery_time_display = "NA"
    docket_slip_upload_display = "NA"
    physical_docs_uploaded_display = "NA"

    # Format and map GeM required documents list
    docs_list_raw = field_lookup.get("required_documents") or field_lookup.get("Document required from seller")
    if docs_list_raw:
        import ast
        parsed_docs = []
        try:
            if isinstance(docs_list_raw, str) and docs_list_raw.startswith("["):
                parsed_docs = ast.literal_eval(docs_list_raw)
            elif isinstance(docs_list_raw, list):
                parsed_docs = docs_list_raw
        except Exception:
            pass
        if not parsed_docs and isinstance(docs_list_raw, str):
            parsed_docs = [d.strip() for d in docs_list_raw.split(",") if d.strip()]
            
        for idx, doc in enumerate(parsed_docs[:9]):
            doc_name = doc.get("document_name") if isinstance(doc, dict) else str(doc)
            if idx == 0: doc_1_display = doc_name
            elif idx == 1: doc_2_display = doc_name
            elif idx == 2: doc_3_display = doc_name
            elif idx == 3: doc_4_display = doc_name
            elif idx == 4: doc_5_display = doc_name
            elif idx == 5: doc_6_display = doc_name
            elif idx == 6: doc_7_display = doc_name
            elif idx == 7: doc_8_display = doc_name
            elif idx == 8: doc_9_display = doc_name

    # Policies displays
    mse_relaxation_display = field_lookup.get("mse_relaxation_experience_turnover") or field_lookup.get("MSE Relaxation for Years of Experience and Turnover") or "NA"
    startup_relaxation_display = field_lookup.get("startup_relaxation_experience_turnover") or field_lookup.get("Startup Relaxation for Years Of Experience and Turnover") or "NA"
    
    mse_pref = field_lookup.get("mse_purchase_preference") or field_lookup.get("MSE Purchase Preference") or "NA"
    mse_band = field_lookup.get("mse_preference_price_band_percent") or field_lookup.get("Purchase Preference to MSE OEMs available upto price within L1+X%")
    mse_qty = field_lookup.get("mse_preference_max_qty_percent") or field_lookup.get("Maximum Percentage of Bid quantity for MSE purchase preference")
    if mse_pref != "NA" and (mse_band or mse_qty):
        mse_preference_display = f"{mse_pref} (Band: {mse_band or 'NA'}, Qty: {mse_qty or 'NA'})"
    else:
        mse_preference_display = mse_pref
        
    mii_pref = field_lookup.get("mii_purchase_preference") or field_lookup.get("MII Purchase Preference") or "NA"
    mii_reason = field_lookup.get("mii_non_applicability_reason") or field_lookup.get("Brief Description of the Approval Granted by Competent Authority")
    if mii_pref != "NA" and mii_reason:
        mii_preference_display = f"{mii_pref} (Reason: {mii_reason})"
    else:
        mii_preference_display = mii_pref

    # Pre-bid display
    pre_bid_display = "NA"
    pre_bid_raw = field_lookup.get("pre_bid_meeting") or field_lookup.get("Pre-Bid Date and Time") or field_lookup.get("Pre-Bid Venue")
    if pre_bid_raw:
        pre_bid_display = str(pre_bid_raw).replace("\n", " ").strip()

    # Schedules display
    schedule_1_details_display = "NA"
    schedule_2_details_display = "NA"
    schedule_3_details_display = "NA"
    
    sch_raw = field_lookup.get("schedules")
    if sch_raw:
        import ast
        schedules_list = []
        try:
            if isinstance(sch_raw, str) and sch_raw.startswith("["):
                schedules_list = ast.literal_eval(sch_raw)
            elif isinstance(sch_raw, list):
                schedules_list = sch_raw
        except Exception:
            pass
            
        for idx, sch in enumerate(schedules_list[:3]):
            sch_num = sch.get("schedule_number", idx+1)
            desc = sch.get("item_description", "NA")
            qty = sch.get("quantity", "NA")
            days = sch.get("delivery_days", "NA")
            specs = sch.get("technical_specs", {})
            specs_str = ", ".join(f"{k}: {v}" for k, v in specs.items()) if isinstance(specs, dict) else str(specs)
            detail = f"Sch {sch_num} | Qty: {qty} | Delivery: {days} days | {desc} | Specs: {specs_str}"
            
            if idx == 0: schedule_1_details_display = detail
            elif idx == 1: schedule_2_details_display = detail
            elif idx == 2: schedule_3_details_display = detail

    return {
        "organization": organization,
        "tender_name": tender_name,
        "tender_id_display": tender_id_display,
        "website": website,
        "bid_due_date_time": bid_due_date_time,
        "te_recommendation_display": te_recommendation_display,
        "te_rejection_reason_display": te_rejection_reason_display,
        "processing_fee_amount_display": processing_fee_amount_display,
        "processing_fee_mode_display": processing_fee_mode_display,
        "tender_fee_amount_display": tender_fee_amount_display,
        "tender_fee_mode_display": tender_fee_mode_display,
        "emd_amount_display": emd_amount_display,
        "emd_required_display": emd_required_display,
        "tender_value_display": tender_value_display,
        "emd_mode_display": emd_mode_display,
        "bid_validity_days_display": bid_validity_days_display,
        "commercial_evaluation_display": commercial_evaluation_display,
        "reverse_auction_applicable_display": reverse_auction_applicable_display,
        "maf_required_display": maf_required_display,
        "delivery_time_supply_display": delivery_time_supply_display,
        "delivery_time_installation_display": delivery_time_installation_display,
        "pbg_mode_display": pbg_mode_display,
        "payment_terms_supply_display": payment_terms_supply_display,
        "payment_terms_installation_display": payment_terms_installation_display,
        "sd_mode_display": sd_mode_display,
        "ld_percentage_display": ld_percentage_display,
        "max_ld_percentage_display": max_ld_percentage_display,
        "pbg_percentage_display": pbg_percentage_display,
        "sd_percentage_display": sd_percentage_display,
        "pbg_duration_display": pbg_duration_display,
        "sd_duration_display": sd_duration_display,
        "physical_docs_required_display": physical_docs_required_display,
        "physical_docs_deadline_display": physical_docs_deadline_display,
        "order_value_1_display": order_value_1_display,
        "avg_annual_turnover_type_display": avg_annual_turnover_type_display,
        "avg_annual_turnover_value_display": avg_annual_turnover_value_display,
        "order_value_2_display": order_value_2_display,
        "working_capital_type_display": working_capital_type_display,
        "working_capital_value_display": working_capital_value_display,
        "order_value_3_display": order_value_3_display,
        "net_worth_type_display": net_worth_type_display,
        "net_worth_value_display": net_worth_value_display,
        "po_selected_documents_display": po_selected_documents_display,
        "solvency_certificate_type_display": solvency_certificate_type_display,
        "solvency_certificate_value_display": solvency_certificate_value_display,
        "commercial_eligibility_documents_display": commercial_eligibility_documents_display,
        "client_name_1_display": client_name_1_display,
        "client_email_1_display": client_email_1_display,
        "client_phone_1_display": client_phone_1_display,
        "client_name_2_display": client_name_2_display,
        "client_email_2_display": client_email_2_display,
        "client_phone_2_display": client_phone_2_display,
        "client_name_3_display": client_name_3_display,
        "client_email_3_display": client_email_3_display,
        "client_phone_3_display": client_phone_3_display,
        "doc_1_display": doc_1_display,
        "doc_2_display": doc_2_display,
        "doc_3_display": doc_3_display,
        "doc_4_display": doc_4_display,
        "doc_5_display": doc_5_display,
        "doc_6_display": doc_6_display,
        "doc_7_display": doc_7_display,
        "doc_8_display": doc_8_display,
        "doc_9_display": doc_9_display,
        "courier_address_display": courier_address_display,
        "courier_provider_display": courier_provider_display,
        "courier_docket_no_display": courier_docket_no_display,
        "courier_delivery_time_display": courier_delivery_time_display,
        "docket_slip_upload_display": docket_slip_upload_display,
        "physical_docs_uploaded_display": physical_docs_uploaded_display,
        "mse_relaxation_display": mse_relaxation_display,
        "startup_relaxation_display": startup_relaxation_display,
        "mse_preference_display": mse_preference_display,
        "mii_preference_display": mii_preference_display,
        "pre_bid_meeting_display": pre_bid_display,
        "schedule_1_details_display": schedule_1_details_display,
        "schedule_2_details_display": schedule_2_details_display,
        "schedule_3_details_display": schedule_3_details_display,
    }

