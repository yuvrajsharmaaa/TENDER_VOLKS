"""
Verification script for data/processed/dataset_sft.jsonl.
Asserts schema compliance, valid JSON in outputs, prints total line count
and displays 3 random sample records.
"""

import json
import os
import random
import sys

# Reconfigure stdout for UTF-8 compatibility
sys.stdout.reconfigure(encoding="utf-8")


def verify_dataset(file_path: str = "data/processed/dataset_sft.jsonl"):
    print(f"=== Verifying SFT Dataset: {file_path} ===")
    if not os.path.exists(file_path):
        print(f"FAIL: File does not exist: {file_path}")
        sys.exit(1)

    file_size_bytes = os.path.getsize(file_path)
    print(f"File size: {file_size_bytes / 1024:.2f} KB ({file_size_bytes} bytes)")

    lines = []
    with open(file_path, "r", encoding="utf-8") as f:
        for idx, line in enumerate(f, start=1):
            line_str = line.strip()
            if not line_str:
                continue
            try:
                record = json.loads(line_str)
            except json.JSONDecodeError as e:
                print(f"FAIL: Line {idx} is not valid JSON: {e}")
                sys.exit(1)

            # Assert exact keys
            expected_keys = {"instruction", "input", "output"}
            actual_keys = set(record.keys())
            assert actual_keys == expected_keys, f"Line {idx} keys mismatch. Expected {expected_keys}, got {actual_keys}"

            # Assert non-empty strings
            assert isinstance(record["instruction"], str) and record["instruction"].strip(), f"Line {idx} 'instruction' must be non-empty string"
            assert isinstance(record["input"], str) and record["input"].strip(), f"Line {idx} 'input' must be non-empty string"
            assert isinstance(record["output"], str) and record["output"].strip(), f"Line {idx} 'output' must be non-empty string"

            # Assert output is valid parseable JSON
            try:
                parsed_output = json.loads(record["output"])
                assert isinstance(parsed_output, dict), f"Line {idx} parsed output must be a dict"
                assert len(parsed_output) >= 2, f"Line {idx} parsed output has fewer than 2 fields: {parsed_output}"
            except json.JSONDecodeError as e:
                print(f"FAIL: Line {idx} 'output' field is not valid JSON: {e}")
                sys.exit(1)

            lines.append(record)

    total_lines = len(lines)
    print(f"PASS: All {total_lines} lines strictly adhere to the SFT JSON schema.")
    print(f"Total line count: {total_lines}")

    print("\n" + "=" * 60)
    print("=== 3 SAMPLE RECORDS (RANDOM SELECTION) ===")
    print("=" * 60)

    sample_count = min(3, total_lines)
    random.seed(42)
    samples = random.sample(lines, sample_count)

    for i, s in enumerate(samples, start=1):
        print(f"\n--- SAMPLE RECORD {i} ---")
        print(f"INSTRUCTION:\n{s['instruction']}")
        print(f"\nINPUT:\n{s['input']}")
        print(f"\nOUTPUT (JSON string):\n{s['output']}")
        print("-" * 40)


if __name__ == "__main__":
    target_path = sys.argv[1] if len(sys.argv) > 1 else "data/processed/dataset_sft.jsonl"
    verify_dataset(target_path)
