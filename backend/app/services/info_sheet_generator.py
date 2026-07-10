from typing import List, Dict, Any
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

def generate_info_sheet_csv(sections: List[Dict[str, Any]], output_path: str) -> None:
    """
    Writes extracted fields into a standard XLSX sheet format using openpyxl.
    Loads natively in spreadsheet viewers like Microsoft Excel.
    Includes status and source snippet columns for traceability.
    """
    wb = Workbook()
    ws = wb.active
    ws.title = "InfoSheet"
    
    # Enable grid lines visibility in Excel
    ws.views.sheetView[0].showGridLines = True
    
    # Headers
    headers = [
        "Row Number",
        "Field Section",
        "Field Name (Column A)",
        "Extracted Value (Column B)",
        "Confidence (Column C)",
        "Status",
        "Source Snippet"
    ]
    ws.append(headers)
    
    row_num = 1
    for sec in sections:
        for field in sec["fields"]:
            ws.append([
                row_num,
                sec["title"],
                field["label"],
                field["value"],
                f"{field.get('confidence', 0)}%",
                field.get("status", "extracted"),
                field.get("sourceSnippet", "")
            ])
            row_num += 1

    # Style definitions
    header_fill = PatternFill(start_color="1B5E20", end_color="1B5E20", fill_type="solid")
    header_font = Font(name="Segoe UI", size=11, bold=True, color="FFFFFF")
    cell_font = Font(name="Segoe UI", size=10)
    
    thin_side = Side(border_style="thin", color="CCCCCC")
    cell_border = Border(left=thin_side, right=thin_side, top=thin_side, bottom=thin_side)
    
    # Apply header formatting
    for col_idx in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = cell_border
        
    # Apply cell formatting for data rows
    for r_idx in range(2, row_num + 1):
        for col_idx in range(1, len(headers) + 1):
            cell = ws.cell(row=r_idx, column=col_idx)
            cell.font = cell_font
            cell.border = cell_border
            
            # Alignments
            if col_idx in (1, 5, 6): # Row Number, Confidence, Status
                cell.alignment = Alignment(horizontal="center", vertical="center")
            else:
                cell.alignment = Alignment(horizontal="left", vertical="center")

    # Set row heights
    ws.row_dimensions[1].height = 28
    for r_idx in range(2, row_num + 1):
        ws.row_dimensions[r_idx].height = 20

    # Auto-adjust column widths with a margin
    for col in ws.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            val_str = str(cell.value or "")
            if len(val_str) > max_len:
                max_len = len(val_str)
        # Apply width (capped at 50 to avoid excessively wide columns for snippets)
        ws.column_dimensions[col_letter].width = min(max(max_len + 4, 12), 50)
        
    wb.save(output_path)
