import os
import sys
import pandas as pd
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv(".env.dev")
DB_URL = os.getenv("DATABASE_URL")

def build_training_view_and_export():
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # 1. Create Postgres View: training_set_win_loss
    cur.execute("DROP VIEW IF EXISTS training_set_win_loss CASCADE;")
    view_sql = """
    CREATE VIEW training_set_win_loss AS
    SELECT 

        o.tender_no,
        o.tender_id,
        o.outcome,
        CASE WHEN o.outcome = 'Won' THEN 1 ELSE 0 END AS is_won,
        o.label_source,
        i.tender_name,
        i.nit_number,
        i.organization,
        i.department,
        i.client,
        i.publish_date,
        i.bid_submission_end_date,
        i.bid_validity_days,
        
        -- Scale & Values
        i.tender_value,
        
        -- EMD: Indicator + Magnitude (0.0 when exempt)
        CASE WHEN i.emd_amount > 0 OR i.emd_required = 'Yes' THEN 1 ELSE 0 END AS emd_required_flag,
        COALESCE(i.emd_amount, 0.0) AS emd_amount,
        
        -- Turnover: Indicator + Magnitude (0.0 when exempt)
        CASE WHEN i.avg_annual_turnover_value > 0 THEN 1 ELSE 0 END AS turnover_req_applicable,
        COALESCE(i.avg_annual_turnover_value, 0.0) AS turnover_required_value,
        
        -- PBG: Indicator + Raw Value (NULL when standard statutory GCC applies)
        CASE WHEN i.pbg_percentage IS NOT NULL AND i.pbg_percentage > 0 THEN 1 ELSE 0 END AS pbg_custom_specified,
        i.pbg_percentage AS pbg_percentage,
        i.pbg_duration AS pbg_duration_months,
        
        -- Security Deposit & LD
        COALESCE(i.sd_percentage, 0.0) AS sd_percentage,
        COALESCE(i.max_ld_percentage, 0.0) AS max_ld_cap_percent,
        
        -- Experience & Delivery
        i.technical_eligibility_age AS technical_experience_years_req,
        i.delivery_time_supply AS delivery_time_supply_days,
        
        -- Qualification & Policy Flags
        COALESCE(i.maf_required, 'No') AS maf_required,
        COALESCE(i.reverse_auction_applicable, 'No') AS reverse_auction_applicable,
        i.created_at AS extraction_timestamp
    FROM tender_outcomes o
    JOIN tender_information i ON o.tender_id = i.tender_id

    WHERE o.outcome IN ('Won', 'Lost');
    """
    cur.execute(view_sql)
    conn.commit()
    print("Created/Updated Postgres view 'training_set_win_loss'")

    # 2. Query view data for export & audit
    cur.execute("SELECT * FROM training_set_win_loss ORDER BY outcome DESC, tender_no ASC;")
    rows = cur.fetchall()
    df = pd.DataFrame(rows)
    print(f"\nTotal rows in training_set_win_loss view: {len(df)}")

    # 3. Export to CSV
    os.makedirs("artifacts", exist_ok=True)
    csv_path = "artifacts/training_set_win_loss.csv"
    df.to_csv(csv_path, index=False)
    print(f"Exported training set CSV to '{csv_path}'")

    # 4. Class balance report
    if not df.empty and 'outcome' in df.columns:
        print("\n=== CLASS DISTRIBUTION (WON vs LOST) ===")
        print(df['outcome'].value_counts())
        print("\nPercentage breakdown:")
        print(df['outcome'].value_counts(normalize=True) * 100)

    # 5. Check exclusion of Won/Lost tenders from total labeled (129 Won, 525 Lost = 654 Total)
    cur.execute("""
        SELECT 
            o.outcome,
            COUNT(*) AS total_labeled,
            COUNT(i.tender_id) AS extracted_and_linked,
            COUNT(*) - COUNT(i.tender_id) AS missing_or_failed
        FROM tender_outcomes o
        LEFT JOIN tender_information i ON o.tender_id = i.tender_id
        WHERE o.outcome IN ('Won', 'Lost')
        GROUP BY o.outcome;
    """)
    stats = cur.fetchall()
    print("\n=== EXTRACTION COVERAGE & EXCLUSION STATS ===")
    for s in stats:
        print(f"Outcome: {s['outcome']:<5} | Total Labeled: {s['total_labeled']:<4} | Extracted & Linked: {s['extracted_and_linked']:<4} | Excluded/Missing: {s['missing_or_failed']:<4}")

    conn.close()

if __name__ == '__main__':
    build_training_view_and_export()
