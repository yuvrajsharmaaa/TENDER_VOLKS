import csv
from typing import List, Dict, Any

def generate_info_sheet_csv(sections: List[Dict[str, Any]], output_path: str) -> None:
    """
    Writes extracted fields into a standard tabbed CSV sheet format.
    Loads natively in spreadsheet viewers like Microsoft Excel.
    Includes status and source snippet columns for traceability.
    """
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Row Number",
            "Field Section",
            "Field Name (Column A)",
            "Extracted Value (Column B)",
            "Confidence (Column C)",
            "Status",
            "Source Snippet"
        ])
        
        row_num = 1
        for sec in sections:
            for field in sec["fields"]:
                writer.writerow([
                    row_num,
                    sec["title"],
                    field["label"],
                    field["value"],
                    f"{field.get('confidence', 0)}%",
                    field.get("status", "extracted"),
                    field.get("sourceSnippet", "")
                ])
                row_num += 1
