import os
import sys
import json
import shutil
import pandas as pd
from pathlib import Path

# Paths configuration
EXCEL_PATH = r"C:\Users\Asus\Desktop\Tender_Volks\main\pqr_documents_cleaned.xlsx"
SOURCE_DUMP_DIR = r"C:\Users\Asus\Desktop\Tender_Volks\main\tender-documents"
OUTPUT_DIR = r"C:\Users\Asus\Desktop\Tender_Volks\main\pqr_matched_files"

DOC_COLUMNS = [
    "po_document",
    "sap_gem_po_document",
    "completion_document",
    "performance_certificate"
]

def parse_file_entries(raw_val):
    if pd.isna(raw_val) or raw_val is None:
        return []
    val_str = str(raw_val).strip()
    if not val_str or val_str.lower() in ["nan", "none", "[]"]:
        return []
    
    # Try parsing as JSON array
    if val_str.startswith("[") and val_str.endswith("]"):
        try:
            parsed = json.loads(val_str)
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if str(item).strip()]
        except Exception:
            pass
    
    # Fallback to splitting by comma or returning as single item
    if "," in val_str:
        return [part.strip().strip("'\"") for part in val_str.split(",") if part.strip()]
    return [val_str.strip("'\"")]

def main():
    print(f"=== PQR Document Extraction Tool ===")
    print(f"Excel Path:       {EXCEL_PATH}")
    print(f"Source Directory: {SOURCE_DUMP_DIR}")
    print(f"Output Directory: {OUTPUT_DIR}\n")

    if not os.path.exists(EXCEL_PATH):
        print(f"ERROR: Excel file not found at {EXCEL_PATH}")
        sys.exit(1)

    if not os.path.exists(SOURCE_DUMP_DIR):
        print(f"WARNING: Source directory does not exist: {SOURCE_DUMP_DIR}")

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    df = pd.read_excel(EXCEL_PATH)
    print(f"Total rows in Excel: {len(df)}")

    # Index source dump directory for fast lookup (basename -> relative/full path)
    print(f"Indexing source dump directory: {SOURCE_DUMP_DIR}...")
    source_files_by_basename = {}
    source_files_by_relpath = {}

    if os.path.exists(SOURCE_DUMP_DIR):
        for root, _, files in os.walk(SOURCE_DUMP_DIR):
            for file in files:
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, SOURCE_DUMP_DIR).replace("\\", "/")
                source_files_by_basename[file.lower()] = full_path
                source_files_by_relpath[rel_path.lower()] = full_path

    print(f"Indexed {len(source_files_by_basename)} distinct file basenames in source directory.\n")

    # Collect all referenced documents from Excel
    referenced_entries = []
    for idx, row in df.iterrows():
        row_id = row.get("id", idx)
        for col in DOC_COLUMNS:
            if col in df.columns:
                file_list = parse_file_entries(row[col])
                for rel_path in file_list:
                    referenced_entries.append({
                        "row_id": row_id,
                        "column": col,
                        "reference": rel_path
                    })

    print(f"Total document references across all columns: {len(referenced_entries)}")
    unique_references = sorted(list(set(e["reference"] for e in referenced_entries)))
    print(f"Total unique file paths referenced: {len(unique_references)}")
    
    unique_basenames = sorted(list(set(os.path.basename(r) for r in unique_references)))
    print(f"Total unique basenames referenced: {len(unique_basenames)}\n")

    found_count = 0
    missing_count = 0
    found_files = []
    missing_files = []

    for ref in unique_references:
        norm_ref = ref.replace("\\", "/").strip().lower()
        base_name = os.path.basename(ref).strip().lower()

        target_source = None
        # 1. Direct relpath match
        if norm_ref in source_files_by_relpath:
            target_source = source_files_by_relpath[norm_ref]
        # 2. Basename match
        elif base_name in source_files_by_basename:
            target_source = source_files_by_basename[base_name]

        if target_source and os.path.exists(target_source):
            dest_path = os.path.join(OUTPUT_DIR, ref.replace("/", os.sep))
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            shutil.copy2(target_source, dest_path)
            found_count += 1
            found_files.append((ref, target_source))
        else:
            missing_count += 1
            missing_files.append(ref)

    print("=" * 50)
    print("EXTRACTION SUMMARY")
    print("=" * 50)
    print(f"Unique files referenced: {len(unique_references)}")
    print(f"Found and copied:        {found_count}")
    print(f"Missing from source:     {missing_count}")
    coverage = (found_count / len(unique_references) * 100) if unique_references else 0.0
    print(f"Coverage:                {coverage:.2f}%")
    print("=" * 50)

    if missing_count > 0:
        print(f"\nFirst 10 missing file references:")
        for m in missing_files[:10]:
            print(f"  - {m}")
        if missing_count > 10:
            print(f"  ... and {missing_count - 10} more.")

if __name__ == "__main__":
    main()
