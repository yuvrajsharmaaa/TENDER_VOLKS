import sys
import os
import re
import json
from pathlib import Path
import fitz

noida_pdf = Path("backend/app/storage/objects/tender-pdfs/a6a5034c-efe2-4d5f-b0a9-3d278b3f8188/GAIL Split Noida.pdf")

doc = fitz.open(str(noida_pdf))
noida_text = "\n".join([page.get_text() for page in doc])

target_numbers = [
    "5,00,00,00,000", "5000000000", "50000000", "5,00,00,00",
    "3,402,000", "3402000", "34.02", "34.02 Lakh",
    "3,490,000", "3490000", "34.90", "34.9", "34.90 Lakh",
    "1,339,000", "1339000", "13.39", "13.39 Lakh"
]

print("--- SEARCH IN EXTRACTION_MEMORY.JSON ---")
memory_file = Path("backend/app/storage/llm_memory/extraction_memory.json")
if memory_file.exists():
    memory_data = json.loads(memory_file.read_text(encoding="utf-8"))
    examples_by_field = memory_data.get("examples_by_field", {})
    print(f"Fields in memory: {list(examples_by_field.keys())}")
    
    for field_key, examples in examples_by_field.items():
        if isinstance(examples, list):
            for idx, ex in enumerate(examples):
                ex_str = json.dumps(ex)
                for num in target_numbers:
                    if num.lower() in ex_str.lower():
                        print(f"\nFOUND MATCH IN MEMORY!")
                        print(f"Field Key: {field_key}")
                        print(f"Example Index: {idx}")
                        print(f"Example Content: {ex_str}")

# Also check fallback hardcoded defaults in tender_mapper.py!
print("\n--- SEARCH IN TENDER_MAPPER.PY FOR HARDCODED DEFAULTS ---")
mapper_file = Path("backend/app/services/tender_mapper.py")
mapper_code = mapper_file.read_text(encoding="utf-8")
for num in target_numbers:
    if num in mapper_code:
        print(f"FOUND IN TENDER_MAPPER.PY: {num}")
        # Find line number
        for line_idx, line in enumerate(mapper_code.split("\n")):
            if num in line:
                print(f"  Line {line_idx + 1}: {line.strip()}")

# Also check pdf_parent_ingest.py or other backend files
print("\n--- SEARCH IN ENTIRE BACKEND FOR HARDCODED DEFAULTS ---")
for p in Path("backend").rglob("*.py"):
    code = p.read_text(encoding="utf-8", errors="ignore")
    for num in ["34.02", "34.9", "13.39", "3402000", "3490000", "1339000", "5,00,00,00,000"]:
        if num in code:
            print(f"Found {num} in {p}")
            for line_idx, line in enumerate(code.split("\n")):
                if num in line:
                    print(f"  Line {line_idx + 1}: {line.strip()}")
