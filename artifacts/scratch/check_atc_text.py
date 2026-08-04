import fitz  # PyMuPDF
import os

folder = r"c:\Users\Asus\Desktop\Tender_Volks\main\backend\app\storage\jobs\6a8a4542-c333-4d64-b34a-930a9e778165\extracted_children"

for filename in os.listdir(folder):
    if filename.endswith(".pdf"):
        path = os.path.join(folder, filename)
        doc = fitz.open(path)
        text = ""
        for page in doc:
            text += page.get_text()
        print(f"File {filename}: len={len(text)}")
        for term in ["deevi", "prabhakar", "sunil", "kasturi"]:
            if term in text.lower():
                print(f"  Matches '{term}'")
