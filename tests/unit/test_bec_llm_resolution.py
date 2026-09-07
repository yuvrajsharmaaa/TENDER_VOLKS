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

def test_bec_llm_resolution_claude_tool_use():
    resolver = LLMFieldResolver(api_key="sk-ant-test-key-12345")
    resolver.enabled = True

    mock_block = MagicMock()
    mock_block.type = "tool_use"
    mock_block.name = "extract_missing_fields"
    mock_block.input = {
        "custom_eligibility_criteria": "Supply, installation, testing and commissioning of VRLA Battery Bank",
        "order_value_1": "Rs. 32.00 Lakh",
        "avg_annual_turnover_value": "Rs. 61.00 Lakh",
        "eligibility_criterion_years": "7",
    }
    mock_response = MagicMock()
    mock_response.content = [mock_block]
    mock_response.stop_reason = "end_turn"
    mock_response.usage.input_tokens = 200
    mock_response.usage.output_tokens = 60
    mock_response.usage.cache_creation_input_tokens = 0
    mock_response.usage.cache_read_input_tokens = 0
    resolver.client.messages.create = MagicMock(return_value=mock_response)

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

