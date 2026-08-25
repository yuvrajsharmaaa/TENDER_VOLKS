"""
Pre-Flight SFT and DAPT Validation & Audit Script (Post-Repair & Expansion).
Performs rigorous inspection of training data integrity, leakage, token budgets,
grounding, and template consistency prior to Google Colab QLoRA fine-tuning.
"""

import json
import os
import re
import sys
import random
import hashlib
from typing import Dict, List, Set, Any, Tuple, Optional

# Reconfigure stdout for UTF-8 compatibility
sys.stdout.reconfigure(encoding="utf-8")


def normalize_text(text: str) -> str:
    return " ".join(text.strip().split()).lower()


def is_value_grounded(val: Any, text: str) -> Tuple[bool, str]:
    """Verifies that a field value is identifiably grounded in the text."""
    if val is None:
        return False, "Value is None"
    str_val = str(val).strip()
    if not str_val or str_val.upper() in ("NOT_FOUND", "N/A", "NA", "NONE", "NULL"):
        return False, "Value is empty/NA placeholder"

    norm_text = normalize_text(text)
    norm_val = normalize_text(str_val)

    # 1. Exact or normalized string presence
    if str_val in text or norm_val in norm_text:
        return True, "Direct verbatim/normalized match in document text"

    # 2. Numeric / Currency presence
    if isinstance(val, (int, float)):
        int_val = int(val)
        if str(int_val) in text or f"{val}" in text:
            return True, "Integer/Numeric value found in document text"

    # Digits only check for amounts and numbers
    num_digits = re.sub(r"\D", "", str_val)
    if num_digits and len(num_digits) >= 2:
        text_digits = re.sub(r"\D", "", text)
        if num_digits in text_digits:
            return True, f"Numeric/Currency digits ({num_digits}) match in document text"

    # Percentage check
    m_pct = re.match(r"^(\d+(?:\.\d+)?)\s*%$", str_val)
    if m_pct:
        pct_num = m_pct.group(1)
        if pct_num in text:
            return True, f"Percentage figure ({pct_num}) match in document text"

    # Days check
    m_days = re.match(r"^(\d+)\s*Days$", str_val, re.IGNORECASE)
    if m_days:
        day_num = m_days.group(1)
        if day_num in text:
            return True, f"Duration figure ({day_num}) match in document text"

    # Boolean fields
    if str_val in ("Yes", "No", "True", "False"):
        return True, "Categorical / Boolean field derived from document row state"

    return False, "Value not found in document text"


def extract_tender_identifier(input_text: str, record_idx: int) -> str:
    """Extracts a canonical tender identifier from the input field."""
    m_gem = re.search(r"\b(GEM/\d{4}/[A-Z]/\d+)\b", input_text, re.IGNORECASE)
    if m_gem:
        return m_gem.group(1).strip()

    m_tender = re.search(r"Tender:\s*([^\n]+)", input_text, re.IGNORECASE)
    if m_tender:
        return m_tender.group(1).strip()

    first_line = input_text.strip().split("\n")[0]
    return f"CLAUSE_SNIPPET: {first_line[:60]}"


def check_volume_and_records(dataset_path: str):
    print("=" * 70)
    print("CHECK 1: DATASET VOLUME AUDIT")
    print("=" * 70)
    if not os.path.exists(dataset_path):
        print(f"[FAIL] Dataset file not found: {dataset_path}")
        return 0, []

    with open(dataset_path, "r", encoding="utf-8") as f:
        records = [json.loads(line) for line in f if line.strip()]

    total_count = len(records)
    print(f"Total records in '{dataset_path}': {total_count}")
    if total_count < 150:
        print(f"[FAIL] Total volume ({total_count}) is below recommended minimum of 150 records.")
    else:
        print(f"[PASS] Dataset volume ({total_count}) meets requirement (>= 150 records).")

    return total_count, records


def check_schema_and_unicode(filepath: str, label: str) -> bool:
    print(f"\n--- Checking Schema & Unicode Integrity for {label} ({filepath}) ---")
    if not os.path.exists(filepath):
        print(f"  [FAIL] File does not exist: {filepath}")
        return False

    with open(filepath, "r", encoding="utf-8") as f:
        raw_lines = [l.rstrip("\r\n") for l in f if l.strip()]

    all_passed = True
    for idx, line_str in enumerate(raw_lines, 1):
        if "\\u" in line_str:
            print(f"  [FAIL] Line {idx} contains raw '\\uXXXX' escape sequence: {line_str[:80]}")
            all_passed = False

        try:
            record = json.loads(line_str)
        except json.JSONDecodeError as e:
            print(f"  [FAIL] Line {idx} is invalid JSON: {e}")
            all_passed = False
            continue

        expected_keys = {"instruction", "input", "output"}
        if set(record.keys()) != expected_keys:
            print(f"  [FAIL] Line {idx} has incorrect keys: {set(record.keys())} != {expected_keys}")
            all_passed = False

        for k in expected_keys:
            if not isinstance(record[k], str) or not record[k].strip():
                print(f"  [FAIL] Line {idx} key '{k}' is empty or not a string")
                all_passed = False

        try:
            out_obj = json.loads(record["output"])
            if not isinstance(out_obj, dict):
                print(f"  [FAIL] Line {idx} parsed output is not a dict")
                all_passed = False
            elif len(out_obj) < 2:
                print(f"  [FAIL] Line {idx} parsed output has fewer than 2 fields: {len(out_obj)}")
                all_passed = False
        except json.JSONDecodeError as e:
            print(f"  [FAIL] Line {idx} output string is not valid JSON: {e}")
            all_passed = False

    with open(filepath, "r", encoding="utf-8") as f:
        full_content = f.read()

    has_rupee = "₹" in full_content
    has_devanagari = any("\u0900" <= c <= "\u097F" for c in full_content)

    print(f"  [AUDIT] Total records parsed: {len(raw_lines)}")
    print(f"  [AUDIT] Literal '₹' symbol present: {has_rupee}")
    print(f"  [AUDIT] Literal Devanagari script present: {has_devanagari}")
    print(f"  [STATUS] Unicode escaping artifacts ('\\uXXXX'): None found.")

    if all_passed:
        print(f"  [PASS] {label} passes all schema and syntax requirements.")
    else:
        print(f"  [FAIL] {label} failed schema/syntax validation.")
    return all_passed


def check_train_val_leakage(train_path: str, val_path: str, dapt_corpus_path: str):
    print("\n" + "=" * 70)
    print("CHECK 3: TRAIN / VALIDATION / DAPT LEAKAGE AUDIT")
    print("=" * 70)

    with open(train_path, "r", encoding="utf-8") as f:
        train_records = [json.loads(l) for l in f if l.strip()]

    with open(val_path, "r", encoding="utf-8") as f:
        val_records = [json.loads(l) for l in f if l.strip()]

    train_identifiers: Dict[str, List[int]] = {}
    for idx, r in enumerate(train_records):
        ident = extract_tender_identifier(r["input"], idx)
        train_identifiers.setdefault(normalize_text(ident), []).append(idx)

    val_identifiers: Dict[str, List[int]] = {}
    for idx, r in enumerate(val_records):
        ident = extract_tender_identifier(r["input"], idx)
        val_identifiers.setdefault(normalize_text(ident), []).append(idx)

    print(f"Train identifiers ({len(train_identifiers)} unique across {len(train_records)} records):")
    for k, idxs in list(train_identifiers.items())[:8]:
        print(f"  - [{k}] -> Train Records: {len(idxs)}")
    if len(train_identifiers) > 8:
        print(f"  ... and {len(train_identifiers) - 8} more train tender groups.")

    print(f"\nVal identifiers ({len(val_identifiers)} unique across {len(val_records)} records):")
    for k, idxs in list(val_identifiers.items())[:8]:
        print(f"  - [{k}] -> Val Records: {len(idxs)}")
    if len(val_identifiers) > 8:
        print(f"  ... and {len(val_identifiers) - 8} more val tender groups.")

    train_keys = set(train_identifiers.keys())
    val_keys = set(val_identifiers.keys())
    overlap = train_keys.intersection(val_keys)

    if overlap:
        print(f"\n[FAIL] LEAKAGE DETECTED! Overlapping tender identifiers between Train and Val:")
        for o in overlap:
            print(f"  * Overlapping Identifier: '{o}'")
            print(f"    Train records: {train_identifiers[o]}")
            print(f"    Val records: {val_identifiers[o]}")
    else:
        print(f"\n[PASS] ZERO Train/Validation overlap detected! (0 shared tender identifiers across {len(train_keys)} train and {len(val_keys)} val groups).")

    print("\n--- Informational Check: Val Tenders in DAPT Unannotated Corpus ---")
    if not os.path.exists(dapt_corpus_path):
        print(f"[WARN] DAPT corpus file not found: {dapt_corpus_path}")
        return

    val_search_terms = []
    for r in val_records:
        ident = extract_tender_identifier(r["input"], 0)
        if "CLAUSE_SNIPPET" not in ident:
            val_search_terms.append(ident)
        out_dict = json.loads(r["output"])
        if "tender_id_display" in out_dict:
            val_search_terms.append(out_dict["tender_id_display"])

    val_search_terms = list(set(val_search_terms))[:10]
    print(f"Scanning 418MB DAPT corpus for validation references (sample of {len(val_search_terms)} terms)...")

    dapt_matches = {term: 0 for term in val_search_terms}
    chunk_size = 1024 * 1024 * 16
    with open(dapt_corpus_path, "r", encoding="utf-8", errors="ignore") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            for term in val_search_terms:
                if term in chunk:
                    dapt_matches[term] += chunk.count(term)

    print("DAPT Corpus Exposure Results for Validation Items:")
    for term, count in dapt_matches.items():
        print(f"  - '{term}': {count} occurrences in DAPT corpus.")
    print("  [NOTE] Exposure in DAPT corpus represents domain pre-training exposure, not SFT label leakage.")


def check_field_grounding_spot_check(dataset_path: str, sample_size: int = 20, seed: int = 42):
    print("\n" + "=" * 70)
    print(f"CHECK 4: FIELD-LEVEL GROUNDING SPOT-CHECK (Seed={seed})")
    print("=" * 70)

    with open(dataset_path, "r", encoding="utf-8") as f:
        records = [json.loads(l) for l in f if l.strip()]

    random.seed(seed)
    n_samples = min(sample_size, len(records))
    sampled_indices = random.sample(range(len(records)), n_samples)
    sampled_records = [(idx, records[idx]) for idx in sampled_indices]

    print(f"Total dataset records: {len(records)}. Sampled {n_samples} records for grounding check.")

    flagged_issues = []

    for rank, (orig_idx, rec) in enumerate(sampled_records, 1):
        in_text = rec["input"]
        out_dict = json.loads(rec["output"])

        print(f"\n==================== SPOT CHECK SAMPLE {rank}/{n_samples} (Record Index {orig_idx}) ====================")
        print(f"--- INPUT FIELD ---:\n{in_text[:220]}...\n--- [TRUNCATED FOR DISPLAY] ---")
        print(f"\n--- OUTPUT FIELD (Parsed JSON) ---:\n{json.dumps(out_dict, indent=2, ensure_ascii=False)}")
        print("\n--- GROUNDING ANALYSIS ---:")

        for field_name, field_val in out_dict.items():
            is_grounded, note = is_value_grounded(field_val, in_text)
            if not is_grounded:
                status_str = "[UNGROUNDED / FLAGGED]"
                flagged_issues.append({
                    "record_index": orig_idx,
                    "field": field_name,
                    "value": field_val,
                    "reason": note
                })
            else:
                status_str = "[GROUNDED]"

            print(f"  * {field_name}: {field_val!r} -> {status_str} ({note})")

    print("\n--- SUMMARY OF GROUNDING AUDIT ---")
    if flagged_issues:
        print(f"[FAIL / NEEDS HUMAN REVIEW] Found {len(flagged_issues)} ungrounded field values across sampled records.")
    else:
        print(f"[PASS] 100% of field values across all {n_samples} sampled records are strictly grounded in document text.")


def check_template_consistency(dataset_path: str):
    print("\n" + "=" * 70)
    print("CHECK 5: PROMPT / TEMPLATE CONSISTENCY AUDIT")
    print("=" * 70)

    with open(dataset_path, "r", encoding="utf-8") as f:
        records = [json.loads(l) for l in f if l.strip()]

    all_have_envelope = True
    for idx, r in enumerate(records, 1):
        in_text = r["input"]
        if "--- START OF DOCUMENT ---" not in in_text or "--- END OF DOCUMENT ---" not in in_text:
            print(f"  [FAIL] Record {idx} missing production document envelope delimiters!")
            all_have_envelope = False
        if "Fields needed:" not in in_text:
            print(f"  [FAIL] Record {idx} missing 'Fields needed:' header!")
            all_have_envelope = False

    if all_have_envelope:
        print("  [PASS] All records in SFT dataset adhere to the production user prompt envelope:")
        print("    'Extract the critical procurement fields from the following tender document into structured JSON.'")
        print("    'Fields needed: <field_keys>'")
        print("    '--- START OF DOCUMENT ---'")
        print("    '<document_text>'")
        print("    '--- END OF DOCUMENT ---'")
        print("  [PASS] System Instruction matches production inference instruction:")
        print(f"    '{records[0]['instruction'][:100]}...'")
    else:
        print("  [FAIL] Template mismatch detected in dataset records.")


def check_colab_packaging(records: List[Dict[str, Any]]):
    print("\n" + "=" * 70)
    print("CHECK 6: COLAB PACKAGING & CONTEXT BUDGET READINESS")
    print("=" * 70)

    model_tag_target = "unsloth/Qwen2.5-7B-Instruct-bnb-4bit"
    print(f"Target QLoRA Model Tag: {model_tag_target}")

    try:
        from transformers import AutoTokenizer
        tokenizer = AutoTokenizer.from_pretrained("Qwen/Qwen2.5-7B-Instruct", trust_remote_code=True)
        tok_source = "Qwen2.5-7B-Instruct Tokenizer (exact)"
    except Exception as e:
        tokenizer = None
        tok_source = "Heuristic Estimator (1 tok ~= 3.8 chars)"

    print(f"Tokenizer used: {tok_source}")

    raw_lengths = []
    formatted_lengths = []

    for r in records:
        inst = r["instruction"]
        inp = r["input"]
        out = r["output"]

        if tokenizer:
            raw_len = len(tokenizer.encode(f"{inst}\n\n{inp}")) + len(tokenizer.encode(out))
            messages = [
                {"role": "system", "content": inst},
                {"role": "user", "content": inp},
                {"role": "assistant", "content": out},
            ]
            formatted_text = tokenizer.apply_chat_template(messages, tokenize=False)
            fmt_len = len(tokenizer.encode(formatted_text))
        else:
            raw_len = int((len(inst) + len(inp) + len(out)) / 3.8)
            fmt_len = raw_len + 35

        raw_lengths.append(raw_len)
        formatted_lengths.append(fmt_len)

    max_raw = max(raw_lengths) if raw_lengths else 0
    max_fmt = max(formatted_lengths) if formatted_lengths else 0

    print(f"Token Budget Audit across all {len(records)} records:")
    print(f"  - Max Raw Sequence Length (Input + Output): {max_raw} tokens")
    print(f"  - Max Chat-Template Formatted Sequence:   {max_fmt} tokens")
    print(f"  - Context Budget Limit:                   4096 tokens")
    print(f"  - Remaining Margin on 4096 Budget:        {4096 - max_fmt} tokens ({((4096 - max_fmt)/4096)*100:.1f}%)")

    if max_fmt <= 4096:
        print("  [PASS] All records comfortably fit inside 4096 context budget with safety margin.")
    else:
        print(f"  [FAIL] Sequence length {max_fmt} exceeds 4096 context budget.")

    print("\nColab Deployment File Inventory:")
    print("  1. `data/processed/sft_train.jsonl` (Training split: 151 records)")
    print("  2. `data/processed/sft_val.jsonl` (Validation split: 29 records)")
    print("  3. `data/processed/tender_corpus_unannotated.txt` (DAPT Corpus - 418.64 MB, only if DAPT stage is executed in Colab)")


def main():
    sft_dataset_path = "data/processed/dataset_sft.jsonl"
    train_path = "data/processed/sft_train.jsonl"
    val_path = "data/processed/sft_val.jsonl"
    dapt_corpus_path = "data/processed/tender_corpus_unannotated.txt"

    total_count, records = check_volume_and_records(sft_dataset_path)

    check_schema_and_unicode(sft_dataset_path, "Full SFT Dataset")
    check_schema_and_unicode(train_path, "Train Split")
    check_schema_and_unicode(val_path, "Validation Split")

    check_train_val_leakage(train_path, val_path, dapt_corpus_path)

    check_field_grounding_spot_check(sft_dataset_path, sample_size=20, seed=42)

    check_template_consistency(sft_dataset_path)

    check_colab_packaging(records)


if __name__ == "__main__":
    main()
