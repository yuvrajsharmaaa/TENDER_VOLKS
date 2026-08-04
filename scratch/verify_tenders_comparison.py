import sys
import os
import re
import json
import sqlite3
from pathlib import Path

# Add project root and backend directory to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from backend.app.services.tender_mapper import build_infosheet_data
from backend.app.services.llm_field_resolver import LLMFieldResolver

def check_fc_regex(full_text: str):
    normalized_full_text = re.sub(r"\s+", " ", full_text).lower()
    m_fc_exempt = re.search(
        r"financial\s+criteria\b(?:(?!financial\s+criteria).){0,150}?not\s+applicable",
        normalized_full_text,
        re.DOTALL,
    )
    if m_fc_exempt:
        return True, m_fc_exempt.group(0)[:150]
    return False, "NO MATCH"

# Test sample tender text files in tests/ or backend/ or data/
sample_texts = {}
for p in Path(__file__).parent.parent.rglob("*.txt"):
    if "node_modules" not in str(p) and ".git" not in str(p):
        try:
            txt = p.read_text(encoding="utf-8", errors="ignore")
            if len(txt) > 200:
                sample_texts[p.name] = txt
        except Exception:
            pass

print(f"Loaded {len(sample_texts)} text files from workspace.")

db_path = Path(__file__).parent.parent / "backend" / "app" / "data" / "tender.db"
if db_path.exists():
    conn = sqlite3.connect(str(db_path))
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    print(f"DB Tables: {tables}")
    if "tender_projects" in tables or "tenders" in tables:
        tbl = "tender_projects" if "tender_projects" in tables else "tenders"
        cursor = conn.cursor()
        cursor.execute(f"SELECT * FROM {tbl} LIMIT 5")
        rows = cursor.fetchall()
        print(f"Fetched {len(rows)} rows from table {tbl}")

# Run comparison on sample texts
resolver = LLMFieldResolver()
for name, raw_text in list(sample_texts.items())[:5]:
    fc_matched, fc_window = check_fc_regex(raw_text)
    page_texts = [{"page": 1, "text": raw_text}]
    info = build_infosheet_data([], page_texts)
    missing_keys = ["custom_eligibility_criteria_display"]
    heuristic_res = resolver._resolve_local_heuristics(raw_text, missing_keys)
    custom_elig = heuristic_res.get("custom_eligibility_criteria_display", {}).get("value")
    
    print(f"\n============================================================")
    print(f"FILE: {name}")
    print(f"FC Exempt Matched: {fc_matched}")
    print(f"FC Window: {fc_window!r}")
    print(f"Turnover Type: {info.get('avg_annual_turnover_type_display')}")
    print(f"Turnover Value: {info.get('avg_annual_turnover_value_display')}")
    print(f"Custom Eligibility Heuristic: {custom_elig}")
