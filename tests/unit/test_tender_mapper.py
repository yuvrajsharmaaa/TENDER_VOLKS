import pytest
from datetime import datetime
from backend.app.services.tender_mapper import (
    map_extraction_to_internal_schema,
    map_internal_to_db_payload,
    map_internal_to_csv_row,
    map_extraction_to_tender_information
)

def test_map_extraction_to_internal_schema():
    extracted = {
        "bid_number": "ABC/2025/001",
        "estimated_value": "Rs. 25 Lakh",
        "bid_validity_days": "60 Days",
        "bid_end_datetime": "12-04-2025 14:00:00",
        "emd_amount": "2,00,000",
        "emd_mode_text": "Demand Draft, Bank Guarantee",
        "pbg_percentage": "5.0",
        "pbg_duration": "12",
        "avg_annual_turnover_value": "50,00,000",
        "avg_annual_turnover_type": "Bidder",
        "technical_eligibility_age": "3",
        "courier_address": "Procurement Cell, CPPP, New Delhi, 110001",
        "organization_name": "Ministry of Power"
    }
    
    internal = map_extraction_to_internal_schema(extracted)
    
    assert internal["bid_number"] == "ABC/2025/001"
    assert internal["tender_value"] == 2500000.0
    assert internal["bid_validity_days"] == 60
    assert internal["deadline_dt"] == datetime(2025, 4, 12, 14, 0, 0)
    assert internal["emd_amount"] == 200000.0
    assert internal["pbg_pct"] == 5.0
    assert internal["pbg_dur"] == 12
    assert internal["turnover_val"] == 5000000.0
    assert internal["experience_years"] == 3
    assert internal["courier_address"] == "Procurement Cell, CPPP, New Delhi, 110001"

def test_map_internal_to_db_payload():
    internal_data = {
        "bid_number": "ABC/2025/001",
        "tender_value": 2500000.0,
        "bid_validity_days": 60,
        "deadline_dt": datetime(2025, 4, 12, 14, 0, 0),
        "emd_amount": 200000.0,
        "emd_mode_raw": "Demand Draft, Bank Guarantee",
        "fee_amount": None,
        "fee_mode_raw": None,
        "processing_fee_amount": None,
        "processing_fee_mode_raw": None,
        "pbg_pct": 5.0,
        "pbg_dur": 12,
        "pbg_mode": None,
        "sd_pct": None,
        "sd_dur": None,
        "sd_mode": None,
        "ld_pct_week": None,
        "max_ld_pct": None,
        "maf_req_raw": None,
        "experience_years": 3,
        "oem_experience": None,
        "turnover_val": 5000000.0,
        "turnover_type": "Bidder",
        "working_capital_value": None,
        "working_capital_type": None,
        "solvency_certificate_value": None,
        "solvency_certificate_type": None,
        "net_worth_value": None,
        "net_worth_type": None,
        "order_value_1": None,
        "order_value_2": None,
        "order_value_3": None,
        "work_value_type": None,
        "custom_rules": "OEM authorization is required",
        "delivery_time_supply": None,
        "delivery_time_installation_days": None,
        "delivery_time_installation_inclusive": None,
        "payment_terms_supply": None,
        "payment_terms_installation": None,
        "courier_address": "Procurement Cell, New Delhi, 110001",
        "courier_name": "Under Secretary",
        "courier_phone": None,
        "org_name": "Ministry of Power",
        "ra_status": "Yes"
    }
    
    payload = map_internal_to_db_payload(internal_data, tender_id=99)
    
    assert payload["tender_id"] == 99
    assert payload["tender_value"] == 2500000.0
    assert payload["emd_required"] == "Yes"
    assert payload["emd_mode"] == ["DD", "BG"]
    assert payload["maf_required"] == "Yes"  # Derived from custom rules text
    assert payload["pbg_required"] == "Yes"
    assert payload["pbg_percentage"] == 5.0
    assert payload["pbg_duration"] == 12
    assert payload["courier_pincode"] == "110001"
    assert payload["courier_address_line_1"] == "Procurement Cell"
    assert payload["client_details_present"] == "Yes"
    assert payload["courier_details_present"] == "Yes"
    
    # Verify manual review fields are set to None
    assert payload["te_recommendation"] is None
    assert payload["te_rejection_reason"] is None

def test_map_internal_to_csv_row():
    db_payload = {
        "tender_id": 99,
        "tender_value": 2500000.0,
        "emd_required": "Yes",
        "emd_mode": ["DD", "BG"],
        "te_recommendation": None
    }
    csv_row = map_internal_to_csv_row(db_payload)
    
    assert csv_row["tender_id"] == "99"
    assert csv_row["tender_value"] == "2500000.0"
    assert csv_row["emd_required"] == "Yes"
    assert csv_row["emd_mode"] == "DD|BG"
    assert csv_row["te_recommendation"] == ""  # None serialized to empty string

def test_map_extraction_to_tender_information():
    extracted = {
        "tender_id": "ABC/2025/001",
        "estimated_value": "Rs. 25 Lakh",
        "emd_amount": "2,00,000"
    }
    
    payload = map_extraction_to_tender_information(extracted, tender_id=99)
    assert payload["tender_id"] == 99
    assert payload["tender_value"] == 2500000.0
    assert payload["emd_amount"] == 200000.0
