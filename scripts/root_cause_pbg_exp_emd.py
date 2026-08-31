import os, sys, fitz, ast
from pathlib import Path
import pandas as pd
from dotenv import load_dotenv

load_dotenv(".env.dev")
df_master = pd.read_csv("master-tenders.csv").set_index("tender_no")

sample_tenders = [
    ("2024_IPGCL_266724_1", "IPGCL Tender"),
    ("02252518B", "IREPS Railway Tender"),
    ("0326D0043A", "Direct HVAC Tender"),
    ("2025_CRIS_ELECT_11", "CRIS Railway Electrical"),
    ("GEM/2024/B/5176335", "GeM Public Bid"),
    ("2025_AAI_248919_1", "AAI Airport Tender"),
    ("2025_ONGC_257559_1", "ONGC Energy Tender"),
    ("56256192A", "Railways Commercial Bid")
]

print("=" * 80)
print("DEEP ROOT-CAUSE ANALYSIS: PBG%, EXPERIENCE, & EMD ACROSS REAL TENDERS")
print("=" * 80)

for t_no, desc in sample_tenders:
    if t_no not in df_master.index:
        continue
    row = df_master.loc[t_no]
    sf_raw = str(row["source_files"])
    folder = str(row["folder_path"]) if str(row["folder_path"]) != "nan" else "tender-documents"
    files = ast.literal_eval(sf_raw) if sf_raw.startswith("[") else [sf_raw]
    pdfs = [f for f in files if str(f).lower().endswith('.pdf')]
    if not pdfs:
        continue
    p_file = pdfs[0]
    p_path = Path(folder) / p_file
    if not p_path.exists():
        continue
        
    doc = fitz.open(p_path)
    print(f"\n[{t_no}] ({desc}) - File: {p_file} ({len(doc)} pages)")
    
    # 1. Search PBG / Performance Security
    pbg_hits = []
    # 2. Search Experience / Past work
    exp_hits = []
    # 3. Search EMD
    emd_hits = []
    
    for p_idx in range(len(doc)):
        txt = doc[p_idx].get_text()
        for line in txt.split('\n'):
            line_l = line.lower()
            if any(k in line_l for k in ['performance security', 'performance guarantee', 'epbg', 'security deposit', 'pbg']):
                if any(c in line for c in ['%', 'percent', 'lakh', 'rs']):
                    clean_l = ''.join(c for c in line.strip() if ord(c) < 128)
                    pbg_hits.append(f"p.{p_idx+1}: {clean_l}")
            if any(k in line_l for k in ['past experience', 'experience criteria', 'years of experience', 'similar work', 'work experience']):
                if any(c in line_l for c in ['year', 'yr', 'completed', 'work']):
                    clean_l = ''.join(c for c in line.strip() if ord(c) < 128)
                    exp_hits.append(f"p.{p_idx+1}: {clean_l}")
            if any(k in line_l for k in ['earnest money', 'emd', 'bid security']):
                if any(c in line for c in ['rs', 'inr', 'exempt', 'nil', 'lakh', 'crore']):
                    clean_l = ''.join(c for c in line.strip() if ord(c) < 128)
                    emd_hits.append(f"p.{p_idx+1}: {clean_l}")

    print("  * PBG / Performance Security:")
    if pbg_hits:
        for h in pbg_hits[:3]: print("    ", h)
    else:
        print("     [NOT PRESENT in document / Standard GTC default]")

    print("  * Technical Experience Criteria:")
    if exp_hits:
        for h in exp_hits[:3]: print("    ", h)
    else:
        print("     [NOT PRESENT / No minimum experience required]")

    print("  * EMD / Bid Security:")
    if emd_hits:
        for h in emd_hits[:3]: print("    ", h)
    else:
        print("     [NOT PRESENT / Zero / Exempted]")
