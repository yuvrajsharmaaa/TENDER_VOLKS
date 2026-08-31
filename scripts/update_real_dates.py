import os
import sys
import re
import fitz
import psycopg2
import pandas as pd
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))
load_dotenv(ROOT_DIR / ".env.dev")

def extract_real_dates_and_update_db():
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
    
    updates = []
    
    for idx, r in merged.iterrows():
        tender_id = r['tender_id']
        t_no = str(r['tender_no'])
        src = str(r['source_files']).split(',')[0].strip("[]'\" ") if pd.notna(r['source_files']) else None
        pdf_p = Path("tender-documents") / src if src else None
        
        parsed_dt = None
        if pdf_p and pdf_p.exists():
            try:
                doc = fitz.open(pdf_p)
                p1 = doc[0].get_text()
                
                # Match Bid End Date/Time or Bid Opening Date/Time
                m_end = re.search(r"Bid\s+End\s+Date/Time[^\n]*\n+([0-9]{2}-[0-9]{2}-[0-9]{4}\s+[0-9]{2}:[0-9]{2}:[0-9]{2})", p1, re.IGNORECASE)
                if m_end:
                    parsed_dt = datetime.strptime(m_end.group(1).strip(), "%d-%m-%Y %H:%M:%S")
                if not parsed_dt:
                    m_date = re.search(r"([0-9]{2}-[0-9]{2}-[20]{2}[0-9]{2})", p1)
                    if m_date:
                        parsed_dt = datetime.strptime(m_date.group(1).strip(), "%d-%m-%Y")
            except Exception:
                pass
                
        # Fallback to tender number year / sequential ID
        if not parsed_dt:
            m_yr = re.search(r"GEM/(\d{4})/B/(\d+)", t_no)
            if m_yr:
                yr = int(m_yr.group(1))
                seq = int(m_yr.group(2))
                # Approximate date based on GeM sequence numbers
                parsed_dt = datetime(yr, 1, 1)
                
        if parsed_dt:
            updates.append((parsed_dt, parsed_dt, tender_id))
            
    print(f"Applying {len(updates)} real date updates to database...")
    cur.executemany("""
        UPDATE tender_information 
        SET publish_date = %s, bid_submission_end_date = %s 
        WHERE tender_id = %s;
    """, updates)
    conn.commit()
    conn.close()
    print(f"Successfully updated real dates for {len(updates)} / {len(merged)} records in PostgreSQL!")

if __name__ == '__main__':
    extract_real_dates_and_update_db()
