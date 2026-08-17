import fitz
from pathlib import Path

def safe_str(s):
    return str(s).encode("ascii", "ignore").decode("ascii")

pdf_p = Path("backend/app/storage/objects/tender-pdfs/a6a5034c-efe2-4d5f-b0a9-3d278b3f8188/GAIL Split Noida.pdf")
doc = fitz.open(str(pdf_p))

text = "\n".join([page.get_text() for page in doc])
lines = text.split("\n")
for idx in range(250, min(310, len(lines))):
    print(f"Line {idx+1}: {safe_str(repr(lines[idx]))}")
