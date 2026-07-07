import csv
import os
from pathlib import Path
from typing import Dict, Any, List
from backend.app.services.csv_schema import CSV_COLUMNS

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
