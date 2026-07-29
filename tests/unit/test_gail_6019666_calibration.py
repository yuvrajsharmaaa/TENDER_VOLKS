import pytest
from backend.app.services.tender_mapper import build_infosheet_data

def test_gail_6019666_ground_truth_calibration():
    """
    Calibrates extraction logic against tender GAIL 1741681257 1456383019 (GEM/2025/B/6019666):
    - EMD Required: Yes, EMD Amount: ₹73,880.00, EMD Mode: BT
    - Payment Terms: Supply 80%, Installation 20%
    - Delivery Time: 120 Days
    - PBG %age: 5%, PBG Duration: 21 Months
    - LD/PRS %age: 0.5%, Max LD: 5%
    - Eligibility Criterion: 7 Years, Bid Validity: 120 Days
    - Work Orders: 1st=₹23.49, 2nd=₹1.00, 3rd=₹1.00
    - Financial: Turnover=Not Applicable, Value=₹0.00
    - Physical Docs: Yes
    """
    gail_text = """
    GeM Bid Number: GEM/2025/B/6019666 Dated: 04-03-2025
    Organisation Name: Gail India Limited
    Tender Title: GAIL 1741681257 1456383019

    EMD Detail:
    EMD Required: Yes
    EMD Amount: 73880

    SECTION-I INVITATION FOR BID (IFB)
    (E) BID SECURITY / EARNEST MONEY DEPOSIT (EMD)
    Amount: Rs. 73,880/-. EMD can be submitted through Online Bank Transfer / NEFT / RTGS mode.

    DELIVERY SCHEDULE / CONTRACTUAL DELIVERY DATE: 120 Days from date of FOA.

    PRICE REDUCTION SCHEDULE (PRS) FOR DELAYED DELIVERY:
    0.5% per week subject to maximum of 5% of Total Order Value.

    PAYMENT TERMS:
    80% payment against supply of materials and 20% payment against installation & commissioning.

    TECHNICAL BEC / ELIGIBILITY CRITERIA:
    Bidder must have experience of past 7 years in similar scope of work.
    3 Works Value: 23.49
    2 Works Value: 1.00
    1 work Value: 1.00

    FINANCIAL CRITERIA:
    Financial Criteria Not Applicable for this tender.

    PHYSICAL DOCUMENTS:
    Physical Docs Submission Required: Yes. Hardcopy must be submitted within 7 days.

    PBG Percentage: 5%
    PBG Duration (Months): 21
    Bid Offer Validity (Days): 120 Days
    """

    sections = [{"id": "sec-unified", "title": "Unified Extraction", "fields": []}]
    page_texts = [{"page": 1, "text": gail_text}]

    info = build_infosheet_data(sections, page_texts, job_id="gail-6019666-test")

    assert info["emd_required_display"] == "Yes"
    assert info["emd_amount_display"] in ("₹73,880.00", "73,880", "₹73,880")
    assert info["emd_mode_display"] == "BT"
    assert info["delivery_time_supply_display"] == "120 Days"
    assert info["pbg_percentage_display"] == "5%"
    assert info["pbg_duration_display"] == "21"
    assert info["bid_validity_days_display"] == "120 Days"
    assert info["order_value_1_display"] == "₹23.49 (units not specified)"
    assert info["order_value_2_display"] == "₹1.00 (units not specified)"
    assert info["order_value_3_display"] == "₹1.00 (units not specified)"
    assert info["avg_annual_turnover_type_display"] in ("N/A", "Not Applicable")
    assert info["avg_annual_turnover_value_display"] in ("₹0.00", "N/A")
