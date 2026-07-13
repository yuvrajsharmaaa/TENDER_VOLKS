import re
import logging
from typing import List, Dict, Any, Tuple, Callable

from backend.app.services.field_registry import get_keywords

logger = logging.getLogger(__name__)

def extract_field_flexible(keywords: List[str], text: str) -> Tuple[str, float, str, str]:
    """
    Looks for keywords in the text.
    Handles horizontal (Keyword: Value) and vertical (Keyword \n Value) layouts.
    Returns (value, confidence, snippet, status)
    """
    for kw in keywords:
        # 1. Match horizontal layout
        horiz_pattern = re.compile(rf'{kw}[^\n\d]*?[:\-:=\s]+([A-Za-z0-9/\-\.,\s#&@\(\)]+)', re.IGNORECASE)
        match = horiz_pattern.search(text)
        if match:
            val = match.group(1).strip()
            val = re.sub(r'[\*`_#]', '', val).strip()
            val = re.sub(r'\s+', ' ', val)
            if val and len(val) > 2 and not any(k in val.lower() for k in ["detail", "required", "exemption"]):
                start = max(0, match.start() - 60)
                end = min(len(text), match.end() + 60)
                snippet = text[start:end].strip().replace("\n", " ")
                return val, 90.0, f"... {snippet} ...", "extracted"

        # 2. Match vertical layout
        vert_pattern = re.compile(rf'{kw}[^\n]*?\n\s*([^\n]+)', re.IGNORECASE)
        match = vert_pattern.search(text)
        if match:
            val = match.group(1).strip()
            val = re.sub(r'[\*`_#]', '', val).strip()
            val = re.sub(r'\s+', ' ', val)
            if val and len(val) > 2 and not any(k in val.lower() for k in ["detail", "compliance", "required", "exemption", "opening date", "emd amount"]):
                start = max(0, match.start() - 60)
                end = min(len(text), match.end() + 60)
                snippet = text[start:end].strip().replace("\n", " ")
                return val, 95.0, f"... {snippet} ...", "extracted"

    return "", 0.0, "", "missing"

def extract_date_field(keywords: List[str], text: str) -> Tuple[str, float, str, str]:
    for kw in keywords:
        # Vertical date with up to 3 lines of labels/translation in between
        pattern = re.compile(rf'{kw}(?:[^\n]*\n){{1,3}}\s*(\d{{2}}-\d{{2}}-\d{{4}}\s+\d{{2}}:\d{{2}}:\d{{2}})', re.IGNORECASE)
        match = pattern.search(text)
        if match:
            val = match.group(1).strip()
            start = max(0, match.start() - 60)
            end = min(len(text), match.end() + 60)
            snippet = text[start:end].strip().replace("\n", " ")
            return val, 95.0, f"... {snippet} ...", "extracted"
            
        # Horizontal date
        horiz_pattern = re.compile(rf'{kw}[^\n\d]*?[:\-:=\s]+(\d{{2}}-\d{{2}}-\d{{4}}(?:\s+\d{{2}}:\d{{2}}:\d{{2}})?)', re.IGNORECASE)
        match = horiz_pattern.search(text)
        if match:
            val = match.group(1).strip()
            start = max(0, match.start() - 60)
            end = min(len(text), match.end() + 60)
            snippet = text[start:end].strip().replace("\n", " ")
            return val, 90.0, f"... {snippet} ...", "extracted"
    return "", 0.0, "", "missing"

def extract_numeric_field(keywords: List[str], text: str) -> Tuple[str, float, str, str]:
    for kw in keywords:
        pattern = re.compile(rf'{kw}[^\n]*?\n\s*(\d{{3,12}})(?!\d)', re.IGNORECASE)
        match = pattern.search(text)
        if match:
            val = match.group(1).strip()
            start = max(0, match.start() - 60)
            end = min(len(text), match.end() + 60)
            snippet = text[start:end].strip().replace("\n", " ")
            return val, 95.0, f"... {snippet} ...", "extracted"
            
        horiz_pattern = re.compile(rf'{kw}[^\n\d]*?[:\-:=\s]+(?:Rs\.?|INR|₹)?\s*([\d\.,]+)', re.IGNORECASE)
        match = horiz_pattern.search(text)
        if match:
            val = match.group(1).strip().replace(",", "")
            if val and val.replace(".", "", 1).isdigit():
                start = max(0, match.start() - 60)
                end = min(len(text), match.end() + 60)
                snippet = text[start:end].strip().replace("\n", " ")
                return val, 90.0, f"... {snippet} ...", "extracted"
    return "", 0.0, "", "missing"

def extract_requirement_field(keywords: List[str], text: str) -> Tuple[str, float, str, str]:
    for kw in keywords:
        # Match label followed by 1 to 4 lines of translation text, then the value starting with a number and unit
        pattern = re.compile(rf'{kw}(?:[^\n]*\n){{1,4}}\s*(\d+\s*(?:Year|Lakh|Lac|Cr|Crore|Month|Day)[^\n]*)', re.IGNORECASE)
        match = pattern.search(text)
        if match:
            val = match.group(1).strip()
            start = max(0, match.start() - 60)
            end = min(len(text), match.end() + 60)
            snippet = text[start:end].strip().replace("\n", " ")
            return val, 95.0, f"... {snippet} ...", "extracted"
    return "", 0.0, "", "missing"

def extract_location(text: str) -> Tuple[str, float, str, str]:
    # Look for Consignees/Reporting Officer table header, then match lines below it
    pattern = re.compile(r'Consignees/Reporting Officer.*?Address/पता.*?\n(?:\d+\s*\n)?\s*([^\n]+)\n\s*([^\n]+)?\n\s*([^\n]+)?\n\s*(\d+)\s*\n\s*(\d+)', re.IGNORECASE | re.DOTALL)
    match = pattern.search(text)
    if match:
        lines = [match.group(1).strip()]
        if match.group(2) and not match.group(2).strip().isdigit() and "consignee" not in match.group(2).lower():
            lines.append(match.group(2).strip())
        if match.group(3) and not match.group(3).strip().isdigit() and "consignee" not in match.group(3).lower():
            lines.append(match.group(3).strip())
        address = ", ".join([l for l in lines if l and l != "***********"])
        if address:
            return address, 90.0, f"... {text[match.start():match.end()].strip().replace(chr(10), ' ')} ...", "extracted"
            
    return extract_field_flexible(["consignee address", "location of site", "location", "place of work"], text)

def extract_products_and_services(pages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    categories = {
        "battery": [r"\bbatter(?:y|ies)\b", r"\bcells?\b", r"\baccumulators?\b"],
        "air_conditioner": [r"\bair\s+conditioner\b", r"\bac\b", r"\bsplit\s+ac\b", r"\bcassette\s+ac\b", r"\bwindow\s+ac\b"],
        "ups": [r"\bups\b", r"\buninterruptible\s+power\b"],
        "inverter": [r"\binverter\b"],
        "solar": [r"\bsolar\b", r"\bphotovoltaic\b", r"\bpv\s+panels?\b"],
        "cable": [r"\bcables?\b", r"\bwires?\b", r"\bconductors?\b"],
        "panel": [r"\bpanels?\b", r"\bswitchboards?\b", r"\bdistribution\s+boards?\b", r"\bmccb\b", r"\bmcb\b"],
        "transformer": [r"\btransformer\s+step\b", r"\btransformers?\b"],
        "stabilizer": [r"\bstabilizer\b", r"\bvoltage\s+regulator\b"],
        "hvac": [r"\bhvac\b", r"\bventilation\b", r"\bcooling\b", r"\bchiller\b"],
        "maintenance_service": [r"\bmaintenance\b", r"\bamc\b", r"\bcomprehensive\s+amc\b", r"\bo&m\b", r"\brepair\b"],
        "installation_service": [r"\binstallation\b", r"\bcommissioning\b", r"\blaying\b", r"\bdeployment\b"],
        "electrical_accessory": [r"\bsockets?\b", r"\bswitches?\b", r"\bplugs?\b", r"\brelays?\b", r"\bfuses?\b"]
    }
    
    extracted_products = []
    
    for page in pages:
        page_num = page.get("page", 1)
        text = page.get("text", "")
        
        lines = text.split("\n")
        for line_idx, line in enumerate(lines):
            for category, regex_list in categories.items():
                for pattern in regex_list:
                    if re.search(pattern, line, re.IGNORECASE):
                        product_name = line.strip()
                        product_name = re.sub(r'[\*`_#]', '', product_name).strip()
                        if len(product_name) < 10 and line_idx + 1 < len(lines):
                            product_name += " " + lines[line_idx + 1].strip()
                        
                        product_name = re.sub(r'\s+', ' ', product_name)
                        if len(product_name) > 120:
                            product_name = product_name[:117] + "..."
                            
                        if any(p["category"] == category and p["page_number"] == page_num for p in extracted_products):
                            continue
                            
                        qty = "1"
                        unit = "Project"
                        context_window = " ".join(lines[max(0, line_idx-1):min(len(lines), line_idx+2)])
                        qty_match = re.search(r'\b(\d+)\s*(?:nos|pcs|units|sets|numbers|qty|quantity)\b', context_window, re.IGNORECASE)
                        if qty_match:
                            qty = qty_match.group(1)
                            unit_match = re.search(r'\b(nos|pcs|units|sets|numbers)\b', context_window, re.IGNORECASE)
                            if unit_match:
                                unit = unit_match.group(1).capitalize()
                        
                        brand = "Any"
                        brand_match = re.search(r'(?:brand|make|oem|manufacturer)[:\-:\s]+([A-Za-z0-9]+)', context_window, re.IGNORECASE)
                        if brand_match:
                            brand = brand_match.group(1).strip()
                            
                        evidence = " | ".join([l.strip() for l in lines[max(0, line_idx-1):min(len(lines), line_idx+2)] if l.strip()])
                        
                        extracted_products.append({
                            "category": category,
                            "product_name": product_name,
                            "qty": qty,
                            "unit": unit,
                            "brand": brand,
                            "page_number": page_num,
                            "evidence": evidence
                        })
                        
    return extracted_products

def extract_tender_fields(pages: List[Dict[str, Any]], filename_title: str) -> List[Dict[str, Any]]:
    """
    Advanced layout-aware field extractor targeting GeM and generic Indian tenders.
    Prefers the cover pages (1 & 2) for standard fields to minimize false positives,
    but falls back to searching the full document when a field isn't found on the
    cover pages, since fields like tender_value sometimes only appear on page 3+.
    """
    # Preferred scope: pages 1 and 2 (the "COVER" zone), where most metadata lives.
    metadata_text = "\n".join([p["text"] for p in pages[:2]])
    # Fallback scope: the entire document, used only when a field is missing on the cover.
    full_doc_text = "\n".join([p["text"] for p in pages])

    def run_with_fallback(field_label: str, extractor_fn: Callable, keywords: List[str], *extra_args):
        """
        Runs an extractor against the cover-page text first. If the field comes back
        missing and the full document has more text than the cover pages, retries
        against the full document (e.g. to catch fields that only appear on page 3+).
        Slightly discounts confidence on fallback matches since they come from outside
        the primary cover-page heuristic. Logs which source and keyword produced the
        final value so extraction failures can be traced field-by-field.
        """
        val, conf, snip, status = extractor_fn(keywords, metadata_text, *extra_args)
        source = "cover_pages"
        if status == "missing" and full_doc_text and full_doc_text != metadata_text:
            fb_val, fb_conf, fb_snip, fb_status = extractor_fn(keywords, full_doc_text, *extra_args)
            if fb_status == "extracted":
                val, conf, snip, status = fb_val, max(0.0, fb_conf - 5.0), fb_snip, fb_status
                source = "full_document_fallback"
        logger.info(
            "[FIELD_TRACE] field=%s source=%s keywords=%s value=%r confidence=%s status=%s",
            field_label, source, keywords, val, conf, status
        )
        return val, conf, snip, status

    # 1. Tender Title
    title_val, title_conf, title_snip, title_status = run_with_fallback(
        "Tender Name / Title", extract_field_flexible, get_keywords("title")
    )
    if not title_val:
        title_val = filename_title
        title_conf = 90.0
        title_snip = f"Filename Title fallback: {filename_title}"
        title_status = "extracted"
        logger.info("[FIELD_TRACE] field=Tender Name / Title source=filename_fallback value=%r", title_val)

    # 2. Reference ID / Bid Number
    ref_id, id_conf, id_snip, id_status = run_with_fallback(
        "Reference ID / NIT No", extract_field_flexible, get_keywords("reference_id")
    )
    if id_status == "missing":
        gem_match = re.search(r'(GEM/\d{4}/[A-Z]/\d+)', full_doc_text)
        if gem_match:
            ref_id = gem_match.group(1)
            id_conf = 95.0
            id_snip = f"... {full_doc_text[max(0, gem_match.start()-40):min(len(full_doc_text), gem_match.end()+40)].strip().replace(chr(10), ' ')} ..."
            id_status = "extracted"
            logger.info("[FIELD_TRACE] field=Reference ID / NIT No source=gem_pattern_fallback value=%r", ref_id)

    # 3. Authority Agency
    auth_name, auth_conf, auth_snip, auth_status = run_with_fallback(
        "Authority Agency", extract_field_flexible, get_keywords("authority")
    )

    # 4. Department
    dept, dept_conf, dept_snip, dept_status = run_with_fallback(
        "Department", extract_field_flexible, get_keywords("department")
    )

    # 5. Ministry
    ministry, min_conf, min_snip, min_status = run_with_fallback(
        "Ministry Name", extract_field_flexible, get_keywords("ministry")
    )

    # 6. Estimated Tender Value
    t_val, val_conf, val_snip, val_status = run_with_fallback(
        "Estimated Tender Value", extract_numeric_field, get_keywords("tender_value")
    )

    # 7. EMD Amount
    emd, emd_conf, emd_snip, emd_status = run_with_fallback(
        "EMD Amount", extract_numeric_field, get_keywords("emd_amount")
    )

    # 8. Tender Fee
    fee, fee_conf, fee_snip, fee_status = run_with_fallback(
        "Tender Fee", extract_numeric_field, get_keywords("tender_fee")
    )

    # 9. Bid Submission Deadline
    deadline, dead_conf, dead_snip, dead_status = run_with_fallback(
        "Bid Submission Deadline", extract_date_field, get_keywords("bid_submission_deadline")
    )

    # 10. Technical Bid Opening Date
    open_date, open_conf, open_snip, open_status = run_with_fallback(
        "Technical Bid Opening Date", extract_date_field, get_keywords("bid_opening_date")
    )

    # 11. Location of Site
    loc, loc_conf, loc_snip, loc_status = extract_location(metadata_text)
    if loc_status == "missing" and full_doc_text != metadata_text:
        fb_loc, fb_loc_conf, fb_loc_snip, fb_loc_status = extract_location(full_doc_text)
        if fb_loc_status == "extracted":
            loc, loc_conf, loc_snip, loc_status = fb_loc, max(0.0, fb_loc_conf - 5.0), fb_loc_snip, fb_loc_status
    logger.info(
        "[FIELD_TRACE] field=Location of Site source=%s value=%r confidence=%s status=%s",
        "cover_pages" if loc_status != "missing" else "none", loc, loc_conf, loc_status
    )

    # 12. Contact Officer
    contact, contact_conf, contact_snip, contact_status = run_with_fallback(
        "Contact Officer", extract_field_flexible, get_keywords("contact_officer")
    )

    # 13. Pre-Bid Meeting Details
    prebid, pb_conf, pb_snip, pb_status = run_with_fallback(
        "Pre-Bid Meeting Date", extract_date_field, get_keywords("prebid_meeting")
    )

    # 14. Turnover Requirement
    turnover, to_conf, to_snip, to_status = run_with_fallback(
        "Annual Turnover Limit", extract_requirement_field, get_keywords("turnover_requirement")
    )

    # 15. Experience Requirement
    experience, exp_conf, exp_snip, exp_status = run_with_fallback(
        "Minimum Experience (Years)", extract_requirement_field, get_keywords("experience_requirement")
    )

    sections = [
        {
            "id": "sec-1",
            "title": "Basic Information",
            "fields": [
                {
                    "id": "f-1",
                    "label": "Tender Name / Title",
                    "value": title_val,
                    "confidence": title_conf,
                    "critical": True,
                    "sourcePage": 1,
                    "sourceSnippet": title_snip,
                    "status": title_status
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
                },
                {
                    "id": "f-4b",
                    "label": "Ministry Name",
                    "value": ministry,
                    "confidence": min_conf,
                    "critical": False,
                    "sourcePage": 1,
                    "sourceSnippet": min_snip if min_snip else None,
                    "status": min_status
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
                },
                {
                    "id": "f-9b",
                    "label": "Pre-Bid Meeting Date",
                    "value": prebid,
                    "confidence": pb_conf,
                    "critical": False,
                    "sourcePage": 1,
                    "sourceSnippet": pb_snip if pb_snip else None,
                    "status": pb_status
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
        },
        {
            "id": "sec-4b",
            "title": "Eligibility Requirements",
            "fields": [
                {
                    "id": "f-12",
                    "label": "Annual Turnover Limit",
                    "value": turnover,
                    "confidence": to_conf,
                    "critical": False,
                    "sourcePage": 1,
                    "sourceSnippet": to_snip if to_snip else None,
                    "status": to_status
                },
                {
                    "id": "f-13",
                    "label": "Minimum Experience (Years)",
                    "value": experience,
                    "confidence": exp_conf,
                    "critical": False,
                    "sourcePage": 1,
                    "sourceSnippet": exp_snip if exp_snip else None,
                    "status": exp_status
                }
            ]
        }
    ]
    
    products = extract_products_and_services(pages)
    if products:
        prod_fields = []
        for idx, p in enumerate(products):
            prod_fields.append({
                "id": f"prod-{idx+1}",
                "label": f"Requirement: {p['category'].upper().replace('_', ' ')}",
                "value": f"Name: {p['product_name']} | Qty: {p['qty']} {p['unit']} | OEM: {p['brand']}",
                "confidence": 90.0,
                "critical": False,
                "sourcePage": p["page_number"],
                "sourceSnippet": p["evidence"],
                "status": "extracted"
            })
        
        sections.append({
            "id": "sec-5",
            "title": "Products & Services",
            "fields": prod_fields
        })
        
    return sections
