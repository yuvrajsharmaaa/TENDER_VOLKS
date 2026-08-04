import fitz
from pathlib import Path

def safe_str(s):
    return str(s).encode("ascii", "ignore").decode("ascii")

pdf_p = Path("backend/app/storage/objects/tender-pdfs/a6a5034c-efe2-4d5f-b0a9-3d278b3f8188/GAIL Split Noida.pdf")
doc = fitz.open(str(pdf_p))

for idx in range(min(5, len(doc))):
    print(f"\n=== PAGE {idx+1} ===")
    text = doc[idx].get_text()
    for line in text.split("\n"):
        if any(k in line.lower() for k in ["estimated", "value", "5000", "5,00", "500", "emd"]):
            print(" ", safe_str(line.strip()))
