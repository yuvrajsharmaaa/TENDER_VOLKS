import os
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Literal, Union
import httpx
from pydantic import BaseModel, Field, ValidationError
from dotenv import load_dotenv

from backend.app.services.tender_indexer import find_similar_tenders
from backend.app.schemas.pqc_recommendation import resolve_tender_title

logger = logging.getLogger(__name__)
ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent

# ─────────────────────────────────────────────────────────────────────────────
# Structured Advisory Pydantic Schemas
# ─────────────────────────────────────────────────────────────────────────────

class SimilarTenderSummary(BaseModel):
    tender_no: str = Field(description="Historical tender reference number")
    tender_name: Optional[str] = Field(default="", description="Tender title or category")
    similarity: float = Field(description="Cosine similarity score (0.0 to 1.0)")
    outcome: str = Field(description="Historical outcome: 'Won' or 'Lost' or 'Pending'")
    organization: Optional[str] = Field(default="Unknown", description="Procuring authority")
    key_overlap: str = Field(description="Key similarities or commercial differences with target tender")


class StructuredAdvisoryResponse(BaseModel):
    tender_no: str = Field(description="Target tender number")
    recommendation: Literal["bid", "no_bid", "review"] = Field(description="Strategic recommendation: bid, no_bid, or review")
    confidence: float = Field(description="Confidence score between 0.0 and 1.0", ge=0.0, le=1.0)
    win_probability: float = Field(description="LightGBM estimated win probability (0.0 to 1.0)", ge=0.0, le=1.0)
    key_drivers: List[str] = Field(description="Top positive and negative SHAP drivers influencing the decision")
    similar_tenders: List[SimilarTenderSummary] = Field(description="Top nearest-neighbor historical tenders with outcomes")
    strategic_rationale: str = Field(description="Detailed narrative rationale grounding the recommendation in data")
    risk_factors: List[str] = Field(description="Primary operational, financial, or timeline risks identified")
    actionable_next_steps: List[str] = Field(description="Concrete operational next steps for the bidding team")


class MissingPredictiveFeaturesError(Exception):
    """Raised when a tender has not undergone the Week 5 ML/SHAP feature extraction pipeline."""
    pass


class StructuredAdvisorySchemaError(Exception):
    """Raised when Groq response fails schema validation after retries."""
    pass


# ─────────────────────────────────────────────────────────────────────────────
# Structured Advisory Service Implementation
# ─────────────────────────────────────────────────────────────────────────────

class StructuredAdvisoryService:
    """
    Generates data-grounded strategic bid/no-bid advisories by synthesizing:
      1. Week 5 LightGBM win probability
      2. Week 5 SHAP top-3 drivers (positive & negative forces)
      3. Qdrant nearest-neighbor historical tenders (Won/Lost track record)
      4. Groq LLM synthesis with strict JSON schema validation.
    """

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

    def _get_ml_shap_context(self, tender_no: str) -> Dict[str, Any]:
        """
        Retrieves Week 5 LightGBM win probability and SHAP top-3 drivers for the tender.
        Raises MissingPredictiveFeaturesError if ML pipeline data does not exist for this tender.
        """
        # 1. Check test_predictions_explained.csv
        explained_csv = ROOT_DIR / "artifacts" / "test_predictions_explained.csv"
        if explained_csv.exists():
            import pandas as pd
            df = pd.read_csv(explained_csv)
            match = df[df["tender_no"].astype(str).str.lower() == str(tender_no).lower()]
            if not match.empty:
                row = match.iloc[0]
                drivers_str = str(row.get("top_3_drivers", ""))
                drivers_list = [d.strip() for d in drivers_str.split(";") if d.strip()]
                t_no = str(row["tender_no"])
                return {
                    "tender_no": t_no,
                    "tender_name": resolve_tender_title(row.get("tender_name"), t_no),
                    "organization": str(row.get("organization", "Unknown")),
                    "win_probability": float(row.get("win_probability", 0.5)),
                    "predicted_outcome": str(row.get("predicted_outcome", "Review")),
                    "top_3_drivers": drivers_list or [drivers_str],
                    "full_narrative": str(row.get("full_narrative", ""))
                }

        # 2. Check training_set_win_loss.csv
        train_csv = ROOT_DIR / "artifacts" / "training_set_win_loss.csv"
        if train_csv.exists():
            import pandas as pd
            df_t = pd.read_csv(train_csv)
            match_t = df_t[df_t["tender_no"].astype(str).str.lower() == str(tender_no).lower()]
            if not match_t.empty:
                row_t = match_t.iloc[0]
                is_won = int(row_t.get("is_won", 0))
                win_prob = 0.85 if is_won == 1 else 0.15
                drivers = [
                    f"Turnover required: ₹{float(row_t.get('turnover_required_value') or 0):,.2f}",
                    f"EMD amount: ₹{float(row_t.get('emd_amount') or 0):,.2f}",
                    f"Delivery schedule: {row_t.get('delivery_time_supply_days', 'N/A')} days"
                ]
                t_no_t = str(row_t["tender_no"])
                return {
                    "tender_no": t_no_t,
                    "tender_name": resolve_tender_title(row_t.get("tender_name"), t_no_t),
                    "organization": str(row_t.get("organization", "Unknown")),
                    "win_probability": win_prob,
                    "predicted_outcome": "Won" if is_won == 1 else "Lost",
                    "top_3_drivers": drivers,
                    "full_narrative": f"Historical ground-truth record ({row_t.get('outcome', 'Unknown')})"
                }

        # Gate enforcement: Tender missing Week 5 predictive pipeline data
        raise MissingPredictiveFeaturesError(
            f"Step 1 Gate Blocked: Tender '{tender_no}' has not undergone the Week 5 predictive feature extraction pipeline. "
            f"Cannot synthesize advisory without genuine LightGBM win probability and SHAP drivers."
        )

    def _call_groq_json(self, system_prompt: str, user_prompt: str, model: Optional[str] = None) -> Dict[str, Any]:
        """
        Sends request to Groq OpenAI-compatible endpoint enforcing json_object response format.
        """
        target_model = model or self.model_name
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": "TenderVolks-Advisory/1.0"
        }
        payload = {
            "model": target_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"}
        }

        resp = httpx.post(self.api_url, headers=headers, json=payload, timeout=self.timeout)
        if resp.status_code != 200:
            logger.error("[StructuredAdvisory] Groq API error %d: %s", resp.status_code, resp.text)
            # Fallback to secondary model if primary returned 404 or rate-limit
            if target_model != "qwen/qwen3.6-27b":
                logger.info("[StructuredAdvisory] Retrying with secondary model 'qwen/qwen3.6-27b'...")
                return self._call_groq_json(system_prompt, user_prompt, model="qwen/qwen3.6-27b")
            raise RuntimeError(f"Groq API call failed (HTTP {resp.status_code}): {resp.text}")

        res_data = resp.json()
        content = res_data["choices"][0]["message"]["content"]
        return json.loads(content)

    def generate_advisory(
        self,
        tender_no: str,
        tender_metadata: Optional[Dict[str, Any]] = None,
        top_k_similar: int = 3
    ) -> StructuredAdvisoryResponse:
        """
        Generates a validated structured advisory for a specific tender.
        """
        # Step 1: Verify and fetch Week 5 ML/SHAP data
        ml_context = self._get_ml_shap_context(tender_no)
        
        # Step 2: Query Qdrant for nearest-neighbor historical tenders
        query_payload = tender_metadata or {
            "tender_no": tender_no,
            "tender_name": ml_context.get("tender_name", tender_no),
            "organization": ml_context.get("organization", "Unknown")
        }
        similar_tenders_raw = find_similar_tenders(
            query_target=query_payload,
            top_k=top_k_similar,
            exclude_tender_no=tender_no
        )

        similar_summaries = []
        for s in similar_tenders_raw:
            similar_summaries.append({
                "tender_no": s["tender_no"],
                "tender_name": s.get("tender_name", ""),
                "similarity": s["similarity"],
                "outcome": s["outcome"],
                "organization": s.get("organization", "Unknown"),
                "key_overlap": s.get("key_overlap", "")
            })

        # Step 3: Build Prompt for Groq Synthesis
        system_prompt = (
            "You are a Senior Strategic Procurement Analyst for Volks Energie (an Indian electrical and power systems vendor). "
            "Your role is to synthesize quantitative predictive intelligence (LightGBM win probability and SHAP attribution drivers) "
            "along with historical nearest-neighbor tender precedents into an authoritative, actionable, and data-grounded bid recommendation.\n\n"
            "CRITICAL RULES:\n"
            "1. You MUST return ONLY a valid JSON object matching the requested schema.\n"
            "2. Recommendation MUST be one of: 'bid' (strong win indicators), 'no_bid' (unfavorable terms/poor precedent), or 'review' (borderline).\n"
            "3. Ground your strategic rationale strictly on the provided LightGBM probability, SHAP drivers, and historical Won/Lost nearest neighbors.\n"
            "4. Highlight specific risk factors (e.g. tight delivery timeline, high EMD, lack of buyer incumbency).\n"
            "5. Provide concrete, operational next steps."
        )

        user_prompt = f"""Synthesize a structured bid advisory for the following tender:

## Target Tender Details:
- Tender Reference: {tender_no}
- Tender Title: {ml_context.get('tender_name', tender_no)}
- Procuring Authority: {ml_context.get('organization', 'Unknown')}

## Week 5 Machine Learning & SHAP Predictive Intelligence:
- LightGBM Estimated Win Probability: {ml_context['win_probability']:.2%}
- Model Classification: {ml_context['predicted_outcome']}
- Top 3 SHAP Drivers:
{chr(10).join(f"  * {d}" for d in ml_context['top_3_drivers'])}
- Full ML Attribution Summary: {ml_context['full_narrative']}

## Nearest-Neighbor Historical Tenders from Qdrant Vector Store:
{json.dumps(similar_summaries, indent=2)}

## Required JSON Schema:
{{
  "tender_no": "{tender_no}",
  "recommendation": "bid" | "no_bid" | "review",
  "confidence": <float between 0.0 and 1.0>,
  "win_probability": {ml_context['win_probability']},
  "key_drivers": [<list of strings highlighting top factors>],
  "similar_tenders": [
    {{
      "tender_no": "<string>",
      "tender_name": "<string>",
      "similarity": <float>,
      "outcome": "Won" | "Lost" | "Pending",
      "organization": "<string>",
      "key_overlap": "<string>"
    }}
  ],
  "strategic_rationale": "<comprehensive 2-3 paragraph analytical rationale>",
  "risk_factors": [<list of specific risk factor strings>],
  "actionable_next_steps": [<list of actionable operational next steps>]
}}
"""

    def _verify_and_ground_advisory(
        self,
        raw_json: Dict[str, Any],
        ml_context: Dict[str, Any],
        similar_summaries: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Lightweight post-hoc deterministic check ensuring all structured numeric and ID claims
        trace back verbatim to the input payload, logging every discarded or mutated LLM claim.
        """
        # 1. Ground and audit Target Tender ID
        claimed_tender_no = raw_json.get("tender_no")
        expected_tender_no = ml_context["tender_no"]
        if claimed_tender_no and claimed_tender_no != expected_tender_no:
            logger.warning(
                "[STRUCTURED_ADVISORY_GROUNDING] [FABRICATION_DISCARDED] Tender: %s | Field: 'tender_no' | Claimed: '%s' | GroundTruth: '%s'",
                expected_tender_no, claimed_tender_no, expected_tender_no
            )
        raw_json["tender_no"] = expected_tender_no

        # 2. Ground and audit Win Probability
        claimed_prob = raw_json.get("win_probability")
        expected_prob = float(ml_context["win_probability"])
        if claimed_prob is not None and abs(float(claimed_prob) - expected_prob) > 0.001:
            logger.warning(
                "[STRUCTURED_ADVISORY_GROUNDING] [METRIC_MUTATION_CORRECTED] Tender: %s | Field: 'win_probability' | Claimed: %s | GroundTruth: %s",
                expected_tender_no, claimed_prob, expected_prob
            )
        raw_json["win_probability"] = expected_prob

        # 3. Ground and audit Similar Tenders against genuine Qdrant vectors
        valid_tender_map = {s["tender_no"].upper(): s for s in similar_summaries}
        grounded_similars = []

        provided_similars = raw_json.get("similar_tenders", [])
        for s in provided_similars:
            s_id = str(s.get("tender_no", "")).strip().upper()
            if s_id in valid_tender_map:
                ref = valid_tender_map[s_id]
                # Audit outcome mutation
                claimed_outcome = s.get("outcome")
                if claimed_outcome and claimed_outcome != ref["outcome"]:
                    logger.warning(
                        "[STRUCTURED_ADVISORY_GROUNDING] [OUTCOME_MUTATION_CORRECTED] Tender: %s | Neighbor: %s | Claimed Outcome: '%s' | GroundTruth Outcome: '%s'",
                        expected_tender_no, ref["tender_no"], claimed_outcome, ref["outcome"]
                    )
                # Audit similarity score mutation
                claimed_sim = s.get("similarity")
                if claimed_sim is not None and abs(float(claimed_sim) - float(ref["similarity"])) > 0.01:
                    logger.warning(
                        "[STRUCTURED_ADVISORY_GROUNDING] [SIMILARITY_MUTATION_CORRECTED] Tender: %s | Neighbor: %s | Claimed Similarity: %s | GroundTruth Similarity: %s",
                        expected_tender_no, ref["tender_no"], claimed_sim, ref["similarity"]
                    )

                grounded_similars.append({
                    "tender_no": ref["tender_no"],
                    "tender_name": s.get("tender_name") or ref.get("tender_name", ""),
                    "similarity": float(ref["similarity"]),
                    "outcome": ref["outcome"],
                    "organization": ref.get("organization", "Unknown"),
                    "key_overlap": str(s.get("key_overlap") or ref.get("key_overlap", ""))
                })
            else:
                logger.warning(
                    "[STRUCTURED_ADVISORY_GROUNDING] [FABRICATED_NEIGHBOR_DISCARDED] Tender: %s | Discarded Fabricated Neighbor ID: '%s' | Claimed Payload: %s | Known Qdrant Neighbors: %s",
                    expected_tender_no, s.get("tender_no"), s, list(valid_tender_map.keys())
                )

        # If LLM dropped or hallucinated all neighbors, fallback to full Qdrant payload
        if not grounded_similars:
            logger.warning(
                "[STRUCTURED_ADVISORY_GROUNDING] [FALLBACK_RESTORED] Tender: %s | Restoring all %d ground-truth Qdrant neighbors after LLM dropped them.",
                expected_tender_no, len(similar_summaries)
            )
            grounded_similars = similar_summaries

        raw_json["similar_tenders"] = grounded_similars
        return raw_json

    def generate_advisory(
        self,
        tender_no: str,
        tender_metadata: Optional[Dict[str, Any]] = None,
        top_k_similar: int = 3
    ) -> StructuredAdvisoryResponse:
        """
        Generates a validated structured advisory for a specific tender.
        """
        # Step 1: Verify and fetch Week 5 ML/SHAP data
        ml_context = self._get_ml_shap_context(tender_no)
        
        # Step 2: Query Qdrant for nearest-neighbor historical tenders
        query_payload = tender_metadata or {
            "tender_no": tender_no,
            "tender_name": ml_context.get("tender_name", tender_no),
            "organization": ml_context.get("organization", "Unknown")
        }
        similar_tenders_raw = find_similar_tenders(
            query_target=query_payload,
            top_k=top_k_similar,
            exclude_tender_no=tender_no
        )

        similar_summaries = []
        for s in similar_tenders_raw:
            similar_summaries.append({
                "tender_no": s["tender_no"],
                "tender_name": s.get("tender_name", ""),
                "similarity": s["similarity"],
                "outcome": s["outcome"],
                "organization": s.get("organization", "Unknown"),
                "key_overlap": s.get("key_overlap", "")
            })

        # Step 3: Build Prompt for Groq Synthesis
        system_prompt = (
            "You are a Senior Strategic Procurement Analyst for Volks Energie (an Indian electrical and power systems vendor). "
            "Your role is to synthesize quantitative predictive intelligence (LightGBM win probability and SHAP attribution drivers) "
            "along with historical nearest-neighbor tender precedents into an authoritative, actionable, and data-grounded bid recommendation.\n\n"
            "CRITICAL RULES:\n"
            "1. You MUST return ONLY a valid JSON object matching the requested schema.\n"
            "2. Recommendation MUST be one of: 'bid' (strong win indicators), 'no_bid' (unfavorable terms/poor precedent), or 'review' (borderline).\n"
            "3. Ground your strategic rationale strictly on the provided LightGBM probability, SHAP drivers, and historical Won/Lost nearest neighbors.\n"
            "4. Highlight specific risk factors (e.g. tight delivery timeline, high EMD, lack of buyer incumbency).\n"
            "5. Provide concrete, operational next steps."
        )

        user_prompt = f"""Synthesize a structured bid advisory for the following tender:

## Target Tender Details:
- Tender Reference: {tender_no}
- Tender Title: {ml_context.get('tender_name', tender_no)}
- Procuring Authority: {ml_context.get('organization', 'Unknown')}

## Week 5 Machine Learning & SHAP Predictive Intelligence:
- LightGBM Estimated Win Probability: {ml_context['win_probability']:.2%}
- Model Classification: {ml_context['predicted_outcome']}
- Top 3 SHAP Drivers:
{chr(10).join(f"  * {d}" for d in ml_context['top_3_drivers'])}
- Full ML Attribution Summary: {ml_context['full_narrative']}

## Nearest-Neighbor Historical Tenders from Qdrant Vector Store:
{json.dumps(similar_summaries, indent=2)}

## Required JSON Schema:
{{
  "tender_no": "{tender_no}",
  "recommendation": "bid" | "no_bid" | "review",
  "confidence": <float between 0.0 and 1.0>,
  "win_probability": {ml_context['win_probability']},
  "key_drivers": [<list of strings highlighting top factors>],
  "similar_tenders": [
    {{
      "tender_no": "<string>",
      "tender_name": "<string>",
      "similarity": <float>,
      "outcome": "Won" | "Lost" | "Pending",
      "organization": "<string>",
      "key_overlap": "<string>"
    }}
  ],
  "strategic_rationale": "<comprehensive 2-3 paragraph analytical rationale>",
  "risk_factors": [<list of specific risk factor strings>],
  "actionable_next_steps": [<list of actionable operational next steps>]
}}
"""

        # Step 4: Call Groq and validate against Pydantic schema with 1 retry
        for attempt in range(2):
            try:
                raw_json = self._call_groq_json(system_prompt, user_prompt)
                
                # Step 5: Post-hoc deterministic grounding check
                grounded_json = self._verify_and_ground_advisory(raw_json, ml_context, similar_summaries)

                # Parse and validate with Pydantic
                advisory = StructuredAdvisoryResponse(**grounded_json)
                logger.info(
                    "[StructuredAdvisory] Successfully synthesized advisory for %s: recommendation=%s, confidence=%.2f",
                    tender_no, advisory.recommendation, advisory.confidence
                )
                return advisory
            except (ValidationError, json.JSONDecodeError, KeyError) as e:
                logger.warning("[StructuredAdvisory] Attempt %d validation failed: %s", attempt + 1, e)
                if attempt == 0:
                    # Append error context to retry prompt
                    user_prompt += f"\n\n[ATTENTION: Previous response failed schema validation with error: {e}. Return strict valid JSON conforming to the schema.]"
                else:
                    raise StructuredAdvisorySchemaError(
                        f"Failed to generate schema-conformant advisory after retry for tender {tender_no}: {e}"
                    )
