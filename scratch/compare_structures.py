
import sys
import re
from pathlib import Path
import fitz

def safe_str(s):
    return str(s).encode("ascii", "ignore").decode("ascii")

pdf_noida = Path("backend/app/storage/objects/tender-pdfs/a6a5034c-efe2-4d5f-b0a9-3d278b3f8188/GAIL Split Noida.pdf")
pdf_rajahmundry = Path("backend/app/storage/objects/tender-pdfs/05f9096e-26e9-4c57-9937-34b222e8ea41/GAIL Rajahmundry NiCd (1).pdf")
pdf_visakhapatnam = Path("backend/app/storage/objects/tender-pdfs/8cf1c0c8-6c43-4224-9907-ec57a51cb3e1/GAIL Visakhapatnam B&BC VRLA.pdf")

def get_pdf_text(p: Path) -> str:
    if not p.exists(): return ""
    doc = fitz.open(str(p))
    return "\n".join([page.get_text() for page in doc])

text_noida = get_pdf_text(pdf_noida)
text_raj = get_pdf_text(pdf_rajahmundry)
text_viz = get_pdf_text(pdf_visakhapatnam)

def analyze_doc(name: str, text: str):
    print(f"\n==========================================================================")
    print(f"STRUCTURAL ANALYSIS FOR: {name} (Length: {len(text)} chars)")
    print(f"==========================================================================")
    
    gem_m = re.search(r"(Bid\s+Document|Government\s+e\-Marketplace)", text, re.IGNORECASE)
    print(f"Header type: {'GeM Standard Portal Header' if gem_m else 'Non-GeM Custom Header'}")
    
    sections = re.findall(r"\n\s*(SECTION-[I|V|X]+[^\n]*)", text, re.IGNORECASE)
    print(f"Sections found ({len(sections)}): {safe_str(sections[:10])}")
    
    bec_clauses = re.findall(r"\n\s*(\b2\.\d\b[^\n]*)", text)
    print(f"BEC Clauses (2.x): {safe_str(bec_clauses[:10])}")
    
    emd_matches = [line.strip() for line in text.split("\n") if "emd" in line.lower()]
    print(f"EMD Lines Count: {len(emd_matches)}")
    print(f"  First 3 EMD lines: {[safe_str(l) for l in emd_matches[:3]]}")
    
    wc_matches = [line.strip() for line in text.split("\n") if "working capital" in line.lower()]
    print(f"Working Capital Lines ({len(wc_matches)}): {[safe_str(l) for l in wc_matches[:3]]}")
    
    pay_matches = [line.strip() for line in text.split("\n") if "payment" in line.lower()]
    print(f"Payment Terms Lines ({len(pay_matches)}): {[safe_str(l) for l in pay_matches[:5]]}")

analyze_doc("GAIL Split Noida", text_noida)
analyze_doc("GAIL Rajahmundry NiCd", text_raj)
analyze_doc("GAIL Visakhapatnam B&BC VRLA", text_viz)
