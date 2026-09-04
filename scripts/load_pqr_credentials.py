import os
import sys
import json
from pathlib import Path
from decimal import Decimal
import pandas as pd
from sqlalchemy import text
from dotenv import load_dotenv

# Ensure repo root is on sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

load_dotenv(ROOT_DIR / ".env.dev")

from backend.app.db.session import engine, SessionLocal, Base
from backend.app.models.pqr_credential import PQRCredential

EXCEL_PATH = ROOT_DIR / "pqr_documents_cleaned.xlsx"

DOC_COLUMN_MAPPING = {
    "po_document": "pqr-po",
    "sap_gem_po_document": "pqr-sap-gem-po",
    "completion_document": "pqr-completion",
    "performance_certificate": "pqr-performance-certificate"
}


def parse_file_entries(raw_val):
    """
    Parses a cell value that may contain a JSON array string, comma-separated list,
    or single path string into a list of individual file references.
    """
    if pd.isna(raw_val) or raw_val is None:
        return []
    val_str = str(raw_val).strip()
    if not val_str or val_str.lower() in ["nan", "none", "[]"]:
        return []
    
    # Try parsing JSON array
    if val_str.startswith("[") and val_str.endswith("]"):
        try:
            parsed = json.loads(val_str)
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if str(item).strip()]
        except Exception:
            pass

    # Fallback to comma separation
    if "," in val_str:
        return [part.strip().strip("'\"") for part in val_str.split(",") if part.strip()]
    return [val_str.strip("'\"")]


def resolve_local_document_path(raw_val, category):
    """
    Resolves a document cell reference to an existing local file path.
    Checks candidate locations:
      1. ROOT_DIR / category / filename
      2. ROOT_DIR / pqr_matched_files / category / filename
    Returns:
      - None if no files exist locally or if raw_val is empty.
      - Relative path string if a file exists locally.
      - Comma-separated paths if multiple valid files exist.
    """
    entries = parse_file_entries(raw_val)
    if not entries:
        return None

    resolved_files = []
    for entry in entries:
        fname = os.path.basename(entry)
        # Determine category directory from entry or fallback
        entry_cat = os.path.dirname(entry).replace("\\", "/").strip("/")
        cat_to_use = entry_cat if entry_cat else category

        candidate_1 = ROOT_DIR / cat_to_use / fname
        candidate_2 = ROOT_DIR / "pqr_matched_files" / cat_to_use / fname

        if candidate_1.exists() and candidate_1.is_file():
            resolved_files.append(f"{cat_to_use}/{fname}")
        elif candidate_2.exists() and candidate_2.is_file():
            resolved_files.append(f"{cat_to_use}/{fname}")

    if not resolved_files:
        return None
    if len(resolved_files) == 1:
        return resolved_files[0]
    return ", ".join(resolved_files)


def to_date_or_none(val):
    if pd.isna(val) or val is None:
        return None
    try:
        ts = pd.to_datetime(val)
        if pd.isna(ts):
            return None
        return ts.date()
    except Exception:
        return None


def to_datetime_or_none(val):
    if pd.isna(val) or val is None:
        return None
    try:
        ts = pd.to_datetime(val)
        if pd.isna(ts):
            return None
        return ts.to_pydatetime()
    except Exception:
        return None


def to_numeric_or_none(val):
    if pd.isna(val) or val is None:
        return None
    try:
        return round(Decimal(str(float(val))), 2)
    except Exception:
        return None


def main():
    print("=" * 70)
    print(" PQR CREDENTIALS TABLE LOADER & LOCAL DOCUMENT RESOLVER")
    print("=" * 70)
    print(f"Reading Excel: {EXCEL_PATH}")

    if not EXCEL_PATH.exists():
        print(f"ERROR: File not found: {EXCEL_PATH}")
        sys.exit(1)

    df = pd.read_excel(EXCEL_PATH)
    total_excel_rows = len(df)
    print(f"Loaded {total_excel_rows} rows from Excel.\n")

    # Step 1: Ensure table exists
    print("1. Initializing database schema...")
    Base.metadata.create_all(bind=engine, tables=[PQRCredential.__table__])
    print("   Table 'pqr_credentials' verified/created.")

    # Step 2: Truncate table on every run (truncate-and-reload)
    print("2. Truncating existing 'pqr_credentials' table (truncate-and-reload)...")
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE TABLE pqr_credentials;"))
    print("   Table truncated successfully.")

    # Step 3: Resolve documents and prepare records
    print("3. Resolving document paths and transforming rows...")
    records_to_insert = []

    for idx, row in df.iterrows():
        # Cleaned numeric value
        clean_val = to_numeric_or_none(row.get("value_clean"))

        # Dates
        po_d = to_date_or_none(row.get("po_date"))
        sap_po_d = to_date_or_none(row.get("sap_gem_po_date"))
        comp_d = to_date_or_none(row.get("completion_date"))

        # Implausible date flag
        date_flagged = bool(row.get("completion_date_flag", False))

        # Resolved document paths
        po_doc = resolve_local_document_path(row.get("po_document"), "pqr-po")
        sap_doc = resolve_local_document_path(row.get("sap_gem_po_document"), "pqr-sap-gem-po")
        comp_doc = resolve_local_document_path(row.get("completion_document"), "pqr-completion")
        perf_doc = resolve_local_document_path(row.get("performance_certificate"), "pqr-performance-certificate")

        proj_name = str(row["project_name"]).strip() if pd.notna(row.get("project_name")) else None
        if proj_name and "RAS evelopment" in proj_name:
            proj_name = proj_name.replace("RAS evelopment", "RAS Development")

        record = {
            "id": int(row["id"]),
            "team_id": int(row["team_id"]) if pd.notna(row.get("team_id")) else None,
            "team_name": str(row["team_name"]).strip() if pd.notna(row.get("team_name")) else None,
            "project_name": proj_name,
            "value": clean_val,
            "item": str(row["item"]).strip() if pd.notna(row.get("item")) else None,
            "item_category": str(row["item_category"]).strip() if pd.notna(row.get("item_category")) else None,
            "po_date": po_d,
            "sap_gem_po_date": sap_po_d,
            "completion_date": comp_d,
            "completion_date_flagged": date_flagged,
            "remarks": str(row["remarks"]).strip() if pd.notna(row.get("remarks")) else None,
            "po_document": po_doc,
            "sap_gem_po_document": sap_doc,
            "completion_document": comp_doc,
            "performance_certificate": perf_doc,
            "created_at": to_datetime_or_none(row.get("created_at")),
            "updated_at": to_datetime_or_none(row.get("updated_at")),
        }
        records_to_insert.append(record)

    # Step 4: Insert records into database
    print("4. Inserting records into PostgreSQL...")
    with SessionLocal() as session:
        for rec in records_to_insert:
            session.add(PQRCredential(**rec))
        session.commit()
    print(f"   Successfully inserted {len(records_to_insert)} records into 'pqr_credentials'.\n")

    # Step 5: Dynamic Post-Load Database Verifications
    print("=" * 70)
    print(" POST-LOAD VERIFICATION RESULTS (QUERIED DIRECTLY FROM DATABASE)")
    print("=" * 70)

    with SessionLocal() as session:
        # Check 1: Total records loaded
        total_loaded = session.query(PQRCredential).count()
        print(f"Total records loaded in 'pqr_credentials': {total_loaded}")

        # Check 2: Records with zero resolvable local documents at all
        zero_doc_query = session.query(PQRCredential).filter(
            PQRCredential.po_document.is_(None),
            PQRCredential.sap_gem_po_document.is_(None),
            PQRCredential.completion_document.is_(None),
            PQRCredential.performance_certificate.is_(None),
        )
        zero_doc_count = zero_doc_query.count()
        print(f"Records with zero resolvable local documents: {zero_doc_count}")

        # Check 3: Missing files verification (1745317635.pdf and 1749881568.pdf)
        rec_29 = session.query(PQRCredential).filter(PQRCredential.id == 29).first()
        rec_53 = session.query(PQRCredential).filter(PQRCredential.id == 53).first()

        print("\nMissing Files Resolution Check:")
        if rec_29:
            print(f"  - Record ID 29 ('{rec_29.project_name}'):")
            print(f"      performance_certificate = {rec_29.performance_certificate} (expected: None/NULL)")
            print(f"      Resolved to NULL without crashing: {rec_29.performance_certificate is None}")
        else:
            print("  - Record ID 29: NOT FOUND in database!")

        if rec_53:
            print(f"  - Record ID 53 ('{rec_53.project_name}'):")
            print(f"      performance_certificate = {rec_53.performance_certificate} (expected: None/NULL)")
            print(f"      Resolved to NULL without crashing: {rec_53.performance_certificate is None}")
        else:
            print("  - Record ID 53: NOT FOUND in database!")

        # Check 4: Year-5024 completion_date_flagged row
        flagged_records = session.query(PQRCredential).filter(PQRCredential.completion_date_flagged.is_(True)).all()
        print(f"\nImplausible Completion Date Check (total flagged = {len(flagged_records)}):")
        for fr in flagged_records:
            print(f"  - Record ID {fr.id} ('{fr.project_name}'):")
            print(f"      completion_date = {fr.completion_date}")
            print(f"      completion_date_flagged = {fr.completion_date_flagged}")

        # Check 5: Record 136 double-decimal value fix
        rec_136 = session.query(PQRCredential).filter(PQRCredential.id == 136).first()
        print("\nClean Numeric Value Check (Record 136 double-decimal fix):")
        if rec_136:
            print(f"  - Record ID 136 ('{rec_136.project_name}'):")
            print(f"      value = {rec_136.value} (Decimal type, expected 21195842.66)")
            print(f"      Numeric match: {rec_136.value == Decimal('21195842.66')}")
        else:
            print("  - Record ID 136: NOT FOUND in database!")

    print("=" * 70)


if __name__ == "__main__":
    main()
