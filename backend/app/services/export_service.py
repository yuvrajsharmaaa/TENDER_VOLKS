import csv
import os
from pathlib import Path
from typing import Dict, Any, List, Tuple
from backend.app.services.csv_schema import CSV_COLUMNS, EVIDENCE_COLUMNS

# Use ordered schema for export
TENDER_INFORMATION_COLUMNS = CSV_COLUMNS

def export_tender_information_csv(row: Dict[str, Any], output_dir: str = "output") -> str:
    """
    Exports a single saved row of tender_information into a CSV sheet file.
    Assures exact column ordering and formatting.
    Converts list/array types into comma-separated strings to avoid Excel parse issues.
    """
    # 1. Create target directory
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    
    # 2. Format filename based on tender_id
    tender_id = row.get("tender_id", "unknown")
    filename = f"tender_{tender_id}_export.csv"
    filepath = out_path / filename
    
    # 3. Clean and prepare data row
    clean_row = {}
    for col in TENDER_INFORMATION_COLUMNS:
        val = row.get(col, None)
        # Handle list/array fields cleanly for CSV format
        if isinstance(val, str) and val.startswith('[') and val.endswith(']'):
            import ast
            try:
                val = ast.literal_eval(val)
            except BaseException:
                pass
                
        if isinstance(val, list):
            clean_row[col] = "|".join([str(item) for item in val if item])
        elif val is None:
            clean_row[col] = ""
        else:
            clean_row[col] = str(val)
            
    # 4. Write CSV file
    with open(filepath, mode="w", newline="", encoding="utf-8-sig") as f: # utf-8-sig ensures Excel opens it with proper encoding
        writer = csv.DictWriter(f, fieldnames=TENDER_INFORMATION_COLUMNS)
        writer.writeheader()
        writer.writerow(clean_row)
        
    return str(filepath)

def export_tender_evidence_csv(rows: List[Dict[str, Any]], tender_id: Any, output_dir: str = "output") -> str:
    """
    Exports all extracted field occurrences (audit evidence) for a tender into an occurrences CSV sheet file.
    """
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    
    filename = f"tender_{tender_id}_evidence.csv"
    filepath = out_path / filename
    
    # Clean and prepare evidence rows
    clean_rows = []
    for r in rows:
        clean_row = {}
        for col in EVIDENCE_COLUMNS:
            val = r.get(col, None)
            if val is None:
                clean_row[col] = ""
            else:
                clean_row[col] = str(val)
        clean_rows.append(clean_row)
        
    # Write CSV file
    with open(filepath, mode="w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=EVIDENCE_COLUMNS)
        writer.writeheader()
        writer.writerows(clean_rows)
        
    return str(filepath)

def export_page_aware_tender_sheets(
    summary_row: Dict[str, Any], 
    evidence_rows: List[Dict[str, Any]], 
    output_dir: str = "output"
) -> Tuple[str, str]:
    """
    Generates both the row-level summary sheet and the evidence-level occurrence log sheets simultaneously.
    """
    summary_path = export_tender_information_csv(summary_row, output_dir)
    tender_id = summary_row.get("tender_id", "unknown")
    evidence_path = export_tender_evidence_csv(evidence_rows, tender_id, output_dir)
    return summary_path, evidence_path
