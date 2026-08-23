"""
Detailed record inspector for dataset_sft.jsonl.
Outputs formatted analysis of each record.
"""
import json
import sys

sys.stdout.reconfigure(encoding="utf-8")

def inspect():
    with open("data/processed/dataset_sft.jsonl", "r", encoding="utf-8") as f:
        records = [json.loads(line) for line in f if line.strip()]

    print(f"Total Records: {len(records)}\n")
    for i, r in enumerate(records):
        out = json.loads(r["output"])
        print(f"--- RECORD {i} ---")
        print(f"Source Type: {'Anchor Text Snippet (Source 3)' if 'Fields to extract:' not in r['input'] else 'Synthetic Header (Source 1/2)'}")
        print(f"Input ({len(r['input'])} chars):\n{r['input']}")
        print(f"Output ({len(out)} fields):\n{json.dumps(out, indent=2, ensure_ascii=False)}")
        print("=" * 60)

if __name__ == "__main__":
    inspect()
