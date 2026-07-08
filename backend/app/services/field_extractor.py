import re
from typing import List, Dict, Any, Tuple

def extract_field_with_context(patterns: List[str], text: str) -> Tuple[str, float, str, str]:
    """
    Searches regex patterns.
    Returns Tuple of: (extracted_value, confidence, source_snippet, status)
    If extraction fails, returns empty values and 'missing' status.
    """
    for p in patterns:
        match = re.search(p, text, re.IGNORECASE)
        if match:
            # Check for group match or full match
            val = match.group(1).strip() if match.groups() else match.group(0).strip()
            
            # Clean up trailing spaces or markdown characters
            val = re.sub(r'[\*`_#]', '', val).strip()
            
            # Extract surrounding context snippet
            start = max(0, match.start() - 60)
            end = min(len(text), match.end() + 60)
            snippet = text[start:end].strip().replace("\n", " ")
            
            return val, 90.0, f"... {snippet} ...", "extracted"
            
    return "", 0.0, "", "missing"

def extract_tender_fields(pages: List[Dict[str, Any]], filename_title: str) -> List[Dict[str, Any]]:
    """
    Harden field extractor that avoids silently inventing fake details.
    If regexes fail to match, fields are reported as missing with 0% confidence.
    """
    full_text = "\n".join([p["text"] for p in pages])
    
    # 1. Reference ID
    id_patterns = [
        r'(?:bid\s+number|gem\s+bid\s+no|gem\s+bid\s+number|nit\s+no|reference\s+no)[:\-:\s]+([A-Za-z0-9\-#/\.]+)',
        r'nit\s+no[:\-\s\.:]+([A-Za-z0-9\-#/\.]+)',
        r'tender\s+ref(?:erence)?\s+no[:\-\s\.:]+([A-Za-z0-9\-#/\.]+)'
    ]
    ref_id, id_conf, id_snip, id_status = extract_field_with_context(id_patterns, full_text)
    
    # 2. Authority Name
    auth_patterns = [
        r'(?:organization|authority|agency|client|employer)\s+name[:\-:\s]+([A-Za-z\s]{4,60})',
        r'office\s+of\s+the\s+([A-Za-z\s]{4,60})',
        r'public\s+works\s+department\s+([A-Za-z\s]{4,30})'
    ]
    auth_name, auth_conf, auth_snip, auth_status = extract_field_with_context(auth_patterns, full_text)
    
    # 3. Department
    dept_patterns = [
        r'(?:department|ministry|division|directorate)[:\-:\s]+([A-Za-z\s]{4,50})',
        r'division\s+office\s+([A-Za-z\s]{4,40})'
    ]
    dept, dept_conf, dept_snip, dept_status = extract_field_with_context(dept_patterns, full_text)
    
    # 4. Tender Value / Estimated Cost
    val_patterns = [
        r'(?:estimated\s+cost|tender\s+value|work\s+value|amount\s+of\s+work)[:\-:\s]+(?:rs\.?|inr|₹)?\s*([\d\.,]+(?:\s*(?:crore|lakh|lacs|cr))?)',
        r'estimated\s+cost\s+of\s+work\s+is\s+rs\.?\s*([\d\.,]+(?:\s*(?:crore|lakh|lacs|cr))?)',
        r'rs\.?\s*([\d\.,]+(?:\s*(?:crore|lakh|lacs|cr))?)\s*estimated'
    ]
    t_val, val_conf, val_snip, val_status = extract_field_with_context(val_patterns, full_text)
    
    # 5. EMD Amount
    emd_patterns = [
        r'(?:emd\s+amount|earnest\s+money\s+deposit|bid\s+security)[:\-:\s]+(?:rs\.?|inr|₹)?\s*([\d\.,]+(?:\s*(?:lakh|lacs|crore|cr))?)',
        r'emd\s+of\s+rs\.?\s*([\d\.,]+)',
        r'emd\s+value\s*[:\-:\s]+\s*([\d\.,]+)'
    ]
    emd, emd_conf, emd_snip, emd_status = extract_field_with_context(emd_patterns, full_text)
    
    # 6. Tender Fee
    fee_patterns = [
        r'(?:tender\s+fee|document\s+cost|cost\s+of\s+tender\s+document)[:\-:\s]+(?:rs\.?|inr|₹)?\s*([\d\.,]+)',
        r'fee\s+of\s+rs\.?\s*([\d\.,]+)'
    ]
    fee, fee_conf, fee_snip, fee_status = extract_field_with_context(fee_patterns, full_text)
    
    # 7. Bid Deadline
    deadline_patterns = [
        r'(?:bid\s+submission\s+end\s+date|bid\s+end\s+date|submission\s+deadline|closing\s+date)[:\-:\s]+(\d{2}[-/\.]\d{2}[-/\.]\d{4}(?:\s+\d{2}:\d{2})?)',
        r'last\s+date\s+of\s+submission\s*[:\-:\s]+(\d{2}[-/\.]\d{2}[-/\.]\d{4})',
        r'bid\s+end\s+date\s*[:\-:\s]+(\d{2}[-/\.]\d{2}[-/\.]\d{4})'
    ]
    deadline, dead_conf, dead_snip, dead_status = extract_field_with_context(deadline_patterns, full_text)
    
    # 8. Bid Opening Date
    open_patterns = [
        r'(?:bid\s+opening\s+date|date\s+of\s+opening|technical\s+bid\s+opening)[:\-:\s]+(\d{2}[-/\.]\d{2}[-/\.]\d{4})',
        r'date\s+of\s+bid\s+opening\s*[:\-:\s]+(\d{2}[-/\.]\d{2}[-/\.]\d{4})'
    ]
    open_date, open_conf, open_snip, open_status = extract_field_with_context(open_patterns, full_text)
    
    # 9. Location
    loc_patterns = [
        r'(?:location|place\s+of\s+work|site\s+location)[:\-:\s]+([A-Za-z\s,]{4,50})',
        r'site\s+at\s+([A-Za-z\s,]{4,40})'
    ]
    loc, loc_conf, loc_snip, loc_status = extract_field_with_context(loc_patterns, full_text)

    # 10. Contact Details
    contact_patterns = [
        r'(?:contact\s+officer|executive\s+engineer|EE|officer\s+name|nodal\s+officer)[:\-:\s]+([A-Za-z\s\.]{4,40})',
        r'shri\s+([A-Za-z\s\.]{4,40})'
    ]
    contact, contact_conf, contact_snip, contact_status = extract_field_with_context(contact_patterns, full_text)

    # Compile Structured JSON sections
    sections = [
        {
            "id": "sec-1",
            "title": "Basic Information",
            "fields": [
                {
                    "id": "f-1",
                    "label": "Tender Name / Title",
                    "value": filename_title,
                    "confidence": 98.0,
                    "critical": True,
                    "sourcePage": 1,
                    "sourceSnippet": f"Filename Title context: {filename_title}",
                    "status": "extracted"
                },
                {
                    "id": "f-2",
                    "label": "Reference ID / NIT No",
                    "value": ref_id,
                    "confidence": id_conf,
                    "critical": True,
                    "sourcePage": 1,
                    "sourceSnippet": id_snip if id_snip else None,
                    "status": id_status
                },
                {
                    "id": "f-3",
                    "label": "Authority Agency",
                    "value": auth_name,
                    "confidence": auth_conf,
                    "critical": True,
                    "sourcePage": 1,
                    "sourceSnippet": auth_snip if auth_snip else None,
                    "status": auth_status
                },
                {
                    "id": "f-4",
                    "label": "Department",
                    "value": dept,
                    "confidence": dept_conf,
                    "critical": False,
                    "sourcePage": 1,
                    "sourceSnippet": dept_snip if dept_snip else None,
                    "status": dept_status
                }
            ]
        },
        {
            "id": "sec-2",
            "title": "Financial Details",
            "fields": [
                {
                    "id": "f-5",
                    "label": "Estimated Tender Value",
                    "value": t_val,
                    "confidence": val_conf,
                    "critical": True,
                    "sourcePage": 1,
                    "sourceSnippet": val_snip if val_snip else None,
                    "status": val_status
                },
                {
                    "id": "f-6",
                    "label": "EMD Amount",
                    "value": emd,
                    "confidence": emd_conf,
                    "critical": True,
                    "sourcePage": 1,
                    "sourceSnippet": emd_snip if emd_snip else None,
                    "status": emd_status
                },
                {
                    "id": "f-7",
                    "label": "Tender Fee",
                    "value": fee,
                    "confidence": fee_conf,
                    "critical": False,
                    "sourcePage": 1,
                    "sourceSnippet": fee_snip if fee_snip else None,
                    "status": fee_status
                }
            ]
        },
        {
            "id": "sec-3",
            "title": "Dates & Timeline",
            "fields": [
                {
                    "id": "f-8",
                    "label": "Bid Submission Deadline",
                    "value": deadline,
                    "confidence": dead_conf,
                    "critical": True,
                    "sourcePage": 1,
                    "sourceSnippet": dead_snip if dead_snip else None,
                    "status": dead_status
                },
                {
                    "id": "f-9",
                    "label": "Technical Bid Opening Date",
                    "value": open_date,
                    "confidence": open_conf,
                    "critical": False,
                    "sourcePage": 1,
                    "sourceSnippet": open_snip if open_snip else None,
                    "status": open_status
                }
            ]
        },
        {
            "id": "sec-4",
            "title": "Contact & Site Details",
            "fields": [
                {
                    "id": "f-10",
                    "label": "Location of Site",
                    "value": loc,
                    "confidence": loc_conf,
                    "critical": False,
                    "sourcePage": 1,
                    "sourceSnippet": loc_snip if loc_snip else None,
                    "status": loc_status
                },
                {
                    "id": "f-11",
                    "label": "Contact Officer",
                    "value": contact,
                    "confidence": contact_conf,
                    "critical": False,
                    "sourcePage": 1,
                    "sourceSnippet": contact_snip if contact_snip else None,
                    "status": contact_status
                }
            ]
        }
    ]
    return sections
