import os
import psycopg2
import pandas as pd
from dotenv import load_dotenv

load_dotenv(".env.dev")
conn = psycopg2.connect(os.getenv("DATABASE_URL"))

df = pd.read_sql("""
    SELECT 
        o.tender_no,
        o.outcome,
        i.tender_value,
        i.emd_amount,
        i.emd_required,
        i.avg_annual_turnover_value AS turnover_req,
        i.technical_eligibility_age AS exp_years,
        i.maf_required,
        i.pbg_percentage,
        i.delivery_time_supply AS delivery_days,
        i.organization,
        i.department
    FROM tender_outcomes o
    JOIN tender_information i ON o.tender_id = i.tender_id
    WHERE o.outcome IN ('Won', 'Lost');
""", conn)

print(f"Total linked Won/Lost rows analyzed: {len(df)}")
print("\n=== FEATURE COMPLETENESS (%) ===")
for col in df.columns:
    if col in ('tender_no', 'outcome'): 
        continue
    non_null_cnt = df[col].notna().sum()
    pct = (non_null_cnt / len(df)) * 100 if len(df) > 0 else 0
    if col in ('tender_value', 'emd_amount', 'turnover_req'):
        real_cnt = (df[col] > 10.0).sum()
        real_pct = (real_cnt / len(df)) * 100 if len(df) > 0 else 0
        print(f"{col:<20}: non-null: {non_null_cnt}/{len(df)} ({pct:.1f}%) | valid > Rs.10: {real_cnt}/{len(df)} ({real_pct:.1f}%)")

    else:
        print(f"{col:<20}: non-null: {non_null_cnt}/{len(df)} ({pct:.1f}%)")

print("\n=== 10 REAL SPOT-CHECK ROWS WITH EXTRACTED FEATURES ===")
sample = df[df["tender_value"].notna() & (df["tender_value"] > 1000)].head(10)
for idx, r in sample.iterrows():
    tv_str = f"Rs. {r['tender_value']:,.2f}"
    emd_str = f"Rs. {r['emd_amount']:,.2f}" if pd.notna(r['emd_amount']) else "None"
    to_str = f"Rs. {r['turnover_req']:,.2f}" if pd.notna(r['turnover_req']) else "None"
    org_str = str(r['organization']) if pd.notna(r['organization']) else "None"
    print(f"[{r['tender_no']}] ({r['outcome']}) | Value: {tv_str:<18} | EMD: {emd_str:<15} | Turnover: {to_str:<15} | Org: {org_str[:25]:<25} | Delivery: {r['delivery_days']}d | MAF: {r['maf_required']}")

conn.close()
