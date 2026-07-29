import json
from pathlib import Path

with open(r"c:\Users\Asus\Desktop\Tender_Volks\main\backend\app\storage\jobs\6a8a4542-c333-4d64-b34a-930a9e778165\tender_detail.json", "r", encoding="utf-8") as f:
    data = json.load(f)

links = data["documents"]["extractedLinkedPdfs"]

# High-priority search: explicit ATC or TENDOC markers
atc_path = None
for l in links:
    if l.get("local_path"):
        local_p = l["local_path"].replace("/app/backend/", "c:/Users/Asus/Desktop/Tender_Volks/main/backend/")
        if Path(local_p).exists() and local_p.lower().endswith(".pdf"):
            url_s = l.get("url", "").lower()
            name_s = l.get("name", "").lower()
            anchor_s = l.get("anchorText", "").lower()
            
            excluding_terms = ["mse", "mii", "gtc", "rules", "list-of-categories", "catalog", "specification", "spec", "drawing", "schedule", "boq"]
            is_explicit_atc = any(k in s for s in (url_s, name_s, anchor_s) for k in ["atc", "tendoc", "buyer1", "buyer_uploaded"]) and not any(k in s for s in (url_s, name_s, anchor_s) for k in excluding_terms)
            is_valid_atc_anchor = l.get("is_atc_anchor") and not any(k in s for s in (url_s, name_s, anchor_s) for k in excluding_terms)
            
            if is_explicit_atc or is_valid_atc_anchor:
                atc_path = Path(local_p)
                print(f"High-priority: Selected {atc_path.name} for link: name={l['name']} url={l['url']}")
                break

if not atc_path:
    # 2. General fallback search if no high-priority match found
    for l in links:
        if l.get("local_path"):
            local_p = l["local_path"].replace("/app/backend/", "c:/Users/Asus/Desktop/Tender_Volks/main/backend/")
            if Path(local_p).exists() and local_p.lower().endswith(".pdf"):
                url_s = l.get("url", "").lower()
                name_s = l.get("name", "").lower()
                anchor_s = l.get("anchorText", "").lower()
                if any(k in s for s in (url_s, name_s, anchor_s) for k in ["upload", "shared", "doc", "buyer", "resource"]):
                    atc_path = Path(local_p)
                    print(f"General fallback: Selected {atc_path.name} for link: name={l['name']} url={l['url']}")
                    break

if not atc_path:
    for l in links:
        if l.get("local_path"):
            local_p = l["local_path"].replace("/app/backend/", "c:/Users/Asus/Desktop/Tender_Volks/main/backend/")
            if Path(local_p).exists() and local_p.lower().endswith(".pdf"):
                atc_path = Path(local_p)
                print(f"Absolute fallback: Selected {atc_path.name} for link: name={l['name']} url={l['url']}")
                break
