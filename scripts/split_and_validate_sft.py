"""
Split SFT Dataset into Train/Val sets (Tender-Group Aware) and run Data Quality & Token Audit.
"""

import json
import os
import re
import sys
import random
import statistics
from typing import Dict, List, Set, Any

# Reconfigure stdout for UTF-8 compatibility
sys.stdout.reconfigure(encoding="utf-8")


def normalize_text(text: str) -> str:
    return " ".join(text.strip().split()).lower()


def extract_tender_group_key(record: Dict[str, Any], idx: int) -> str:
    """Extracts tender ID or document hash to group records from the same tender."""
    in_text = record["input"]
    out_text = record["output"]
    try:
        out_obj = json.loads(out_text)
        if "tender_id_display" in out_obj:
            return normalize_text(str(out_obj["tender_id_display"]))
    except Exception:
        pass

    # Look for GeM bid pattern in input
    m = re.search(r"GEM/\d{4}/[A-Z]/\d+", in_text)
    if m:
        return normalize_text(m.group(0))

    # Look for tender name in input header if present
    m_t = re.search(r"Tender:\s*([^\n]+)", in_text)
    if m_t:
        return normalize_text(m_t.group(1))

    # Fallback to first line hash
    first_line = in_text.strip().split("\n")[0]
    return f"doc_group_{first_line[:40]}"


def split_and_validate():
    src_file = "data/processed/dataset_sft.jsonl"
    train_file = "data/processed/sft_train.jsonl"
    val_file = "data/processed/sft_val.jsonl"

    print("=== STEP 1: SPLITTING SFT DATASET (Tender-Group Aware) ===")
    assert os.path.exists(src_file), f"Source file {src_file} does not exist!"

    with open(src_file, "r", encoding="utf-8") as f:
        records = [json.loads(line) for line in f if line.strip()]

    total = len(records)
    print(f"Total source records: {total}")

    # Group records by tender key
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for idx, r in enumerate(records):
        g_key = extract_tender_group_key(r, idx)
        groups.setdefault(g_key, []).append(r)

    print(f"Distinct tender groups: {len(groups)}")

    # Deterministic split by tender group (85% train / 15% val)
    random.seed(42)
    group_keys = sorted(list(groups.keys()))
    random.shuffle(group_keys)

    train_records: List[Dict[str, Any]] = []
    val_records: List[Dict[str, Any]] = []

    target_val_count = max(2, int(total * 0.15))

    for g in group_keys:
        recs = groups[g]
        if len(val_records) < target_val_count:
            val_records.extend(recs)
        else:
            train_records.extend(recs)

    print(f"Train split: {len(train_records)} records ({len(train_records)/total*100:.1f}%) -> {train_file}")
    print(f"Val split:   {len(val_records)} records ({len(val_records)/total*100:.1f}%) -> {val_file}")

    # Assert 0 leakage
    train_keys = {extract_tender_group_key(r, 0) for r in train_records}
    val_keys = {extract_tender_group_key(r, 0) for r in val_records}
    overlap = train_keys.intersection(val_keys)
    assert len(overlap) == 0, f"Train/Val tender group overlap detected: {overlap}"
    print(f"Zero tender leakage verified: {len(train_keys)} train groups vs {len(val_keys)} val groups (0 overlap).")

    # Write train
    with open(train_file, "w", encoding="utf-8") as f:
        for r in train_records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # Write val
    with open(val_file, "w", encoding="utf-8") as f:
        for r in val_records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print("\n=== STEP 2: DATA QUALITY & UNICODE INTEGRITY AUDIT ===")
    files_to_check = [
        ("Full Dataset", src_file),
        ("Train Set", train_file),
        ("Validation Set", val_file),
    ]

    for label, filepath in files_to_check:
        print(f"\n--- Checking {label} ({filepath}) ---")
        with open(filepath, "r", encoding="utf-8") as f:
            raw_lines = [l.strip() for l in f if l.strip()]

        for idx, line_str in enumerate(raw_lines, 1):
            parsed = json.loads(line_str)
            assert set(parsed.keys()) == {"instruction", "input", "output"}, f"Line {idx} invalid keys: {parsed.keys()}"

            out_obj = json.loads(parsed["output"])
            assert isinstance(out_obj, dict), f"Line {idx} output is not a JSON dict"
            assert len(out_obj) >= 2, f"Line {idx} output has < 2 fields: {out_obj}"

            # Check for raw \uXXXX escape sequences in raw line
            assert "\\u" not in line_str, f"Line {idx} has raw unicode escapes: {line_str[:80]}"

        print(f"  [PASS] {len(raw_lines)} records: Strict 1-line JSON, valid nested JSON output.")

        # Verify Unicode symbols
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        has_rupee = "₹" in content
        has_devanagari = any("\u0900" <= c <= "\u097F" for c in content)
        print(f"  [PASS] Unicode Integrity: ₹ currency symbol present ({has_rupee}), Devanagari text intact ({has_devanagari}), NO \\uXXXX corruption.")

    print("\n=== STEP 3: TOKEN LENGTH ESTIMATION & CONTEXT BUDGET AUDIT ===")
    try:
        from transformers import AutoTokenizer
        tokenizer = AutoTokenizer.from_pretrained("Qwen/Qwen2.5-7B-Instruct", trust_remote_code=True)
        tok_name = "Qwen2.5-7B-Instruct Tokenizer"
    except Exception as e:
        print(f"Loading local HuggingFace tokenizer failed ({e}), using character-to-token ratio (1 token ~= 3.8 chars)...")
        tokenizer = None
        tok_name = "Heuristic Character-Token Estimator"

    print(f"Tokenizer: {tok_name}")

    input_tokens = []
    output_tokens = []
    total_tokens = []
    formatted_tokens = []

    for r in records:
        in_text = f"{r['instruction']}\n\n{r['input']}"
        out_text = r["output"]

        if tokenizer:
            in_tok = len(tokenizer.encode(in_text))
            out_tok = len(tokenizer.encode(out_text))
            messages = [
                {"role": "system", "content": r["instruction"]},
                {"role": "user", "content": r["input"]},
                {"role": "assistant", "content": r["output"]},
            ]
            fmt_tok = len(tokenizer.encode(tokenizer.apply_chat_template(messages, tokenize=False)))
        else:
            in_tok = max(1, int(len(in_text) / 3.8))
            out_tok = max(1, int(len(out_text) / 3.8))
            fmt_tok = in_tok + out_tok + 35

        input_tokens.append(in_tok)
        output_tokens.append(out_tok)
        total_tokens.append(in_tok + out_tok)
        formatted_tokens.append(fmt_tok)

    print(f"Token Length Summary across all {len(records)} records:")
    print(f"  - Input Tokens:  Min = {min(input_tokens)}, Max = {max(input_tokens)}, Median = {statistics.median(input_tokens)}")
    print(f"  - Output Tokens: Min = {min(output_tokens)}, Max = {max(output_tokens)}, Median = {statistics.median(output_tokens)}")
    print(f"  - Total Tokens:  Min = {min(total_tokens)}, Max = {max(total_tokens)}, Median = {statistics.median(total_tokens)}")
    print(f"  - Formatted Chat Tokens: Min = {min(formatted_tokens)}, Max = {max(formatted_tokens)}, Median = {statistics.median(formatted_tokens)}")

    max_fmt = max(formatted_tokens)
    print(f"\nMax total formatted sequence length: {max_fmt} tokens")
    if max_fmt <= 4096:
        print(f"  [PASS] Fits within 4,096 context budget with {4096 - max_fmt} tokens ({(4096-max_fmt)/4096*100:.1f}%) margin.")
    else:
        print(f"  [WARN] Max sequence length {max_fmt} exceeds 4,096 tokens.")


if __name__ == "__main__":
    split_and_validate()
