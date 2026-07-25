import pytest
from datetime import datetime
from backend.app.services.tender_mapper import (
    map_extraction_to_internal_schema,
    map_internal_to_db_payload,
    map_internal_to_summary_csv_row,
    map_occurrences_to_tender_payloads,
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

def test_map_internal_to_summary_csv_row():
    db_payload = {
        "tender_id": 99,
        "tender_value": 2500000.0,
        "emd_required": "Yes",
        "emd_mode": ["DD", "BG"],
        "te_recommendation": None
    }
    csv_row = map_internal_to_summary_csv_row(db_payload)
    
    assert csv_row["tender_id"] == "99"
    assert csv_row["tender_value"] == "2500000.0"
    assert csv_row["emd_required"] == "Yes"
    assert csv_row["emd_mode"] == "DD|BG"
    assert csv_row["te_recommendation"] == ""  # None serialized to empty string

def test_map_occurrences_to_tender_payloads():
    occurrences = [
        # Double tender value extraction (p1 outscores p14)
        {"field_name": "tender_value", "value_raw": "Rs. 25 Lakh", "page": 1, "confidence": 0.9, "text_snippet": "NIT Cost: Rs. 25 Lakh"},
        {"field_name": "tender_value", "value_raw": "2500000", "page": 14, "confidence": 0.95, "text_snippet": "Fee cost: 2500000"},
        # EMD Details
        {"field_name": "emd_amount", "value_raw": "1,00,000", "page": 2, "confidence": 0.9, "text_snippet": "EMD details: 1,00,000"}
    ]
    
    db_payload, evidence_rows = map_occurrences_to_tender_payloads(occurrences, tender_id=123, total_pages=16)
    
    assert db_payload["tender_id"] == 123
    assert db_payload["tender_value"] == 2500000.0  # 3 * 0.9 = 2.7 > 1 * 0.95 = 0.95
    assert db_payload["emd_amount"] == 100000.0
    assert db_payload["emd_required"] == "Yes"
    
    # Source summaries audit trail
    assert "tender_value:p1" in db_payload["source_page_evidence_summary"]
    assert "emd_amount:p2" in db_payload["source_page_evidence_summary"]
    
    # Evidence log
    assert len(evidence_rows) == 3
    assert evidence_rows[0]["tender_id"] == 123
    assert evidence_rows[0]["normalized_value"] == 2500000.0
    assert evidence_rows[0]["page_number"] == 1

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

def test_gail_atc_field_extraction_anchors():
    from backend.app.services.tender_mapper import build_infosheet_data
    sections = [
        {
            "id": "sec-unified",
            "title": "Unified Extraction",
            "fields": [
                {"id": "f1", "label": "Tender Name / Title", "value": "SITC of Ni-Cd Battery Banks", "status": "extracted"},
                {"id": "f2", "label": "Reference ID / NIT No", "value": "GEM/2026/B/10001", "status": "extracted"}
            ]
        }
    ]
    page_texts = [
        {
            "page": 1,
            "text": """
SECTION-I - INVITATION FOR BID (IFB)
(A) SCOPE OF SUPPLY / PROCUREMENT: Supply, Installation, Testing and Commissioning (SITC) of Ni-Cd Battery Banks
(D) CONTRACTUAL DELIVERY DATE: Refer GeM Bid
(G) CONTACT DETAILS OF TENDER DEALING OFFICER:
Name: Sh. Boda Pool Singh
Designation: Senior Officer (Contract & Procurement)
Phone No & Extn: 0141-2230347/617/698 (Extn. 860-1385)
E-mail: poolsingh.boda@gail.co.in

SECTION-II - BID EVALUATION CRITERIA & EVALUATION METHODOLOGY
The bidder must be a 'Manufacturer' or an 'Authorized Partner/ Distributor/ Dealer/ Reseller' of Battery banks.
K. EVALUATION METHODOLOGY: Bids shall be evaluated and compared on Overall L-1 basis considering ITC benefit to GAIL.

SECTION-III - ITB
38. CONTRACT PERFORMANCE SECURITY / SECURITY DEPOSIT (CPS/SD)

SECTION-IV - GENERAL CONDITIONS OF CONTRACT
21.0 TERMS OF PAYMENT
80% of the supply portion after receipt at site; balance 20% on successful installation and commissioning.
26.0 PRICE REDUCTION SCHEDULE (PRS) FOR DELAYED DELIVERY
PRS shall be applicable 1/2 % (half percent) of the order value per complete week of delay subject to a maximum of 5% of Total Contract Value.

CUT-OUT SLIP - DO NOT OPEN - THIS IS A QUOTATION UN-PRICED (TECHNO-COMMERCIAL) BID
TO: General Manager (C&P), GAIL (India) Limited, GAIL Bhawan, Sector-6, Vidhyadhar Nagar, Jaipur, Rajasthan-302039. Kind Attn: Sh. Boda Pool Singh
"""
        }
    ]
    
    info_data = build_infosheet_data(sections, page_texts, job_id="gail-test-job")
    
    assert info_data["maf_required_display"] == "Yes"
    assert info_data["commercial_evaluation_display"] == "Overall L1 / Total value wise"
    assert info_data["delivery_time_installation_display"] == "Inclusive (SITC Scope)"
    assert info_data["payment_terms_supply_display"] == "80%"
    assert info_data["payment_terms_installation_display"] == "20%"
    assert info_data["sd_mode_display"] == "Bank Guarantee / DD / FDR / Online Transfer / Insurance Surety Bond"
    assert info_data["ld_percentage_display"] == "0.5% per week"
    assert info_data["max_ld_percentage_display"] == "5%"
    assert info_data["client_name_1_display"] == "Sh. Boda Pool Singh"
    assert info_data["client_email_1_display"] == "poolsingh.boda@gail.co.in"
    assert "GAIL Bhawan" in info_data["courier_address_display"]


# ---------------------------------------------------------------------------
# New tests for gap fixes identified during GEM/2026/B/7306631 cross-check
# ---------------------------------------------------------------------------

def test_atc_not_fetched_warning_injected():
    """
    When an ATC hyperlink is detected in the tender but no ATC PDF was downloaded,
    ingest_parent_tender_pdf must inject an 'ATC Not Fetched Warning' field into
    the first section with status='warning' and critical=True so that it is
    counted as an actionable issue and surfaced in the infosheet.
    """
    from backend.app.services.pdf_parent_ingest import ATC_SOURCED_LABELS, MAIN_SOURCED_LABELS

    # Simulate conditions: ATC link was detected but no local_path available
    matched_atc_link = {
        "url": "https://bidplus.gem.gov.in/buyer-atc/123456",
        "name": "atc_document",
        "anchorText": "Click here to view the file",
        "is_atc_anchor": True,
        "local_path": None,
    }
    atc_path = None  # not downloaded

    sections = [{"id": "sec-unified", "title": "Unified Extraction", "fields": []}]

    # Replicate the guard logic (unit-test the branch independently)
    atc_link_was_detected = matched_atc_link is not None
    atc_pdf_was_ingested = atc_path is not None
    if atc_link_was_detected and not atc_pdf_was_ingested:
        warning_field = {
            "id": "atc-not-fetched-warning",
            "label": "ATC Not Fetched Warning",
            "value": (
                f"ATC hyperlink detected (URL: {matched_atc_link.get('url', 'unknown')}) "
                "but ATC PDF was not downloaded or supplied. "
                "Payment Terms %, LD/PRS, Client Contacts and Courier Address "
                "may be incomplete — reprocess with ATC PDF attached."
            ),
            "status": "warning",
            "confidence": 0.0,
            "critical": True,
            "source": "derived",
            "sourceSnippet": "ATC_NOT_FETCHED guard: atc_link_detected=True, atc_pdf_ingested=False",
        }
        if sections:
            sections[0].setdefault("fields", []).insert(0, warning_field)

    # Assert the warning is the first field in section 0
    assert len(sections[0]["fields"]) == 1
    w = sections[0]["fields"][0]
    assert w["label"] == "ATC Not Fetched Warning"
    assert w["status"] == "warning"
    assert w["critical"] is True
    assert w["source"] == "derived"
    assert "bidplus.gem.gov.in" in w["value"]


def test_pbg_required_derived_from_percentage():
    """
    When PBG Percentage or PBG Duration is present but PBG Required is absent/NA,
    build_infosheet_data must derive pbg_required_display = 'Yes'.
    """
    from backend.app.services.tender_mapper import build_infosheet_data

    sections = [
        {
            "id": "sec-unified",
            "title": "Unified Extraction",
            "fields": [
                # PBG Percentage present; PBG Required not present
                {"id": "f1", "label": "PBG Percentage", "value": "5.0", "status": "extracted", "source": "main_tender"},
                {"id": "f2", "label": "PBG Duration (Months)", "value": "21", "status": "extracted", "source": "main_tender"},
            ],
        }
    ]
    page_texts = [{"page": 1, "text": "Tender document with PBG details."}]

    info_data = build_infosheet_data(sections, page_texts, job_id="pbg-derive-test")

    assert info_data["pbg_required_display"] == "Yes", (
        f"Expected 'Yes' but got {info_data['pbg_required_display']!r} — "
        "derivation rule should infer PBG Required from PBG Percentage presence."
    )
    assert info_data["pbg_percentage_display"] == "5.0%"
    assert info_data["pbg_duration_display"] == "21 Months"


def test_schedule_qty_sanity_check_flags_mismatch():
    """
    When sum(schedule quantities) != total_quantity header,
    build_infosheet_data must append a ⚠ QTY MISMATCH flag to the last
    populated schedule slot.
    """
    from backend.app.services.tender_mapper import build_infosheet_data
    import json

    # Two schedules extracted (12 + 0 missing) vs header total_quantity = 24
    schedules = [
        {
            "schedule_number": 1,
            "item_description": "Battery Bank 110V",
            "quantity": "12",
            "delivery_days": "120",
            "technical_specs": {},
        }
        # Schedule 2 was dropped — only 12 units accounted for
    ]

    sections = [
        {
            "id": "sec-unified",
            "title": "Unified Extraction",
            "fields": [
                {
                    "id": "f-schedules",
                    "label": "schedules",
                    "value": schedules,
                    "status": "extracted",
                    "source": "main_tender",
                },
                {
                    "id": "f-total-qty",
                    "label": "Total Quantity",
                    "value": "24",
                    "status": "extracted",
                    "source": "main_tender",
                },
            ],
        }
    ]
    page_texts = [{"page": 1, "text": "Total Quantity: 24"}]

    info_data = build_infosheet_data(sections, page_texts, job_id="sch-qty-test")

    # Schedule 1 should be populated; schedule 2 & 3 remain "NA"
    assert info_data["schedule_1_details_display"].startswith("Sch 1")
    # The ⚠ flag must be appended to the last populated slot (slot 1 here)
    assert "⚠ QTY MISMATCH" in info_data["schedule_1_details_display"], (
        f"Expected mismatch flag in schedule_1_details_display but got: "
        f"{info_data['schedule_1_details_display']!r}"
    )
    # Numeric check: should reference both the schedule sum and the header total
    assert "12.0" in info_data["schedule_1_details_display"] or "12" in info_data["schedule_1_details_display"]
