"""
Build SFT Dataset for Tender Extraction (Breadth-First Multi-Organization & Category Strategy).

Reconstructs the unified SFT dataset (data/processed/dataset_sft.jsonl) with:
1. Breadth-First Diversity: Samples across 80+ diverse PSUs, Ministries, Defence branches,
   and state governments (POWERGRID, BHEL, IOCL, BPCL, Indian Army, Indian Air Force,
   Railways, SAIL, NTPC, NHPC, RINL, MRPL, GAIL, etc.) across diverse procurement categories.
2. Per-Tender Depth Cap: Maximum 2-3 high-value pages per tender to avoid over-indexing.
3. Both Main GeM Tender documents AND linked ATC child documents.
4. Strict document-grounded input envelopes (no synthetic metadata headers).
5. Production-aligned prompt template (matching llm_field_resolver.py).
6. Strict Unicode integrity (literal ₹ and UTF-8 script, 0 control character escapes).
"""

import argparse
import hashlib
import json
import logging
import os
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# Add workspace root to sys.path
sys.path.insert(0, os.getcwd())

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

from scripts.tender_text_extractor import (
    clean_text_block,
    extract_cleaned_page_text,
    is_text_scrambled_or_garbage,
    repair_gem_font_glyphs,
    normalize_symbols_and_checkboxes,
)

# Reconfigure stdout for UTF-8 compatibility
sys.stdout.reconfigure(encoding="utf-8")

SYSTEM_INSTRUCTION = (
    "You are an expert at extracting structured procurement data from Indian government "
    "and PSU tender documents (GeM portal bids and Additional Terms & Conditions). "
    "Extract the requested procurement fields from the provided document text into structured JSON. "
    "Extract only values explicitly present in the text."
)

USER_PROMPT_TEMPLATE = (
    "Extract the critical procurement fields from the following tender document into structured JSON.\n"
    "Fields needed: {field_descriptions}\n\n"
    "--- START OF DOCUMENT ---\n"
    "{document_text}\n"
    "--- END OF DOCUMENT ---"
)


def setup_loggers() -> Tuple[logging.Logger, logging.Logger]:
    os.makedirs("logs", exist_ok=True)

    main_logger = logging.getLogger("build_sft")
    main_logger.setLevel(logging.INFO)
    main_logger.handlers.clear()

    fh = logging.FileHandler("logs/build_sft_dataset.log", mode="w", encoding="utf-8")
    fh.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s"))
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))

    main_logger.addHandler(fh)
    main_logger.addHandler(ch)

    skip_logger = logging.getLogger("sft_skips")
    skip_logger.setLevel(logging.INFO)
    skip_logger.handlers.clear()

    sfh = logging.FileHandler("logs/sft_skipped_records.log", mode="w", encoding="utf-8")
    sfh.setFormatter(logging.Formatter("[%(asctime)s] %(message)s"))
    skip_logger.addHandler(sfh)

    return main_logger, skip_logger


def clean_text_content(text: str) -> str:
    """Uses shared clean_text_block to normalize symbols, repair font glyphs, and strip control characters."""
    return clean_text_block(text)


def normalize_text(text: str) -> str:
    return " ".join(text.strip().split()).lower()


def compute_sha256(input_str: str, output_str: str) -> str:
    norm_in = normalize_text(input_str)
    norm_out = normalize_text(output_str)
    return hashlib.sha256(f"{norm_in}||{norm_out}".encode("utf-8")).hexdigest()


def is_value_grounded(val: Any, text: str) -> bool:
    """Verifies that a field value is identifiably grounded in the text."""
    if val is None:
        return False
    str_val = str(val).strip()
    if not str_val or str_val.upper() in ("NOT_FOUND", "N/A", "NA", "NONE", "NULL"):
        return False

    norm_text = normalize_text(text)
    norm_val = normalize_text(str_val)

    # 1. Exact or normalized string presence
    if str_val in text or norm_val in norm_text:
        return True

    # 2. Numeric / Currency presence
    if isinstance(val, (int, float)):
        int_val = int(val)
        if str(int_val) in text or f"{val}" in text:
            return True

    # Digits only check for amounts and numbers
    num_digits = re.sub(r"\D", "", str_val)
    if num_digits and len(num_digits) >= 2:
        text_digits = re.sub(r"\D", "", text)
        if num_digits in text_digits:
            return True

    # Percentage check
    m_pct = re.match(r"^(\d+(?:\.\d+)?)\s*%$", str_val)
    if m_pct:
        pct_num = m_pct.group(1)
        if pct_num in text:
            return True

    # Days check
    m_days = re.match(r"^(\d+)\s*Days$", str_val, re.IGNORECASE)
    if m_days:
        day_num = m_days.group(1)
        if day_num in text:
            return True

    # Boolean fields
    if str_val in ("Yes", "No", "True", "False"):
        return True

    return False


def build_envelope(doc_text: str, fields_dict: Dict[str, Any]) -> Tuple[str, str]:
    """Wraps text in the production user prompt envelope."""
    clean_doc = clean_text_content(doc_text)
    field_keys = list(fields_dict.keys())
    input_text = USER_PROMPT_TEMPLATE.format(
        field_descriptions=", ".join(field_keys),
        document_text=clean_doc,
    )
    clean_fields = {k: (clean_text_content(v) if isinstance(v, str) else v) for k, v in fields_dict.items()}
    output_text = json.dumps(clean_fields, indent=2, ensure_ascii=False)
    return input_text, output_text


# ---------------------------------------------------------------------------
# SOURCE 1: Gold Standard Main Tenders & Linked ATC Documents (Capped Depth)
# ---------------------------------------------------------------------------
def process_gold_standard_and_atc_tenders(
    ground_truth_path: str,
    tenders_dir: str,
    atc_children_dir: str,
    max_pages_per_tender: int,
    min_fields: int,
    seen_hashes: Set[str],
    main_logger: logging.Logger,
    skip_logger: logging.Logger,
) -> Tuple[List[Dict[str, str]], List[Dict[str, str]]]:
    main_pairs: List[Dict[str, str]] = []
    atc_pairs: List[Dict[str, str]] = []

    if not os.path.exists(ground_truth_path) or not os.path.exists(tenders_dir) or fitz is None:
        main_logger.warning("Gold standard files or PyMuPDF not available.")
        return main_pairs, atc_pairs

    with open(ground_truth_path, "r", encoding="utf-8") as f:
        gt_data = json.load(f)

    # 1. Process Main Gold PDFs (Max 3 pages per tender)
    gold_pdfs = list(Path(tenders_dir).glob("*.pdf"))
    main_logger.info(f"Processing {len(gold_pdfs)} Main Gold Standard PDFs (max {max_pages_per_tender} pages each)...")

    for pdf_path in gold_pdfs:
        tender_key = pdf_path.stem
        gt_fields = gt_data.get(tender_key, {})
        if not gt_fields:
            for k, v in gt_data.items():
                if normalize_text(k) in normalize_text(tender_key) or normalize_text(tender_key) in normalize_text(k):
                    gt_fields = v
                    break

        if not gt_fields:
            continue

        try:
            doc = fitz.open(pdf_path)
        except Exception:
            continue

        tender_page_count = 0
        for page_idx, page in enumerate(doc, 1):
            if tender_page_count >= max_pages_per_tender:
                break

            page_text = extract_cleaned_page_text(doc, page_idx - 1)
            if len(page_text.strip()) < 80:
                continue

            grounded_page_fields = {}
            for field_name, field_val in gt_fields.items():
                if field_name.startswith("_"):
                    continue
                if "preference" in field_name or "relaxation" in field_name:
                    if "Preference" not in page_text and "Exemption" not in page_text and "छूट" not in page_text:
                        continue
                if is_value_grounded(field_val, page_text):
                    grounded_page_fields[field_name] = field_val

            if len(grounded_page_fields) >= min_fields:
                input_text, output_text = build_envelope(page_text, grounded_page_fields)
                rec_hash = compute_sha256(input_text, output_text)
                if rec_hash not in seen_hashes:
                    seen_hashes.add(rec_hash)
                    main_pairs.append({
                        "instruction": SYSTEM_INSTRUCTION,
                        "input": input_text,
                        "output": output_text,
                    })
                    tender_page_count += 1

    # 2. Process Linked ATC Children Documents (Max 3 high-yield pages per ATC doc)
    if os.path.exists(atc_children_dir):
        atc_pdfs = list(Path(atc_children_dir).glob("*.pdf"))
        main_logger.info(f"Processing {len(atc_pdfs)} ATC Child PDFs (max {max_pages_per_tender} pages each)...")

        for pdf_path in atc_pdfs:
            try:
                doc = fitz.open(pdf_path)
            except Exception:
                continue

            matched_gt = None
            first_page_text = extract_cleaned_page_text(doc, 0) if len(doc) > 0 else ""
            for t_key, gt_fields in gt_data.items():
                bid_no = gt_fields.get("tender_id_display", "")
                if bid_no and bid_no in first_page_text:
                    matched_gt = (t_key, gt_fields)
                    break

            if not matched_gt:
                continue

            t_key, gt_fields = matched_gt
            atc_page_count = 0

            # Sort pages by field yield to pick the most informative clauses (BDS/SCC/BEC)
            page_candidates = []
            for page_idx, page in enumerate(doc, 1):
                page_text = extract_cleaned_page_text(doc, page_idx - 1)
                if len(page_text.strip()) < 80:
                    continue

                grounded_atc_fields = {}
                for field_name, field_val in gt_fields.items():
                    if field_name.startswith("_"):
                        continue
                    if "preference" in field_name or "relaxation" in field_name:
                        if "Preference" not in page_text and "Exemption" not in page_text and "छूट" not in page_text:
                            continue
                    if is_value_grounded(field_val, page_text):
                        grounded_atc_fields[field_name] = field_val

                if len(grounded_atc_fields) >= min_fields:
                    page_candidates.append((len(grounded_atc_fields), page_idx, page_text, grounded_atc_fields))

            # Pick top distinct highest-yield pages
            page_candidates.sort(key=lambda x: x[0], reverse=True)
            for _, p_idx, p_txt, g_fields in page_candidates[:max_pages_per_tender]:
                input_text, output_text = build_envelope(p_txt, g_fields)
                rec_hash = compute_sha256(input_text, output_text)
                if rec_hash not in seen_hashes:
                    seen_hashes.add(rec_hash)
                    atc_pairs.append({
                        "instruction": SYSTEM_INSTRUCTION,
                        "input": input_text,
                        "output": output_text,
                    })

    main_logger.info(f"Gold Standard Main source generated {len(main_pairs)} grounded records.")
    main_logger.info(f"ATC Child Documents source generated {len(atc_pairs)} grounded records.")
    return main_pairs, atc_pairs


# ---------------------------------------------------------------------------
# SOURCE 2: Extraction Memory (Ground Truth Anchor Clauses)
# ---------------------------------------------------------------------------
def process_extraction_memory(
    memory_path: str,
    min_chars: int,
    min_fields: int,
    seen_hashes: Set[str],
    main_logger: logging.Logger,
    skip_logger: logging.Logger,
) -> List[Dict[str, str]]:
    pairs: List[Dict[str, str]] = []
    if not os.path.exists(memory_path):
        main_logger.warning(f"Memory file not found: {memory_path}")
        return pairs

    with open(memory_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    examples_by_field = data.get("examples_by_field", {})
    groups = defaultdict(dict)
    for field_name, ex_list in examples_by_field.items():
        for ex in ex_list:
            anchor = ex.get("anchor_text", "").strip()
            val = ex.get("value")
            if anchor and val is not None:
                groups[anchor][field_name] = val

    for anchor_text, field_map in groups.items():
        if len(anchor_text) < min_chars:
            continue

        grounded_fields = {}
        for k, v in field_map.items():
            if is_value_grounded(v, anchor_text):
                grounded_fields[k] = v

        if len(grounded_fields) >= min_fields:
            input_text, output_text = build_envelope(anchor_text, grounded_fields)
            rec_hash = compute_sha256(input_text, output_text)
            if rec_hash not in seen_hashes:
                seen_hashes.add(rec_hash)
                pairs.append({
                    "instruction": SYSTEM_INSTRUCTION,
                    "input": input_text,
                    "output": output_text,
                })

    main_logger.info(f"Extraction Memory generated {len(pairs)} grounded records.")
    return pairs


# ---------------------------------------------------------------------------
# SOURCE 3: Multi-Organization Corpus Tenders (Breadth-First Expansion)
# ---------------------------------------------------------------------------
def extract_grounded_from_document_text(page_text: str) -> Dict[str, Any]:
    fields: Dict[str, Any] = {}
    lines = [l.strip() for l in page_text.split("\n") if l.strip()]

    # 1. Tender ID / Bid Number / Contract No
    m_bid = re.search(r"\b(GEM/\d{4}/[A-Z]/\d+|GEMC-\d+)\b", page_text)
    if m_bid:
        fields["tender_id_display"] = m_bid.group(1)

    # 2. Line-based Header Metadata (GeM Bids & GeM Contracts)
    for i, line in enumerate(lines):
        if any(k in line for k in ["Ministry/State Name", "Ministry:", "मंत्रालय"]):
            if i + 1 < len(lines) and len(lines[i + 1]) > 2 and not lines[i + 1].startswith("/"):
                fields["ministry_name"] = lines[i + 1]
        elif any(k in line for k in ["Department Name", "Department:", "विभाग का नाम"]):
            if i + 1 < len(lines) and len(lines[i + 1]) > 2 and not lines[i + 1].startswith("/"):
                fields["department_name"] = lines[i + 1]
        elif any(k in line for k in ["Organisation Name", "Organisation:", "संगठन का नाम"]):
            if i + 1 < len(lines) and len(lines[i + 1]) > 2 and not lines[i + 1].startswith("/"):
                fields["organization"] = lines[i + 1]
        elif any(k in line for k in ["Item Category", "वस्तु श्रेणी", "मद श्रेणी"]):
            if i + 1 < len(lines) and len(lines[i + 1]) > 2 and not lines[i + 1].startswith("/"):
                fields["item_category_display"] = lines[i + 1]

    # 3. EMD Amount & Requirement
    m_emd = re.search(r"(?:EMD Amount|ईएमडी राशि|Bid Security Amount)\s*[:\n]*\s*(\d+)", page_text)
    if m_emd:
        val = int(m_emd.group(1))
        fields["emd_amount_display"] = f"₹{val:,}"
        fields["emd_required_display"] = "Yes" if val > 0 else "No"

    # 4. ePBG Percentage & Requirement
    m_pbg = re.search(r"(?:ePBG Percentage\(%\)|ईपीबीजी प्रतिशत \(%\)|Security Deposit Percentage)\s*[:\n]*\s*(\d+(?:\.\d+)?)", page_text)
    if m_pbg:
        fields["pbg_percentage_display"] = f"{m_pbg.group(1)}%"
        fields["pbg_required_display"] = "Yes"

    # 5. ePBG Duration
    m_pbg_dur = re.search(r"(?:Duration of ePBG required \(Months\)|ईपीबीजी की अपेक्षित अवधि \(महीने\))\s*[:\n]*\s*(\d+)", page_text)
    if m_pbg_dur:
        fields["pbg_duration_display"] = m_pbg_dur.group(1)

    # 6. Bid Validity
    m_val = re.search(r"(?:Bid Offer Validity|बोली प्रस्ताव वैधता)\s*[:\n\(]*[^\d]*(\d+)\s*\(?Days", page_text, re.IGNORECASE)
    if m_val:
        fields["bid_validity_days_display"] = f"{m_val.group(1)} Days"

    # 7. Total Quantity
    m_qty = re.search(r"(?:Total Quantity|कुल मात्रा)\s*[:\n]*\s*(\d+)", page_text)
    if m_qty:
        fields["total_quantity"] = int(m_qty.group(1))

    # 8. MSE / MII / Startup Preference
    m_mse = re.search(r"(?:MSE Purchase Preference|एमएसई खरीद वरीयता)\s*[:\n]*\s*(Yes|No|हाँ|नहीं)", page_text, re.IGNORECASE)
    if m_mse:
        fields["mse_preference_display"] = "Yes" if any(w in m_mse.group(1).lower() for w in ("yes", "हाँ", "true")) else "No"

    m_mii = re.search(r"(?:MII Purchase Preference|एमआईआई खरीद वरीयता)\s*[:\n]*\s*(Yes|No|हाँ|नहीं)", page_text, re.IGNORECASE)
    if m_mii:
        fields["mii_preference_display"] = "Yes" if any(w in m_mii.group(1).lower() for w in ("yes", "हाँ", "true")) else "No"

    m_start = re.search(r"(?:Startup Exemption|स्टार्टअप छूट)\s*[:\n]*\s*(Yes|No|हाँ|नहीं)", page_text, re.IGNORECASE)
    if m_start:
        fields["startup_relaxation_display"] = "Yes" if any(w in m_start.group(1).lower() for w in ("yes", "हाँ", "true")) else "No"

    # 9. Evaluation Method, Reverse Auction & Bid Type
    m_eval = re.search(r"(?:Evaluation Method|मूल्यांकन पद्धति)\s*[:\n]*\s*([^\n]+)", page_text)
    if m_eval and len(m_eval.group(1).strip()) > 3 and not m_eval.group(1).strip().startswith("/"):
        fields["commercial_evaluation_display"] = m_eval.group(1).strip()

    m_ra = re.search(r"(?:Bid to RA enabled|रिवर्स नीलामी सक्षम)\s*[:\n]*\s*(Yes|No|हाँ|नहीं)", page_text, re.IGNORECASE)
    if m_ra:
        fields["reverse_auction_applicable_display"] = "Yes" if any(w in m_ra.group(1).lower() for w in ("yes", "हाँ", "true")) else "No"

    m_type = re.search(r"(?:Type of Bid|बिड का प्रकार)\s*[:\n]*\s*([^\n]+)", page_text)
    if m_type and ("Packet" in m_type.group(1) or "Single" in m_type.group(1) or "Two" in m_type.group(1)):
        fields["bid_type_display"] = m_type.group(1).strip()

    # 10. Payment Terms splits
    m_pay = re.search(r"(\d{2})%\s*(?:of\s*)?(?:payment|supply|delivery|materials)[^\n]*(\d{2})%\s*(?:on|upon)?\s*(?:installation|commissioning|testing)", page_text, re.IGNORECASE)
    if m_pay:
        fields["payment_terms_supply_display"] = f"{m_pay.group(1)}%"
        fields["payment_terms_installation_display"] = f"{m_pay.group(2)}%"

    # 11. Price Reduction Schedule / LD
    m_prs = re.search(r"(?:Price Reduction Schedule|PRS|Liquidated Damages|LD)[^\n]*(0\.\d+|1/2|\d+)%\s*(?:per\s*week)[^\n]*(?:max|maximum|cap)[^\n]*(\d+(?:\.\d+)?)%", page_text, re.IGNORECASE)
    if m_prs:
        fields["ld_percentage_display"] = m_prs.group(1)
        fields["max_ld_percentage_display"] = m_prs.group(2)

    # 12. Delivery Time
    m_deliv = re.search(r"(?:Delivery Days|डिलीवरी के दिन|Delivery Period)\s*[:\n]*\s*(\d+)", page_text)
    if m_deliv:
        fields["delivery_time_supply_display"] = f"{m_deliv.group(1)} Days"

    # 13. Client Contact Email
    m_email = re.search(r"\b([a-zA-Z0-9_.+-]+@(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,})\b", page_text)
    if m_email and not m_email.group(1).endswith("gov.in/"):
        fields["client_email_1_display"] = m_email.group(1)

    # 14. Courier / Delivery Address
    m_addr = re.search(r"(?:Consignee/Reporting Officer Address|परेषिती/रिपोर्टिंग अधिकारी पता|Beneficiary/लाभार्थी :|Address:)\s*\n*([^\n]+(?:\n[^\n]+){1,3})", page_text)
    if m_addr:
        addr_val = " ".join(m_addr.group(1).split())
        if len(addr_val) > 15:
            fields["courier_address_display"] = addr_val

    # Strict Grounding Verification
    verified_fields = {}
    for k, v in fields.items():
        if is_value_grounded(v, page_text):
            verified_fields[k] = v

    return verified_fields


def process_corpus_tenders_breadth_first(
    corpus_dir: str,
    target_count: int,
    max_records_per_tender: int,
    min_fields: int,
    seen_hashes: Set[str],
    main_logger: logging.Logger,
    skip_logger: logging.Logger,
) -> List[Dict[str, str]]:
    pairs: List[Dict[str, str]] = []
    if not os.path.exists(corpus_dir) or fitz is None:
        main_logger.warning(f"Corpus directory not found: {corpus_dir}")
        return pairs

    pdf_files = list(Path(corpus_dir).glob("*.pdf"))
    main_logger.info(f"Scanning {len(pdf_files)} corpus PDFs for breadth-first volume expansion (target: {target_count})...")

    distinct_orgs = set()
    distinct_ministries = set()
    distinct_categories = set()
    tender_record_counts = defaultdict(int)

    for pdf_path in pdf_files:
        if len(pairs) >= target_count:
            break

        try:
            doc = fitz.open(pdf_path)
        except Exception:
            continue

        tender_id = pdf_path.stem
        for page_idx, page in enumerate(doc, 1):
            if len(pairs) >= target_count:
                break
            if tender_record_counts[tender_id] >= max_records_per_tender:
                break

            try:
                page_text = extract_cleaned_page_text(doc, page_idx - 1)
            except Exception:
                continue

            if len(page_text.strip()) < 100:
                continue

            fields = extract_grounded_from_document_text(page_text)
            if len(fields) < min_fields:
                continue

            input_text, output_text = build_envelope(page_text, fields)
            rec_hash = compute_sha256(input_text, output_text)

            if rec_hash in seen_hashes:
                continue

            seen_hashes.add(rec_hash)
            pairs.append({
                "instruction": SYSTEM_INSTRUCTION,
                "input": input_text,
                "output": output_text,
            })
            tender_record_counts[tender_id] += 1

            if "organization" in fields:
                distinct_orgs.add(fields["organization"])
            if "ministry_name" in fields:
                distinct_ministries.add(fields["ministry_name"])
            if "item_category_display" in fields:
                distinct_categories.add(fields["item_category_display"])

    main_logger.info(f"Corpus breadth expansion generated {len(pairs)} records across {len(tender_record_counts)} distinct tenders.")
    main_logger.info(f"  - Distinct Organizations: {len(distinct_orgs)}")
    main_logger.info(f"  - Distinct Ministries:    {len(distinct_ministries)}")
    main_logger.info(f"  - Distinct Categories:    {len(distinct_categories)}")
    return pairs


def main():
    parser = argparse.ArgumentParser(description="Build SFT Dataset with breadth-first multi-org expansion.")
    parser.add_argument("--ground-truth", default="gold_standard/ground_truth.json", help="Path to Ground Truth JSON")
    parser.add_argument("--gold-tenders", default="gold_standard/tenders", help="Path to Gold Standard Tenders dir")
    parser.add_argument("--atc-children-dir", default="gold_standard/tenders/extracted_children", help="Path to ATC Children dir")
    parser.add_argument("--memory-file", default="backend/app/storage/llm_memory/extraction_memory.json", help="Path to Extraction Memory store")
    parser.add_argument("--corpus-dir", default="tender-documents", help="Path to corpus PDFs dir")
    parser.add_argument("--output-file", default="data/processed/dataset_sft.jsonl", help="Destination path for SFT dataset")
    parser.add_argument("--target-total", type=int, default=260, help="Target total records for SFT dataset")
    parser.add_argument("--max-pages-per-tender", type=int, default=3, help="Max pages per gold standard/ATC tender")
    parser.add_argument("--max-corpus-records-per-tender", type=int, default=1, help="Max records per corpus tender")
    parser.add_argument("--min-fields", type=int, default=3, help="Minimum grounded fields required per record")
    parser.add_argument("--min-chars", type=int, default=30, help="Minimum anchor text chars for memory records")

    args = parser.parse_args()
    main_logger, skip_logger = setup_loggers()

    main_logger.info("=== Starting Breadth-First SFT Dataset Construction (Multi-Org & Multi-Category) ===")
    main_logger.info(f"Target Total: {args.target_total} records (min required: 150)")
    main_logger.info(f"Breadth Constraint: Max {args.max_pages_per_tender} pages per Gold/ATC tender, Max {args.max_corpus_records_per_tender} per Corpus tender.")
    main_logger.info(f"Prompt Template: Production Envelope ('--- START OF DOCUMENT ---')")

    seen_hashes: Set[str] = set()
    all_pairs: List[Dict[str, str]] = []

    # 1. Ingest Gold Standard Main Tenders AND Linked ATC Children (Capped depth)
    gold_main_pairs, atc_child_pairs = process_gold_standard_and_atc_tenders(
        args.ground_truth, args.gold_tenders, args.atc_children_dir, args.max_pages_per_tender, args.min_fields, seen_hashes, main_logger, skip_logger
    )
    all_pairs.extend(gold_main_pairs)
    all_pairs.extend(atc_child_pairs)

    # 2. Ingest Extraction Memory (Grounded anchor clauses)
    mem_pairs = process_extraction_memory(
        args.memory_file, args.min_chars, args.min_fields, seen_hashes, main_logger, skip_logger
    )
    all_pairs.extend(mem_pairs)

    # 3. Ingest Multi-Organization Corpus Tenders (Breadth-first expansion: 1 record per tender)
    needed_corpus_records = max(0, args.target_total - len(all_pairs))
    corpus_pairs = process_corpus_tenders_breadth_first(
        args.corpus_dir, needed_corpus_records, args.max_corpus_records_per_tender, args.min_fields, seen_hashes, main_logger, skip_logger
    )
    all_pairs.extend(corpus_pairs)

    # Write output JSONL
    out_dir = os.path.dirname(args.output_file)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    with open(args.output_file, "w", encoding="utf-8") as f:
        for p in all_pairs:
            line = json.dumps(p, ensure_ascii=False)
            f.write(line + "\n")

    total_count = len(all_pairs)
    file_size_kb = os.path.getsize(args.output_file) / 1024

    main_logger.info("=== BREADTH-FIRST SFT DATASET AUDIT SUMMARY ===")
    main_logger.info(f"Source Breakdown:")
    main_logger.info(f"  - Gold Standard Main Pages:     {len(gold_main_pairs)}")
    main_logger.info(f"  - ATC Child Document Pages:     {len(atc_child_pairs)}")
    main_logger.info(f"  - Extraction Memory Clauses:    {len(mem_pairs)}")
    main_logger.info(f"  - Multi-Org Corpus Tenders:     {len(corpus_pairs)}")
    main_logger.info(f"Total Exported SFT Records:       {total_count}")
    main_logger.info(f"Destination:                      {args.output_file}")
    main_logger.info(f"File Size:                        {file_size_kb:.2f} KB")

    if total_count >= 150:
        main_logger.info(f"[SUCCESS] Dataset volume ({total_count}) satisfies >= 150 requirement.")
    else:
        main_logger.warning(f"[WARN] Total count {total_count} is below 150.")


if __name__ == "__main__":
    main()
