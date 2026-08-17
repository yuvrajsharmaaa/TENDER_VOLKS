import os
import psycopg2
import json
from dotenv import load_dotenv

load_dotenv(".env.dev")

db_url_local = "postgresql://postgres:postgres@127.0.0.1:5433/tender_db"

try:
    conn = psycopg2.connect(db_url_local)
    cursor = conn.cursor()
    
    cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'tender_information'")
    cols = [r[0] for r in cursor.fetchall()]
    
    # Query latest tender_information row as dictionary
    cursor.execute("SELECT * FROM public.tender_information ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()
    if row:
        row_dict = dict(zip(cols, row))
        print("Latest Tender Information JSON:")
        # Convert datetime/numeric values to string for printing
        clean_dict = {}
        for k, v in row_dict.items():
            if v is not None:
                clean_dict[k] = str(v)
            else:
                clean_dict[k] = None
        print(json.dumps(clean_dict, indent=2))
        
        # Let's search documents associated with this tender
        cursor.execute("SELECT id, name, origin, url FROM public.documents WHERE tender_id = %s", (row_dict.get('tender_id'),))
        docs = cursor.fetchall()
        print("\nAssociated Documents:")
        for d in docs:
            print(f"Doc ID: {d[0]} | Name: {d[1]} | Origin: {d[2]}")
            
    conn.close()
except Exception as e:
    print("Error:", e)
