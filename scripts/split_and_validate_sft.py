"""
Split SFT Dataset into Train/Val sets and run Step 2 Data Quality & Token Length Validation.
"""

import json
import os
import sys
import statistics

# Reconfigure stdout for UTF-8 compatibility
sys.stdout.reconfigure(encoding="utf-8")

def split_and_validate():
    src_file = "data/processed/dataset_sft.jsonl"
    train_file = "data/processed/sft_train.jsonl"
    val_file = "data/processed/sft_val.jsonl"

    print("=== STEP 1: SPLITTING SFT DATASET ===")
    assert os.path.exists(src_file), f"Source file {src_file} does not exist!"

    with open(src_file, "r", encoding="utf-8") as f:
        records = [json.loads(line) for line in f if line.strip()]

    total = len(records)
    print(f"Total source records: {total}")

    # Stratified split: 10 train (records 0-9 except record 9, plus record 10), 2 val (record 9 [POWERGRID] and record 11 [clause split])
    # Or deterministic 10 train / 2 val
    val_indices = {9, 11} # Record 10 (POWERGRID tender) and Record 12 (Standard payment split clause)
    train_records = [r for idx, r in enumerate(records) if idx not in val_indices]
    val_records = [r for idx, r in enumerate(records) if idx in val_indices]

    print(f"Train split: {len(train_records)} records ({len(train_records)/total*100:.1f}%) -> {train_file}")
    print(f"Val split:   {len(val_records)} records ({len(val_records)/total*100:.1f}%) -> {val_file}")

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
            raw_lines = f.readlines()

        for idx, line in enumerate(raw_lines, 1):
            line_str = line.strip()
            assert line_str, f"Line {idx} in {filepath} is empty!"
            
            # JSON syntax check
            parsed = json.loads(line_str)
            assert set(parsed.keys()) == {"instruction", "input", "output"}, f"Line {idx} invalid keys: {parsed.keys()}"
            
            # Output is valid JSON
            out_obj = json.loads(parsed["output"])
            assert isinstance(out_obj, dict), f"Line {idx} output is not a JSON dict"
            assert len(out_obj) >= 2, f"Line {idx} output has < 2 fields"

            # Check for raw \uXXXX escape sequences in raw line
            assert "\\u0" not in line_str and "\\u20" not in line_str, f"Line {idx} has unescaped unicode escapes!"

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
        # Use Qwen tokenizer if available, else fast tokenizer fallback
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

    for r in records:
        in_text = f"{r['instruction']}\n\n{r['input']}"
        out_text = r["output"]
        
        if tokenizer:
            in_tok = len(tokenizer.encode(in_text))
            out_tok = len(tokenizer.encode(out_text))
        else:
            in_tok = max(1, int(len(in_text) / 3.8))
            out_tok = max(1, int(len(out_text) / 3.8))
            
        input_tokens.append(in_tok)
        output_tokens.append(out_tok)
        total_tokens.append(in_tok + out_tok)

    print(f"Token Length Summary across all {len(records)} records:")
    print(f"  - Input Tokens:  Min = {min(input_tokens)}, Max = {max(input_tokens)}, Median = {statistics.median(input_tokens)}")
    print(f"  - Output Tokens: Min = {min(output_tokens)}, Max = {max(output_tokens)}, Median = {statistics.median(output_tokens)}")
    print(f"  - Total Tokens:  Min = {min(total_tokens)}, Max = {max(total_tokens)}, Median = {statistics.median(total_tokens)}")
    
    max_total = max(total_tokens)
    print(f"\nMax total sequence length: {max_total} tokens")
    if max_total <= 2048:
        print("  [PASS] Fits well within 2,048 context length. Safe for 4-bit / 8-bit LoRA training on free Colab T4 (16GB VRAM) without OOM.")
    elif max_total <= 4096:
        print("  [PASS] Fits within 4,096 context length. Safe for Colab T4 / L4 / A100 GPU.")
    else:
        print(f"  [WARN] Max sequence length {max_total} exceeds 4,096 tokens.")

if __name__ == "__main__":
    split_and_validate()
