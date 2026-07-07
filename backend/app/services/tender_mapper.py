import logging
from typing import Dict, Any, Optional, List
from backend.app.services.normalizer import (
    parse_money,
    parse_int,
    parse_float,
    parse_yes_no,
    parse_datetime,
    normalize_text,
    split_multi_value_field,
    parse_address_components,
    derive_presence_flag,
    detect_tender_type
)
from backend.app.services.csv_schema import CSV_COLUMNS

logger = logging.getLogger(__name__)

def map_extraction_to_internal_schema(extracted: dict) -> dict:
    """
    Standardizes OCR/LLM raw extraction keys into a normalized schema dictionary.
    Safe and null-friendly.
    """
    normalized = {}
    
    # Handle list format from some OCR output models
    if "extracted_fields" in extracted and isinstance(extracted["extracted_fields"], list):
        flat_data = {}
        for field in extracted["extracted_fields"]:
            if isinstance(field, dict) and "field_name" in field and "value" in field:
                flat_data[field["field_name"]] = field["value"]
                
        # Proactively map common alternate list keys to expected names
        if "EMD" in flat_data:
            flat_data["emd_amount"] = flat_data["EMD"]
        if "Tender Fee" in flat_data:
            flat_data["tender_fee_amount"] = flat_data["Tender Fee"]
        if "Tender Value" in flat_data:
            flat_data["tender_value"] = flat_data["Tender Value"]
        if "Bid Submission End Date" in flat_data:
            flat_data["physical_docs_deadline"] = flat_data["Bid Submission End Date"]
        if "bid_end_datetime" in flat_data:
            flat_data["physical_docs_deadline"] = flat_data["bid_end_datetime"]
        if "Organisation" in flat_data:
            flat_data["authority_name"] = flat_data["Organisation"]
            
        extracted = {**extracted, **flat_data}

    # Standardize values
    normalized["bid_number"] = extracted.get("bid_number") or extracted.get("tender_id")
    normalized["tender_value"] = parse_money(extracted.get("tender_value") or extracted.get("estimated_value"))
    normalized["bid_validity_days"] = parse_int(extracted.get("bid_validity_days"))
    
    # Deadline mapping
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
    normalized["delivery_time_installation_inclusive"] = extracted.get("delivery_time_installation_inclusive")
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
    Maps normalized internal fields dictionary into a database-ready payload
    matching database table columns exactly. Applies all derivation rules.
    """
    # Derive required flags
    emd_req = "Yes" if data.get("emd_amount") and data.get("emd_amount") > 0 else derive_presence_flag(data.get("emd_amount"))
    fee_req = "Yes" if data.get("fee_amount") and data.get("fee_amount") > 0 else derive_presence_flag(data.get("fee_amount"))
    proc_req = "Yes" if data.get("processing_fee_amount") and data.get("processing_fee_amount") > 0 else derive_presence_flag(data.get("processing_fee_amount"))
    
    pbg_req = "Yes" if data.get("pbg_pct") and data.get("pbg_pct") > 0 else derive_presence_flag(data.get("pbg_pct"))
    sd_req = "Yes" if data.get("sd_pct") and data.get("sd_pct") > 0 else derive_presence_flag(data.get("sd_pct"))
    ld_req = "Yes" if data.get("max_ld_pct") and data.get("max_ld_pct") > 0 else derive_presence_flag(data.get("max_ld_pct"))
    
    # Derived eligibility checks
    maf_req = parse_yes_no(data.get("custom_rules"), ["OEM authorization", "maf", "manufacturer authorization"]) if data.get("custom_rules") else "No"
    if data.get("maf_req_raw"):
        maf_req = parse_yes_no(str(data.get("maf_req_raw")), ["yes", "required", "y"])
        
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
        "pbg_percentage": data.get("pbg_percentage") or data.get("pbg_pct"),
        "pbg_duration": data.get("pbg_dur"),
        "pbg_mode": data.get("pbg_mode"),
        "sd_required": sd_req,
        "sd_percentage": data.get("sd_percentage") or data.get("sd_pct"),
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
        "courier_state": None
    }
    
    return db_payload

def map_internal_to_csv_row(data: dict) -> dict:
    """
    Step 7C: Serializes DB payload values into flat string mappings matching
    the exact ordered fields CSV_COLUMNS list.
    """
    csv_row = {}
    for col in CSV_COLUMNS:
        val = data.get(col)
        if val is None:
            csv_row[col] = ""
        elif isinstance(val, list):
            csv_row[col] = "|".join([str(item) for item in val if item])
        else:
            csv_row[col] = str(val)
    return csv_row

def map_extraction_to_tender_information(extracted: dict, tender_id: int) -> dict:
    """
    Combined old entry point for backward compatibility.
    Maps raw extraction to database dictionary.
    """
    normalized = map_extraction_to_internal_schema(extracted)
    return map_internal_to_db_payload(normalized, tender_id)
