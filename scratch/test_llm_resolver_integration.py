import fitz
import json
from pathlib import Path
import sys

# Add project root and backend to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from backend.app.services.llm_field_resolver import FIELD_PROMPT_MAP

print("=== VERIFYING REGISTERED FALLBACK KEYS IN FIELD_PROMPT_MAP ===")
registered_keys = list(FIELD_PROMPT_MAP.keys())
print(f"Total LLM Fallback Keys Registered: {len(registered_keys)}")
for k in registered_keys:
    print(f"  - {k} -> {FIELD_PROMPT_MAP[k][0]}")

# Confirm work order and financial fields are present
check_keys = [
    "order_value_1_display",
    "order_value_2_display",
    "order_value_3_display",
    "avg_annual_turnover_value_display",
    "working_capital_value_display",
    "solvency_certificate_value_display",
    "net_worth_value_display",
]

all_registered = all(k in registered_keys for k in check_keys)
print(f"\nAll Work Order & Financial keys registered for LLM fallback: {all_registered}")

