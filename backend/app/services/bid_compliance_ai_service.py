import os
import json
import logging
from pathlib import Path
from typing import Any, Dict, List

import httpx
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent


class BidComplianceAIService:
    """
    Groq-powered explanation layer for deterministic bid compliance results.

    IMPORTANT:
    - This service explains existing compliance evidence.
    - It does NOT calculate PASS/FAIL.
    - It does NOT change compliance scores or risk levels.
    - Final procurement decisions remain with the Procurement Officer.
    """

    def __init__(self, timeout: float = 30.0):
        load_dotenv(ROOT_DIR / ".env.dev", override=False)

        self.api_key = os.getenv(
            "GROQ_API_KEY",
            os.getenv("LLM_API_KEY", ""),
        )

        self.model = os.getenv(
            "GROQ_MODEL",
            "openai/gpt-oss-20b",
        )

        self.api_url = os.getenv(
            "GROQ_BASE_URL",
            "https://api.groq.com/openai/v1/chat/completions",
        )

        self.timeout = timeout

    def explain(
        self,
        submission_id: str,
        compliance_score: float,
        risk_level: str,
        checks: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Generate an officer-facing explanation from deterministic results.
        """

        if not self.api_key or self.api_key == "disabled":
            logger.warning(
                "[BidComplianceAI] Groq API key unavailable; skipping AI explanation."
            )
            return {
                "available": False,
                "summary": "AI explanation unavailable. Deterministic compliance results remain authoritative.",
                "key_findings": [],
                "missing_evidence": [],
                "inconsistencies": [],
                "risk_reasoning": [],
                "officer_recommendation": (
                    "Review the deterministic compliance findings and supporting evidence "
                    "before making the final procurement decision."
                ),
            }

        # Keep the prompt compact and evidence-grounded.
        compact_checks = []

        for check in checks:
            compact_checks.append({
                "requirement_code": check.get("requirement_code"),
                "requirement_name": check.get("requirement_name"),
                "status": check.get("status"),
                "passed": check.get("passed"),
                "mandatory": check.get("mandatory", True),
                "confidence": check.get("confidence"),
                "reason": check.get("reason"),
                "evidence": check.get("evidence"),
                "verification": check.get("verification"),
            })

        system_prompt = """
You are an AI compliance analyst assisting an Indian government procurement officer.

Your task is ONLY to explain the deterministic bid-compliance findings supplied to you.

STRICT RULES:
1. Do not change, reinterpret, or override PASS, FAILED, or NEEDS_REVIEW statuses.
2. Do not invent documents, certifications, registrations, financial values, or verification results.
3. Base every statement only on the supplied checks and evidence.
4. Clearly identify missing evidence and explicit inconsistencies.
5. Explain why the current risk level follows from the supplied findings.
6. The Procurement Officer makes the final qualification/disqualification decision.
7. Return ONLY valid JSON.
""".strip()

        user_prompt = f"""
Analyze this bid compliance assessment.

Submission ID: {submission_id}
Deterministic compliance score: {compliance_score}
Deterministic risk level: {risk_level}

Compliance checks:
{json.dumps(compact_checks, indent=2, default=str)}

Return exactly this JSON structure:

{{
  "available": true,
  "summary": "2-4 sentence officer-facing summary",
  "key_findings": [
    "important finding 1",
    "important finding 2"
  ],
  "missing_evidence": [
    "missing document/evidence, only when explicitly supported"
  ],
  "inconsistencies": [
    "explicit mismatch or inconsistency, only when supported"
  ],
  "risk_reasoning": [
    "reason 1 directly grounded in the checks",
    "reason 2 directly grounded in the checks"
  ],
  "officer_recommendation": "Neutral procedural recommendation for procurement-officer review"
}}

For missing_evidence and inconsistencies, use an empty array when none are supported by the supplied evidence.
Do not introduce facts not present in the input.
""".strip()

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {
                    "role": "user",
                    "content": user_prompt,
                },
            ],
            "temperature": 0.1,
            "response_format": {
                "type": "json_object",
            },
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": "TenderVolks-BidCompliance/1.0",
        }

        try:
            response = httpx.post(
                self.api_url,
                headers=headers,
                json=payload,
                timeout=self.timeout,
            )

            if response.status_code != 200:
                logger.error(
                    "[BidComplianceAI] Groq API error %s: %s",
                    response.status_code,
                    response.text[:1000],
                )
                return {
                    "available": False,
                    "summary": "AI explanation unavailable. Deterministic compliance results remain authoritative.",
                    "key_findings": [],
                    "missing_evidence": [],
                    "inconsistencies": [],
                    "risk_reasoning": [],
                    "officer_recommendation": (
                        "Review the deterministic compliance findings and supporting "
                        "evidence before making the final procurement decision."
                    ),
                }

            data = response.json()
            content = data["choices"][0]["message"]["content"]

            result = json.loads(content)

            return {
                "available": True,
                "summary": str(result.get("summary", "")),
                "key_findings": list(result.get("key_findings", [])),
                "missing_evidence": list(result.get("missing_evidence", [])),
                "inconsistencies": list(result.get("inconsistencies", [])),
                "risk_reasoning": list(result.get("risk_reasoning", [])),
                "officer_recommendation": str(
                    result.get("officer_recommendation", "")
                ),
            }

        except Exception as exc:
            logger.exception(
                "[BidComplianceAI] Failed to generate compliance explanation: %s",
                exc,
            )

            return {
                "available": False,
                "summary": "AI explanation unavailable. Deterministic compliance results remain authoritative.",
                "key_findings": [],
                "missing_evidence": [],
                "inconsistencies": [],
                "risk_reasoning": [],
                "officer_recommendation": (
                    "Review the deterministic compliance findings and supporting "
                    "evidence before making the final procurement decision."
                ),
            }
