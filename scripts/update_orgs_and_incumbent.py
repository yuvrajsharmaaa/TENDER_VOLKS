import os
import sys
import re
import fitz
import psycopg2
import pandas as pd
import numpy as np
from pathlib import Path
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))
load_dotenv(ROOT_DIR / ".env.dev")

def canonicalize_org(raw_str):
    if not raw_str or pd.isna(raw_str):
        return None
    s = str(raw_str).upper().strip()
    # Canonical mappings for major Indian PSUs / Departments
    if any(k in s for k in ["GAIL", "GAS AUTHORITY"]):
        return "GAIL"
    if any(k in s for k in ["POWER GRID", "POWERGRID", "PGCIL"]):
        return "POWERGRID"
    if any(k in s for k in ["AIRPORTS AUTHORITY", "AIRPORT AUTHORITY", "AAI"]):
        return "AAI"
    if any(k in s for k in ["AIR FORCE", "IAF"]):
        return "INDIAN_AIR_FORCE"
    if any(k in s for k in ["INDIAN ARMY", "ARMY"]):
        return "INDIAN_ARMY"
    if any(k in s for k in ["INDIAN NAVY", "NAVY"]):
        return "INDIAN_NAVY"
    if any(k in s for k in ["BHARAT PETROLEUM", "BPCL"]):
        return "BPCL"
    if any(k in s for k in ["INDIAN OIL", "IOCL"]):
        return "IOCL"
    if any(k in s for k in ["HINDUSTAN PETROLEUM", "HPCL"]):
        return "HPCL"
    if any(k in s for k in ["NTPC"]):
        return "NTPC"
    if any(k in s for k in ["BHEL", "BHARAT HEAVY"]):
        return "BHEL"
    if any(k in s for k in ["CRIS", "CENTRE FOR RAILWAY INFORMATION"]):
        return "CRIS"
    if any(k in s for k in ["RAILTEL", "RAILWAY", "RAILWAYS", "IREPS"]):
        return "RAILWAYS"
    if any(k in s for k in ["HAL", "HINDUSTAN AERONAUTICS"]):
        return "HAL"
    if any(k in s for k in ["ISRO", "SPACE APPLICATIONS", "VSSC", "URSC"]):
        return "ISRO"
    if any(k in s for k in ["ONGC", "OIL AND NATURAL GAS"]):
        return "ONGC"
    if any(k in s for k in ["MILITARY ENGINEER", "MES"]):
        return "MES"
    if any(k in s for k in ["BSF", "BORDER SECURITY"]):
        return "BSF"
    if any(k in s for k in ["GSECL", "GUJARAT STATE ELECTRICITY"]):
        return "GSECL"
    if any(k in s for k in ["NIT ", "NATIONAL INSTITUTE OF TECHNOLOGY"]):
        return "NIT"
    if any(k in s for k in ["IIT ", "INDIAN INSTITUTE OF TECHNOLOGY"]):
        return "IIT"
    if "N/A" in s or "UNKNOWN" in s or len(s) < 3:
        return None
    # General cleanup
    for noise in ["LIMITED", "LTD", "CORP", "CORPORATION", "GOVT", "GOVERNMENT OF INDIA", "INDIA"]:
        s = s.replace(noise, "").strip()
    return s[:25]

def extract_and_update_db_organizations():
    conn = psycopg2.connect(os.getenv("DATABASE_URL"))
    cur = conn.cursor()
    
    cur.execute("""
        SELECT o.tender_no, i.tender_id 
        FROM tender_outcomes o 
        JOIN tender_information i ON o.tender_id = i.tender_id
        WHERE o.outcome IN ('Won', 'Lost');
    """)
    rows = cur.fetchall()
    
    master_df = pd.read_csv("master-tenders.csv")
    outcomes_df = pd.DataFrame(rows, columns=['tender_no', 'tender_id'])
    merged = outcomes_df.merge(master_df, on='tender_no', how='left')
    
    updated_count = 0
    updates = []
    
    for idx, r in merged.iterrows():
        tender_id = r['tender_id']
        src = str(r['source_files']).split(',')[0].strip("[]'\" ") if pd.notna(r['source_files']) else None
        pdf_p = Path("tender-documents") / src if src else None
        
        raw_org = None
        raw_dept = None
        
        if pdf_p and pdf_p.exists():
            try:
                doc = fitz.open(pdf_p)
                p1 = doc[0].get_text()
                
                m_org = re.search(r"Organisation\s+Name[^\n]*\n+([^\n]+)", p1, re.IGNORECASE)
                if m_org:
                    raw_org = m_org.group(1).strip()
                m_dept = re.search(r"Department\s+Name[^\n]*\n+([^\n]+)", p1, re.IGNORECASE)
                if m_dept:
                    raw_dept = m_dept.group(1).strip()
                if not raw_org:
                    for kw in ["GAIL", "BHEL", "IOCL", "NTPC", "POWERGRID", "ISRO", "INDIAN AIR FORCE", "INDIAN RAILWAYS", "NORTHERN RAILWAY", "WESTERN RAILWAY", "CENTRAL RAILWAY", "MILITARY ENGINEER SERVICES", "BPCL", "HPCL", "ONGC", "CRIS", "GSECL", "AAI", "MES", "BSF", "HAL"]:
                        if kw.lower() in p1.lower():
                            raw_org = kw
                            break
            except Exception:
                pass
                
        canon = canonicalize_org(raw_org or raw_dept)
        if canon:
            updates.append((canon, raw_dept or canon, tender_id))
            updated_count += 1
            
    print(f"Applying {len(updates)} organization updates to database...")
    cur.executemany("""
        UPDATE tender_information 
        SET organization = %s, department = %s 
        WHERE tender_id = %s;
    """, updates)
    conn.commit()
    conn.close()
    print(f"Successfully updated {updated_count} / {len(merged)} records in PostgreSQL!")

if __name__ == '__main__':
    extract_and_update_db_organizations()
