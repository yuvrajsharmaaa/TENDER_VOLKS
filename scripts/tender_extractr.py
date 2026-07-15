"""
tender_extractor.py

Rule-based (regex + keyword proximity) extraction engine for GeM / PSU tender
ATC, Buyer Specification, and Instructions-to-Bidders documents.

No LLM calls. Pure deterministic text parsing on OCR output.
Designed to slot into a pipeline where Gemini/LLM validation is added LATER
as an optional second pass -- this module works standalone.

Usage:
    from tender_extractor import extract_all
    result = extract_all(ocr_text)
    # result is a dict matching your master infosheet schema
"""

import re
from typing import Optional, List, Dict, Any


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _window(text: str, keyword_pattern: str, before: int = 80, after: int = 250,
            flags=re.IGNORECASE) -> List[str]:
    """
    Return text windows around every match of keyword_pattern.
    This is the core primitive: instead of trying to match one giant regex
    for a whole clause, we find the anchor keyword, then grab surrounding
    context and run finer-grained extraction on that smaller window.
    """
    windows = []
    for m in re.finditer(keyword_pattern, text, flags):
        start = max(0, m.start() - before)
        end = min(len(text), m.end() + after)
        windows.append(text[start:end])
    return windows


def _window_parts(text: str, keyword_pattern: str, before: int = 80, after: int = 250,
                  flags=re.IGNORECASE) -> List[Dict[str, Any]]:
    """
    Return text windows split into parts around every match of keyword_pattern.
    """
    results = []
    for m in re.finditer(keyword_pattern, text, flags):
        start = max(0, m.start() - before)
        end = min(len(text), m.end() + after)
        results.append({
            "before": text[start:m.start()],
            "keyword": m.group(0),
            "after": text[m.end():end],
            "full": text[start:end]
        })
    return results


def _first_number_pattern(text: str, pattern: str, flags=re.IGNORECASE) -> Optional[str]:
    m = re.search(pattern, text, flags)
    if m:
        if m.groups() and m.group(1) is not None:
            return m.group(1).strip()
        return m.group(0).strip()
    return None


def _clause_ref_in_parts(parts: Dict[str, Any]) -> Optional[str]:
    """
    Look for a clause/section reference near the matched window, preferring
    the text after the keyword, then falling back to text before.
    """
    pattern = r"""
        (?:cl(?:ause)?\.?\s*no\.?\s*\d+(?:\.\d+)*\s*(?:of\s*)?(?:sec(?:tion)?[\s\-]*[ivx0-9]+(?:\s*\([A-Za-z]+\))?)?) |
        (?:cl(?:ause)?\.?\s*no\.?\s*\d+(?:\.\d+)*)      |
        (?:cl(?:ause)?\.?\s*\d+(?:\.\d+)*)               |
        (?:sec(?:tion)?[\s\-]*[ivx0-9]+(?:\s*\([A-Za-z]+\))?) |
        (?:para(?:graph)?\.?\s*\d+(?:\.\d+)*)            |
        (?:GCC\s*\d+(?:\.\d+)*)                          |
        (?:SCC\s*\d+(?:\.\d+)*)
    """
    # 1. Search in 'after' text first
    m_after = re.search(pattern, parts["after"], re.IGNORECASE | re.VERBOSE)
    if m_after:
        return m_after.group(0).strip()
    
    # 2. Search in 'before' text from right to left (closest to keyword first)
    matches_before = list(re.finditer(pattern, parts["before"], re.IGNORECASE | re.VERBOSE))
    if matches_before:
        return matches_before[-1].group(0).strip()
        
    return None


def _clause_ref_near(window_text: str) -> Optional[str]:
    """Fallback version that works on a flat string."""
    pattern = r"""
        (?:cl(?:ause)?\.?\s*no\.?\s*\d+(?:\.\d+)*)      |
        (?:cl(?:ause)?\.?\s*\d+(?:\.\d+)*)               |
        (?:sec(?:tion)?[\s\-]*[ivx0-9]+(?:\s*\([A-Za-z]+\))?) |
        (?:para(?:graph)?\.?\s*\d+(?:\.\d+)*)            |
        (?:GCC\s*\d+(?:\.\d+)*)                          |
        (?:SCC\s*\d+(?:\.\d+)*)
    """
    m = re.search(pattern, window_text, re.IGNORECASE | re.VERBOSE)
    return m.group(0).strip() if m else None


def _defers_to_other_doc_in_parts(parts: Dict[str, Any]) -> Optional[str]:
    """
    Detect explicit deferral language: 'as per Tender Document',
    'GCC applies', 'refer to Section III', etc.
    """
    defer_patterns = [
        (r"as per (?:the )?tender document", "TENDER_DOCUMENT"),
        (r"as per (?:the )?gcc\b", "GCC"),
        (r"as per (?:the )?scc\b", "SCC"),
        (r"general terms and conditions", "GTC"),
        (r"as per (?:the )?section[\s\-]*iii", "SECTION_III_ITB"),
        (r"refer(?:red)? to (?:the )?tender document", "TENDER_DOCUMENT"),
    ]
    for pat, tag in defer_patterns:
        if re.search(pat, parts["after"], re.IGNORECASE):
            return f"REFER_TO_{tag}"
        if re.search(pat, parts["before"], re.IGNORECASE):
            return f"REFER_TO_{tag}"
    return None


def _defers_to_other_doc(window_text: str) -> Optional[str]:
    """Fallback version that works on a flat string."""
    defer_patterns = [
        (r"as per (?:the )?tender document", "TENDER_DOCUMENT"),
        (r"as per (?:the )?gcc\b", "GCC"),
        (r"as per (?:the )?scc\b", "SCC"),
        (r"general terms and conditions", "GTC"),
        (r"as per (?:the )?section[\s\-]*iii", "SECTION_III_ITB"),
        (r"refer(?:red)? to (?:the )?tender document", "TENDER_DOCUMENT"),
    ]
    for pat, tag in defer_patterns:
        if re.search(pat, window_text, re.IGNORECASE):
            return f"REFER_TO_{tag}"
    return None


def _yes_no_near(window_text: str, positive_words, negative_words) -> str:
    low = window_text.lower()
    if any(w in low for w in negative_words):
        return "No"
    if any(w in low for w in positive_words):
        return "Yes"
    return "NOT_FOUND"


NOT_FOUND = "NOT_FOUND"


def normalize_ocr_text(text: str) -> str:
    """
    Clean common OCR artifacts before running extraction. Run this on raw
    OCR output BEFORE calling extract_all().
    """
    text = re.sub(r"\s+", " ", text)                    # collapse whitespace/line breaks
    text = text.replace("%o", "%").replace("°/o", "%")  # common OCR mangling of %
    text = re.sub(r"\b(?:Rs\.?|INR)\b|₹", "Rs.", text, flags=re.IGNORECASE)
    return text


# ---------------------------------------------------------------------------
# Field extractors
# ---------------------------------------------------------------------------

def extract_payment_terms(text: str) -> Dict[str, str]:
    result = {
        "payment_terms_supply_pct": NOT_FOUND,
        "payment_terms_installation_pct": NOT_FOUND,
        "payment_terms_raw_clause": NOT_FOUND,
    }

    parts_list = _window_parts(text, r"payment\s+terms?|payment\s+shall\s+be|released\s+on|against\s+(?:delivery|supply)|\bpayments?\b", before=30, after=400)

    if not parts_list:
        return result

    combined = " ".join([p["full"] for p in parts_list])

    # Supply % — look for "% ... (on|against|after|within|upon|following) delivery|supply|dispatch|receipt"
    supply_pct = _first_number_pattern(
        combined,
        r"\d{1,3}\s*%\s*(?:.{0,50}?)(?:on|against|after|within|upon|following)\s*(?:delivery|supply|dispatch|receipt|handover)"
    )
    if supply_pct:
        result["payment_terms_supply_pct"] = supply_pct

    # Installation % — look for "% ... (on|against|after|within|upon|following) installation|commissioning"
    install_pct = _first_number_pattern(
        combined,
        r"\d{1,3}\s*%\s*(?:.{0,50}?)(?:on|against|after|within|upon|following)\s*(?:installation|commissioning|completion|acceptance|testing)"
    )
    if install_pct:
        result["payment_terms_installation_pct"] = install_pct

    # 100% single-milestone case
    if result["payment_terms_supply_pct"] == NOT_FOUND and result["payment_terms_installation_pct"] == NOT_FOUND:
        hundred = re.search(r"100\s*%\s*payment", combined, re.IGNORECASE)
        if hundred:
            result["payment_terms_supply_pct"] = "100% (single milestone)"

    for parts in parts_list:
        clause = _clause_ref_in_parts(parts)
        defer = _defers_to_other_doc_in_parts(parts)
        if clause:
            result["payment_terms_raw_clause"] = clause
            break
        elif defer:
            result["payment_terms_raw_clause"] = defer

    return result


def extract_ld(text: str) -> Dict[str, str]:
    result = {
        "ld_applicable": NOT_FOUND,
        "ld_percentage_per_week": NOT_FOUND,
        "ld_max_percentage": NOT_FOUND,
        "ld_clause_reference": NOT_FOUND,
    }

    parts_list = _window_parts(text, r"liquidated\s+damages|\bLD\b", before=30, after=350)
    if not parts_list:
        return result

    result["ld_applicable"] = "Yes"
    combined = " ".join([p["full"] for p in parts_list])

    per_week = _first_number_pattern(
        combined,
        r"\d{1,2}(?:\.\d+)?\s*%\s*(?:of\s+)?(?:the\s+)?(?:contract\s+|estimate\s+|order\s+)?value\s*(?:per\s*week|weekly)(?:\s*or\s+part\s+thereof)?"
    )
    if not per_week:
        per_week = _first_number_pattern(combined, r"\d{1,2}(?:\.\d+)?\s*%\s*(?:per\s*week|weekly)(?:\s*or\s+part\s+thereof)?")
    if per_week:
        result["ld_percentage_per_week"] = per_week

    max_pct = _first_number_pattern(
        combined,
        r"(?:max(?:imum)?\s*(?:limit|cap)?|subject\s+to\s+(?:a\s+)?max(?:imum)?|not\s+exceeding|capped\s+at|up\s+to|ceiling\s+of)\s*(?:of\s*)?\d{1,2}(?:\.\d+)?\s*%"
    )
    if max_pct:
        result["ld_max_percentage"] = max_pct

    for parts in parts_list:
        clause = _clause_ref_in_parts(parts)
        defer = _defers_to_other_doc_in_parts(parts)
        if clause:
            result["ld_clause_reference"] = clause
            break
        elif defer:
            result["ld_clause_reference"] = defer

    return result


def extract_eligibility(text: str) -> Dict[str, str]:
    result = {
        "eligibility_criterion_years": NOT_FOUND,
        "eligibility_works_value_1": NOT_FOUND,
        "eligibility_works_value_2": NOT_FOUND,
        "eligibility_works_value_3": NOT_FOUND,
        "custom_eligibility_notes": NOT_FOUND,
    }

    windows = _window(text, r"experience|similar\s+(?:nature\s+of\s+)?work", before=30, after=350)
    if not windows:
        return result
    combined = " ".join(windows)

    # Experience years: support digits or word representations
    years = _first_number_pattern(combined, r"(?:\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten)\s*years?")
    if years:
        result["eligibility_criterion_years"] = years

    # 1 similar work - estimated value suffix is optional
    single = re.search(
        r"(?:one|1|single)\s+(?:similar\s+)?work(?:s)?(?:[\s\w,;:-]{0,120}?)(\d{1,3}\s*%\s*(?:(?:of\s+)?(?:the\s+)?(?:estimated|contract|tender)\s*(?:bid)?\s*value)?|\bRs\.\s*[\d,\.]+\s*(?:lakh|lakhs|crore|crores)?\b)",
        combined, re.IGNORECASE
    )
    if single:
        result["eligibility_works_value_1"] = single.group(1).strip()

    # 2 similar works
    two = re.search(
        r"(?:two|2|double)\s+(?:similar\s+)?work(?:s)?(?:[\s\w,;:-]{0,120}?)(\d{1,3}\s*%\s*(?:(?:of\s+)?(?:the\s+)?(?:estimated|contract|tender)\s*(?:bid)?\s*value)?|\bRs\.\s*[\d,\.]+\s*(?:lakh|lakhs|crore|crores)?\b)",
        combined, re.IGNORECASE
    )
    if two:
        result["eligibility_works_value_2"] = two.group(1).strip()

    # 3 similar works
    three = re.search(
        r"(?:three|3|triple)\s+(?:similar\s+)?work(?:s)?(?:[\s\w,;:-]{0,120}?)(\d{1,3}\s*%\s*(?:(?:of\s+)?(?:the\s+)?(?:estimated|contract|tender)\s*(?:bid)?\s*value)?|\bRs\.\s*[\d,\.]+\s*(?:lakh|lakhs|crore|crores)?\b)",
        combined, re.IGNORECASE
    )
    if three:
        result["eligibility_works_value_3"] = three.group(1).strip()

    # Flag non-standard clauses worth a human look
    flags = []
    if re.search(r"psu\s+experience|only\s+from\s+(?:government|psu)", combined, re.IGNORECASE):
        flags.append("Requires PSU/Govt-specific experience")
    if re.search(r"export\s+experience|foreign\s+experience", combined, re.IGNORECASE):
        flags.append("References foreign/export experience")
    if flags:
        result["custom_eligibility_notes"] = "; ".join(flags)

    return result


def extract_financials(text: str) -> Dict[str, str]:
    result = {
        "avg_annual_turnover_type": NOT_FOUND,
        "avg_annual_turnover_value": NOT_FOUND,
        "working_capital_type": NOT_FOUND,
        "working_capital_value": NOT_FOUND,
        "solvency_certificate_type": NOT_FOUND,
        "solvency_certificate_value": NOT_FOUND,
        "net_worth_type": NOT_FOUND,
        "net_worth_value": NOT_FOUND,
    }

    # --- Turnover ---
    windows = _window(text, r"annual\s+turnover|average\s+annual\s+turnover|\bAATO\b",
                       before=30, after=300)
    if windows:
        combined = " ".join(windows)
        has_oem = bool(re.search(r"\bOEM\b", combined))
        has_bidder = bool(re.search(r"bidder", combined, re.IGNORECASE))
        if has_oem and has_bidder:
            result["avg_annual_turnover_type"] = "Both"
        elif has_oem:
            result["avg_annual_turnover_type"] = "OEM"
        elif has_bidder:
            result["avg_annual_turnover_type"] = "Bidder"
        else:
            result["avg_annual_turnover_type"] = "Bidder"
            
        val = _first_number_pattern(
            combined, r"\d{1,3}\s*%\s*(?:of\s+)?(?:the\s+)?(?:estimated|contract|tender)\s*(?:bid)?\s*(?:value|cost|price|amount|turnover)?"
        )
        if not val:
            val = _first_number_pattern(combined, r"(?:rs\.?|₹|inr)\s*[\d,\.]+\s*(?:lakh|crore)?")
        if val:
            result["avg_annual_turnover_value"] = val

    # --- Working Capital ---
    windows = _window(text, r"working\s+capital", before=30, after=250)
    if windows:
        combined = " ".join(windows)
        has_oem = bool(re.search(r"\bOEM\b", combined))
        has_bidder = bool(re.search(r"bidder", combined, re.IGNORECASE))
        if has_oem and has_bidder:
            result["working_capital_type"] = "Both"
        elif has_oem:
            result["working_capital_type"] = "OEM"
        else:
            result["working_capital_type"] = "Bidder"
            
        val = _first_number_pattern(
            combined, r"\d{1,3}\s*%\s*(?:of\s+)?(?:the\s+)?(?:estimated|contract|tender)\s*(?:bid)?\s*(?:value|cost|price|amount|turnover)?"
        )
        if not val:
            val = _first_number_pattern(combined, r"(?:rs\.?|₹|inr)\s*[\d,\.]+\s*(?:lakh|crore)?")
        if val:
            result["working_capital_value"] = val

    # --- Solvency ---
    windows = _window(text, r"solvency\s+certificate", before=30, after=250)
    if windows:
        combined = " ".join(windows)
        result["solvency_certificate_type"] = "Bank Solvency Certificate"
        val = _first_number_pattern(combined, r"(?:rs\.?|₹|inr)\s*[\d,\.]+\s*(?:lakh|crore)?")
        if val:
            result["solvency_certificate_value"] = val

    # --- Net Worth ---
    windows = _window(text, r"net\s*worth", before=30, after=250)
    if windows:
        combined = " ".join(windows)
        if re.search(r"positive\s+net\s*worth", combined, re.IGNORECASE):
            result["net_worth_type"] = "Positive Net Worth Required"
        val = _first_number_pattern(combined, r"(?:rs\.?|₹|inr)\s*[\d,\.]+\s*(?:lakh|crore)?")
        if val:
            result["net_worth_value"] = val

    return result


def extract_security_deposit(text: str) -> Dict[str, str]:
    result = {
        "security_deposit_required": NOT_FOUND,
        "security_deposit_pct": NOT_FOUND,
        "security_deposit_duration_months": NOT_FOUND,
    }

    windows = _window(text, r"security\s+deposit|\bSD\b", before=30, after=300)
    epbg_windows = _window(text, r"e?PBG", before=30, after=300)

    combined_sd = " ".join(windows)
    combined_epbg = " ".join(epbg_windows)

    # ePBG replacing SD Check
    if re.search(r"(?:in\s+lieu\s+of|in\s+place\s+of|instead\s+of|substituted\s+for|in\s+lieu\s+of\s+performance)\s+(?:security\s+deposit|performance\s+security|SD|SD/PBG|security\s+deposit/performance)", combined_epbg, re.IGNORECASE):
        result["security_deposit_required"] = "Not Applicable - ePBG in lieu"
        return result

    if windows:
        low_sd = combined_sd.lower()
        if any(w in low_sd for w in ["exempt", "not required", "no security deposit", "not applicable"]):
            result["security_deposit_required"] = "No"
        elif any(w in low_sd for w in ["shall be deposited", "sd required", "shall submit", "shall be submitted", "performance security", "security deposit of", "sd/pbg", "deposit at"]):
            result["security_deposit_required"] = "Yes"
        elif re.search(r"\d{1,2}(?:\.\d+)?\s*%", combined_sd):
            result["security_deposit_required"] = "Yes"
        else:
            result["security_deposit_required"] = "Yes"
            
        pct = _first_number_pattern(combined_sd, r"\d{1,2}(?:\.\d+)?\s*%")
        if pct:
            result["security_deposit_pct"] = pct
        months = _first_number_pattern(combined_sd, r"\d{1,3}\s*months?")
        if months:
            result["security_deposit_duration_months"] = months

    return result

def is_valid_name(name: str) -> bool:
    if name == NOT_FOUND:
        return False
    low = name.lower()
    # Reject if it looks like an instruction sentence rather than a name/office
    reject_words = [
        "following", "copy", "instrument", "document", "must be", "shall be", 
        "sent to", "submitted to", "within", "days", "pincode", "fee", "emd", 
        "details", "upload", "online", "attached", "tender", "bidder", "contract"
    ]
    if any(w in low for w in reject_words):
        return False
    if len(name) > 60:
        return False
    return True


def extract_address_details(window_text: str) -> Dict[str, str]:
    addr = {
        "courier_name": NOT_FOUND,
        "courier_phone": NOT_FOUND,
        "courier_address_line1": NOT_FOUND,
        "courier_address_line2": NOT_FOUND,
        "courier_city": NOT_FOUND,
        "courier_state": NOT_FOUND,
        "courier_pincode": NOT_FOUND,
    }
    
    pin_match = re.search(r"\b\d{6}\b", window_text)
    if not pin_match:
        return addr
    pincode = pin_match.group(0)
    addr["courier_pincode"] = pincode
    
    phone_match = re.search(r"(?:PNo\.?|Phone|Mobile|Tel|Contact)[:\s]*([\d\-\s]{8,15})", window_text, re.IGNORECASE)
    if phone_match:
        addr["courier_phone"] = phone_match.group(1).strip()
    
    pin_start = pin_match.start()
    addr_text = window_text[max(0, pin_start - 250):pin_start].strip()
    
    # Avoid crossing sentence boundaries
    sentences = re.split(r"\.(?:\s+|$)|[\r\n]{2,}", addr_text)
    if sentences:
        addr_text = sentences[-1].strip()
        
    lines = [line.strip() for line in re.split(r"\. |\n|,", addr_text) if line.strip()]
    if not lines:
        return addr
        
    clean_lines = []
    for line in lines:
        line = re.sub(r"^(?:original\s+documents?\s+(?:[\w\s]{0,20}?)(?:sent\s+to|submitted\s+to|sent|submitted)|send\s+to|address|to:?|submitted\s+to:?|at:?)\s*", "", line, flags=re.IGNORECASE)
        if line.strip():
            clean_lines.append(line.strip())
            
    if not clean_lines:
        return addr
        
    addr["courier_name"] = clean_lines[0]
    
    if len(clean_lines) > 1:
        addr["courier_address_line1"] = clean_lines[1]
    if len(clean_lines) > 2:
        addr["courier_address_line2"] = ", ".join(clean_lines[2:])
        
    # Validate the courier_name, if it is invalid, reset fields
    if not is_valid_name(addr["courier_name"]):
        addr["courier_name"] = NOT_FOUND
        addr["courier_address_line1"] = NOT_FOUND
        addr["courier_address_line2"] = NOT_FOUND
        addr["courier_city"] = NOT_FOUND
        addr["courier_state"] = NOT_FOUND
        return addr

    # Filter out phone numbers, pincodes, emails, etc. from address lines for city/state extraction
    addr_lines = []
    for line in clean_lines:
        line_low = line.lower()
        if any(w in line_low for w in ["phone", "mobile", "tel", "contact", "email", "pincode", "fax"]):
            continue
        if re.match(r"^[\d\s\-]+$", line):
            continue
        addr_lines.append(line)

    if addr_lines:
        last_line = addr_lines[-1]
        last_line = re.sub(r"\b\d{6}\b", "", last_line)
        last_line = re.sub(r"[-,\s]+$", "", last_line).strip()
        
        if "," in last_line:
            parts = [p.strip() for p in last_line.split(",")]
            addr["courier_city"] = parts[0]
            addr["courier_state"] = parts[1]
        else:
            words = [w.strip() for w in re.split(r"[\s-]+", last_line) if w.strip()]
            states = {"uttar pradesh", "madhya pradesh", "andhra pradesh", "himachal pradesh", "arunachal pradesh",
                      "west bengal", "tamil nadu", "jammu kashmir", "karnataka", "maharashtra", "gujarat", 
                      "rajasthan", "punjab", "haryana", "bihar", "odisha", "orissa", "kerala", "assam", 
                      "telangana", "goa", "delhi", "jharkhand", "chhattisgarh", "uttarakhand"}
            
            found_state = None
            city_words = []
            if len(words) >= 2:
                two_words = (words[-2] + " " + words[-1]).lower()
                if two_words in states:
                    found_state = words[-2] + " " + words[-1]
                    city_words = words[:-2]
            if not found_state and words:
                last_word = words[-1].lower()
                if last_word in states or last_word in ["up", "mp", "ap", "hp", "wb", "tn", "jk", "mh", "gj", "rj", "pb", "hr", "br", "kl", "as", "ts", "dl", "uk"]:
                    found_state = words[-1]
                    city_words = words[:-1]
                    
            if found_state:
                addr["courier_state"] = found_state
                if city_words:
                    addr["courier_city"] = " ".join(city_words)
                elif len(addr_lines) > 1:
                    addr["courier_city"] = addr_lines[-2]
            else:
                if len(addr_lines) > 1:
                    addr["courier_state"] = last_line
                    addr["courier_city"] = addr_lines[-2]
                elif words:
                    addr["courier_city"] = words[-1]
                    if len(words) > 1:
                        addr["courier_state"] = " ".join(words[:-1])
                
    return addr


def extract_courier_info(text: str) -> Dict[str, str]:
    result = {
        "courier_name": NOT_FOUND,
        "courier_phone": NOT_FOUND,
        "courier_address_line1": NOT_FOUND,
        "courier_address_line2": NOT_FOUND,
        "courier_city": NOT_FOUND,
        "courier_state": NOT_FOUND,
        "courier_pincode": NOT_FOUND,
        "physical_docs_required": NOT_FOUND,
        "physical_document_type": NOT_FOUND,
        "physical_docs_deadline": NOT_FOUND,
    }

    windows = _window(
        text, 
        r"hard\s*cop(?:y|ies)|physical\s+(?:submission|copy|document)|original\s+documents?\s+(?:[\w\s]{0,30}?)(?:sent|submitted|received|sent\s+to|postal)|postal\s+address|\bcourier\b|address\s+for\s+submission", 
        before=30, 
        after=400
    )
    if not windows:
        result["physical_docs_required"] = "No"
        return result

    combined = " ".join(windows)
    result["physical_docs_required"] = "Yes"

    deadline = _first_number_pattern(
        combined, r"within\s+\d{1,2}\s*days|\d{1,2}[-/]\d{1,2}[-/]\d{2,4}"
    )
    if deadline:
        result["physical_docs_deadline"] = deadline

    doc_type = _first_number_pattern(
        combined,
        r"(?:original\s+[A-Za-z\s]+?(?:instrument|certificate|affidavit|document))"
    )
    if doc_type:
        result["physical_document_type"] = doc_type.strip()

    best_addr = result
    max_filled = 0
    for w in windows:
        addr = extract_address_details(w)
        filled = sum(1 for k, v in addr.items() if v != NOT_FOUND)
        if filled > max_filled:
            max_filled = filled
            best_addr = addr
            
    result.update(best_addr)
    return result


def extract_competent_authority(text: str) -> Dict[str, str]:
    """
    GeM MII/MSE sections use a rigid label:value block:
        "Name of Competent Authority: NARASINGHA RAO"
        "Designation of Competent Authority: CM"
        "Office / Department / Division of Competent Authority: C&P"
    Anchor on these exact labels rather than proximity search.
    """
    result = {"name": NOT_FOUND, "designation": NOT_FOUND, "department": NOT_FOUND}

    name = re.search(r"Name of Competent Authority\s*:?\s*([A-Za-z][A-Za-z .]+?)(?=\n|Designation|$)",
                      text, re.IGNORECASE)
    desig = re.search(r"Designation of Competent Authority\s*:?\s*([A-Za-z0-9&\s]+?)(?=\n|Office|$)",
                       text, re.IGNORECASE)
    dept = re.search(r"(?:Office\s*/\s*Department\s*/\s*Division of Competent Authority)\s*:?\s*([A-Za-z0-9&\s]+?)(?=\n|$)",
                      text, re.IGNORECASE)

    if name:
        result["name"] = name.group(1).strip()
    if desig:
        result["designation"] = desig.group(1).strip()
    if dept:
        result["department"] = dept.group(1).strip()

    return result


def extract_other_contacts(text: str) -> List[Dict[str, str]]:
    contacts = []
    patterns = [
        (r"\b(?i:consignee)\s*(?:/|(?i:reporting))?\s*(?i:reporting)\s*(?i:officer)\s*:?\s*([A-Za-z][A-Za-z .]+?)(?=\n|(?i:address)|(?i:phone)|(?i:email)|(?i:extn)|\b[A-Z]{2,}\b|,|$)", "Consignee / Reporting Officer"),
        (r"\b(?i:consignee)\s*:?\s*([A-Za-z][A-Za-z .]+?)(?=\n|(?i:address)|(?i:phone)|(?i:email)|(?i:extn)|\b[A-Z]{2,}\b|,|$)", "Consignee"),
        (r"\b(?i:nodal)\s+(?i:officer)\s*:?\s*([A-Za-z][A-Za-z .]+?)(?=\n|(?i:address)|(?i:phone)|(?i:email)|(?i:extn)|\b[A-Z]{2,}\b|,|$)", "Nodal Officer"),
        (r"\b(?i:tender)\s+(?i:inviting)\s+(?i:authority)\s*:?\s*([A-Za-z][A-Za-z .]+?)(?=\n|(?i:address)|(?i:phone)|(?i:email)|(?i:extn)|\b[A-Z]{2,}\b|,|$)", "Tender Inviting Authority"),
        (r"\b(?i:contact)\s+(?i:person)\s*:?\s*([A-Za-z][A-Za-z .]+?)(?=\n|(?i:address)|(?i:phone)|(?i:email)|(?i:extn)|\b[A-Z]{2,}\b|,|$)", "Contact Person"),
        (r"\b(?i:contact)\s*:?\s*([A-Za-z][A-Za-z .]+?)(?=\n|(?i:address)|(?i:phone)|(?i:email)|(?i:extn)|\b[A-Z]{2,}\b|,|$)", "Contact Person"),
    ]
    for pat, desig in patterns:
        for m in re.finditer(pat, text):
            name = m.group(1).strip().rstrip(".")
            
            # Clean designation prefixes from the start of names repeatedly
            old_name = ""
            while name != old_name:
                old_name = name
                name = re.sub(r"^(?:consignee|officer|person|contact|nodal|authority|mr\.?|ms\.?|mrs\.|dr\.)[:\s]+", "", name, flags=re.IGNORECASE).strip()
            
            if len(name) > 3 and name.lower() not in ["name", "designation", "address", "phone", "email"]:
                tail = text[m.end(): m.end() + 250]
                # Split tail by other contact keywords to avoid crossing into other contacts
                parts = re.split(r"\b(?:consignee|nodal|tender|contact|person|officer|authority)\b", tail, flags=re.IGNORECASE)
                if parts:
                    tail = parts[0]
                phone = _first_number_pattern(tail, r"(?:PNo\.?|Phone|Mobile|Tel|Contact)[:\s]*([\d\-]{8,13})")
                extn = _first_number_pattern(tail, r"Extn?[:.\s]*\d{2,5}(?:-\d{2,5})?")
                email_match = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", tail)
                email = email_match.group(0) if email_match else NOT_FOUND
                pincode = _first_number_pattern(tail, r"\b\d{6}\b")
                
                phone_combined = " / ".join([p for p in (phone, extn) if p]) or NOT_FOUND
                contacts.append({
                    "name": name,
                    "designation": desig,
                    "phone_or_extension": phone_combined,
                    "email": email,
                    "pincode": pincode if pincode else NOT_FOUND,
                })
    return contacts


def extract_client_contacts(text: str) -> List[Dict[str, str]]:
    """
    Master contact extractor. Combines the tightly-anchored contact scanners
    and the competent-authority parser.
    """
    contacts = extract_other_contacts(text)

    ca = extract_competent_authority(text)
    if ca["name"] != NOT_FOUND:
        contacts.append({
            "name": ca["name"],
            "designation": f"Competent Authority ({ca['designation']}, {ca['department']})"
                            if ca["designation"] != NOT_FOUND else "Competent Authority",
            "phone_or_extension": NOT_FOUND,
            "email": NOT_FOUND,
            "pincode": NOT_FOUND,
        })

    # De-dupe based on name only
    seen = set()
    deduped = []
    for c in contacts:
        key = c["name"].lower()
        if key not in seen and c["name"] != NOT_FOUND:
            seen.add(key)
            deduped.append(c)

    if not deduped:
        deduped = [{"name": NOT_FOUND, "designation": NOT_FOUND,
                     "phone_or_extension": NOT_FOUND, "email": NOT_FOUND, "pincode": NOT_FOUND}]

    return deduped


# ---------------------------------------------------------------------------
# Master entry point
# ---------------------------------------------------------------------------

def extract_all(ocr_text: str) -> Dict[str, Any]:
    """
    Run every extractor against the OCR text and merge into one dict
    matching the master infosheet schema.
    """
    ocr_text = normalize_ocr_text(ocr_text)
    result: Dict[str, Any] = {}
    result.update(extract_payment_terms(ocr_text))
    result.update(extract_ld(ocr_text))
    result.update(extract_eligibility(ocr_text))
    result.update(extract_financials(ocr_text))
    result.update(extract_security_deposit(ocr_text))
    result.update(extract_courier_info(ocr_text))
    result["client_contacts"] = extract_client_contacts(ocr_text)
    return result


# ---------------------------------------------------------------------------
# Quick manual test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    sample = """
    Payment terms: 90% payment shall be released on delivery, 10% payment
    against installation and commissioning as per Cl.no.11 of Section-III (ITB).

    Liquidated Damages: 0.5% of the contract value per week of delay,
    subject to a maximum of 10% of contract value, as per Clause 9.2 GCC.

    Bidder should have experience of three similar works of value not less
    than 40% of the estimated bid value, or two similar works of 50%,
    or one similar work of 80% of the estimated value, in the last 3 years.

    Average Annual Turnover of the bidder should not be less than 30% of
    the estimated bid value in the last three financial years.

    ePBG shall be submitted in lieu of Security Deposit.

    Physical documents: hard copy of original EMD instrument to be sent
    within 7 days to the following address, pincode 530012.
    Contact: Consignee Uppada V Prasad Reddy, Extn: 885-380.
    """
    import json
    print(json.dumps(extract_all(sample), indent=2))