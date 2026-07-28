"""
Regression test suite for generalized de-hardcoded anchor resolution
Covering GCC-Goods Rev.1 clause renumbering (ATC) and GEM_DOC field reordering (MAIN).
"""

import pytest
from backend.app.services.tender_mapper import resolve_atc_anchor_fields, build_infosheet_data
from backend.app.services.gail_clause_aliases import ATC_CLAUSE_ALIASES
from backend.app.services.gem_field_aliases import MAIN_FIELD_ALIASES

def test_atc_clause_renumbering_gcc_goods():
    """
    Tests ATC resolver against an ATC text with GCC-Goods Rev.1 clause numbering:
    - Clause 12: CONTRACT PERFORMANCE SECURITY (CPS) @ 3% within 30 days of FOA
    - Clause 21: TERMS OF PAYMENT (90% supply, 10% installation)
    - Clause 26: PRICE REDUCTION SCHEDULE (PRS) FOR DELAYED DELIVERY (0.5% per week, max 5%)
    Verifies extraction succeeds despite clause numbers differing from Clause 38/39/26.
    """
    gcc_atc_text = """
SECTION-III: SPECIAL CONDITIONS OF CONTRACT (SCC)

11.0 INSPECTION AND TESTING
All goods shall be tested prior to dispatch.

12.0 CONTRACT PERFORMANCE SECURITY / SECURITY DEPOSIT (CPS/SD)
12.1 Within 30 days of receipt of Fax of Acceptance (FOA), the successful bidder shall
submit Security Deposit / Contract Performance Security @ 3% of Total Order value within 30 days of FOA.
12.2 The CPS shall be in the form of Bank Guarantee or Demand Draft.

21.0 TERMS OF PAYMENT
21.1 Payment shall be released as under:
(a) 90% of total order value on receipt of materials at site.
(b) Balance 10% on successful installation and commissioning.

26.0 PRICE REDUCTION SCHEDULE (PRS) FOR DELAYED DELIVERY
26.1 In case of delay in delivery, price reduction at the rate of 1/2% percent per complete week
subject to a maximum of 5% percent of total order value shall apply.

30.0 RESOLUTION OF DISPUTES
All disputes shall be referred to arbitration.
    """
    
    res = resolve_atc_anchor_fields(gcc_atc_text)
    
    assert res.get("sd_percentage") == 3.0, f"Expected 3.0, got {res.get('sd_percentage')}"
    assert res.get("sd_duration") == 30, f"Expected 30, got {res.get('sd_duration')}"
    assert res.get("sd_mode") is not None
    assert res.get("payment_terms_supply_percent") == 90.0
    assert res.get("payment_terms_installation_percent") == 10.0
    assert res.get("ld_percentage_per_week") == 0.5
    assert res.get("max_ld_percentage") == 5.0

def test_main_field_reordering_gem_doc():
    """
    Tests MAIN resolver against a GEM_DOC layout with reordered fields and alternative headers:
    - "ePBG Detail" instead of "PBG Percentage"
    - "Years of Experience" instead of "Eligibility Criterion (Years)"
    - "Bid Validity Period" instead of "Bid Validity (Days)"
    - "EMD Detail" instead of "EMD Amount"
    """
    reordered_gem_doc_text = """
Bid Details / बिड विवरण
Bid Number: GEM/2025/B/9988776
Dated: 15-07-2025

Item Title: Supply and SITC of Industrial Valves
Department Name: Procurement Division

EMD Detail:
EMD Amount: Rs. 150000.00
EMD Required: Yes

ePBG Detail:
ePBG Percentage: 5.00
Duration of ePBG: 18

Experience Criteria:
Years of Experience: 3 Years
Past Performance: 80%

Bid Validity Period: 120 Days
    """
    
    sections = [
        {
            "id": "sec-1",
            "title": "Bid Summary",
            "fields": [
                {"label": "Bid Number", "field_name": "bid_number", "value": "GEM/2025/B/9988776"},
                {"label": "EMD Detail", "field_name": "emd_amount", "value": "₹150,000.00"},
                {"label": "ePBG Detail", "field_name": "pbg_percentage", "value": "5.00%"},
                {"label": "Years of Experience", "field_name": "eligibility_criterion_years", "value": "3"},
                {"label": "Bid Validity Period", "field_name": "bid_validity_days", "value": "120"}
            ]
        }
    ]
    
    page_texts = [{"page": 1, "text": reordered_gem_doc_text}]
    
    infosheet = build_infosheet_data(sections, page_texts)
    
    assert infosheet.get("emd_amount_display") == "₹1,50,000"
    assert infosheet.get("pbg_percentage_display") == "5%"
    assert "120" in infosheet.get("bid_validity_days_display")
