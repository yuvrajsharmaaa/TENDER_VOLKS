with open(r"c:\Users\Asus\Desktop\Tender_Volks\main\backend\app\api\routes\tenders.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

for idx in range(849, 900):
    if idx < len(lines):
        print(f"{idx+1}: {lines[idx].strip()}")
