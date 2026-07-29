"""
Verify the key fixes still produce correct results using a synthetic test
that mimics the NiCd Ranchi ATC text patterns.
"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

# Test the build_infosheet_data function directly with synthetic sections and pages
from backend.app.services.tender_mapper import build_infosheet_data

# Simulate sections as would come from ATC parsing of NiCd Ranchi tender
sections = [
    {
        "id": "sec1",
        "title": "Unified Extraction",
        "fields": [
            {"id": "f1", "label": "Tender Name / Title", "value": "GAIL NiCd Ranchi - Supply of Ni-Cd Battery Banks", "status": "extracted"},
            {"id": "f2", "label": "eligibility_criterion_years", "value": "7", "status": "extracted"},
            {"id": "f3", "label": "Bid Validity (Days)", "value": "120", "status": "extracted"},
        ]
    }
]

pages = [
    {
        "page": 1,
        "text": """
SECTION-I - INVITATION FOR BID (IFB)
(A) SCOPE OF SUPPLY: Supply of Ni-Cd Battery Banks at GAIL Ranchi

SECTION-II - BID EVALUATION CRITERIA & EVALUATION METHODOLOGY
1.1 Experience Criteria: The bidder should have experience of executing works during last 7 (seven) years.
1.2 Technical Criteria:
  Table-1: Minimum Executed Order Values
  Schedule 1: Rs. 34.02 Lakhs
  Schedule 2: Rs. 34.90 Lakhs
  Schedule 3: Rs. 13.39 Lakhs

SECTION-V - SCOPE OF WORK
9.0 TERMS OF PAYMENT
70% Payment of Supply portion on receipt of material at site.
30% Payment of Installation portion on successful installation and commissioning.

CONTRACT COMPLETION PERIOD: 3 Months for supply and 30 days for installation.
"""
    }
]

info = build_infosheet_data(sections, pages, job_id="ranchi-test")

print("\n--- Ranchi Synthetic Verification ---")
fields = [
    ("experience_years_display", "7"),
    ("bid_validity_days_display", "120 Days"),
    ("delivery_time_supply_display", "90 Days"),     # 3 months → 90 days
    ("delivery_time_installation_display", "30 Days"),
    ("installation_inclusive_display", "No"),
    ("payment_terms_supply_display", "70%"),
    ("payment_terms_installation_display", "30%"),
]

all_pass = True
for key, expected in fields:
    actual = info.get(key)
    status = "✅" if actual == expected else "❌"
    if actual != expected:
        all_pass = False
    print(f"  {status} {key}: expected={expected!r}, got={actual!r}")

print()
print("Order values (from lakh regex):")
print(f"  order_value_1_display: {info.get('order_value_1_display')}")
print(f"  order_value_2_display: {info.get('order_value_2_display')}")
print(f"  order_value_3_display: {info.get('order_value_3_display')}")

print()
if all_pass:
    print("ALL TESTS PASSED ✅")
else:
    print("SOME TESTS FAILED ❌")
