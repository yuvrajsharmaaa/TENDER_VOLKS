with open(r"c:\Users\Asus\Desktop\Tender_Volks\main\backend\app\api\routes\tenders.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if "process_pdf" in line:
        print(f"Line {i+1}: {line.strip()}")
