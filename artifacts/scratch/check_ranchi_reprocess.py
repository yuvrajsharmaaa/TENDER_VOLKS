import json
import sys
from pathlib import Path
from backend.app.services.tender_mapper import build_infosheet_data

sys.stdout.reconfigure(encoding='utf-8')

job_id = "06e824d6-0d81-454e-abba-68e951e85170"
job_dir = Path(fr"c:\Users\Asus\Desktop\Tender_Volks\main\backend\app\storage\jobs\{job_id}")

with open(job_dir / "tender_detail.json", "r", encoding="utf-8") as f:
    payload = json.load(f)

sections = payload.get("infoSheetSections", [])
pages = payload.get("rawTextPages", [])

infosheet_data = build_infosheet_data(sections, pages, job_id=job_id)

print("\n--- RANCHI INFOSHEET DATA VERIFICATION ---")
fields_to_check = [
    "experience_years_display", "bid_validity_days_display",
    "order_value_1_display", "order_value_2_display", "order_value_3_display",
    "payment_terms_supply_display", "payment_terms_installation_display",
    "delivery_time_supply_display", "installation_inclusive_display", "delivery_time_installation_display"
]

for k in fields_to_check:
    print(f"  {k}: {infosheet_data.get(k)!r}")
