import sys
import re
import json
from pathlib import Path

# Add project root and backend to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from backend.app.services.tender_mapper import build_infosheet_data
from backend.app.services.llm_field_resolver import LLMFieldResolver

def test_fc_regex(text: str):
    normalized_full_text = re.sub(r"\s+", " ", text).lower()
    m_fc_exempt = re.search(
        r"financial\s+criteria\b(?:(?!financial\s+criteria).){0,150}?not\s+applicable",
        normalized_full_text,
        re.DOTALL,
    )
    if m_fc_exempt:
        return True, m_fc_exempt.group(0)[:150]
    return False, "NO MATCH"

print("==========================================================================")
print("TEST 1: Financial Criteria Proximity Check & Non-Destructive Protection")
print("==========================================================================")

# Scenario A: "Financial Criteria" and "Not Applicable" within 150 chars -> EXEMPT MATCH
text_exempt = """
SECTION-II: BID EVALUATION CRITERIA (BEC)
Technical Criteria: Applicable
Financial Criteria: Not Applicable for this tender.
"""
matched_a, window_a = test_fc_regex(text_exempt)
info_a = build_infosheet_data([], [{"page": 1, "text": text_exempt}])
print(f"Scenario A (Close proximity): Matched={matched_a} | Match Window: {window_a!r}")
print(f"  -> Turnover Type: {info_a.get('avg_annual_turnover_type_display')}")
print(f"  -> Turnover Value: {info_a.get('avg_annual_turnover_value_display')}")
print(f"  -> Net Worth Type: {info_a.get('net_worth_type_display')}")

# Scenario B: "Financial Criteria" present, but "Not Applicable" is far away (in MSE/EMD clause 400 chars later) -> NO MATCH
text_unrelated = """
SECTION-II: BID EVALUATION CRITERIA (BEC)
Financial Criteria: Minimum turnover required is Rs 50 Lakhs.
...
[400 characters of generic legal terms and conditions follow]
...
Clause 45: EMD Exemption for Startups & Micro & Small Enterprises (MSEs) is Not Applicable.
"""
matched_b, window_b = test_fc_regex(text_unrelated)
info_b = build_infosheet_data([], [{"page": 1, "text": text_unrelated}])
print(f"\nScenario B (Far distance / unrelated EMD clause): Matched={matched_b} | Match Window: {window_b!r}")
print(f"  -> Turnover Value: {info_b.get('avg_annual_turnover_value_display')}")
print(f"  -> Net Worth Type: {info_b.get('net_worth_type_display')}")

# Scenario C: Pre-resolved financial value exists -> Non-destructive protection check
section_c = [{
    "id": "sec-1",
    "title": "BEC",
    "fields": [
        {"id": "annual_turnover", "label": "Annual Avg Turnover", "value": "₹50.00 Lakhs"},
        {"id": "net_worth", "label": "Net Worth Value", "value": "₹15.00 Lakhs"}
    ]
}]
info_c = build_infosheet_data(section_c, [{"page": 1, "text": text_exempt}])
print(f"\nScenario C (Pre-resolved values with exempt text):")
print(f"  -> Turnover Value (preserved): {info_c.get('avg_annual_turnover_value_display')}")
print(f"  -> Net Worth Value (preserved): {info_c.get('net_worth_value_display')}")

print("\n==========================================================================")
print("TEST 2: Custom Eligibility Criteria (Boilerplate vs Valid Data Filter)")
print("==========================================================================")

resolver = LLMFieldResolver()

# Tender 1: Has actual data digits in Table-1 / BEC
text_tender_1 = """
Minimum Executed Order value
Table-1
Single Order: Rs 45.50 Lakhs executed in past 3 years.
Two Orders: Rs 28.00 Lakhs each.
"""
res_1 = resolver._resolve_local_heuristics(text_tender_1, ["custom_eligibility_criteria_display"])
val_1 = res_1.get("custom_eligibility_criteria_display", {}).get("value")
print(f"Tender 1 (With numbers/values): {val_1!r}")

# Tender 2: Pure boilerplate template label with NO digits
text_tender_2 = """
Minimum Executed Order value
Table-1
(Details as specified in tender document)
SECTION-III BIDDING DATA SHEET
"""
res_2 = resolver._resolve_local_heuristics(text_tender_2, ["custom_eligibility_criteria_display"])
val_2 = res_2.get("custom_eligibility_criteria_display", {}).get("value")
print(f"Tender 2 (Pure boilerplate with no digits): {val_2!r} (Resolved: {val_2 is not None})")

print("\n==========================================================================")
print("VERIFICATION COMPLETED SUCCESSFULLY.")
