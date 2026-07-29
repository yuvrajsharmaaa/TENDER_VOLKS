"""
LLM Field Resolver — Gemini Flash hybrid fallback for GAIL/GeM ATC parsing.

Architecture:
  1. Only activates for fields still NA after the full regex pass.
  2. Uses GAIL/GeM-specific BDS/clause anchor knowledge in the system prompt.
  3. Learns from every successful extraction via extraction_memory.json (few-shot store).
  4. Validated output: non-hallucination check anchors extracted value back to source text.

Ground-truth anchor knowledge compiled from manual analysis of:
  - GAIL Rajahmundry NiCd (1) ATC
  - GGL Agra VRLA Batteries ATC (GEM/2026/B/7772525)
  - GAIL Jaipur AMC ATC
  - GAIL GCC-Goods Rev.1 (April 2022)
"""

import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

# Path where few-shot examples accumulate across all parsed documents
_MEMORY_DIR = Path(__file__).parent.parent / "storage" / "llm_memory"
_MEMORY_FILE = _MEMORY_DIR / "extraction_memory.json"
_MEMORY_MAX_EXAMPLES_PER_FIELD = int(os.getenv("LLM_MAX_EXAMPLES_PER_FIELD", "5"))

# ─────────────────────────────────────────────────────────────────────────────
# GAIL / GeM ATC Anchor Knowledge Base
# Compiled from: GAIL GCC-Goods Rev.1 (2022), BDS Section-III, all ATC samples
# ─────────────────────────────────────────────────────────────────────────────
GAIL_GEM_SYSTEM_PROMPT = """You are an expert at extracting structured data from Indian government procurement tender documents — specifically GAIL/PSU Additional Terms & Conditions (ATC) PDFs procured on the GeM portal.

## GAIL / GeM Document Structure Knowledge

### Section & Clause Map (GAIL GCC-Goods Rev.1, April 2022)
- **SECTION-I (IFB Summary)**: IFB Tags (A)–(H) — fixed-format summary rows
  - Tag (E): BID SECURITY / EMD AMOUNT — extract exact ₹ amount here, NOT from Clause 16
  - Tag (G): CONTACT DETAILS OF TENDER DEALING OFFICER — primary contact block
  - Tag (H): DEALING GAIL'S OFFICE ADDRESS — courier/physical submission address
- **SECTION-II**: BID EVALUATION CRITERIA (BEC) — eligibility, MAF, technical criteria
  - "Financial criteria: Not Applicable" → all 4 financial sub-fields are Not Applicable
  - MAF/OEM: "Manufacturer Authorization", "Authorized Dealer/Partner" → maf_required=true
- **SECTION-III (BDS)**: BIDDING DATA SHEET — second occurrence (ignore TOC listing near front)
  - Find the SECOND occurrence of "BIDDING DATA SHEET (BDS)" and slice to next SECTION-
  - BDS 8.1 / 22.2: Courier/Submission address
  - BDS 39.2 / 39.3: Nodal Officer / second contact block
- **CLAUSE 9.0 / 26.0 (Goods/SITC)** or **CLAUSE 21.0 / 3.1 (Services/AMC)**: TERMS OF PAYMENT
  - For Goods/SITC contracts: 70% on supply receipt, 30% on installation/commissioning
  - For Services/AMC: look under SECTION-V, SCC, or SPECIAL CONDITIONS OF CONTRACT
  - NEVER read from generic GCC boilerplate which only lists general terms
- **CLAUSE 38.0 / 39.0**: CONTRACT PERFORMANCE SECURITY / SECURITY DEPOSIT
  - Extract: percentage (%), days after FOA, accepted instrument types
  - Common instruments: Bank Guarantee, Demand Draft, FDR, Online Transfer, Insurance Surety Bond
- **PRICE REDUCTION SCHEDULE (PRS) FOR DELAYED DELIVERY** (NOT "Liquidated Damages"):
  - Typically: 1/2% (0.5%) per complete week of delay, maximum 5% of total order value
  - Search phrases: "PRICE REDUCTION SCHEDULE", "PRS FOR DELAYED DELIVERY"

### EMD Mode Instrument Mapping (from AGENTS.md rules)
- "demand draft" → DD
- "banker's cheque", "imps", "neft", "rtgs", "online banking", "bank transfer" → BT
- "surety bond", "insurance surety" → SB
- "fixed deposit", "fdr" → FDR
- "bank guarantee", "bg" → BG
- Multiple instruments separated by " / "

### GeM Portal Indicators
- Bid number format: GEM/20XX/B/NNNNNNN
- Header: "Government e-Marketplace" or "GeM"
- "Processing Fee" and "Tender Fee" DO NOT exist in ATC — these come only from GeM portal cover page
- If text says "Processing Fee: Not Applicable" — that is correct

### Contract Type Detection
- Title contains "AMC" or "Annual Maintenance" → Services contract
- Title contains "SITC" or "Supply, Installation" → Goods+Installation
- Default → Goods

## CRITICAL EXTRACTION RULES
1. Extract ONLY values explicitly present in the provided document text.
2. Do NOT infer, guess, or hallucinate values.
3. Return null for any field not found in the text.
4. For payment terms: extract INTEGER percentages only (e.g. 70, not "70%").
5. For LD/PRS: extract DECIMAL rate (e.g. 0.5, not "0.5%").
6. For SD/PBG mode: list all accepted instruments as a human-readable string.
7. Return valid JSON ONLY — no markdown fences, no explanation text.

{few_shot_section}
"""

# Map from infosheet_data key → (prompt_field_name, extraction_type, description)
FIELD_PROMPT_MAP = {
    "payment_terms_supply_display": (
        "payment_terms_supply_pct",
        "integer",
        "Percentage of contract value paid on supply/delivery/receipt of materials (e.g. 70)"
    ),
    "payment_terms_installation_display": (
        "payment_terms_installation_pct",
        "integer",
        "Percentage paid on installation/commissioning/site acceptance (e.g. 30)"
    ),
    "ld_percentage_display": (
        "ld_percentage_per_week",
        "decimal",
        "PRS/LD rate as % per complete week of delay — look under 'PRICE REDUCTION SCHEDULE (PRS)', NOT 'Liquidated Damages' (e.g. 0.5)"
    ),
    "max_ld_percentage_display": (
        "max_ld_percentage",
        "decimal",
        "Maximum PRS/LD cap as % of total order value (e.g. 5.0)"
    ),
    "sd_required_display": (
        "sd_required",
        "boolean",
        "Is Security Deposit / CPS required? (true/false) — if PBG at 5% covers CPS, SD is false"
    ),
    "sd_mode_display": (
        "sd_mode",
        "string",
        "Accepted payment instruments for Security Deposit/CPS (e.g. 'Bank Guarantee / DD / FDR / Insurance Surety Bond')"
    ),
    "sd_percentage_display": (
        "sd_percentage",
        "decimal",
        "Security Deposit percentage of contract value (e.g. 5.0)"
    ),
    "sd_duration_display": (
        "sd_duration_months",
        "integer",
        "Security Deposit validity duration in months"
    ),
    "maf_required_display": (
        "maf_required",
        "boolean",
        "Is Manufacturer Authorization Form (MAF) / OEM Authorization required? Look in BEC Section-II"
    ),
    "client_name_1_display": (
        "client_name_1",
        "string",
        "Name of primary contact / Tender Dealing Officer from BDS Tag (G) or Clause 39.2"
    ),
    "client_email_1_display": (
        "client_email_1",
        "string",
        "Email address of primary contact (e.g. ramar@gail.co.in)"
    ),
    "client_phone_1_display": (
        "client_phone_1",
        "string",
        "Phone number of primary contact"
    ),
    "client_name_2_display": (
        "client_name_2",
        "string",
        "Name of second contact / Nodal Officer from BDS Clause 39.3"
    ),
    "client_email_2_display": (
        "client_email_2",
        "string",
        "Email of second contact / Nodal Officer"
    ),
    "courier_address_display": (
        "courier_address",
        "string",
        "Full office address for physical document submission from BDS Tag (H) or Clause 22.2"
    ),
    "delivery_time_supply_display": (
        "delivery_time_supply_days",
        "integer",
        "Number of days for supply/delivery from date of purchase order (e.g. 150)"
    ),
    "pbg_mode_display": (
        "pbg_mode",
        "string",
        "Accepted instruments for PBG/ePBG (e.g. 'Bank Guarantee / Insurance Surety Bond')"
    ),
    "commercial_evaluation_display": (
        "commercial_evaluation_type",
        "string",
        "Commercial evaluation method — look for 'Overall GST Inclusive', 'L1 basis', etc."
    ),
    "reverse_auction_display": (
        "reverse_auction_applicable",
        "boolean",
        "Is Reverse Auction applicable for this bid? (true/false)"
    ),
}

# ─────────────────────────────────────────────────────────────────────────────
# Extraction Memory Store
# ─────────────────────────────────────────────────────────────────────────────

def _load_memory() -> Dict[str, List[Dict]]:
    """Load few-shot examples from persistent JSON store."""
    if not _MEMORY_FILE.exists():
        return {}
    try:
        with open(_MEMORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("examples_by_field", {})
    except Exception as e:
        logger.warning("[LLM_MEMORY] Could not load extraction_memory.json: %s", e)
        return {}


def _save_memory(field_key: str, anchor_text: str, value: Any, doc_type: str, confidence: float = 0.90):
    """Persist a successful extraction example to the few-shot memory store."""
    try:
        _MEMORY_DIR.mkdir(parents=True, exist_ok=True)
        existing: Dict[str, List[Dict]] = {}
        if _MEMORY_FILE.exists():
            with open(_MEMORY_FILE, "r", encoding="utf-8") as f:
                raw = json.load(f)
                existing = raw.get("examples_by_field", {})

        examples = existing.get(field_key, [])
        # Deduplicate by anchor_text
        anchor_set = {ex["anchor_text"][:100] for ex in examples}
        if anchor_text[:100] not in anchor_set:
            examples.append({
                "anchor_text": anchor_text[:300],
                "value": value,
                "doc_type": doc_type,
                "confidence": confidence,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
        # Keep only highest-confidence examples
        examples.sort(key=lambda x: x.get("confidence", 0), reverse=True)
        examples = examples[:_MEMORY_MAX_EXAMPLES_PER_FIELD]
        existing[field_key] = examples

        with open(_MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump({"version": 2, "examples_by_field": existing}, f, indent=2, ensure_ascii=False)
        logger.info("[LLM_MEMORY] Saved example for field '%s': %r", field_key, str(value)[:60])
    except Exception as e:
        logger.warning("[LLM_MEMORY] Could not save example: %s", e)


def record_correction(field_key: str, corrected_value: Any, anchor_context: str, doc_type: str = "GAIL_GOODS"):
    """
    Called when user manually corrects a field in the workspace review panel.
    Saved with higher confidence so it surfaces first in few-shot examples.
    """
    _save_memory(field_key, anchor_context, corrected_value, doc_type, confidence=0.99)
    logger.info("[LLM_MEMORY] User correction recorded for '%s'", field_key)


# ─────────────────────────────────────────────────────────────────────────────
# Few-Shot Section Builder
# ─────────────────────────────────────────────────────────────────────────────

def _build_few_shot_section(missing_fields: List[str], memory: Dict[str, List[Dict]]) -> str:
    """Build the few-shot examples section of the prompt from memory."""
    lines = []
    for display_key in missing_fields:
        prompt_field, _, _ = FIELD_PROMPT_MAP.get(display_key, (None, None, None))
        if not prompt_field:
            continue
        examples = memory.get(display_key, []) or memory.get(prompt_field, [])
        if not examples:
            continue
        lines.append(f"\n## Learned Examples for `{prompt_field}`:")
        for ex in examples[:3]:  # Max 3 per field to keep prompt concise
            lines.append(f"  - Anchor: \"{ex['anchor_text'][:120]}\"")
            lines.append(f"    → Value: {json.dumps(ex['value'])} (confidence: {ex.get('confidence', 0.9):.2f})")
    if not lines:
        return ""
    return "\n## Few-Shot Extraction Examples (from previously parsed GAIL/GeM documents):\n" + "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Main Resolver Class
# ─────────────────────────────────────────────────────────────────────────────

class LLMFieldResolver:
    """
    LLM fallback extractor for GAIL/GeM ATC fields.
    Supports Google Gemini API or any OpenAI-compatible provider (e.g. Groq, OpenRouter, Ollama).
    Only invoked for fields that remain NA after the full regex pipeline.
    """

    def __init__(self):
        self.provider = os.getenv("LLM_PROVIDER", "gemini").lower()
        self.api_key = os.getenv("LLM_API_KEY", os.getenv("GEMINI_API_KEY", ""))
        self.model_name = os.getenv("LLM_MODEL", os.getenv("GEMINI_MODEL", "gemini-1.5-flash"))
        self.base_url = os.getenv("LLM_BASE_URL", "")
        self.enabled = os.getenv("LLM_FALLBACK_ENABLED", "true").lower() == "true"
        self._client = None

    def _get_client(self):
        if self.provider != "gemini":
            return None  # OpenAI-compatible calls bypass standard Google SDK init
        if self._client is not None:
            return self._client
        if not self.api_key or "placeholder" in self.api_key.lower() or "fake" in self.api_key.lower():
            raise RuntimeError("LLM_FALLBACK: GEMINI_API_KEY/LLM_API_KEY not configured or is a placeholder.")
        try:
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)
            self._client = genai.GenerativeModel(
                model_name=self.model_name,
                generation_config={
                    "temperature": 0.1,       # Low temperature = deterministic extraction
                    "top_p": 0.95,
                    "max_output_tokens": 1024,
                    "response_mime_type": "application/json",
                }
            )
            return self._client
        except ImportError:
            raise RuntimeError("google-generativeai not installed. Run: pip install google-generativeai")

    def _call_openai_compatible(self, system_prompt: str, user_prompt: str) -> str:
        """Call any OpenAI-compatible API endpoint via standard Python urllib (no external SDK required)."""
        import urllib.request
        import json
        
        url = self.base_url or "https://api.openai.com/v1/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        
        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"}
        }
        
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST"
        )
        
        with urllib.request.urlopen(req, timeout=30) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            return res_data["choices"][0]["message"]["content"]


    def _detect_doc_type(self, text: str) -> str:
        """Detect GAIL contract type from text content."""
        text_l = text.lower()
        if any(kw in text_l for kw in ["annual maintenance", " amc ", "amc contract"]):
            return "GAIL_AMC_SERVICES"
        if any(kw in text_l for kw in ["sitc", "supply, installation, testing", "supply installation"]):
            return "GAIL_SITC_GOODS"
        return "GAIL_GOODS"

    def _build_user_prompt(self, full_text: str, missing_fields: List[str]) -> str:
        """Build the structured extraction prompt for the given missing fields."""
        field_specs = []
        for display_key in missing_fields:
            entry = FIELD_PROMPT_MAP.get(display_key)
            if not entry:
                continue
            prompt_field, dtype, description = entry
            field_specs.append({
                "field_name": prompt_field,
                "type": dtype,
                "description": description
            })

        if not field_specs:
            return ""

        # Truncate text to fit within model context (keep first + last portions)
        max_chars = 900_000  # ~200k tokens for Gemini Flash
        if len(full_text) > max_chars:
            half = max_chars // 2
            full_text = full_text[:half] + "\n\n[... MIDDLE TRUNCATED ...]\n\n" + full_text[-half:]

        fields_json = json.dumps(field_specs, indent=2, ensure_ascii=False)
        return f"""Extract the following fields from this ATC document.
Return a single JSON object with exactly these field names. Use null for any not found.

Fields to extract:
{fields_json}

ATC Document Text:
--- START OF DOCUMENT ---
{full_text}
--- END OF DOCUMENT ---"""

    def _validate_and_anchor(self, field_key: str, value: Any, full_text: str) -> Optional[str]:
        """
        Non-hallucination check: verify that the extracted value appears verbatim
        or numerically in the source text. Returns anchor snippet or None if invalid.
        """
        if value is None:
            return None
        str_val = str(value).strip()
        if not str_val or str_val in ("null", "None", "NA", ""):
            return None
        # For numeric values, check presence of the number
        num_str = str_val.replace("%", "").replace("₹", "").replace(",", "").strip()
        if num_str and re.search(re.escape(num_str[:8]), full_text[:500000]):
            # Find surrounding context for memory storage
            m = re.search(re.escape(num_str[:8]), full_text)
            if m:
                start = max(0, m.start() - 100)
                end = min(len(full_text), m.end() + 150)
                return full_text[start:end]
        # For string values, check key words
        if isinstance(value, str) and len(value) > 3:
            key_words = [w for w in value.split() if len(w) > 3][:3]
            if key_words and all(re.search(re.escape(w), full_text, re.IGNORECASE) for w in key_words):
                m = re.search(re.escape(key_words[0]), full_text, re.IGNORECASE)
                if m:
                    start = max(0, m.start() - 100)
                    end = min(len(full_text), m.end() + 150)
                    return full_text[start:end]
        # Booleans don't need anchoring
        if isinstance(value, bool):
            return "boolean_value"
        return None

    def _map_to_display_value(self, display_key: str, raw_value: Any) -> Optional[str]:
        """Convert raw Gemini output value to the display string format used in infosheet_data."""
        if raw_value is None:
            return None
        entry = FIELD_PROMPT_MAP.get(display_key)
        if not entry:
            return str(raw_value)
        _, dtype, _ = entry
        try:
            if dtype == "integer":
                num = int(float(str(raw_value)))
                if "pct" in entry[0] or "supply" in display_key or "installation" in display_key:
                    return f"{num}%"
                return str(num)
            elif dtype == "decimal":
                num = float(str(raw_value))
                if "ld" in display_key or "sd" in display_key or "pbg" in display_key:
                    return f"{num}%"
                return str(num)
            elif dtype == "boolean":
                if isinstance(raw_value, bool):
                    return "Yes" if raw_value else "No"
                return "Yes" if str(raw_value).lower() in ("true", "yes", "1") else "No"
            else:
                return str(raw_value).strip()
        except Exception:
            return str(raw_value).strip()

    def resolve(
        self,
        atc_full_text: str,
        missing_display_keys: List[str],
        doc_type: Optional[str] = None
    ) -> Dict[str, str]:
        """
        Main entry point. Returns dict of {display_key: display_value_string}
        for fields successfully resolved by LLM.
        Gracefully returns empty dict on any error.
        """
        if not self.enabled:
            logger.info("[LLM_FALLBACK] Disabled via LLM_FALLBACK_ENABLED=false")
            return {}
        if not atc_full_text or not missing_display_keys:
            return {}

        # Filter to known fields only
        known_missing = [k for k in missing_display_keys if k in FIELD_PROMPT_MAP]
        if not known_missing:
            return {}

        logger.info("[LLM_FALLBACK] Resolving %d missing fields via LLM (%s): %s", len(known_missing), self.provider, known_missing)

        if self.provider == "gemini":
            try:
                client = self._get_client()
            except RuntimeError as e:
                logger.warning("[LLM_FALLBACK] %s — skipping LLM resolution", e)
                return {}

        detected_type = doc_type or self._detect_doc_type(atc_full_text)
        memory = _load_memory()
        few_shot_section = _build_few_shot_section(known_missing, memory)

        system_prompt = GAIL_GEM_SYSTEM_PROMPT.format(few_shot_section=few_shot_section)
        user_prompt = self._build_user_prompt(atc_full_text, known_missing)
        if not user_prompt:
            return {}

        try:
            t0 = time.time()
            if self.provider == "gemini":
                response = client.generate_content(
                    [{"role": "user", "parts": [system_prompt + "\n\n" + user_prompt]}]
                )
                raw_text = response.text.strip()
            else:
                raw_text = self._call_openai_compatible(system_prompt, user_prompt).strip()
                
            elapsed = time.time() - t0
            logger.info("[LLM_FALLBACK] LLM (%s) responded in %.2fs", self.provider, elapsed)

            # Strip any accidental markdown fences
            raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text)
            raw_text = re.sub(r"\s*```$", "", raw_text)

            llm_data: Dict[str, Any] = json.loads(raw_text)
        except json.JSONDecodeError as e:
            logger.error("[LLM_FALLBACK] JSON parse error: %s | raw: %r", e, raw_text[:200])
            return {}
        except Exception as e:
            logger.error("[LLM_FALLBACK] LLM API call failed: %s", e, exc_info=True)
            return {}

        # Map prompt field names back to display keys
        prompt_to_display = {entry[0]: dk for dk, entry in FIELD_PROMPT_MAP.items() if dk in known_missing}
        results: Dict[str, str] = {}

        for prompt_field, raw_value in llm_data.items():
            display_key = prompt_to_display.get(prompt_field)
            if not display_key or raw_value is None:
                continue

            # Non-hallucination validation
            anchor_snippet = self._validate_and_anchor(display_key, raw_value, atc_full_text)
            if anchor_snippet is None and not isinstance(raw_value, bool):
                logger.warning("[LLM_FALLBACK] Could not anchor '%s'=%r in source text — skipping", display_key, raw_value)
                continue

            display_val = self._map_to_display_value(display_key, raw_value)
            if display_val:
                results[display_key] = display_val
                logger.info("[LLM_FALLBACK] Resolved '%s' = %r", display_key, display_val)
                # Save to learning memory
                if anchor_snippet and anchor_snippet != "boolean_value":
                    _save_memory(display_key, anchor_snippet, raw_value, detected_type)

        logger.info("[LLM_FALLBACK] Resolved %d/%d fields via Gemini", len(results), len(known_missing))
        return results
