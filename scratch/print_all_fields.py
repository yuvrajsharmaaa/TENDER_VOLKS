import json
import sys
sys.stdout.reconfigure(encoding='utf-8')

with open("backend/app/storage/jobs/6b266bb1-6cd4-4db8-96b2-61d488f66122/tender_detail.json", "r", encoding="utf-8") as f:
    data = json.load(f)

print("ALL FIELDS EXTRACTED (JSON):")
for sec in data.get("infoSheetSections", []):
    print(f"[{sec.get('name')}]")
    for f in sec.get("fields", []):
        val = str(f["value"])
        print(f"  {f['label']}: {val}")
