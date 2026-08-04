
import openpyxl
import sys

sys.stdout.reconfigure(encoding='utf-8')

wb = openpyxl.load_workbook(r"c:\Users\Asus\Desktop\Tender_Volks\main\backend\app\storage\jobs\6a8a4542-c333-4d64-b34a-930a9e778165\GAIL Rajahmundry NiCd (1)_InfoSheet.xlsx")
ws = wb["InfoSheet"]

for r in range(1, 100):
    row_vals = [ws.cell(row=r, column=i).value for i in range(1, 7)]
    if any(row_vals):
        # Print representation to avoid console encoding crashes
        print(f"Row {r:02d}: {row_vals!r}")
