import json

with open(r"c:\Users\Asus\Desktop\Tender_Volks\main\backend\app\storage\jobs\6a8a4542-c333-4d64-b34a-930a9e778165\tender_detail.json", "r", encoding="utf-8") as f:
    data = json.load(f)

print("Field statuses in JSON:")
for key in ["client_name_1_display", "client_email_1_display", "client_phone_1_display", "client_name_2_display", "client_email_2_display", "client_phone_2_display"]:
    print(f"  {key}: {data['field_statuses'].get(key)}")

print("\nSections containing 'client':")
for sec in data["infoSheetSections"]:
    for f in sec["fields"]:
        if "client" in f.get("label", "").lower() or "client" in f.get("field_name", "").lower():
            print(f"  Section: {sec['title']} | ID: {f['id']} | Label: {f['label']} | Value: {f['value']}")
