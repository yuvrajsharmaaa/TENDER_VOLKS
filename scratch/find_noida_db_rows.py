import psycopg2
import json

db_url_local = "postgresql://postgres:postgres@127.0.0.1:5433/tender_db"
conn = psycopg2.connect(db_url_local)
cursor = conn.cursor()

cursor.execute("SELECT id, project_id, tender_name FROM public.tender_projects")
projects = cursor.fetchall()
print("Tender Projects:")
for p in projects:
    print(" ", p)

cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'tender_information'")
cols = [c[0] for c in cursor.fetchall()]

cursor.execute("SELECT * FROM public.tender_information")
rows = cursor.fetchall()
print(f"\nTender Information Rows ({len(rows)}):")
for r in rows:
    info_dict = dict(zip(cols, r))
    print(f"\n--- ID {info_dict.get('id')} | Tender ID {info_dict.get('tender_id')} ---")
    for k, v in info_dict.items():
        if v is not None and v != "" and str(v) != "None":
            print(f"  {k}: {v}")

conn.close()
