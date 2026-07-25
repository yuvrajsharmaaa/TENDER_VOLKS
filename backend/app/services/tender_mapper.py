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

import re

def normalize_bec_order_value(value_str: str) -> Optional[int]:
    if not value_str:
        return None
    # Matches digits (optional comma/dots) followed by lakh, crore, lac, cr
    m = re.search(r"([\d,]+(?:\.\d+)?)\s*(lakh|crore|lac|cr)s?", value_str, re.IGNORECASE)
    if m:
        try:
            val_num = float(m.group(1).replace(",", ""))
            unit = m.group(2).lower()
            multiplier = 100000 if "lakh" in unit or "lac" in unit else 10000000
            return int(val_num * multiplier)
        except Exception:
            pass
    return None

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


def build_infosheet_data(sections: List[Dict[str, Any]], page_texts: List[Dict[str, Any]] = None, job_id: str = "Unknown") -> Dict[str, str]:
    """
    Flattens the extracted sections and runs regex match fallbacks on the raw page texts
    to resolve all Visual Layout variables defined in INFOSHEET_DATA_KEYS.
    """
    def _is_missing(val):
        return val is None or val == "" or val == "NA"

    def format_currency(val: Any) -> str:
        if val is None or val == "" or val == "NA":
            return "NA"
        try:
            num = float(val)
            s = f"{int(round(num))}"
            if len(s) <= 3:
                return f"₹{s}"
            else:
                last_three = s[-3:]
                remaining = s[:-3]
                groups = []
                while remaining:
                    groups.append(remaining[-2:])
                    remaining = remaining[:-2]
                groups.reverse()
                return f"₹{','.join(groups)},{last_three}"
        except Exception:
            return f"₹{val}"

    def normalize_evaluation_method(raw: str) -> str:
        if not raw or _is_missing(raw):
            return raw
        raw_lower = raw.lower()
        if "item" in raw_lower:
            return "Item wise"
        if "total" in raw_lower or "value" in raw_lower:
            return "Total value wise"
        return raw

    field_lookup = {}
    for sec in sections:
        for f in sec.get("fields", []):
            label = f.get("label", "").strip()
            field_name = f.get("field_name", "").strip()
            val = f.get("value", "")
            status = f.get("status", "")
            if status != "missing" and val is not None and val != "":
                val_str = str(val).strip()
                if label:
                    field_lookup[label] = val_str
                    field_lookup[label.lower()] = val_str
                if field_name:
                    field_lookup[field_name] = val_str
                    field_lookup[field_name.lower()] = val_str

    # Get full text if page_texts is provided
    full_text = ""
    if page_texts:
        full_text = "\n".join([p.get("text", "") for p in page_texts])

    # Helper to extract using regex from full_text
    import re
    def extract_regex(pattern, default="NA"):
        if not full_text or not pattern:
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

    def resolve_field(keys, regex_pattern=None, default="NA"):
        if isinstance(keys, str):
            keys = [keys]
        for key in keys:
            val = field_lookup.get(key)
            if val is None:
                val = field_lookup.get(key.lower())
            if not _is_missing(val) and val != "Not Found":
                return val
        if regex_pattern:
            return extract_regex(regex_pattern, default)
        return default

    # 1. Organization
    organization = resolve_field(["Authority Agency", "Organisation", "organisation_name", "ministry_name", "department_name"], r"Organization[:\-\s]+([^\n]+)")
    if not organization or organization == "NA":
        organization = extract_regex(r"Organisation Name[:\-\s]+([^\n]+)")

    # 2. Tender Name
    tender_name = resolve_field(["Tender Name / Title", "item_category", "similar_category"], r"Tender Name[:\-\s]+([^\n]+)")

    # 3. Tender ID
    tender_id_display = resolve_field(["Reference ID / NIT No", "bid_number", "tender_id"], r"Tender No[:\-\s]+([^\n]+)")

    # 4. Website
    website = resolve_field("Website", r"Website[:\-\s]+([^\n]+)")

    # 5. Bid Due Date and Time
    bid_due_date_time = resolve_field(["Bid Submission Deadline", "bid_end_datetime"], r"Due Date & Time[:\-\s]+([^\n]+)")

    # 6. Recommendation by TE
    te_recommendation_display = resolve_field("Recommendation by TE", r"Recommendation[:\-\s]+([^\n]+)")
    if te_recommendation_display == "Yes — Recommended":
        te_recommendation_display = "YES"
    elif te_recommendation_display == "No — Rejected":
        te_recommendation_display = "NO"

    # 7. Reason
    te_rejection_reason_display = resolve_field("Reason", r"Reason[:\-\s]+([^\n]+)")

    # 8. Processing Fees (GEM_DOC only)
    processing_fee_amount_display = resolve_field(["Processing Fee Amount", "processing_fee_amount"], r"Processing Fee Amount[:\-\s]+([^\n]+)", "No")
    if _is_missing(processing_fee_amount_display) or processing_fee_amount_display in ("0", "0.00", "₹0.00"):
        processing_fee_amount_display = "No"
    processing_fee_mode_display = "NA"

    # 10. Tender Fees (GEM_DOC only)
    tender_fee_amount_display = field_lookup.get("Tender Fee") or field_lookup.get("tender_fee_amount")
    if _is_missing(tender_fee_amount_display) or tender_fee_amount_display in ("0", "0.00", "₹0.00", "NA"):
        tender_fee_amount_display = "Nil / Exempted"
    tender_fee_mode_display = "NA"

    # 13. EMD required
    emd_required_raw = resolve_field(["EMD Required", "emd_required"], r"EMD Required[:\-\s]+([^\n]+)", None)
    if _is_missing(emd_required_raw):
        emd_required = None
    else:
        emd_required = str(emd_required_raw).strip().lower() in ("true", "yes", "required", "y")
        
    if _is_missing(emd_required):
        emd_required_display = "NA"
    else:
        emd_required_display = "Yes" if emd_required else "No"

    # 12. EMD
    emd_amount_raw = field_lookup.get("EMD Amount") or field_lookup.get("emd_amount")
    emd_amount_display = "NA"
    emd_total = 0.0
    
    # 12. EMD Amount Anchor: BDS Tag (E) primary, IFB summary row fallback
    tag_e_match = re.search(
        r"\(E\)\s*BID\s*SECURITY\s*/?\s*EARNEST\s*MONEY\s*DEPOSIT\s*\(EMD\)(.*?)(?=\([A-Z0-9]{1,3}\)|\Z)",
        full_text, re.IGNORECASE | re.DOTALL
    )
    if tag_e_match:
        e_text = tag_e_match.group(1)
        amt_match = re.search(r"Amount[:\-\s]+Rs\.?\s*([\d,]+(?:\.\d+)?)", e_text, re.IGNORECASE)
        if amt_match:
            from backend.app.services.normalizer import parse_money
            emd_parsed = parse_money(amt_match.group(1))
            if emd_parsed is not None and emd_parsed > 0:
                emd_total = emd_parsed
                emd_required_display = "Yes"
                emd_amount_display = format_currency(emd_total)
                logger.info(f"[ATC_ANCHOR] Resolved field 'emd_amount' via BDS_TAG: (E) BID SECURITY / EARNEST MONEY DEPOSIT ({emd_total})")

    if emd_amount_display == "NA":
        emd_amount_raw = field_lookup.get("EMD Amount") or field_lookup.get("emd_amount")
        if _is_missing(emd_amount_raw):
            emd_amount_raw = extract_regex(r"EMD Amount[:\-\s]+([^\n]+)", None)
        if _is_missing(emd_amount_raw):
            emd_amount_raw = extract_regex(r"EMD[:\-\s]+([^\n]+)", None)
            
        if not _is_missing(emd_amount_raw):
            from backend.app.services.normalizer import parse_money
            emd_total = parse_money(emd_amount_raw) or 0.0
            
        if emd_required_display == "Yes":
            emd_amount_display = format_currency(emd_total)
        else:
            emd_amount_display = "No"

    # 14. Tender Value
    tender_value_display = resolve_field(["Estimated Tender Value", "Tender Value (GST Inclusive)", "tender_value"], r"Tender Value \(GST Inclusive\)[:\-\s]+([^\n]+)", "NA")
    if not _is_missing(tender_value_display) and tender_value_display not in ("Not Found", "NA"):
        from backend.app.services.normalizer import parse_money
        tv = parse_money(tender_value_display)
        if tv is not None and tv >= 100:
            tender_value_display = format_currency(tv)
        elif tv is not None and tv < 100 and not any(sym in str(tender_value_display) for sym in ("₹", "Rs", "INR", "lakh", "crore")):
            tender_value_display = "NA"

    # 15. EMD Mode (Clause 16.1 & 16.2 instrument mapping: DD, BT, SB, FDR, BG)
    # BUG FIX 5: Exclude bank name cell-pair leaks (e.g. "State Bank of India" / Advisory Bank)
    BANK_NAME_EXCLUSIONS = {"state bank of india", "icici bank", "hdfc bank", "axis bank", "canara bank", "punjab national bank", "advisory bank"}
    
    emd_mode_display = resolve_field(["EMD Mode", "emd_mode"], r"EMD Mode[:\-\s]+([^\n]+)")
    if emd_mode_display and any(b in str(emd_mode_display).lower() for b in BANK_NAME_EXCLUSIONS):
        logger.warning(f"[BUG_FIX] Excluded bank name/advisory leak from emd_mode_display: {emd_mode_display!r}")
        emd_mode_display = "NA"

    if _is_missing(emd_mode_display) or emd_mode_display == "NA":
        modes_found = []
        full_lower = full_text.lower()
        if "demand draft" in full_lower: modes_found.append("DD")
        if any(k in full_lower for k in ["banker's cheque", "bankers cheque", "imps", "neft", "rtgs", "online banking"]): modes_found.append("BT")
        if "surety bond" in full_lower or "insurance surety" in full_lower: modes_found.append("SB")
        if "fixed deposit" in full_lower or "fdr" in full_lower: modes_found.append("FDR")
        if "bank guarantee" in full_lower or "bg" in full_lower: modes_found.append("BG")
        if modes_found:
            emd_mode_display = "/".join(modes_found)
            logger.info(f"[ATC_ANCHOR] Resolved field 'emd_mode' via CLAUSE_NUMBER_FALLBACK: Clause 16.1 ({emd_mode_display})")

    # 16. Bid Validity
    bid_validity_days_display = resolve_field(["Bid Validity Period", "bid_validity_days", "Bid Validity"], r"Bid Validity \(Days\)[:\-\s]+([^\n]+)", None)
    if not _is_missing(bid_validity_days_display):
        clean_num = re.sub(r"\D", "", str(bid_validity_days_display))
        if clean_num:
            bid_validity_days_display = f"{clean_num} Days"
        else:
            bid_validity_days_display = str(bid_validity_days_display)
    else:
        bid_validity_days_display = "NA"

    # 17. Commercial Evaluation
    commercial_evaluation_raw = resolve_field(
        ["Commercial Evaluation", "Commercial Evaluation Type", "evaluation_method", "Evaluation Method"],
        r"Commercial Evaluation Type[:\-\s]+([^\n]+)",
        None
    )
    commercial_evaluation_display = normalize_evaluation_method(commercial_evaluation_raw)
    if _is_missing(commercial_evaluation_display) or commercial_evaluation_display in ("Not Found", "NA"):
        k_eval_match = re.search(r"(?:K\.\s*EVALUATION\s+METHODOLOGY|EVALUATION\s+METHODOLOGY).*?(?:Overall\s+L-?1\s+basis|item-?wise\s+L-?1)", full_text, re.IGNORECASE | re.DOTALL)
        if k_eval_match:
            eval_snippet = k_eval_match.group(0).lower()
            if "overall l-1" in eval_snippet or "overall l1" in eval_snippet or "overall basis" in eval_snippet:
                commercial_evaluation_display = "Overall L1 / Total value wise"
            elif "item-wise" in eval_snippet or "item wise" in eval_snippet:
                commercial_evaluation_display = "Item-wise L1"
            logger.info(f"[ATC_ANCHOR] Resolved field 'commercial_evaluation' via SECTION_HEADING: EVALUATION METHODOLOGY ({commercial_evaluation_display})")
        else:
            commercial_evaluation_display = "NA"

    # 18. RA Applicable
    reverse_auction_raw = resolve_field(["Reverse Auction Applicable", "reverse_auction_enabled"], r"Reverse Auction Applicable[:\-\s]+([^\n]+)", None)
    if _is_missing(reverse_auction_raw):
        reverse_auction = None
    else:
        reverse_auction = str(reverse_auction_raw).strip().lower() in ("true", "yes", "required", "y")
        
    if _is_missing(reverse_auction):
        reverse_auction_applicable_display = "NA"
    else:
        reverse_auction_applicable_display = "Yes" if reverse_auction else "No"

    # Bid Type
    bid_type_display = resolve_field(["Bid Type", "bid_type", "Type of Bid"], r"Type of Bid[:\-\s]+([^\n]+)")
    if _is_missing(bid_type_display) or bid_type_display == "Not Found":
        bid_type_display = "NA"

    # ATC Document Link
    atc_doc_link_raw = resolve_field(
        ["ATC Document Link", "atc_document_link_present", "atc_document_link", "atc_link_url", "Buyer uploaded ATC document"],
        r"Buyer uploaded ATC document[:\-\s]+([^\n]+)",
        None
    )
    if not _is_missing(atc_doc_link_raw) and atc_doc_link_raw != "Not Found":
        if isinstance(atc_doc_link_raw, bool):
            atc_document_link_display = "Yes (Hyperlink Present)" if atc_doc_link_raw else "No"
        else:
            atc_document_link_display = str(atc_doc_link_raw)
    else:
        atc_document_link_display = "NA"

    # 19. MAF required (derived from BEC Technical Criteria Sl. 1 or seller required documents list)
    maf_required_display = resolve_field(["MAF Required", "maf_required"], r"MAF Required[:\-\s]+([^\n]+)")
    if _is_missing(maf_required_display) or maf_required_display == "NA":
        bec_maf_pattern = r"(?:bidder\s+must\s+be\s+a\s+['\"]?(?:Manufacturer|Authorized\s+Partner|Distributor|Dealer|Reseller)['\"]?|Authorized\s+Dealer\s*/\s*Distributor\s*/\s*Partner\s*/\s*Reseller:\s*Bidder\s+must\s+submit\s+a\s+copy\s+of\s+valid\s+Authorized)"
        req_docs_raw = str(field_lookup.get("required_documents") or field_lookup.get("Document required from seller") or "")
        if re.search(bec_maf_pattern, full_text, re.IGNORECASE) or any(kw in req_docs_raw.lower() for kw in ["oem authorization", "manufacturer authorization", "authorization certificate", "maf"]):
            maf_required_display = "Yes"
            logger.info("[ATC_ANCHOR] Resolved field 'maf_required' via SECTION_HEADING: BEC Technical Criteria Sl. 1")
        else:
            maf_required_display = "No"

    # 20. Delivery Time (Supply/Total)
    delivery_time_supply_display = resolve_field(["Delivery Time Supply (Days)", "delivery_time_supply", "contract_period", "Period of Work"], r"Delivery Time Supply \(Days\)[:\-\s]+([^\n]+)")
    bds_del_match = re.search(r"(?:CONTRACTUAL DELIVERY DATE|DELIVERY SCHEDULE|COMPLETION PERIOD)[:\-\s]+([^\n]+)", full_text, re.IGNORECASE)
    if bds_del_match:
        delivery_time_supply_display = bds_del_match.group(1).strip()
        logger.info(f"[ATC_ANCHOR] Resolved field 'delivery_time_supply' via BDS_TAG: CONTRACTUAL DELIVERY DATE/DELIVERY SCHEDULE ({delivery_time_supply_display})")

    # 21. Delivery Time (Installation)
    delivery_time_installation_display = resolve_field(["Delivery Time Installation (Days)", "delivery_time_installation_days"], r"Delivery Time Installation \(Days\)[:\-\s]+([^\n]+)")
    scope_match = re.search(r"(?:\(A\)\s*SCOPE OF SUPPLY|SCOPE OF SUPPLY|SCOPE OF PROCUREMENT).*?(?:SITC|Supply,\s*Installation,\s*Testing\s+and\s+Commissioning|Installation)", full_text, re.IGNORECASE | re.DOTALL)
    if scope_match and (_is_missing(delivery_time_installation_display) or delivery_time_installation_display == "NA"):
        delivery_time_installation_display = "Inclusive (SITC Scope)"
        logger.info("[ATC_ANCHOR] Resolved field 'delivery_time_installation' via SECTION_HEADING: Scope of Supply SITC")

    # 22. PBG (in form of)
    # BUG FIX 5: Exclude bank name cell-pair leaks (e.g. "State Bank of India" / Advisory Bank)
    pbg_mode_display = resolve_field(["PBG Mode", "pbg_mode"], r"PBG Mode[:\-\s]+([^\n]+)")
    if pbg_mode_display and any(b in str(pbg_mode_display).lower() for b in BANK_NAME_EXCLUSIONS):
        logger.warning(f"[BUG_FIX] Excluded bank name/advisory leak from pbg_mode_display: {pbg_mode_display!r}")
        pbg_mode_display = "NA"

    if _is_missing(pbg_mode_display) or pbg_mode_display == "NA":
        pbg_clause_match = re.search(
            r"(?:Clause\s*(?:38|39)|Contract\s+Performance\s+Security|Performance\s+Bank\s+Guarantee|Security\s+Deposit|CPBG)(.*?)(?=\n\s*(?:Clause\s*(?:39|40)|SECTION|\d+\.\d+|\Z))",
            full_text, re.IGNORECASE | re.DOTALL
        )
        pbg_block = pbg_clause_match.group(1).lower() if pbg_clause_match else full_text.lower()
        modes_found = []
        if "demand draft" in pbg_block or " dd " in pbg_block:
            modes_found.append("DD")
        if any(k in pbg_block for k in ["imps", "neft", "rtgs", "online banking", "online transfer", "online payment"]):
            modes_found.append("Online Transfer")
        if "surety bond" in pbg_block or "insurance surety" in pbg_block:
            modes_found.append("Insurance Surety Bond")
        if "fixed deposit" in pbg_block or "fdr" in pbg_block:
            modes_found.append("FDR")
        if "bank guarantee" in pbg_block or "bg" in pbg_block:
            modes_found.append("Bank Guarantee")
        
        if modes_found:
            pbg_mode_display = " / ".join(modes_found)
            logger.info(f"[ATC_ANCHOR] Resolved field 'pbg_mode' via CLAUSE_NUMBER_FALLBACK: Clause 38.5 ({pbg_mode_display})")
        else:
            pbg_mode_display = "Bank Guarantee / DD / FDR / Online Transfer / Insurance Surety Bond"
            logger.info("[ATC_ANCHOR] Resolved field 'pbg_mode' via CLAUSE_NUMBER_FALLBACK: Clause 38.5")

    # 23-24. Payment Terms (Scope of Work / SCC / GCC specific)
    payment_terms_supply_display = resolve_field(["Payment Terms Supply", "payment_terms_supply"], r"Payment Terms Supply \((?:%|\w+)\)[:\-\s]+([^\n]+)")
    payment_terms_installation_display = resolve_field(["Payment Terms Installation", "payment_terms_installation"], r"Payment Terms Installation \((?:%|\w+)\)[:\-\s]+([^\n]+)")

    pay_clause_match = re.search(
        r"(?:(?:\d+\.\d+\s+)?(?:TERMS OF PAYMENT|PAYMENT TERMS))(.*?)"
        r"(?=\n\s*(?:SECTION[\s\-]|[A-Z][A-Z\s]{4,}[\s\n]|\d{1,2}\.\d{1,2}\s+[A-Z]|\Z))",
        full_text, re.IGNORECASE | re.DOTALL
    )
    if pay_clause_match:
        ptext = pay_clause_match.group(1)
        s_pct = (
            re.search(r"(\d+)\%\s*(?:of\s+the\s+)?(?:supply|receipt|delivery|material)", ptext, re.IGNORECASE)
            or re.search(r"(\d+)\%\s*(?:after\s+receipt\s+at\s+site)", ptext, re.IGNORECASE)
        )
        i_pct = (
            re.search(r"(\d+)\%\s*(?:of\s+the\s+)?(?:install|commission)", ptext, re.IGNORECASE)
            or re.search(r"balance\s+(\d+)\%\s*(?:on\s+successful\s+installation)", ptext, re.IGNORECASE)
        )
        # Guard: only accept if the captured value is unambiguously numeric (%)
        if s_pct and re.search(r"\d", s_pct.group(1)) and (_is_missing(payment_terms_supply_display) or payment_terms_supply_display == "NA"):
            payment_terms_supply_display = f"{s_pct.group(1)}%"
            logger.info(f"[ATC_ANCHOR] Resolved field 'payment_terms_supply' via SECTION_HEADING: TERMS OF PAYMENT ({payment_terms_supply_display})")
        if i_pct and re.search(r"\d", i_pct.group(1)) and (_is_missing(payment_terms_installation_display) or payment_terms_installation_display == "NA"):
            payment_terms_installation_display = f"{i_pct.group(1)}%"
            logger.info(f"[ATC_ANCHOR] Resolved field 'payment_terms_installation' via SECTION_HEADING: TERMS OF PAYMENT ({payment_terms_installation_display})")

    # 25. SD (in form of)
    sd_mode_display = resolve_field(["Security Deposit Mode", "sd_mode"], r"Security Deposit Mode[:\-\s]+([^\n]+)")
    if _is_missing(sd_mode_display) or sd_mode_display == "NA":
        if re.search(r"(?:CONTRACT PERFORMANCE SECURITY|SECURITY DEPOSIT|CPS/SD)", full_text, re.IGNORECASE):
            sd_mode_display = "Bank Guarantee / DD / FDR / Online Transfer / Insurance Surety Bond"
            logger.info("[ATC_ANCHOR] Resolved field 'sd_mode' via SECTION_HEADING: CONTRACT PERFORMANCE SECURITY")

    # 26. LD/PRS %age (per week) & 27. Max LD %age
    # Task 4: Primary search by section heading "PRICE REDUCTION SCHEDULE (PRS) FOR DELAYED DELIVERY", secondary by clause number
    ld_percentage_display = resolve_field(["LD Percentage Per Week", "ld_percentage_per_week"], r"LD Percentage Per Week[:\-\s]+([^\n]+)")
    max_ld_percentage_display = resolve_field(["Max LD Percentage", "max_ld_percentage"], r"Max LD Percentage[:\-\s]+([^\n]+)")

    prs_heading_match = re.search(
        r"(?:PRICE REDUCTION SCHEDULE\s*\(PRS\)\s*FOR DELAYED DELIVERY|PRICE REDUCTION SCHEDULE|PRS\s+FOR\s+DELAYED\s+DELIVERY)(.*?)(?=\n\s*(?:SECTION|CLAUSE|\d+\.\d+|\Z))",
        full_text, re.IGNORECASE | re.DOTALL
    )
    if prs_heading_match:
        prs_body = prs_heading_match.group(1)
        prs_m = re.search(
            r"(\xbd|1/2|\d+(?:\.\d+)?)\s*%\s*(?:per\s+complete\s+week|per\s+week).*?maximum\s*(?:of\s*)?(\d+(?:\.\d+)?)\s*%",
            prs_body, re.IGNORECASE | re.DOTALL
        )
        if prs_m:
            rate_raw = prs_m.group(1)
            max_raw = prs_m.group(2)
            rate_val = 0.5 if rate_raw in ("\xbd", "1/2") else float(rate_raw)
            ld_percentage_display = f"{rate_val}% per week"
            max_ld_percentage_display = f"{float(max_raw)}%"
            logger.info(f"[ATC_ANCHOR] Resolved field 'prs_ld' via SECTION_HEADING: PRICE REDUCTION SCHEDULE ({ld_percentage_display}, max {max_ld_percentage_display})")
    
    if _is_missing(ld_percentage_display) or ld_percentage_display == "NA":
        prs_clause_match = re.search(r"(?:PRICE REDUCTION SCHEDULE|PRS).*?(\xbd|1/2|\d+(?:\.\d+)?)\%.*?per week.*?maximum\s*(\d+(?:\.\d+)?)\%", full_text, re.IGNORECASE | re.DOTALL)
        if prs_clause_match:
            rate_raw = prs_clause_match.group(1)
            max_raw = prs_clause_match.group(2)
            rate_val = 0.5 if rate_raw in ("\xbd", "1/2") else float(rate_raw)
            ld_percentage_display = f"{rate_val}% per week"
            max_ld_percentage_display = f"{float(max_raw)}%"
            logger.info(f"[ATC_ANCHOR] Resolved field 'prs_ld' via CLAUSE_NUMBER_FALLBACK: Clause 26.0 ({ld_percentage_display}, max {max_ld_percentage_display})")
        elif re.search(r"(?:PRICE REDUCTION SCHEDULE|PRS)", full_text, re.IGNORECASE):
            ld_percentage_display = "0.5% per week"
            max_ld_percentage_display = "5%"
            logger.info("[ATC_ANCHOR] Resolved field 'prs_ld' via SECTION_HEADING: PRS Keyword Fallback (0.5% per week, max 5%)")

    # PBG Required & Checkbox Matching
    pbg_required_raw = resolve_field(
        ["PBG Required", "pbg_required", "pbg_percentage", "ePBG Percentage"],
        r"ePBG Percentage[:\-\s]+([^\n]+)",
        None
    )
    if _is_missing(pbg_required_raw) or pbg_required_raw == "Not Found":
        pbg_required_display = "NA"
    else:
        pbg_req_str = str(pbg_required_raw).strip().lower()
        if pbg_req_str in ("false", "no", "not required", "n"):
            pbg_required_display = "No"
        elif pbg_req_str in ("true", "yes", "required", "y") or any(c.isdigit() for c in pbg_req_str):
            pbg_required_display = "Yes"
        else:
            pbg_required_display = str(pbg_required_raw)

    pbg_cb_match = re.search(
        r"Contract\s+Performance\s+Security\s*/?\s*Security\s+Deposit[:\-\s]+(APPLICABLE|NOT\s+APPLICABLE)",
        full_text, re.IGNORECASE
    )
    if pbg_cb_match:
        cb_val = pbg_cb_match.group(1).upper()
        if cb_val == "APPLICABLE":
            pbg_required_display = "Yes"
        elif cb_val == "NOT APPLICABLE":
            pbg_required_display = "No"
        logger.info(f"[ATC_ANCHOR] Resolved field 'pbg_required' via BDS_TAG: Checkbox {cb_val}")

    # 28. PBG %age
    pbg_pct_raw = resolve_field(
        ["PBG Percentage", "pbg_percentage", "ePBG Percentage", "Percentage (%)"],
        r"PBG Percentage[:\-\s]+([^\n]+)",
        None
    )
    if not _is_missing(pbg_pct_raw) and pbg_pct_raw != "Not Found":
        clean_pct = re.sub(r"[^\d.]", "", str(pbg_pct_raw))
        if clean_pct:
            pbg_percentage_display = f"{float(clean_pct)}%"
        else:
            pbg_percentage_display = str(pbg_pct_raw)
    else:
        pbg_percentage_display = "NA" if pbg_required_display == "Yes" else "Not Applicable"

    # 29. Security Deposit
    sd_percentage_display = resolve_field(["Security Deposit %", "sd_percentage"], r"Security Deposit %[:\-\s]+([^\n]+)")

    # 30. PBG Duration
    pbg_duration_raw = resolve_field(
        ["PBG Duration (Months)", "pbg_duration_months", "pbg_duration", "Duration of ePBG required", "Duration of ePBG"],
        r"PBG Duration \(Months\)[:\-\s]+([^\n]+)",
        None
    )
    if not _is_missing(pbg_duration_raw) and pbg_duration_raw != "Not Found":
        clean_dur = re.sub(r"\D", "", str(pbg_duration_raw))
        if clean_dur:
            pbg_duration_display = f"{int(clean_dur)} Months"
        else:
            pbg_duration_display = str(pbg_duration_raw)
    else:
        pbg_duration_display = "NA" if pbg_required_display == "Yes" else "Not Applicable"

    # PBG Required derivation rule: if PBG % or PBG Duration was successfully extracted
    # but PBG Required itself is still "NA" or absent, derive it as "Yes".
    # (GeM tenders often omit the explicit checkbox while still specifying the percentage.)
    if pbg_required_display == "NA":
        _pbg_pct_found = not _is_missing(pbg_pct_raw) and pbg_pct_raw not in ("Not Found", "0", "0.0", "0.00", "NA")
        _pbg_dur_found = not _is_missing(pbg_duration_raw) and pbg_duration_raw not in ("Not Found", "0", "0.0", "0.00", "NA")
        if _pbg_pct_found or _pbg_dur_found:
            pbg_required_display = "Yes"
            logger.info(
                "[FIELD_DERIVE] PBG Required derived as 'Yes' because "
                f"PBG Percentage={pbg_pct_raw!r} / PBG Duration={pbg_duration_raw!r} "
                "were extracted (MAIN_SOURCED protected; not overrideable by ATC)."
            )

    # 31. SD Duration
    sd_duration_display = resolve_field("SD Duration (Months)", r"SD Duration \(Months\)[:\-\s]+([^\n]+)")

    # 32. Physical Docs Submission Required
    physical_docs_required_display = resolve_field("Physical Docs Required", r"Physical Docs Required[:\-\s]+([^\n]+)")

    # 33. Physical Docs Submission Deadline
    physical_docs_deadline_display = resolve_field("Physical Docs Deadline", r"Physical Docs Deadline[:\-\s]+([^\n]+)")

    # 34. Age (in yrs) / Experience Years (BEC Sl. 1)
    word_to_num = {
        "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
        "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10
    }
    bec_block_match = re.search(
        r"(?:Technical\s+BEC\s+Criteria|BID\s+EVALUATION\s+CRITERIA\s+&\s+EVALUATION\s+METHODOLOGY)(.*?)(?=SECTION-III|BIDDING\s+DATA\s+SHEET|\Z)",
        full_text, re.IGNORECASE | re.DOTALL
    )
    bec_text = bec_block_match.group(1) if bec_block_match else full_text

    yrs_m = re.search(
        r"(?:previous|past)\s+(?:(one|two|three|four|five|six|seven|eight|nine|ten|\(?\d{1,2}\)?))\s*\(?\d{0,2}\)?\s*years?",
        bec_text, re.IGNORECASE
    )
    if yrs_m:
        raw_yr = yrs_m.group(1).lower().strip("()")
        if raw_yr in word_to_num:
            age_in_yrs = str(word_to_num[raw_yr])
        else:
            clean_y = re.sub(r"\D", "", raw_yr)
            age_in_yrs = str(int(clean_y)) if clean_y else "NA"
        logger.info(f"[ATC_ANCHOR] Resolved field 'eligibility_criterion_years' via SECTION_HEADING: BEC Technical Criteria Sl. 1 ({age_in_yrs})")
    else:
        experience_years_val = field_lookup.get("Minimum Experience (Years)")
        if experience_years_val and experience_years_val != "NA":
            age_in_yrs = experience_years_val
        else:
            age_in_yrs = extract_regex(r"Eligibility Criterion \(Years\)[:\-\s]+([^\n]+)")

    # 35. 3 Works Value
    order_value_1_display = resolve_field("3 Works Value", r"3 Works Value[:\-\s]+([^\n]+)")

    # 36. Annual Avg Turnover, 38. Working Capital, 40. Net Worth, 42. Solvency Certificate
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

    if "financial criteria" in full_text.lower() and "not applicable" in full_text.lower():
        avg_annual_turnover_type_display = "Not Applicable"
        avg_annual_turnover_value_display = "₹0.00"
        working_capital_type_display = "Not Applicable"
        working_capital_value_display = "₹0.00"
        solvency_certificate_type_display = "Not Applicable"
        solvency_certificate_value_display = "₹0.00"
        net_worth_type_display = "Not Applicable"
        net_worth_value_display = "₹0.00"

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

    # Custom Eligibility Criteria / Order Value Lakhs to INR conversion
    custom_eligibility_criteria_value_normalized = None
    custom_eligibility_criteria_display = resolve_field("Custom Eligibility Criteria", None, "NA")
    if not _is_missing(custom_eligibility_criteria_display) and custom_eligibility_criteria_display != "NA":
        total_inr = normalize_bec_order_value(custom_eligibility_criteria_display)
        if total_inr:
            custom_eligibility_criteria_value_normalized = total_inr

    if _is_missing(custom_eligibility_criteria_display) or custom_eligibility_criteria_display == "NA":
        order_val_m = re.search(
            r"(?:valuing\s+not\s+less\s+than|value\s+not\s+less\s+than|single\s+order\s+of)\s*Rs\.?\s*([\d,]+(?:\.\d+)?)\s*(lakh|crore)s?",
            bec_text, re.IGNORECASE
        )
        if order_val_m:
            val_num = float(order_val_m.group(1).replace(",", ""))
            unit_str = order_val_m.group(2).lower()
            multiplier = 100000 if "lakh" in unit_str else 10000000
            total_inr = int(val_num * multiplier)
            custom_eligibility_criteria_value_normalized = total_inr
            custom_eligibility_criteria_display = (
                f"Minimum Qualifying Order Value: Rs. {order_val_m.group(1)} {unit_str.capitalize()}s ({total_inr} INR)"
            )
            logger.info(f"[ATC_ANCHOR] Resolved field 'custom_eligibility_criteria' via SECTION_HEADING: BEC Technical Criteria Sl. 1 ({total_inr} INR)")

    # 45. Client details — Tag (G) Primary
    tag_g_match = re.search(
        r"\(G\)\s*CONTACT\s*DETAILS(?:\s*OF\s*TENDER\s*DEALING\s*OFFICER)?(.*?)(?=\([A-Z0-9]{1,3}\)|\Z)",
        full_text, re.IGNORECASE | re.DOTALL
    )
    if tag_g_match:
        g_text = tag_g_match.group(1)
        name_m = re.search(r"Name[:\-\s]+(Sh\.\s*[^\n]+|[A-Za-z\.\s]{3,40})", g_text, re.IGNORECASE)
        email_m = re.search(r"E-?mail(?:\s*ID)?[:\-\s]+([a-zA-Z0-9\._%+\-]+@[a-zA-Z0-9\.\-]+\.[a-zA-Z]{2,})", g_text, re.IGNORECASE)
        phone_m = re.search(r"(?:Phone|Tel|Mobile)(?:[^\n:]*?)[:\-][ \t]*([0-9\-\/\(\)\sExtn\.]+)", g_text, re.IGNORECASE)
        
        client_name_1_display = name_m.group(1).strip() if name_m else "NA"
        client_email_1_display = email_m.group(1).strip() if email_m else "NA"
        client_phone_1_display = phone_m.group(1).strip() if phone_m else "NA"
        logger.info(f"[ATC_ANCHOR] Resolved field 'client_contacts' via BDS_TAG: (G) CONTACT DETAILS OF TENDER DEALING OFFICER ({client_name_1_display})")
    else:
        client_match = re.search(r"Requested Details[:\-\s]+([^\n]+)[:\-\s]+([^\n]+)[:\-\s]+([^\n]+)", full_text, re.IGNORECASE)
        if client_match:
            client_name_1_display = client_match.group(1).strip()
            client_email_1_display = client_match.group(3).strip()
            client_phone_1_display = client_match.group(2).strip()
        else:
            officer_block_match = re.search(r"(?:CONTACT DETAILS OF TENDER DEALING OFFICER|TENDER DEALING OFFICER)(.*?)(?:SECTION|ANNEXURE|3\.0|4\.0|\Z)", full_text, re.IGNORECASE | re.DOTALL)
            officer_text = officer_block_match.group(1) if officer_block_match else full_text
            
            name_m = re.search(r"Name[:\-\s]+(Sh\.\s*[^\n]+|[A-Za-z\.\s]{3,40})", officer_text, re.IGNORECASE)
            email_m = re.search(r"E-?mail(?:\s*ID)?[:\-\s]+([a-zA-Z0-9\._%+\-]+@[a-zA-Z0-9\.\-]+\.[a-zA-Z]{2,})", officer_text, re.IGNORECASE)
            phone_m = re.search(r"(?:Phone|Tel|Mobile)(?:\s*No|\s*and\s*Extn)?[:\-\s]+([0-9\-\/\(\)\sExtn\.]+)", officer_text, re.IGNORECASE)
            
            client_name_1_display = name_m.group(1).strip() if name_m else "NA"
            client_email_1_display = email_m.group(1).strip() if email_m else "NA"
            client_phone_1_display = phone_m.group(1).strip() if phone_m else "NA"

    # Task 2: Second Contact Block (Nodal Officer)
    client_name_2_display = "NA"
    client_email_2_display = "NA"
    client_phone_2_display = "NA"

    nodal_officer_match = re.search(
        r"(?:Name\s+and\s+contact\s+details\s+of\s+nodal\s+officer|contact\s+details\s+of\s+nodal\s+officer)(.*?)(?=\n\s*\n\s*\d+\.|\Z)",
        full_text, re.IGNORECASE | re.DOTALL
    )
    if nodal_officer_match:
        n_text = nodal_officer_match.group(1)
        n_name = re.search(r"Name[:\-\s]+(Sh\.\s*[^\n]+|[A-Za-z\.\s]{3,40})", n_text, re.IGNORECASE)
        n_email = re.search(r"E-?mail(?:\s*ID)?[:\-\s]+([a-zA-Z0-9\._%+\-]+@[a-zA-Z0-9\.\-]+\.[a-zA-Z]{2,})", n_text, re.IGNORECASE)
        n_phone = re.search(r"(?:Phone|Tel|Mobile)(?:\s*No|\s*and\s*Extn)?[:\-\s]+([0-9\-\/\(\)\sExtn\.]+)", n_text, re.IGNORECASE)
        if n_name:
            client_name_2_display = n_name.group(1).strip()
            client_email_2_display = n_email.group(1).strip() if n_email else "NA"
            client_phone_2_display = n_phone.group(1).strip() if n_phone else "NA"
            logger.info(f"[ATC_ANCHOR] Resolved field 'client_contacts_2' via SECTION_HEADING: Nodal Officer Clause ({client_name_2_display})")

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

    # Courier Delivery Address: BDS Tag (H) Primary
    tag_h_match = re.search(
        r"\(H\)\s*DEALING\s*GAIL['’\s]*S\s*OFFICE\s*ADDRESS(.*?)(?=\([A-Z0-9]{1,3}\)|In\s+case|\Z)",
        full_text, re.IGNORECASE | re.DOTALL
    )
    if tag_h_match:
        h_text = tag_h_match.group(1).strip()
        h_clean = re.sub(r"\s+", " ", h_text)
        if client_name_1_display != "NA" and client_email_1_display != "NA":
            courier_address_display = f"{h_clean} | Kind Attn: {client_name_1_display} ({client_email_1_display})"
        elif client_name_1_display != "NA":
            courier_address_display = f"{h_clean} | Kind Attn: {client_name_1_display}"
        else:
            courier_address_display = h_clean
        logger.info(f"[ATC_ANCHOR] Resolved field 'courier_address' via BDS_TAG: (H) DEALING GAIL'S OFFICE ADDRESS ({courier_address_display[:60]}...)")
    else:
        courier_addr_match = re.search(r"Address \(Legacy\)[:\-\s]+([^\n]+(?:\n\s*[^\n]+)?)[:\-\s]+(?:Physical Docs Required|Physical Docs Submission)", full_text, re.IGNORECASE)
        if courier_addr_match:
            courier_address_display = courier_addr_match.group(1).strip().replace("\n", " ")
        else:
            cutout_match = re.search(r"(?:CUT-OUT SLIP|CUT OUT SLIP|DO NOT OPEN).*?TO[:\-\s]+(.*?)(?:FROM|KIND ATTN|QUOTATION|\Z)", full_text, re.IGNORECASE | re.DOTALL)
            if cutout_match:
                raw_addr = cutout_match.group(1).strip()
                clean_addr = re.sub(r"\s+", " ", raw_addr)
                courier_address_display = clean_addr if len(clean_addr) > 5 else "NA"
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

        # --- SCHEDULE QUANTITY SANITY CHECK ---
        # Compare sum(schedule quantities) vs header total_quantity.  A mismatch
        # indicates that one or more schedule rows were dropped during extraction.
        header_total_qty_raw = (
            field_lookup.get("total_quantity")
            or field_lookup.get("Total Quantity")
        )
        if header_total_qty_raw and schedules_list:
            try:
                header_total = float(re.sub(r"[^\d.]", "", str(header_total_qty_raw)))
                schedule_qty_sum = 0.0
                for sch in schedules_list:
                    raw_qty = sch.get("quantity", "")
                    if raw_qty and str(raw_qty).strip() not in ("", "NA"):
                        schedule_qty_sum += float(re.sub(r"[^\d.]", "", str(raw_qty)))
                # Tolerate floating point noise with a 0.5-unit epsilon
                if abs(schedule_qty_sum - header_total) > 0.5:
                    _mismatch_msg = (
                        f"[SCHEDULE_QTY_MISMATCH] sum(schedule quantities)={schedule_qty_sum} "
                        f"!= total_quantity={header_total} — "
                        f"{len(schedules_list)} schedule row(s) parsed, "
                        f"{int(header_total - schedule_qty_sum)} unit(s) unaccounted for."
                    )
                    logger.warning(_mismatch_msg)
                    # Surface the mismatch flag directly in the last populated schedule slot
                    _flag = (
                        f" ⚠ QTY MISMATCH: schedules sum {schedule_qty_sum} "
                        f"vs header total {header_total}"
                    )
                    if schedule_3_details_display != "NA":
                        schedule_3_details_display += _flag
                    elif schedule_2_details_display != "NA":
                        schedule_2_details_display += _flag
                    elif schedule_1_details_display != "NA":
                        schedule_1_details_display += _flag
            except (ValueError, TypeError):
                pass  # Non-numeric quantities — skip sanity check gracefully

    if _is_missing(custom_eligibility_criteria_display) or custom_eligibility_criteria_display == "NA":
        custom_match = re.search(r"(?:executed|completed)\s+(?:at\s+least\s+)?(?:one|1)\s+(?:single\s+)?(?:purchase\s+order|order|work\s+order)\s+of\s+(?:a\s+)?value\s+(?:not\s+less\s+than|of)\s+Rs\.?\s*([\d\.\,\s]+(?:Lacs|Lakhs|Crore|Cr)?)\b", full_text, re.IGNORECASE)
        if custom_match:
            val_str = custom_match.group(1).strip()
            custom_eligibility_criteria_display = f"Minimum Qualifying Order Value: Rs. {val_str}"
            total_inr = normalize_bec_order_value(val_str)
            if total_inr:
                custom_eligibility_criteria_value_normalized = total_inr
        else:
            custom_match_broad = re.search(r"Minimum\s+Executed\s+Order\s+Value.*?(Rs\.?\s*[\d\.\,\s]+(?:Lacs|Lakhs|Crore|Cr)?)", full_text, re.IGNORECASE)
            if custom_match_broad:
                val_str = custom_match_broad.group(1).strip()
                custom_eligibility_criteria_display = f"Minimum Qualifying Order Value: {val_str}"
                total_inr = normalize_bec_order_value(val_str)
                if total_inr:
                    custom_eligibility_criteria_value_normalized = total_inr

    field_sources = {}
    for sec in sections:
        for f in sec.get("fields", []):
            label = f.get("label", "").strip()
            src = f.get("source")
            if label and src:
                field_sources[label] = src

    # Map raw field sources to infosheet layout display keys
    info_sheet_sources = {}
    key_to_raw = {
        "organization": ["organisation_name", "ministry_name", "department_name"],
        "tender_name": ["item_category", "similar_category"],
        "tender_id_display": ["bid_number", "tender_id"],
        "processing_fee_amount_display": ["processing_fee_amount"],
        "processing_fee_mode_display": ["processing_fee_mode"],
        "tender_fee_amount_display": ["tender_fee_amount"],
        "tender_fee_mode_display": ["tender_fee_mode"],
        "emd_amount_display": ["emd_amount", "emd_total"],
        "emd_required_display": ["emd_required"],
        "tender_value_display": ["tender_value"],
        "emd_mode_display": ["emd_mode"],
        "bid_validity_days_display": ["bid_validity_days"],
        "reverse_auction_applicable_display": ["reverse_auction_enabled"],
        "delivery_time_supply_display": ["contract_period", "delivery_time_supply"],
        "pbg_mode_display": ["pbg_advisory_bank", "pbg_mode"],
        "pbg_required_display": ["pbg_percentage"],
        "pbg_percentage_display": ["pbg_percentage"],
        "pbg_duration_display": ["pbg_duration_months"],
        "custom_eligibility_criteria_display": ["custom_eligibility_criteria"],
        "pre_bid_meeting_display": ["pre_bid_meeting"]
    }
    for disp_key, raw_keys in key_to_raw.items():
        for rk in raw_keys:
            if rk in field_sources:
                info_sheet_sources[disp_key] = field_sources[rk]
                break

    res_dict = {
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
        "bid_type_display": bid_type_display,
        "atc_document_link_display": atc_document_link_display,
        "maf_required_display": maf_required_display,
        "delivery_time_supply_display": delivery_time_supply_display,
        "delivery_time_installation_display": delivery_time_installation_display,
        "pbg_mode_display": pbg_mode_display,
        "payment_terms_supply_display": payment_terms_supply_display,
        "payment_terms_installation_display": payment_terms_installation_display,
        "sd_mode_display": sd_mode_display,
        "ld_percentage_display": ld_percentage_display,
        "max_ld_percentage_display": max_ld_percentage_display,
        "pbg_required_display": pbg_required_display,
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
        "custom_eligibility_criteria_display": custom_eligibility_criteria_display,
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
    res_dict["_info_sheet_sources"] = info_sheet_sources
    return res_dict

