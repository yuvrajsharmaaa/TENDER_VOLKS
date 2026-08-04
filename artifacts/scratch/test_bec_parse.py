import json
import re

job_id = "526f4449-2e3b-4e7a-9c53-9a91d4c1b617"
path = fr"c:\Users\Asus\Desktop\Tender_Volks\main\backend\app\storage\jobs\{job_id}\tender_detail.json"

with open(path, "r", encoding="utf-8") as f:
    data = json.load(f)

pages = data.get("rawTextPages", [])
full_text = "\n".join([p.get("text", "") for p in pages])

# Search for single / two / three order values in full_text
print("Search 1 order:")
m1 = re.search(r"(?:one|1st|single)\s*(?:single\s*)?(?:completed\s*)?(?:order|work)[^\n]*?Rs\.?\s*([\d,]+(?:\.\d+)?)", full_text, re.IGNORECASE)
if m1: print("Found 1st work:", m1.group(1))

print("Search 2 order:")
m2 = re.search(r"(?:two|2nd)\s*(?:completed\s*)?(?:orders|works)[^\n]*?Rs\.?\s*([\d,]+(?:\.\d+)?)", full_text, re.IGNORECASE)
if m2: print("Found 2nd work:", m2.group(1))

print("Search 3 order:")
m3 = re.search(r"(?:three|3rd)\s*(?:completed\s*)?(?:orders|works)[^\n]*?Rs\.?\s*([\d,]+(?:\.\d+)?)", full_text, re.IGNORECASE)
if m3: print("Found 3rd work:", m3.group(1))

# Check child ATC files for text
import fitz
import os

child_folder = fr"c:\Users\Asus\Desktop\Tender_Volks\main\backend\app\storage\jobs\{job_id}\extracted_children"
for f_name in os.listdir(child_folder):
    if f_name.endswith(".pdf"):
        doc = fitz.open(os.path.join(child_folder, f_name))
        atc_t = "".join([page.get_text() for page in doc])
        for term in ["34,02,000", "34,90,000", "13,39,000", "34.02", "34.90", "13.39"]:
            if term in atc_t:
                print(f"File {f_name} contains term '{term}'")
