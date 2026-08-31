import os
import sys
import uuid
import ast
import json
import time
import logging
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
import pandas as pd
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

# Ensure project root is in sys.path and load environment
sys.path.insert(0, os.getcwd())
os.environ["LLM_FALLBACK_ENABLED"] = "false"
os.environ["ENABLE_NEO4J"] = "false"
os.environ["OFFLINE_EXTRACTION"] = "true"
load_dotenv(".env.dev")
os.environ["LLM_FALLBACK_ENABLED"] = "false"
os.environ["ENABLE_NEO4J"] = "false"
os.environ["OFFLINE_EXTRACTION"] = "true"

from backend.app.services.pdf_parent_ingest import ingest_parent_tender_pdf
from backend.app.services.tender_mapper import map_extraction_to_tender_information
from backend.app.services.tender_repository import save_tender_information
from backend.app.db.session import SessionLocal

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("batch_backfill")

def get_db_connection():
    load_dotenv(".env.dev")
    db_url = os.getenv("DATABASE_URL", "postgresql://postgres:volks_dev_secure_pass_2026@localhost:5432/tender_db")
    return psycopg2.connect(db_url)

def resolve_pdf_path(primary_file: str, folder: str) -> Path | None:
    if not primary_file or primary_file == 'nan':
        return None
    candidates = [
        Path(primary_file),
        Path(folder) / primary_file if folder and folder != 'nan' else None,
        Path("tender-documents") / os.path.basename(primary_file),
        Path("tender-documents") / primary_file
    ]
    for c in candidates:
        if c and c.exists():
            return c
    return None

def process_single_tender(tender_no: str, outcome: str, primary_file: str, folder: str, target_tender_id: int):
    """
    Worker function executed in worker process.
    """
    load_dotenv(".env.dev")
    pdf_path = resolve_pdf_path(primary_file, folder)
    if not pdf_path:
        return {
            "tender_no": tender_no,
            "outcome": outcome,
            "status": "FAILED",
            "reason": "FILE_NOT_FOUND",
            "error": f"Primary document file not found on disk: '{primary_file}'",
            "tender_id": None
        }

    job_id = str(uuid.uuid4())
    try:
        result = ingest_parent_tender_pdf(
            job_id=job_id,
            pdf_path=pdf_path,
            original_filename=pdf_path.name
        )

        extracted_fields = []
        for sec in result.get("infoSheetSections", []):
            for f in sec.get("fields", []):
                extracted_fields.append({
                    "field_name": f.get("label", f.get("name", "")),
                    "value": f.get("value"),
                    "confidence": f.get("confidence", 100.0) / 100.0 if f.get("confidence") else 1.0,
                    "source_page": f.get("page", 1),
                    "evidence": f.get("sourceSnippet", "")
                })

        from backend.app.services.normalizer import parse_money, parse_int, parse_float

        db = SessionLocal()
        try:
            db_payload = map_extraction_to_tender_information({"extracted_fields": extracted_fields}, target_tender_id)
            db_payload["nit_number"] = result.get("reference_id") or tender_no
            db_payload["tender_name"] = result.get("title") or tender_no
            db_payload["organization"] = result.get("authorityName") or db_payload.get("organization")
            db_payload["department"] = result.get("department") or db_payload.get("department")

            # Parse top-level resolved values if present
            if result.get("tenderValue"):
                tv = parse_money(result.get("tenderValue"))
                if tv is not None:
                    db_payload["tender_value"] = tv
                    db_payload["estimated_cost"] = tv

            if result.get("emdAmount"):
                emd = parse_money(result.get("emdAmount"))
                if emd is not None:
                    db_payload["emd_amount"] = emd
                    db_payload["emd_required"] = "Yes" if emd > 0 else "No"

            if result.get("tenderFee"):
                fee = parse_money(result.get("tenderFee"))
                if fee is not None:
                    db_payload["tender_fee_amount"] = fee
                    db_payload["tender_fee_required"] = "Yes" if fee > 0 else "No"

            # Check section fields for any missing features (e.g. turnover, experience, maf, pbg, ld, sd, mse, mii, ra)
            for f in extracted_fields:
                fn = f.get("field_name", "").lower()
                val = f.get("value")
                if val is None or val in ("Not Found", "Out of Scope (Stage 1)", "NA", "N/A", ""):
                    continue
                val_str = str(val).strip()
                if "turnover" in fn and db_payload.get("avg_annual_turnover_value") is None:
                    db_payload["avg_annual_turnover_value"] = parse_money(val)
                elif "experience" in fn and db_payload.get("technical_eligibility_age") is None:
                    db_payload["technical_eligibility_age"] = parse_int(val)
                elif "validity" in fn and db_payload.get("bid_validity_days") is None:
                    db_payload["bid_validity_days"] = parse_int(val)
                elif "pbg" in fn and "%" in val_str and db_payload.get("pbg_percentage") is None:
                    db_payload["pbg_percentage"] = parse_float(val)
                    db_payload["pbg_required"] = "Yes"
                elif "pbg" in fn and ("duration" in fn or "month" in fn) and db_payload.get("pbg_duration") is None:
                    db_payload["pbg_duration"] = parse_int(val)
                elif ("sd" in fn or "security deposit" in fn) and "%" in val_str and db_payload.get("sd_percentage") is None:
                    db_payload["sd_percentage"] = parse_float(val)
                    db_payload["sd_required"] = "Yes"
                elif ("ld" in fn or "prs" in fn) and db_payload.get("max_ld_percentage") is None:
                    db_payload["max_ld_percentage"] = parse_float(val)
                elif "maf" in fn and db_payload.get("maf_required") in (None, "No"):
                    if any(w in val_str.lower() for w in ["yes", "required", "true", "mandatory"]):
                        db_payload["maf_required"] = "Yes"
                elif "delivery" in fn or "period" in fn:
                    if db_payload.get("delivery_time_supply") is None:
                        db_payload["delivery_time_supply"] = parse_int(val)
                elif "mse_purchase_preference" in fn or ("mse" in fn and "preference" in fn):
                    if any(w in val_str.lower() for w in ["yes", "true", "applicable"]):
                        db_payload["mse_purchase_preference"] = "Yes"
                    elif any(w in val_str.lower() for w in ["no", "false"]):
                        db_payload["mse_purchase_preference"] = "No"
                elif "mii_purchase_preference" in fn or ("mii" in fn and "preference" in fn):
                    if any(w in val_str.lower() for w in ["yes", "true", "applicable"]):
                        db_payload["mii_purchase_preference"] = "Yes"
                    elif any(w in val_str.lower() for w in ["no", "false"]):
                        db_payload["mii_purchase_preference"] = "No"
                elif "reverse" in fn or "auction" in fn:
                    if any(w in val_str.lower() for w in ["yes", "true", "applicable"]):
                        db_payload["reverse_auction_applicable"] = "Yes"

            save_tender_information(db, db_payload)
            db.commit()

        except Exception as err:
            db.rollback()
            raise err
        finally:
            db.close()

        # Update tender_outcomes linking
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            UPDATE tender_outcomes 
            SET tender_id = %s, updated_at = NOW() 
            WHERE tender_no = %s;
        """, (target_tender_id, tender_no))
        conn.commit()
        conn.close()

        return {
            "tender_no": tender_no,
            "outcome": outcome,
            "status": "SUCCESS",
            "reason": None,
            "error": None,
            "tender_id": target_tender_id
        }

    except Exception as e:
        return {
            "tender_no": tender_no,
            "outcome": outcome,
            "status": "FAILED",
            "reason": "EXTRACTION_OR_DB_ERROR",
            "error": str(e),
            "tender_id": None
        }

def run_backfill(outcomes_filter=None, max_workers=4, batch_limit=None):
    logger.info("Starting historical tender backfill...")
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # 1. Fetch unextracted or unlinked rows from tender_outcomes
    query = """
        SELECT o.id, o.tender_no, o.outcome, o.tender_id
        FROM tender_outcomes o
        WHERE (o.tender_id IS NULL OR NOT EXISTS (
            SELECT 1 FROM tender_information i WHERE i.tender_id = o.tender_id
        ))
    """
    if outcomes_filter:
        placeholders = ','.join(['%s'] * len(outcomes_filter))
        query += f" AND o.outcome IN ({placeholders})"
    query += " ORDER BY CASE WHEN o.outcome='Won' THEN 1 WHEN o.outcome='Lost' THEN 2 ELSE 3 END, o.tender_no ASC;"

    params = tuple(outcomes_filter) if outcomes_filter else ()
    cur.execute(query, params)
    unprocessed = cur.fetchall()

    if batch_limit:
        unprocessed = unprocessed[:batch_limit]

    logger.info(f"Found {len(unprocessed)} tenders to process (Filter: {outcomes_filter}, Limit: {batch_limit})")

    if not unprocessed:
        logger.info("No tenders to process.")
        conn.close()
        return

    # Load master mapping
    df_master = pd.read_csv("master-tenders.csv").set_index("tender_no")

    # Determine starting tender_id
    cur.execute("SELECT COALESCE(MAX(tender_id), 0) FROM tender_information;")
    max_id = cur.fetchone()["coalesce"]
    conn.close()

    tasks_to_run = []
    current_t_id = max_id
    for item in unprocessed:
        t_no = item["tender_no"]
        outcome = item["outcome"]
        current_t_id += 1

        primary_file = ""
        folder = "tender-documents"
        if t_no in df_master.index:
            row = df_master.loc[t_no]
            sf_raw = str(row["source_files"])
            folder = str(row["folder_path"]) if str(row["folder_path"]) != "nan" else "tender-documents"
            try:
                files = ast.literal_eval(sf_raw) if sf_raw.startswith("[") else [sf_raw]
            except Exception:
                files = [sf_raw]
            if files and len(files) > 0:
                # Prioritize PDF files over non-PDF (e.g. BOQ xls files)
                pdf_candidates = [f for f in files if str(f).lower().endswith('.pdf')]
                if pdf_candidates:
                    primary_file = pdf_candidates[0]
                else:
                    primary_file = files[0]


        tasks_to_run.append((t_no, outcome, primary_file, folder, current_t_id))

    logger.info(f"Prepared {len(tasks_to_run)} tasks. Running with {max_workers} worker processes...")

    succeeded = 0
    failed = 0
    failures = []
    start_time = time.time()
    os.makedirs("artifacts", exist_ok=True)

    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(process_single_tender, t_no, outcome, p_file, folder, t_id): t_no
            for (t_no, outcome, p_file, folder, t_id) in tasks_to_run
        }

        completed_count = 0
        for future in as_completed(futures):
            t_no_orig = futures[future]
            completed_count += 1
            try:
                res = future.result()
            except Exception as e:
                res = {
                    "tender_no": t_no_orig,
                    "outcome": "Unknown",
                    "status": "FAILED",
                    "reason": "EXTRACTION_CRASH",
                    "error": str(e)
                }

            if res["status"] == "SUCCESS":
                succeeded += 1
            else:
                failed += 1
                failures.append(res)
                logger.warning(f"Failed [{res['tender_no']}] ({res.get('outcome')}) - Reason: {res.get('reason')}: {res.get('error')}")
                # Write failure log incrementally
                with open("artifacts/backfill_failures.json", "w", encoding="utf-8") as f:
                    json.dump(failures, f, indent=2)

            if completed_count % 25 == 0 or completed_count == len(tasks_to_run):
                elapsed = time.time() - start_time
                rate = completed_count / elapsed if elapsed > 0 else 0
                logger.info(f"Progress: {completed_count}/{len(tasks_to_run)} ({succeeded} ok, {failed} fail) - {rate:.1f} tenders/sec")


    elapsed_total = time.time() - start_time
    logger.info(f"\n==========================================")
    logger.info(f"BACKFILL SUMMARY")
    logger.info(f"==========================================")
    logger.info(f"Total Processed: {completed_count}")
    logger.info(f"Succeeded:       {succeeded}")
    logger.info(f"Failed:          {failed}")
    logger.info(f"Time Taken:      {elapsed_total:.1f}s")

    # Save final failure log
    with open("artifacts/backfill_failures.json", "w", encoding="utf-8") as f:
        json.dump(failures, f, indent=2)
    logger.info(f"Wrote {len(failures)} total failures to artifacts/backfill_failures.json")

    return {
        "total": completed_count,
        "succeeded": succeeded,
        "failed": failed,
        "failures": failures
    }

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true", help="Process all tenders including Do Not Bid/Pending")
    parser.add_argument("--workers", type=int, default=12, help="Number of worker processes")
    parser.add_argument("--limit", type=int, default=None, help="Batch limit")
    parser.add_argument("--purge-stubs", action="store_true", help="Purge old stub/corrupt tender_information rows and reset linking before backfill")
    args = parser.parse_args()

    if args.purge_stubs:
        logger.info("Purging old stub tender_information rows and resetting tender_outcomes linking...")
        p_conn = get_db_connection()
        p_cur = p_conn.cursor()
        p_cur.execute("""
            UPDATE tender_outcomes SET tender_id = NULL 
            WHERE tender_id IN (
                SELECT tender_id FROM tender_information 
                WHERE tender_name IS NULL OR tender_value = 1.0 OR nit_number IS NULL
            );
            DELETE FROM tender_information 
            WHERE tender_name IS NULL OR tender_value = 1.0 OR nit_number IS NULL;
        """)
        p_conn.commit()
        logger.info("Purged stub rows from tender_information and reset linking in tender_outcomes.")
        p_conn.close()

    filter_outcomes = None if args.all else ["Won", "Lost"]
    run_backfill(outcomes_filter=filter_outcomes, max_workers=args.workers, batch_limit=args.limit)

