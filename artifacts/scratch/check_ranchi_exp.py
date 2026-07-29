import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

job_id = "06e824d6-0d81-454e-abba-68e951e85170"
path = fr"c:\Users\Asus\Desktop\Tender_Volks\main\backend\app\storage\jobs\{job_id}\tender_detail.json"

with open(path, "r", encoding="utf-8") as f:
    data = json.load(f)

print("Title:", data.get("title"))

for sec in data.get("infoSheetSections", []):
    for f in sec.get("fields", []):
        lbl = f.get("label", "")
        val = f.get("value")
        fn = f.get("field_name")
        if any(k in lbl.lower() for k in ["experience", "years", "eligibility", "delivery", "order", "payment"]):
            print(f"Field: label={lbl!r}, val={val!r}, fn={fn!r}")
