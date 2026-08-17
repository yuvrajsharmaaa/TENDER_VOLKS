import pytest
import re
from backend.app.services.tender_mapper import (
    build_infosheet_data,
    collect_repeated_documents,
    _RE_SD_CLAUSE38,
    FIELD_STATUS_MISSING,
    FIELD_STATUS_NOT_APPLICABLE,
    FIELD_STATUS_OK
)
from backend.app.services.gem_field_aliases import MAIN_FIELD_ALIASES

def test_issue1_delivery_time_no_validity_bleed():
    """Issue 1: Delivery Time (Supply) must be 150 Days and not bleed from Bid Offer Validity 90 Days."""
    sample_text = """
    Government e-Marketplace Bid Details
    Bid Offer Validity (From End Date): 90 (Days)
    Delivery Period (In Days): 150
    """
    sections = [
        {
            "section_name": "Main Details",
            "fields": [
                {"label": "Bid Offer Validity (Days)", "value": "90"},
                {"label": "Delivery Period (In Days)", "value": "150"}
            ]
        }
    ]
    page_texts = [{"text": sample_text}]
    info = build_infosheet_data(sections, page_texts)
    assert info.get("delivery_time_supply_display") == "150 Days"

def test_issue2_sd_duration_not_conflated_with_foa():
    """Issue 2: Security Deposit 30 days of FOA must not set SD Duration to 30."""
    sd_text = "Security Deposit / CPS: 3% of Total Order Value within 30 days of FOA."
    m = _RE_SD_CLAUSE38.search(sd_text)
    assert m is not None
    assert m.group(1) == "3"
    # SD Duration should remain None or NA when only FOA deadline is specified
    sections = [{"section_name": "Guarantees", "fields": []}]
    info = build_infosheet_data(sections, [{"text": sd_text}])
    assert info.get("sd_duration_display") in ("N/A", "NA", None, "⚠️ MISSING")

def test_issue3_working_capital_bank_guarantee_and_exemption():
    """Issue 3: Bank Guarantee Net Worth Rs 100 Crores must not populate Working Capital, and Financial Criteria Not Applicable must override all 8 financial sub-fields."""
    sample_text = """
    BID EVALUATION CRITERIA (BEC)
    Financial Criteria: Not Applicable
    Clause 16.3: Bank Guarantee shall be issued by any Commercial Bank having Net Worth of Rs. 100 Crores.
    """
    sections = [
        {
            "section_name": "Financial",
            "fields": [
                {"label": "Working Capital Value", "value": "NA"}
            ]
        }
    ]
    info = build_infosheet_data(sections, [{"text": sample_text}])
    assert info.get("working_capital_value_display") == "₹0.00"
    assert info.get("working_capital_type_display") == "Not Applicable"
    assert info.get("avg_annual_turnover_value_display") == "₹0.00"
    assert info.get("avg_annual_turnover_type_display") == "Not Applicable"
    assert info.get("net_worth_value_display") == "₹0.00"

def test_issue4_present_fields_extraction():
    """Issue 4: Verify 5 present fields are extracted cleanly."""
    sample_text = """
    Experience Criteria: 7 Year(s)
    Startup Exemption for Years of Experience and Turnover: Yes | Complete
    MSE Purchase Preference: Yes
    MII Purchase Preference: No
    Delivery Period (In Days): 150
    """
    sections = [
        {
            "section_name": "GeM Details",
            "fields": [
                {"label": "Experience Criteria", "value": "7 Year(s)"},
                {"label": "Startup Exemption for Years of Experience and Turnover", "value": "Yes | Complete"},
                {"label": "MSE Purchase Preference", "value": "Yes"},
                {"label": "MII Purchase Preference", "value": "No"},
                {"label": "Delivery Period (In Days)", "value": "150"}
            ]
        }
    ]
    info = build_infosheet_data(sections, [{"text": sample_text}])
    assert "7" in str(info.get("experience_years_display") or info.get("eligibility_criterion_years"))
    assert "Yes" in str(info.get("startup_relaxation_display"))
    assert "Yes" in str(info.get("mse_preference_display"))
    assert info.get("mii_preference_display") == "No"
    assert info.get("delivery_time_installation_display") == "150 Days"

def test_issue5_pre_bid_meeting_mojibake_handling():
    """Issue 5: Mojibake header '5ी- बड़ &थान/Pre-Bid Venue' must fall back to Date/Time/MS Teams link."""
    sample_text = """
    Pre-Bid Meeting Date: 13-03-2026, 11:00 AM
    MS Teams, Meeting ID: 436 966 051 957 22, Passcode: o27yw6kA
    """
    sections = [
        {
            "section_name": "Pre-Bid",
            "fields": [
                {"label": "Pre-Bid Venue", "value": "5ी- बड़ &थान/Pre-Bid Venue"}
            ]
        }
    ]
    info = build_infosheet_data(sections, [{"text": sample_text}])
    val = info.get("pre_bid_meeting_display")
    assert "5ी" not in val
    assert "13-03-2026" in val or "Meeting ID: 436 966 051 957 22" in val

def test_issue6_documents_list_no_disclaimer_fragmentation():
    """Issue 6: Disclaimer prose must not be split into discrete sentence fragments."""
    sections = [
        {
            "section_name": "Checklist",
            "fields": [
                {
                    "label": "Document required from seller",
                    "value": "Experience Criteria, Past Performance, In case any bidder is seeking exemption, the supporting documents to prove his eligibility for exemption must be uploaded for evaluation by the buyer"
                }
            ]
        }
    ]
    docs = collect_repeated_documents(sections)
    descriptions = [d["description"] for d in docs]
    assert "Experience Criteria" in descriptions
    assert "Past Performance" in descriptions
    assert not any("supporting documents to prove his eligibility" in d for d in descriptions)

def test_issue7_courier_address_truncation_fix():
    """Issue 7: Trailing comma / truncated courier address must trigger BDS Tag (H) fallback."""
    sample_text = """
    (H) DEALING GAIL'S OFFICE ADDRESS
    GAIL (India) Limited, Site Office, P.O. Vijaypur, District Guna, MP, 473111
    """
    sections = [
        {
            "section_name": "Address",
            "fields": [
                {"label": "Courier Address", "value": "GAIL (India) Limited,"}
            ]
        }
    ]
    info = build_infosheet_data(sections, [{"text": sample_text}])
    addr = info.get("courier_address_display")
    assert "Vijaypur" in addr or "473111" in addr

def test_issue8_client_contacts_email_and_contact3():
    """Issue 8: Nodal officer raw email without E-mail prefix and site contact officer for Client Contact 3."""
    sample_text = """
    Nodal Officer: Shri Sheew Shankar
    sheewshankar@gail.co.in
    Phone: 07544-274444

    Site Contact Officer: Shri Megha Ram Meena
    mrmeena@gail.co.in
    """
    sections = [{"section_name": "Contacts", "fields": []}]
    info = build_infosheet_data(sections, [{"text": sample_text}])
    assert "Sheew Shankar" in info.get("client_name_2_display")
    assert info.get("client_email_2_display") == "sheewshankar@gail.co.in"
    assert info.get("client_name_3_display") == "Megha Ram Meena"
    assert info.get("client_email_3_display") == "mrmeena@gail.co.in"

def test_issue9_health_check_na_vs_missing_classification():
    """Issue 9: Unextracted fields defaulting to NA must be classified as MISSING rather than N/A."""
    sections = [
        {
            "section_name": "Sample Section",
            "fields": [
                {"label": "Reference ID / NIT No", "value": "GEM/2026/B/7306631"}
            ]
        }
    ]
    info = build_infosheet_data(sections, [{"text": "Sample text"}])
    statuses = info.get("_info_sheet_statuses", {})
    summary = info.get("status_summary", {})
    assert summary.get(FIELD_STATUS_MISSING, 0) > 0
    assert info.get("website") == "⚠️ MISSING"
    assert info.get("tender_name") == "⚠️ MISSING"

def test_generalization_financial_criteria_applicable():
    """Generalization: Financial criteria fields must NOT be suppressed to Not Applicable when values are present."""
    sample_text = """
    BID EVALUATION CRITERIA (BEC)
    Financial Criteria: Applicable
    Annual Turnover Limit: Rs. 50 Lakhs
    Working Capital Value: Rs. 20 Lakhs
    """
    sections = [
        {
            "section_name": "Financial",
            "fields": [
                {"label": "Annual Turnover Limit", "value": "Rs. 50 Lakhs"},
                {"label": "Working Capital Value", "value": "Rs. 20 Lakhs"}
            ]
        }
    ]
    info = build_infosheet_data(sections, [{"text": sample_text}])
    assert info.get("working_capital_type_display") != "Not Applicable"
    assert info.get("avg_annual_turnover_type_display") != "Not Applicable"
    assert info.get("working_capital_value_display") in ("Rs. 20 Lakhs", "₹20 Lakhs", "20 Lakhs", "₹20,00,000.00", "₹20,00,000")
    assert info.get("avg_annual_turnover_value_display") in ("Rs. 50 Lakhs", "₹50 Lakhs", "50 Lakhs", "₹50,00,000.00", "₹50,00,000")

def test_generalization_different_disclaimer_wording():
    """Generalization: Alternate disclaimer phrasing must be stripped cleanly without eating valid documents."""
    sections = [
        {
            "section_name": "Checklist",
            "fields": [
                {
                    "label": "Document required from seller",
                    "value": "Experience Criteria, OEM Authorization Certificate, ISO 9001 Certificate, If bidder claims exemption under MSE or Startup policy the supporting proof must be uploaded for evaluation by buyer, Technical Compliance Sheet"
                }
            ]
        }
    ]
    docs = collect_repeated_documents(sections)
    descriptions = [d["description"] for d in docs]
    assert "Experience Criteria" in descriptions
    assert "OEM Authorization Certificate" in descriptions
    assert "ISO 9001 Certificate" in descriptions
    assert "Technical Compliance Sheet" in descriptions
    assert not any("claims exemption under MSE" in d for d in descriptions)
