"""
Build SFT Dataset for Tender Extraction.
Merges gold_standard/ground_truth.json (Primary),
gold_standard/fresh_pipeline_audit_dump.json (Secondary),
and backend/app/storage/llm_memory/extraction_memory.json (Supplementary)
into data/processed/dataset_sft.jsonl.
"""

import argparse
import hashlib
import json
import logging
import os
import sys
from collections import defaultdict
from typing import Any, Dict, List, Set, Tuple

# Reconfigure stdout for UTF-8 compatibility
sys.stdout.reconfigure(encoding="utf-8")

METADATA_KEYS = {
    "_info_sheet_statuses",
    "status_summary",
    "missing_fields",
    "_info_sheet_sources",
}

INSTRUCTION_TEXT = (
    "Extract the critical procurement fields from the following tender clause into structured JSON."
)


def setup_loggers() -> Tuple[logging.Logger, logging.Logger]:
    os.makedirs("logs", exist_ok=True)

    # Main build logger
    main_logger = logging.getLogger("build_sft")
    main_logger.setLevel(logging.INFO)
    main_logger.handlers.clear()

    fh = logging.FileHandler("logs/build_sft_dataset.log", mode="w", encoding="utf-8")
    fh.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s"))
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))

    main_logger.addHandler(fh)
    main_logger.addHandler(ch)

    # Skip logger
    skip_logger = logging.getLogger("sft_skips")
    skip_logger.setLevel(logging.INFO)
    skip_logger.handlers.clear()

    sfh = logging.FileHandler("logs/sft_skipped_records.log", mode="w", encoding="utf-8")
    sfh.setFormatter(logging.Formatter("[%(asctime)s] %(message)s"))
    skip_logger.addHandler(sfh)

    return main_logger, skip_logger


def normalize_text(text: str) -> str:
    return " ".join(text.strip().split()).lower()


def compute_sha256(input_str: str, output_str: str) -> str:
    norm_in = normalize_text(input_str)
    norm_out = normalize_text(output_str)
    return hashlib.sha256(f"{norm_in}||{norm_out}".encode("utf-8")).hexdigest()


def filter_dict_values(raw_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Remove MISSING placeholders and internal metadata keys."""
    clean = {}
    for k, v in raw_dict.items():
        if k in METADATA_KEYS:
            continue
        if isinstance(v, str):
            if "MISSING" in v or v.strip() == "":
                continue
        if v is None:
            continue
        clean[k] = v
    return clean


def process_source_1(
    file_path: str,
    min_fields: int,
    seen_tenders: Set[str],
    seen_hashes: Set[str],
    main_logger: logging.Logger,
    skip_logger: logging.Logger,
) -> Tuple[List[Dict[str, str]], int, int, int]:
    pairs: List[Dict[str, str]] = []
    total_ingested = 0
    skipped_too_few = 0
    skipped_dup = 0

    if not os.path.exists(file_path):
        main_logger.warning(f"SOURCE 1 file not found: {file_path}")
        return pairs, total_ingested, skipped_too_few, skipped_dup

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    total_ingested = len(data)
    main_logger.info(f"Loaded {total_ingested} records from SOURCE 1 ({file_path})")

    for tender_name, fields_dict in data.items():
        clean_fields = filter_dict_values(fields_dict)
        if len(clean_fields) < min_fields:
            skip_logger.info(
                f"[SKIP] Source: SOURCE 1 | Record: {tender_name} | Reason: Output has {len(clean_fields)} fields (< {min_fields})"
            )
            skipped_too_few += 1
            continue

        org = clean_fields.get("organization", "").strip()
        field_keys = [k for k in clean_fields.keys() if k != "organization"]
        
        if org:
            input_text = f"Tender: {tender_name}\nOrganization: {org}\nFields to extract: {', '.join(field_keys)}"
        else:
            input_text = f"Tender: {tender_name}\nFields to extract: {', '.join(field_keys)}"

        output_text = json.dumps(clean_fields, indent=2, ensure_ascii=False)
        record_hash = compute_sha256(input_text, output_text)

        if record_hash in seen_hashes:
            skip_logger.info(
                f"[SKIP] Source: SOURCE 1 | Record: {tender_name} | Reason: Duplicate SHA-256 hash {record_hash[:8]}"
            )
            skipped_dup += 1
            continue

        seen_hashes.add(record_hash)
        seen_tenders.add(normalize_text(tender_name))

        pairs.append({
            "instruction": INSTRUCTION_TEXT,
            "input": input_text,
            "output": output_text,
        })

    return pairs, total_ingested, skipped_too_few, skipped_dup


def process_source_2(
    file_path: str,
    min_fields: int,
    seen_tenders: Set[str],
    seen_hashes: Set[str],
    main_logger: logging.Logger,
    skip_logger: logging.Logger,
) -> Tuple[List[Dict[str, str]], int, int, int, int]:
    pairs: List[Dict[str, str]] = []
    total_ingested = 0
    skipped_too_few = 0
    skipped_tender_dup = 0
    skipped_hash_dup = 0

    if not os.path.exists(file_path):
        main_logger.warning(f"SOURCE 2 file not found: {file_path}")
        return pairs, total_ingested, skipped_too_few, skipped_tender_dup, skipped_hash_dup

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    total_ingested = len(data)
    main_logger.info(f"Loaded {total_ingested} records from SOURCE 2 ({file_path})")

    for tender_name, fields_dict in data.items():
        # Check tender deduplication
        norm_tname = normalize_text(tender_name)
        if norm_tname in seen_tenders:
            skip_logger.info(
                f"[SKIP] Source: SOURCE 2 | Record: {tender_name} | Reason: Tender name already processed in higher-priority source"
            )
            skipped_tender_dup += 1
            continue

        clean_fields = filter_dict_values(fields_dict)
        if len(clean_fields) < min_fields:
            skip_logger.info(
                f"[SKIP] Source: SOURCE 2 | Record: {tender_name} | Reason: Output has {len(clean_fields)} fields (< {min_fields})"
            )
            skipped_too_few += 1
            continue

        org = clean_fields.get("organization", "").strip()
        field_keys = [k for k in clean_fields.keys() if k != "organization"]

        if org:
            input_text = f"Tender: {tender_name}\nOrganization: {org}\nFields to extract: {', '.join(field_keys)}"
        else:
            input_text = f"Tender: {tender_name}\nFields to extract: {', '.join(field_keys)}"

        output_text = json.dumps(clean_fields, indent=2, ensure_ascii=False)
        record_hash = compute_sha256(input_text, output_text)

        if record_hash in seen_hashes:
            skip_logger.info(
                f"[SKIP] Source: SOURCE 2 | Record: {tender_name} | Reason: Duplicate SHA-256 hash {record_hash[:8]}"
            )
            skipped_hash_dup += 1
            continue

        seen_hashes.add(record_hash)
        seen_tenders.add(norm_tname)

        pairs.append({
            "instruction": INSTRUCTION_TEXT,
            "input": input_text,
            "output": output_text,
        })

    return pairs, total_ingested, skipped_too_few, skipped_tender_dup, skipped_hash_dup


def process_source_3(
    file_path: str,
    min_chars: int,
    min_fields: int,
    seen_hashes: Set[str],
    main_logger: logging.Logger,
    skip_logger: logging.Logger,
) -> Tuple[List[Dict[str, str]], int, int, int, int]:
    pairs: List[Dict[str, str]] = []
    total_ingested = 0
    skipped_too_short = 0
    skipped_too_few = 0
    skipped_hash_dup = 0

    if not os.path.exists(file_path):
        main_logger.warning(f"SOURCE 3 file not found: {file_path}")
        return pairs, total_ingested, skipped_too_short, skipped_too_few, skipped_hash_dup

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    examples_by_field = data.get("examples_by_field", {})
    total_fields = len(examples_by_field)
    
    # Count total raw examples
    raw_ex_count = sum(len(exs) for exs in examples_by_field.values())
    main_logger.info(
        f"Loaded SOURCE 3 ({file_path}): {total_fields} field categories, {raw_ex_count} total examples"
    )

    # Group by anchor_text
    groups = defaultdict(dict)
    for field_name, ex_list in examples_by_field.items():
        for ex in ex_list:
            total_ingested += 1
            anchor = ex.get("anchor_text", "").strip()
            val = ex.get("value")
            if anchor and val is not None:
                groups[anchor][field_name] = val

    main_logger.info(f"SOURCE 3 formed {len(groups)} distinct anchor_text groups")

    for anchor_text, field_map in groups.items():
        if len(anchor_text) < min_chars:
            skip_logger.info(
                f"[SKIP] Source: SOURCE 3 | Record: anchor_len={len(anchor_text)} | Reason: Anchor text shorter than {min_chars} chars ({anchor_text[:30]!r}...)"
            )
            skipped_too_short += 1
            continue

        if len(field_map) < min_fields:
            skip_logger.info(
                f"[SKIP] Source: SOURCE 3 | Record: fields={list(field_map.keys())} | Reason: Fewer than {min_fields} distinct fields ({len(field_map)})"
            )
            skipped_too_few += 1
            continue

        input_text = anchor_text
        output_text = json.dumps(field_map, indent=2, ensure_ascii=False)
        record_hash = compute_sha256(input_text, output_text)

        if record_hash in seen_hashes:
            skip_logger.info(
                f"[SKIP] Source: SOURCE 3 | Record: anchor_len={len(anchor_text)} | Reason: Duplicate SHA-256 hash {record_hash[:8]}"
            )
            skipped_hash_dup += 1
            continue

        seen_hashes.add(record_hash)
        pairs.append({
            "instruction": INSTRUCTION_TEXT,
            "input": input_text,
            "output": output_text,
        })

    return pairs, total_ingested, skipped_too_short, skipped_too_few, skipped_hash_dup


def main():
    parser = argparse.ArgumentParser(description="Build SFT Dataset from multi-source tender extractions.")
    parser.add_argument("--primary", default="gold_standard/ground_truth.json", help="Path to SOURCE 1 ground truth")
    parser.add_argument("--audit-dump", default="gold_standard/fresh_pipeline_audit_dump.json", help="Path to SOURCE 2 audit dump")
    parser.add_argument("--memory-file", default="backend/app/storage/llm_memory/extraction_memory.json", help="Path to SOURCE 3 extraction memory")
    parser.add_argument("--output-file", default="data/processed/dataset_sft.jsonl", help="Path to destination .jsonl file")
    parser.add_argument("--min-chars", type=int, default=30, help="Min chars for SOURCE 3 anchor text")
    parser.add_argument("--min-fields", type=int, default=2, help="Min non-missing fields required in output")

    args = parser.parse_args()
    main_logger, skip_logger = setup_loggers()

    main_logger.info("=== Starting SFT Dataset Construction ===")
    main_logger.info(f"Primary: {args.primary}")
    main_logger.info(f"Audit Dump: {args.audit_dump}")
    parser_memory = args.memory_file
    main_logger.info(f"Memory File: {parser_memory}")
    main_logger.info(f"Output File: {args.output_file}")
    main_logger.info(f"Min Chars: {args.min_chars} | Min Fields: {args.min_fields}")

    seen_tenders: Set[str] = set()
    seen_hashes: Set[str] = set()
    all_pairs: List[Dict[str, str]] = []

    # 1. Process SOURCE 1
    s1_pairs, s1_total, s1_skip_fields, s1_skip_hash = process_source_1(
        args.primary, args.min_fields, seen_tenders, seen_hashes, main_logger, skip_logger
    )
    all_pairs.extend(s1_pairs)

    # 2. Process SOURCE 2
    s2_pairs, s2_total, s2_skip_fields, s2_skip_tender, s2_skip_hash = process_source_2(
        args.audit_dump, args.min_fields, seen_tenders, seen_hashes, main_logger, skip_logger
    )
    all_pairs.extend(s2_pairs)

    # 3. Process SOURCE 3
    s3_pairs, s3_total, s3_skip_short, s3_skip_fields, s3_skip_hash = process_source_3(
        args.memory_file, args.min_chars, args.min_fields, seen_hashes, main_logger, skip_logger
    )
    all_pairs.extend(s3_pairs)

    # Write output JSONL
    out_dir = os.path.dirname(args.output_file)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    with open(args.output_file, "w", encoding="utf-8") as f:
        for pair in all_pairs:
            line = json.dumps(pair, ensure_ascii=False)
            f.write(line + "\n")

    file_size_mb = os.path.getsize(args.output_file) / (1024 * 1024)
    line_count = len(all_pairs)

    main_logger.info("=== SFT DATASET BUILD AUDIT SUMMARY ===")
    main_logger.info(f"Total records ingested per source:")
    main_logger.info(f"  - SOURCE 1 (Ground Truth): {s1_total} records ingested -> {len(s1_pairs)} exported")
    main_logger.info(f"  - SOURCE 2 (Audit Dump):   {s2_total} records ingested -> {len(s2_pairs)} exported")
    main_logger.info(f"  - SOURCE 3 (Memory File):  {s3_total} examples ingested -> {len(s3_pairs)} pairs exported")
    main_logger.info(f"Records skipped:")
    main_logger.info(f"  - Too few fields (< {args.min_fields}): {s1_skip_fields + s2_skip_fields + s3_skip_fields}")
    main_logger.info(f"  - Anchor text too short (< {args.min_chars} chars): {s3_skip_short}")
    main_logger.info(f"  - Cross-source duplicate tenders dropped: {s2_skip_tender}")
    main_logger.info(f"  - Exact duplicate SHA-256 pairs dropped: {s1_skip_hash + s2_skip_hash + s3_skip_hash}")
    main_logger.info(f"Final exported SFT dataset:")
    main_logger.info(f"  - Destination: {args.output_file}")
    main_logger.info(f"  - Total valid SFT pairs (line count): {line_count}")
    main_logger.info(f"  - File size: {file_size_mb:.4f} MB ({os.path.getsize(args.output_file)} bytes)")


if __name__ == "__main__":
    main()
