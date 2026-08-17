import re
from pathlib import Path

mapper_path = Path("backend/app/services/tender_mapper.py")
code = mapper_path.read_text(encoding="utf-8")

print("=== AUDIT OF HARDCODED LITERAL FALLBACK ASSIGNMENTS IN TENDER_MAPPER.PY ===")

for line_idx, line in enumerate(code.split("\n")):
    # Look for assignments like = "something" or else: var = "something"
    if re.search(r"else\s*:.*=\s*[\"'][^\"']+[\"']", line) or re.search(r"=\s*[\"']\d+[\.\d\w\s]*[\"']", line):
        # Exclude standard sentinels
        if not any(s in line for s in ['"NA"', '"N/A"', '""', '"None"', '"No"', '"Yes"', '"Not Found"', '"Not Applicable"', '"0"', '"₹0.00"']):
            print(f"Line {line_idx + 1}: {line.strip()}")
