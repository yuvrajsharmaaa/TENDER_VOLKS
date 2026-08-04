import json
import sys
from backend.app.services.tender_mapper import build_infosheet_data

sys.stdout.reconfigure(encoding='utf-8')

job_id = "526f4449-2e3b-4e7a-9c53-9a91d4c1b617"
path = fr"c:\Users\Asus\Desktop\Tender_Volks\main\backend\app\storage\jobs\{job_id}\tender_detail.json"

with open(path, "r", encoding="utf-8") as f:
    data = json.load(f)

sections = data.get("infoSheetSections", [])
pages = data.get("rawTextPages", [])

infosheet_data = build_infosheet_data(sections, pages, job_id=job_id)

print("\n--- ALL INFOSHEET_DATA KEYS AND VALUES FOR RANCHI ---")
for k, v in infosheet_data.items():
    if not k.startswith("_"):
        st = infosheet_data.get("_info_sheet_statuses", {}).get(k)
        print(f"  {k}: {v!r} (status: {st})")
