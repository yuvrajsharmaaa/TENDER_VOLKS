import json
import sys
from backend.app.api.routes.tenders import _regenerate_infosheet_workbook
import openpyxl

sys.stdout.reconfigure(encoding='utf-8')

job_id = "6a8a4542-c333-4d64-b34a-930a9e778165"
with open(fr"c:\Users\Asus\Desktop\Tender_Volks\main\backend\app\storage\jobs\{job_id}\tender_detail.json", "r", encoding="utf-8") as f:
    payload = json.load(f)

xlsx_path = _regenerate_infosheet_workbook(job_id, payload)
print(f"Regenerated workbook at {xlsx_path}")

wb = openpyxl.load_workbook(str(xlsx_path))
ws = wb["InfoSheet"]

for r in range(32, 38):
    row_vals = [ws.cell(row=r, column=i).value for i in range(1, 7)]
    print(f"Row {r:02d}: {row_vals!r}")
