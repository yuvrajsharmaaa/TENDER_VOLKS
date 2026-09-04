import pytest
from unittest.mock import MagicMock
from backend.app.services.llm_field_resolver import LLMFieldResolver, _fmt_years
from backend.app.services.tender_mapper import is_unconditional_financial_exemption

def test_fmt_years():
    assert _fmt_years("7 years") == "7"
    assert _fmt_years("7") == "7"
    assert _fmt_years("seven") == "7"
    assert _fmt_years("three financial years") == "3"
    assert _fmt_years(None) is None
    assert _fmt_years("") is None

def test_is_unconditional_financial_exemption():
    # 1. Unconditional exemption -> True
    text1 = "SECTION-II: BID EVALUATION CRITERIA. Financial Criteria: Not Applicable. Technical criteria as below."
    assert is_unconditional_financial_exemption(text1) is True

    text2 = "BEC Clause 2: Financial Criteria is Not Applicable for this tender."
    assert is_unconditional_financial_exemption(text2) is True

    # 2. Conditional exemption for MSE / Startups only -> False
    text3 = "Financial criteria is not applicable for MSE / Startups. For other bidders, turnover shall be Rs. 61 Lakh."
    assert is_unconditional_financial_exemption(text3) is False

    text4 = "BEC Clause: Financial criteria: Not Applicable in case of MSE bidders. Non-MSE bidders must meet Rs. 50 Lakh turnover."
    assert is_unconditional_financial_exemption(text4) is False

    # 3. Denial of relaxation -> False
    text5 = "Relaxation in financial criteria: Not Applicable. All bidders must submit audited balance sheets."
    assert is_unconditional_financial_exemption(text5) is False

def test_anchor_monetary_with_multipliers():
    resolver = LLMFieldResolver()

    # Case 1: Source text has 32.00 under table with "(Rs. in Lakhs)" header
    doc_text_lakh = """
    SECTION-II: BID EVALUATION CRITERIA (BEC)
    Table-1: Minimum Executed Order Value (Rs. in Lakhs)
    Single order: 32.00
    Two orders: 16.00
    Three orders: 8.00
    """
    normalized_lakh = " ".join(doc_text_lakh.split())

    # LLM outputs "Rs. 32.00 Lac"
    anchor1 = resolver._anchor_monetary_with_multipliers("Rs. 32.00 Lac", doc_text_lakh, normalized_lakh)
    assert anchor1 is not None

    # LLM outputs expanded full rupee "₹32,00,000"
    anchor2 = resolver._anchor_monetary_with_multipliers("₹32,00,000", doc_text_lakh, normalized_lakh)
    assert anchor2 is not None

    # Case 2: Source text has full rupees "Rs. 32,00,000/-"
    doc_text_rupees = "Bidder must have executed single order of value not less than Rs. 32,00,000/- in preceding 7 years."
    normalized_rupees = " ".join(doc_text_rupees.split())

    # LLM outputs "Rs. 32.00 Lakh"
    anchor3 = resolver._anchor_monetary_with_multipliers("Rs. 32.00 Lakh", doc_text_rupees, normalized_rupees)
    assert anchor3 is not None

    # Case 3: Net worth "Must be positive"
    doc_text_nw = "Net worth of the bidder should be positive as per audited financial results."
    normalized_nw = " ".join(doc_text_nw.split())
    anchor4 = resolver._anchor_monetary_with_multipliers("Must be positive", doc_text_nw, normalized_nw)
    assert anchor4 is not None

    # Case 4: Hallucinated value not present in text -> returns None
    anchor_fake = resolver._anchor_monetary_with_multipliers("Rs. 999.00 Lakh", doc_text_lakh, normalized_lakh)
    assert anchor_fake is None

def test_validate_and_anchor_custom_eligibility_criteria_semantic_fallback():
    resolver = LLMFieldResolver()
    doc_text = """
    SECTION-II: BID EVALUATION CRITERIA
    Technical Criteria:
    The bidder must have successfully executed supply, installation, testing and commissioning of 48V VRLA Battery Bank.
    Minimum single order value Rs. 32.00 Lakhs.
    """
    # LLM output rephrases slightly or uses full rupee figures
    llm_criteria = "Supply, installation, testing and commissioning of 48V VRLA Battery Bank with minimum executed value ₹32,00,000."
    anchor = resolver._validate_and_anchor("custom_eligibility_criteria_display", llm_criteria, doc_text)
    assert anchor is not None

def test_validate_and_anchor_eligibility_years():
    resolver = LLMFieldResolver()
    doc_text = "The prior experience should be during preceding 7 years reckoned from the bid due date."
    anchor = resolver._validate_and_anchor("eligibility_criterion_years_display", "7", doc_text)
    assert anchor is not None

    anchor_fake = resolver._validate_and_anchor("eligibility_criterion_years_display", "25", doc_text)
    assert anchor_fake is None

def test_bec_llm_resolution_authoritative_override():
    resolver = LLMFieldResolver()
    resolver.provider = "gemini"
    resolver._sdk_type = "genai_v2"
    resolver._init_gemini_client = MagicMock()
    resolver.api_key = "AIzaSyRealKeyStyleForTesting"
    resolver.enabled = True

    mock_json = """
    {
        "custom_eligibility_criteria": "Supply, installation, testing and commissioning of VRLA Battery Bank",
        "order_value_1": "Rs. 32.00 Lakh",
        "avg_annual_turnover_value": "Rs. 61.00 Lakh",
        "eligibility_criterion_years": "7"
    }
    """
    resolver._call_gemini_v2 = MagicMock(return_value=mock_json)
    resolver._call_openai_compatible = MagicMock(return_value=mock_json)

    atc_text = """
    SECTION-II: BID EVALUATION CRITERIA
    Table-1: Minimum Executed Order Value (Rs. in Lakhs)
    Single order: 32.00
    Minimum Average Annual Turnover: Rs. 61.00 Lakhs
    Technical: Supply, installation, testing and commissioning of VRLA Battery Bank in preceding 7 years.
    """

    res = resolver.resolve(atc_text, [
        "custom_eligibility_criteria_display",
        "order_value_1_display",
        "avg_annual_turnover_value_display",
        "eligibility_criterion_years_display"
    ])

    assert res["order_value_1_display"]["value"] == "Rs. 32.00 Lakh"
    assert res["avg_annual_turnover_value_display"]["value"] == "Rs. 61.00 Lakh"
    assert res["eligibility_criterion_years_display"]["value"] == "7"
    assert "Supply, installation" in res["custom_eligibility_criteria_display"]["value"]
