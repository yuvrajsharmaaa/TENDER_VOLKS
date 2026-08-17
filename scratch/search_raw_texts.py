import sys
import re
from pathlib import Path
import fitz  # PyMuPDF

# Find Rajahmundry and Visakhapatnam PDFs
rajahmundry_pdf = None
visakhapatnam_pdf = None

for p in Path("backend/app/storage").rglob("*.pdf"):
    if "Rajahmundry" in p.name and rajahmundry_pdf is None:
        rajahmundry_pdf = p
    elif "Visakhapatnam" in p.name and visakhapatnam_pdf is None:
        visakhapatnam_pdf = p

def search_text_context(pdf_path: Path, label: str):
    print(f"\n==========================================================================")
    print(f"SEARCHING FOR {label!r} IN {pdf_path.name}")
    print(f"==========================================================================")
    
    doc = fitz.open(str(pdf_path))
    pages_text = []
    for idx, page in enumerate(doc):
        text = page.get_text()
        matches = list(re.finditer(re.escape(label), text, re.IGNORECASE))
        if matches:
            print(f"Found {len(matches)} match(es) on Page {idx + 1}:")
            for m in matches:
                start = max(0, m.start() - 150)
                end = min(len(text), m.end() + 150)
                print(f"--- MATCH AT INDEX {m.start()} ---")
                print(text[start:end])
                print("-" * 50)
        pages_text.append(text)
    
    full_text = "\n".join(pages_text)
    if not any(re.search(re.escape(label), t, re.IGNORECASE) for t in pages_text):
        print(f"Result: Literal string {label!r} DOES NOT exist in the PDF text.")

for pdf_p in [rajahmundry_pdf, visakhapatnam_pdf]:
    if pdf_p and pdf_p.exists():
        for phrase in ["Table-1", "Minimum Executed Order", "Financial Criteria"]:
            search_text_context(pdf_p, phrase)
    else:
        print(f"PDF path {pdf_p} does not exist.")
