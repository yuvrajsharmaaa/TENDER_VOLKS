import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

job_id = "526f4449-2e3b-4e7a-9c53-9a91d4c1b617"
path = fr"c:\Users\Asus\Desktop\Tender_Volks\main\backend\app\storage\jobs\{job_id}\tender_detail.json"

with open(path, "r", encoding="utf-8") as f:
    data = json.load(f)

print("Title:", data.get("title"))
print("Status Summary:", data.get("status_summary"))

print("\n--- ALL SECTIONS AND FIELDS ---")
for sec in data.get("infoSheetSections", []):
    print(f"\nSECTION: {sec.get('title')}")
    for field in sec.get("fields", []):
        lbl = field.get("label")
        val = field.get("value")
        st = field.get("status")
        src = field.get("source")
        f_name = field.get("field_name")
        print(f"  [{src}] {lbl} (name: {f_name}) -> {val!r} (status: {st})")
