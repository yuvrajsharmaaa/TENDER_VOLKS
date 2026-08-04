import fitz
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')

pdf_path = r"c:\Users\Asus\Desktop\Tender_Volks\main\backend\app\storage\jobs\526f4449-2e3b-4e7a-9c53-9a91d4c1b617\extracted_children\atc_fbc694871ade2db2.pdf"

doc = fitz.open(pdf_path)
full_text = "\n".join([page.get_text() for page in doc])

for term in ["34.02", "34.90", "13.39", "70%", "30%", "Doranda", "834 002", "834002", "Mecon"]:
    matches = [m.start() for m in re.finditer(re.escape(term), full_text, re.IGNORECASE)]
    print(f"Term '{term}': {len(matches)} matches")
    for idx in matches[:3]:
        snippet = full_text[max(0, idx-100):min(len(full_text), idx+100)].replace("\n", " ")
        print(f"   --> {snippet}")
