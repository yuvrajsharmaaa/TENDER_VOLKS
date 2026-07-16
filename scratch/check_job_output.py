import json
from pathlib import Path

job_id = "0a77f878-21d2-4024-86e7-e22b6fe720e3"
job_dir = Path(r"c:\Users\Asus\Desktop\Tender_Volks\main\backend\app\storage\jobs") / job_id

detail_path = job_dir / "tender_detail.json"
if detail_path.exists():
    with open(detail_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    print("=== TENDER DETAIL ===")
    raw_pages = data.get("rawTextPages", [])
    print(f"Total rawTextPages: {len(raw_pages)}")
    with open(r"c:\Users\Asus\Desktop\Tender_Volks\main\scratch\raw_ocr_dump.txt", "w", encoding="utf-8") as out:
        for page in raw_pages:
            out.write(f"=== PAGE {page.get('page')} ===\n")
            out.write(page.get('text', '') + "\n\n")
    print("Dumped rawTextPages to scratch/raw_ocr_dump.txt")
else:
    print(f"tender_detail.json not found!")
