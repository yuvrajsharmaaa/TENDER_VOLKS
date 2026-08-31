import os
import re
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
import httpx
from pydantic import BaseModel, Field
from dotenv import load_dotenv

logger = logging.getLogger(__name__)
ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent

# ─────────────────────────────────────────────────────────────────────────────
# RFQ Data Schemas & Exceptions
# ─────────────────────────────────────────────────────────────────────────────

class LineItemSpec(BaseModel):
    item_name: str
    quantity: Any
    unit: Optional[str] = "Nos"
    technical_spec: Optional[str] = None
    delivery_location: Optional[str] = None
    required_by_date: Optional[str] = None
    status: Optional[str] = "ok"  # "ok", "missing", "FIELD_STATUS_MISSING", etc.
    confidence_score: Optional[float] = 1.0
    field_confidences: Optional[Dict[str, float]] = None


class RFQDraftRequest(BaseModel):
    tender_no: str
    organization: str
    tender_title: str
    oem_recipient_name: Optional[str] = "Authorized OEM Partner"
    line_items: List[LineItemSpec]
    commercial_terms: Optional[Dict[str, Any]] = None
    terms_confidences: Optional[Dict[str, float]] = None


class RFQDraftResponse(BaseModel):
    tender_no: str
    subject: str
    draft_body: str
    contains_missing_fields: bool
    missing_fields_list: List[str]
    is_ready_for_dispatch: bool
    status_summary: str


class BlockedRFQSendError(Exception):
    """
    Raised when an attempt is made to dispatch or transmit an RFQ draft that
    contains '[NEEDS REVIEW: <field>]' guardrail placeholders.
    """
    pass


# ─────────────────────────────────────────────────────────────────────────────
# RFQ Drafting Service Implementation
# ─────────────────────────────────────────────────────────────────────────────

class RFQDraftingService:
    """
    Synthesizes OEM Request for Quotation (RFQ) communications from extracted BoQ line items
    and technical specifications, enforcing deterministic safety guardrails.
    """

    GUARDRAIL_PATTERN = re.compile(r"\[NEEDS REVIEW:\s*([^\]]+)\]", re.IGNORECASE)
    MISSING_VALUES = {"not found", "none", "null", "undefined", "⚠️ missing", "missing", "", "unknown"}
    SUSPICIOUS_PLACEHOLDERS = re.compile(r"^(?:lorem ipsum|tbd|placeholder|000000|test item|xxx+|\.\.\.+)$", re.IGNORECASE)
    CONFIDENCE_THRESHOLD = 0.85

    def __init__(
        self,
        model_name: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: float = 30.0
    ):
        load_dotenv(ROOT_DIR / ".env.dev")
        self.api_key = api_key or os.getenv("GROQ_API_KEY", os.getenv("LLM_API_KEY", ""))
        self.model_name = model_name or os.getenv("GROQ_ADVISORY_MODEL", "openai/gpt-oss-120b")
        self.timeout = timeout
        self.api_url = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1/chat/completions")
        self.drafts_dir = ROOT_DIR / "artifacts" / "rfq_drafts"
        self.drafts_dir.mkdir(parents=True, exist_ok=True)

    def _is_invalid_or_low_confidence(self, val: Any, conf: Optional[float] = None) -> bool:
        """
        Returns True if a field value is missing, matches a known placeholder literal,
        or has an extraction confidence below CONFIDENCE_THRESHOLD (0.85).
        """
        if val is None:
            return True
        v_str = str(val).strip()
        if not v_str or v_str.lower() in self.MISSING_VALUES:
            return True
        if self.SUSPICIOUS_PLACEHOLDERS.match(v_str):
            return True
        if conf is not None and conf < self.CONFIDENCE_THRESHOLD:
            return True
        return False

    def _sanitize_line_item(self, item: LineItemSpec) -> tuple[Dict[str, Any], List[str]]:
        """
        Inspects each field of a line item. If the field is missing, has suspicious placeholder
        content, or falls below the confidence threshold, injects the verbatim guardrail tag:
        [NEEDS REVIEW: <field name>].
        """
        missing_fields = []
        item_dict = item.model_dump()
        f_conf = item.field_confidences or {}
        overall_conf = item.confidence_score if item.confidence_score is not None else 1.0
        
        # Check Item Name
        name_conf = f_conf.get("item_name", overall_conf)
        if self._is_invalid_or_low_confidence(item.item_name, name_conf) or "missing" in str(item.status).lower():
            item_dict["item_name"] = "[NEEDS REVIEW: item_name]"
            missing_fields.append("item_name")

        # Check Quantity
        qty_conf = f_conf.get("quantity", overall_conf)
        if self._is_invalid_or_low_confidence(item.quantity, qty_conf):
            item_dict["quantity"] = "[NEEDS REVIEW: quantity]"
            missing_fields.append("quantity")

        # Check Delivery Location
        loc_conf = f_conf.get("delivery_location", overall_conf)
        if self._is_invalid_or_low_confidence(item.delivery_location, loc_conf):
            item_dict["delivery_location"] = "[NEEDS REVIEW: delivery_location]"
            missing_fields.append("delivery_location")

        # Check Technical Specification
        spec_conf = f_conf.get("technical_spec", overall_conf)
        if self._is_invalid_or_low_confidence(item.technical_spec, spec_conf):
            item_dict["technical_spec"] = "[NEEDS REVIEW: technical_spec]"
            missing_fields.append("technical_spec")

        return item_dict, missing_fields

    def draft_rfq(self, request: RFQDraftRequest) -> RFQDraftResponse:
        """
        Generates an OEM RFQ draft via Groq, preserving all [NEEDS REVIEW: <field>] guardrails.
        """
        sanitized_items = []
        all_missing = []

        for item in request.line_items:
            s_item, m_fields = self._sanitize_line_item(item)
            sanitized_items.append(s_item)
            all_missing.extend(m_fields)

        # Check commercial terms for missing values or low confidence
        terms = request.commercial_terms or {}
        terms_conf = request.terms_confidences or {}
        sanitized_terms = {}
        for k, v in terms.items():
            k_conf = terms_conf.get(k, 1.0)
            if self._is_invalid_or_low_confidence(v, k_conf):
                sanitized_terms[k] = f"[NEEDS REVIEW: {k}]"
                all_missing.append(k)
            else:
                sanitized_terms[k] = v

        system_prompt = (
            "You are an expert Procurement & Supply Chain Specialist at Volks Energie. "
            "Your task is to draft a formal, high-precision Request for Quotation (RFQ) to an OEM equipment manufacturer.\n\n"
            "CRITICAL GUARDRAIL RULES:\n"
            "1. Whenever an input item or term contains '[NEEDS REVIEW: <field_name>]', you MUST PRESERVE THAT EXACT STRING VERBATIM in your output. "
            "DO NOT invent or guess values for those fields.\n"
            "2. NEVER invent, inject, or create any new '[NEEDS REVIEW: ...]' tags in the output. You must ONLY output a '[NEEDS REVIEW: ...]' tag if that exact tag appeared in the input JSON above.\n"
            "3. Present the line items in a clear, formatted itemized list or text table.\n"
            "4. Request unit price, lead time (weeks/days), GST breakdown, and technical compliance sheet.\n"
            "5. Maintain a professional, executive tone."
        )

        user_prompt = f"""Draft a formal OEM RFQ letter/email for:
- Tender Reference: {request.tender_no}
- Procuring Authority: {request.organization}
- Project Title: {request.tender_title}
- Addressed To: {request.oem_recipient_name}

Itemized Bill of Quantities (BoQ) & Requirements:
{json.dumps(sanitized_items, indent=2)}

Key Commercial & Delivery Constraints:
{json.dumps(sanitized_terms, indent=2)}

Return your output with:
SUBJECT: <clear subject line>
BODY:
<full body of the RFQ>
"""

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": "TenderVolks-RFQ/1.0"
        }
        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.1
        }

        try:
            resp = httpx.post(self.api_url, headers=headers, json=payload, timeout=self.timeout)
            if resp.status_code != 200:
                if self.model_name != "qwen/qwen3.6-27b":
                    payload["model"] = "qwen/qwen3.6-27b"
                    resp = httpx.post(self.api_url, headers=headers, json=payload, timeout=self.timeout)
                if resp.status_code != 200:
                    raise RuntimeError(f"Groq RFQ generation failed: {resp.text}")
            content = resp.json()["choices"][0]["message"]["content"]
        except Exception as api_err:
            logger.warning("[RFQ_DRAFTING] Groq API call failed or timed out (%s). Using deterministic template fallback.", api_err)
            # Deterministic template fallback formatting
            items_text = "\n".join([f"- {it.get('item_name', 'Item')}: Qty {it.get('quantity', 'N/A')}, Location: {it.get('delivery_location', 'N/A')}, Spec: {it.get('technical_spec', 'N/A')}" for it in sanitized_items])
            terms_text = "\n".join([f"- {k}: {v}" for k, v in sanitized_terms.items()])
            content = f"""SUBJECT: RFQ: Equipment & Technical Pricing for Tender {request.tender_no} - {request.tender_title}
BODY:
Dear Sir/Madam,

{request.organization}, acting as the Procuring Authority, hereby invites your quotation for Tender {request.tender_no} ({request.tender_title}).

Itemized Bill of Quantities:
{items_text}

Commercial & Delivery Constraints:
{terms_text}

Please provide your technical compliance statement and firm price quotation.
"""
        
        # Parse Subject and Body
        subject = f"RFQ: Equipment & Technical Pricing for Tender {request.tender_no} - {request.tender_title}"
        draft_body = content
        if "SUBJECT:" in content and "BODY:" in content:
            parts = content.split("BODY:")
            subj_part = parts[0].replace("SUBJECT:", "").strip()
            if subj_part:
                subject = subj_part
            draft_body = parts[1].strip()

        # CRITICAL GUARDRAIL ENFORCEMENT:
        # If input was 100% clean (all_missing is empty), sanitize any spurious LLM hallucinated tags
        if not all_missing:
            draft_body = self.GUARDRAIL_PATTERN.sub(lambda m: m.group(1).replace("_", " "), draft_body)
            detected_placeholders = []
            unique_missing = []
        else:
            detected_placeholders = self.GUARDRAIL_PATTERN.findall(draft_body)
            unique_missing = list(set(all_missing + detected_placeholders))

        has_missing = len(unique_missing) > 0

        response = RFQDraftResponse(
            tender_no=request.tender_no,
            subject=subject,
            draft_body=draft_body,
            contains_missing_fields=has_missing,
            missing_fields_list=unique_missing,
            is_ready_for_dispatch=not has_missing,
            status_summary="READY_FOR_DISPATCH" if not has_missing else f"BLOCKED_ON_REVIEW ({len(unique_missing)} placeholders)"
        )

        # Persist draft to local queue directory
        safe_t_no = re.sub(r"[^\w\-]", "_", request.tender_no)
        out_file = self.drafts_dir / f"rfq_{safe_t_no}.json"
        with open(out_file, "w", encoding="utf-8") as f:
            f.write(response.model_dump_json(indent=2))

        logger.info(
            "[RFQDrafting] Drafted RFQ for %s | Ready: %s | Missing: %s",
            request.tender_no, response.is_ready_for_dispatch, unique_missing
        )
        return response

    def send_rfq(self, draft: RFQDraftResponse, destination_email: str) -> Dict[str, Any]:
        """
        Enforces a hard transmission block. If any '[NEEDS REVIEW:' placeholder exists,
        raises BlockedRFQSendError and logs the blocked attempt.
        """
        # Scan body and subject for guardrail tags
        matches = self.GUARDRAIL_PATTERN.findall(draft.draft_body) + self.GUARDRAIL_PATTERN.findall(draft.subject)
        
        if draft.contains_missing_fields or len(matches) > 0 or not draft.is_ready_for_dispatch:
            msg = (
                f"[GUARDRAIL VIOLATION] Refusing to send RFQ for tender '{draft.tender_no}'. "
                f"Draft contains {len(matches)} unverified '[NEEDS REVIEW: ...]' placeholder(s): {matches}. "
                f"Live transmission is strictly blocked until manual resolution."
            )
            logger.warning("[RFQ_SEND_BLOCKED] %s", msg)
            raise BlockedRFQSendError(msg)

        # In production, dispatch email via SMTP/SendGrid. Here we record approved dispatch log.
        logger.info(
            "[RFQ_SEND_APPROVED] Dispatching verified RFQ for %s to %s (Subject: %s)",
            draft.tender_no, destination_email, draft.subject
        )
        return {
            "status": "SENT",
            "tender_no": draft.tender_no,
            "destination_email": destination_email,
            "subject": draft.subject,
            "timestamp": "2026-08-31T10:00:00Z"
        }
