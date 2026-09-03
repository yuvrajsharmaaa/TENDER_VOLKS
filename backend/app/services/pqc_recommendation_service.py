import os
import json
import time
import logging
import re
import traceback
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional, Union, Tuple
import numpy as np
import pandas as pd
import joblib
import httpx
from dotenv import load_dotenv

from backend.app.services.compliance.regulatory import (
    RegulatoryComplianceService,
    VendorProfile,
    ComplianceStatus
)
from backend.app.services.tender_indexer import find_similar_tenders, build_tender_composite_text
from backend.app.schemas.pqc_recommendation import resolve_tender_title
from backend.app.services.claude_fit_cache import ClaudeFitCache

logger = logging.getLogger("pqc_recommendation_service")
ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
load_dotenv(ROOT_DIR / ".env.dev")

DEFAULT_WEIGHTS = {
    "compliance": 0.35,
    "similarity": 0.35,
    "ml_win_prob": 0.15,
    "claude": 0.15
}


class PQCRecommendationService:
    """
    4-Signal PQC Tender Recommendation and Ranking Service:
      Signal 1 (0.35): Deterministic Statutory & Commercial Compliance (F_hard rules passed / 8)
      Signal 2 (0.15): Persisted LightGBM 16-feature ML win probability (tiebreaker)
      Signal 3 (0.35): Qdrant Top-5 Nearest-Neighbor historical win rate (Won / Total)
      Signal 4 (0.15): Claude LLM (claude-haiku-4-5-20251001) strategic fit score (0.0 to 1.0)
    """

    def __init__(
        self,
        weights: Optional[Dict[str, float]] = None,
        model_path: Optional[Union[str, Path]] = None,
        vendor_profile: Optional[VendorProfile] = None,
        anthropic_api_key: Optional[str] = None,
        anthropic_model: Optional[str] = None,
        cache_db_path: Optional[Path] = None
    ):
        self.weights = weights or DEFAULT_WEIGHTS.copy()
        self.vendor_profile = vendor_profile or VendorProfile.from_yaml()
        self.compliance_service = RegulatoryComplianceService(default_profile=self.vendor_profile)
        self.cache = ClaudeFitCache(db_path=cache_db_path)
        
        # Load ML model artifact
        self.model_path = Path(model_path or (ROOT_DIR / "artifacts" / "lgbm_win_predictor.joblib"))
        self.model = None
        self.feature_cols = []
        self._load_ml_model()

        # Claude / Anthropic configuration (Signal 4)
        self.anthropic_api_key = anthropic_api_key or os.getenv("ANTHROPIC_API_KEY", "")
        self.anthropic_model = anthropic_model or os.getenv("ANTHROPIC_FAST_MODEL", os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001"))

        # Similarity signal availability (checked once to eliminate 600+ repetitive import warnings)
        self._similarity_available = self._check_similarity_support()

    def _check_similarity_support(self) -> bool:
        try:
            import sentence_transformers  # noqa: F401
            return True
        except ImportError:
            logger.info(
                "[PQCService] sentence-transformers not installed; Qdrant vector similarity signal "
                "will use default historical baseline (0.19) without per-tender warnings."
            )
            return False

    def _load_ml_model(self):
        """Loads persisted LightGBM model and feature list."""
        if self.model_path.exists():
            try:
                artifact = joblib.load(self.model_path)
                if isinstance(artifact, dict):
                    self.model = artifact.get("model") or artifact.get("stat_model")
                    self.feature_cols = artifact.get("feature_cols", [])
                else:
                    self.model = artifact
                logger.info(f"[PQCService] Successfully loaded ML model from {self.model_path}")
            except Exception as e:
                logger.warning(f"[PQCService] Could not load model artifact from {self.model_path}: {e}")
                self.model = None
        else:
            logger.warning(f"[PQCService] Model artifact not found at {self.model_path}")

    # =========================================================================
    # SIGNAL 1: COMPLIANCE EVALUATION (F_hard)
    # =========================================================================
    def evaluate_compliance_signal(
        self,
        tender_no: str,
        row_dict: Dict[str, Any]
    ) -> Tuple[float, str, List[str], List[str], List[Dict[str, Any]]]:
        """
        Runs RegulatoryComplianceService.evaluate_compliance and calculates:
        compliance_score = rules_passed / 8.0
        """
        field_map = {
            "avg_annual_turnover_value_display": row_dict.get("avg_annual_turnover_value") or row_dict.get("annual_turnover"),
            "working_capital_value_display": row_dict.get("working_capital_value"),
            "experience_criteria_years": row_dict.get("technical_eligibility_age") or row_dict.get("technical_experience_years_req"),
            "pbg_percentage": row_dict.get("pbg_percentage"),
            "pbg_required": row_dict.get("pbg_required"),
            "bid_validity_days": row_dict.get("bid_validity_days"),
            "required_documents": row_dict.get("required_documents"),
            "mii_purchase_preference": row_dict.get("mii_purchase_preference"),
        }

        try:
            resp = self.compliance_service.evaluate_compliance(tender_no, field_map, self.vendor_profile)
            total_rules = max(len(resp.rule_results), 8)
            passed_rules = sum(1 for r in resp.rule_results if r.passed)
            compliance_score = round(passed_rules / float(total_rules), 4)
            rule_summaries = [
                {
                    "rule_name": r.rule_name,
                    "field_name": r.field_name,
                    "status": r.status.value,
                    "passed": r.passed,
                    "reason": r.reason
                }
                for r in resp.rule_results
            ]
            return (
                compliance_score,
                resp.overall_status.value,
                resp.disqualification_reasons,
                resp.review_reasons,
                rule_summaries
            )
        except Exception as e:
            logger.error(f"[PQCService] Compliance evaluation failed for {tender_no}: {e}")
            return 0.5, "NEEDS_REVIEW", [], [f"Compliance evaluation error: {e}"], []

    # =========================================================================
    # SIGNAL 2: LIGHTGBM ML WIN PROBABILITY
    # =========================================================================
    def engineer_single_feature_vector(
        self,
        row_dict: Dict[str, Any],
        org_win_rate: float = 0.0,
        incumbent_buyer: int = 0
    ) -> pd.DataFrame:
        """
        Builds the 16-feature vector matching the trained LightGBM model format.
        """
        profile = {
            "avg_annual_turnover": self.vendor_profile.annual_turnover,
            "msme_registered": self.vendor_profile.is_mse_registered,
            "incumbent_psu_list": ["IOCL", "AAI", "HPCL", "GAIL", "NTPC", "SAIL", "ONGC", "PGETL", "BPCL"]
        }

        # Tender Value & EMD
        raw_tv = row_dict.get("tender_value") or row_dict.get("estimated_cost") or 0.0
        try:
            val_f = float(raw_tv) if raw_tv is not None else 0.0
        except (ValueError, TypeError):
            val_f = 0.0
        
        tv_imputed = 0
        if val_f < 10_000.0 or val_f > 1_000_000_000.0:
            val_f = 4_315_000.0  # global median fallback
            tv_imputed = 1
            
        log_tv = float(np.log1p(val_f))

        raw_emd = row_dict.get("emd_amount") or 0.0
        try:
            emd_f = float(raw_emd) if raw_emd is not None else 0.0
        except (ValueError, TypeError):
            emd_f = 0.0
        emd_bounded = min(max(emd_f, 0.0), 100_000_000.0)
        log_emd = float(np.log1p(emd_bounded))
        emd_ratio = float(emd_bounded / profile["avg_annual_turnover"])

        # Turnover Ratio
        raw_to = row_dict.get("avg_annual_turnover_value") or 0.0
        try:
            to_f = float(raw_to) if raw_to is not None else 0.0
        except (ValueError, TypeError):
            to_f = 0.0
        turnover_req_app = 1 if to_f > 0 else 0
        turnover_ratio = float(to_f / profile["avg_annual_turnover"]) if turnover_req_app else 0.0

        # PBG, LD, Delivery, Bid Validity
        pbg_pct = float(row_dict.get("pbg_percentage") or 0.0)
        pbg_dur = float(row_dict.get("pbg_duration") or 0.0)
        max_ld = float(row_dict.get("max_ld_percentage") or 0.0)
        del_days = float(row_dict.get("delivery_time_supply") or row_dict.get("delivery_time_supply_days") or 0.0)
        
        raw_bv = row_dict.get("bid_validity_days")
        try:
            bv_f = float(raw_bv) if raw_bv is not None else 90.0
        except (ValueError, TypeError):
            bv_f = 90.0
        bv_bounded = min(max(bv_f, 1.0), 365.0)

        # Flags
        maf_req = 1 if str(row_dict.get("maf_required", "")).lower() in ["yes", "true", "1", "mandatory"] else 0
        ra_flag = 1 if str(row_dict.get("reverse_auction_applicable", "")).lower() in ["yes", "true", "1", "applicable"] else 0
        mse_pref = 1 if str(row_dict.get("mse_purchase_preference", "")).lower() in ["yes", "true", "1"] else 0
        msme_match = 1 if (mse_pref and profile["msme_registered"]) else 0

        # Incumbent PSU match
        org_str = str(row_dict.get("organization") or row_dict.get("department") or row_dict.get("client") or "").upper()
        is_incumbent = 1 if any(psu in org_str for psu in profile["incumbent_psu_list"]) else 0

        feat_dict = {
            "emd_ratio": [emd_ratio],
            "log_tender_value": [log_tv],
            "tender_value_imputed_num": [tv_imputed],
            "turnover_ratio": [turnover_ratio],
            "pbg_duration_months": [pbg_dur],
            "max_ld_cap_percent": [max_ld],
            "delivery_time_supply_days": [del_days],
            "bid_validity_days_bounded": [bv_bounded],
            "log_emd_amount": [log_emd],
            "maf_required_flag": [maf_req],
            "reverse_auction_flag": [ra_flag],
            "is_incumbent_psu": [is_incumbent],
            "authority_win_rate": [org_win_rate],
            "incumbent_buyer_status": [incumbent_buyer],
            "msme_match": [msme_match],
            "turnover_req_applicable": [turnover_req_app]
        }
        return pd.DataFrame(feat_dict)

    def predict_ml_win_probability(self, features_df: pd.DataFrame) -> Tuple[float, List[str]]:
        """
        Runs LightGBM inference and returns estimated win probability + top drivers.
        """
        if self.model is None:
            # Fallback baseline win probability
            return 0.19, ["ML model artifact unavailable; using empirical prior (19.0%)"]

        try:
            cols = self.feature_cols if self.feature_cols else list(features_df.columns)
            X = features_df[cols]
            prob = float(self.model.predict_proba(X)[0, 1])
            
            # Simple feature attribution proxy
            drivers = []
            if features_df["is_incumbent_psu"].iloc[0] == 1:
                drivers.append("Incumbent PSU client match (+)")
            if features_df["msme_match"].iloc[0] == 1:
                drivers.append("MSE purchase preference applicable (+)")
            if features_df["authority_win_rate"].iloc[0] > 0.3:
                drivers.append(f"Strong buyer track record ({features_df['authority_win_rate'].iloc[0]:.0%} win rate)")
            if features_df["turnover_ratio"].iloc[0] > 0.8:
                drivers.append("High turnover threshold ratio (-)")
            if features_df["delivery_time_supply_days"].iloc[0] > 0 and features_df["delivery_time_supply_days"].iloc[0] < 30:
                drivers.append("Aggressive delivery timeline (-)")
            
            if not drivers:
                drivers.append(f"Standard commercial profile (Win Prob {prob:.1%})")

            return round(prob, 4), drivers[:3]
        except Exception as e:
            logger.warning(f"[PQCService] ML prediction failed: {e}")
            return 0.19, [f"ML prediction error ({e})"]

    # =========================================================================
    # SIGNAL 3: QDRANT HISTORICAL NEAREST-NEIGHBOR WIN RATE
    # =========================================================================
    def evaluate_similarity_signal(
        self,
        tender_dict: Dict[str, Any],
        top_k: int = 5
    ) -> Tuple[float, float, List[Dict[str, Any]]]:
        """
        Queries Qdrant for top-5 historical tenders and calculates:
        similarity_win_rate = won_neighbors / total_neighbors
        avg_similarity = mean(similarity scores)
        """
        if not self._similarity_available:
            return 0.19, 0.0, []

        tender_no = str(tender_dict.get("tender_no", ""))
        try:
            similar = find_similar_tenders(
                query_target=tender_dict,
                top_k=top_k,
                exclude_tender_no=tender_no
            )
            if not similar:
                return 0.19, 0.0, []

            won_count = sum(1 for t in similar if str(t.get("outcome", "")).strip().lower() == "won")
            total = len(similar)
            win_rate = round(won_count / float(total), 4) if total > 0 else 0.19
            avg_sim = round(float(np.mean([t["similarity"] for t in similar])), 4) if total > 0 else 0.0

            summaries = [
                {
                    "tender_no": t["tender_no"],
                    "tender_name": resolve_tender_title(t.get("tender_name"), t["tender_no"]),
                    "similarity": t["similarity"],
                    "outcome": t.get("outcome", "Unknown"),
                    "organization": t.get("organization", "Unknown"),
                    "key_overlap": t.get("key_overlap", "")
                }
                for t in similar
            ]
            return win_rate, avg_sim, summaries
        except Exception as e:
            logger.warning(f"[PQCService] Qdrant similarity lookup failed for {tender_no}: {e}")
            return 0.19, 0.0, []

    # =========================================================================
    # SIGNAL 4: CLAUDE LLM STRATEGIC FIT (TOP-50 ONLY)
    # =========================================================================
    def evaluate_claude_strategic_fit(
        self,
        tender_no: str,
        tender_name: str,
        organization: str,
        tender_value: float,
        compliance_status: str,
        ml_win_prob: float,
        similar_tenders: List[Dict[str, Any]],
        timeout: float = 12.0,
        is_override: bool = False,
        deadline: Optional[str] = None
    ) -> Tuple[float, str]:
        # 1. Staleness check & Cache lookup (strictly bypassed if is_override=True)
        payload_hash = ClaudeFitCache.compute_payload_hash(
            tender_no=tender_no,
            tender_name=tender_name,
            organization=organization,
            tender_value=tender_value,
            compliance_status=compliance_status,
            ml_win_prob=ml_win_prob,
            similar_tenders=similar_tenders,
            deadline=deadline
        )

        if not is_override:
            cached = self.cache.get(tender_no=tender_no, current_hash=payload_hash)
            if cached is not None:
                logger.info(f"[PQCService][CACHE_HIT] Reusing cached Claude strategic fit for {tender_no}: {cached[0]:.2f}")
                return cached
        else:
            logger.info(f"[PQCService] is_override=True: Bypassing cache read for tender {tender_no}")

        # 2. Trimmed system instruction (role, concise schema, no filler)
        system_prompt = (
            "You are a senior bidding analyst for Volks Energie (Indian electrical systems vendor). "
            "Evaluate commercial and strategic fit of this tender (0.0 to 1.0). Return ONLY a JSON object:\n"
            '{"strategic_fit": <float between 0.0 and 1.0>, "strategic_rationale": "<1-2 concise executive sentences>"}'
        )

        # 3. Compact user prompt with compressed similar tenders JSON
        compact_similar = [
            {
                "no": str(s.get("tender_no", "")).strip(),
                "name": str(s.get("tender_name", ""))[:50].strip(),
                "sim": round(float(s.get("similarity", 0.0)), 2),
                "out": str(s.get("outcome", "")).strip()
            }
            for s in (similar_tenders or [])[:3]
        ]

        user_content = (
            f"Tender: {tender_no}\n"
            f"Title: {tender_name}\n"
            f"Authority: {organization}\n"
            f"Value: INR {tender_value:,.2f}\n"
            f"Compliance: {compliance_status}\n"
            f"ML Win Prob: {ml_win_prob:.1%}\n"
            f"Precedents: {json.dumps(compact_similar, separators=(',', ':'))}"
        )

        if not self.anthropic_api_key or self.anthropic_api_key == "disabled":
            logger.warning("[PQCService] Anthropic API key not configured or disabled. Returning 0.50 neutral fallback.")
            return 0.50, "Claude strategic enrichment offline; using neutral baseline."

        # 4. Bounded retries with exponential backoff & tight token limit (max_tokens=300)
        max_retries = 2
        delays = [1.0, 2.0]
        max_tokens = 300

        for attempt in range(max_retries + 1):
            try:
                raw_text = None
                in_tok = 0
                out_tok = 0
                cache_read = 0
                cache_create = 0

                try:
                    import anthropic
                    client = anthropic.Anthropic(api_key=self.anthropic_api_key, timeout=timeout)
                    system_blocks = [
                        {
                            "type": "text",
                            "text": system_prompt,
                            "cache_control": {"type": "ephemeral"}
                        }
                    ]
                    resp = client.messages.create(
                        model=self.anthropic_model,
                        max_tokens=max_tokens,
                        system=system_blocks,
                        messages=[{"role": "user", "content": user_content}]
                    )
                    raw_text = resp.content[0].text.strip()
                    in_tok = getattr(resp.usage, "input_tokens", 0)
                    out_tok = getattr(resp.usage, "output_tokens", 0)
                    cache_read = getattr(resp.usage, "cache_read_input_tokens", 0)
                    cache_create = getattr(resp.usage, "cache_creation_input_tokens", 0)
                except ImportError:
                    headers = {
                        "x-api-key": self.anthropic_api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json"
                    }
                    payload = {
                        "model": self.anthropic_model,
                        "max_tokens": max_tokens,
                        "temperature": 0.1,
                        "system": [
                            {
                                "type": "text",
                                "text": system_prompt,
                                "cache_control": {"type": "ephemeral"}
                            }
                        ],
                        "messages": [{"role": "user", "content": user_content}]
                    }
                    with httpx.Client(timeout=timeout) as client:
                        r = client.post("https://api.anthropic.com/v1/messages", headers=headers, json=payload)
                        if r.status_code == 200:
                            res_json = r.json()
                            raw_text = res_json["content"][0]["text"].strip()
                            usage = res_json.get("usage", {})
                            in_tok = usage.get("input_tokens", 0)
                            out_tok = usage.get("output_tokens", 0)
                            cache_read = usage.get("cache_read_input_tokens", 0)
                            cache_create = usage.get("cache_creation_input_tokens", 0)
                        elif r.status_code == 429:
                            raise RuntimeError(f"RateLimit 429: {r.text}")
                        else:
                            raise RuntimeError(f"HTTP {r.status_code}: {r.text}")

                if raw_text:
                    logger.info(
                        f"[PQCService][Claude Token Usage] Tender: {tender_no} | "
                        f"In: {in_tok} | Out: {out_tok} | CacheRead: {cache_read} | CacheCreate: {cache_create}"
                    )
                    clean = re.sub(r"^```(?:json)?\s*", "", raw_text)
                    clean = re.sub(r"\s*```$", "", clean)
                    content = json.loads(clean)
                    fit = float(content.get("strategic_fit", 0.50))
                    fit = round(min(max(fit, 0.0), 1.0), 4)
                    rationale = str(content.get("strategic_rationale", "Strategic fit evaluated by Claude AI."))

                    # Post-call cache store (strictly bypassed if is_override=True)
                    if not is_override:
                        self.cache.set(
                            tender_no=tender_no,
                            data_hash=payload_hash,
                            strategic_fit=fit,
                            strategic_rationale=rationale,
                            input_tokens=in_tok,
                            output_tokens=out_tok
                        )
                    else:
                        logger.info(f"[PQCService] is_override=True: Bypassing cache write for tender {tender_no}")

                    return fit, rationale

            except Exception as e:
                err_str = str(e).lower()
                is_rate_limit = "rate_limit" in err_str or "429" in err_str
                if attempt < max_retries:
                    delay = delays[attempt]
                    logger.warning(
                        f"[PQCService] Call failed on attempt {attempt + 1}/{max_retries + 1} for {tender_no} ({e}). "
                        f"Retrying in {delay}s with backoff..."
                    )
                    time.sleep(delay)
                else:
                    if is_rate_limit:
                        logger.error(f"[PQCService] Claude API rate limit (429) hit for tender {tender_no} after {max_retries + 1} attempts.")
                        return 0.50, "RATE_LIMIT_429"
                    logger.error(f"[PQCService] Claude strategic fit call failed for {tender_no} after {max_retries + 1} attempts: {e}")
                    return 0.50, f"Claude evaluation defaulted ({e})."

        return 0.50, "Claude evaluation returned empty response."

    # =========================================================================
    # COMPOSITE SCORING & MULTI-TENDER RANKING
    # =========================================================================
    def score_single_tender(
        self,
        tender_dict: Dict[str, Any],
        include_claude: bool = False,
        is_override: bool = False,
        org_win_rate: float = 0.0,
        incumbent_buyer: int = 0
    ) -> Dict[str, Any]:
        """
        Computes all 4 signals and composite score for a single tender.
        """
        raw_no = tender_dict.get("tender_no")
        tender_no = (
            str(raw_no).strip()
            if raw_no is not None and not (isinstance(raw_no, float) and np.isnan(raw_no)) and str(raw_no).strip().lower() not in ("nan", "none", "")
            else "UNKNOWN"
        )
        tender_name = resolve_tender_title(tender_dict.get("tender_name"), tender_no if tender_no != "UNKNOWN" else None)
        
        raw_org = tender_dict.get("organization") or tender_dict.get("client") or tender_dict.get("department")
        organization = (
            str(raw_org).strip()
            if raw_org is not None and not (isinstance(raw_org, float) and np.isnan(raw_org)) and str(raw_org).strip().lower() not in ("nan", "none", "")
            else "Unknown Authority"
        )
        
        raw_val = tender_dict.get("tender_value") or tender_dict.get("estimated_cost") or 0.0
        try:
            tender_value = float(raw_val) if raw_val is not None and not (isinstance(raw_val, float) and np.isnan(raw_val)) else 0.0
            if np.isnan(tender_value):
                tender_value = 0.0
        except (ValueError, TypeError):
            tender_value = 0.0

        # 1. Signal 1: Compliance
        comp_score, comp_status, disq_reasons, review_reasons, rule_results = self.evaluate_compliance_signal(tender_no, tender_dict)

        # 2. Signal 2: ML Win Probability
        feat_df = self.engineer_single_feature_vector(tender_dict, org_win_rate=org_win_rate, incumbent_buyer=incumbent_buyer)
        ml_win_prob, key_drivers = self.predict_ml_win_probability(feat_df)

        # 3. Signal 3: Similarity Track Record
        sim_score, avg_sim, similar_tenders = self.evaluate_similarity_signal(tender_dict, top_k=5)

        # 4. Signal 4: Claude Strategic Fit (Short-circuit on DISQUALIFIED and CANNOT_EVALUATE)
        if comp_status == "DISQUALIFIED":
            claude_score = 0.0
            disq_detail = f" ({'; '.join(disq_reasons[:2])})" if disq_reasons else ""
            strategic_rationale = f"Skipped Claude enrichment: Disqualified by Hard Compliance Filter{disq_detail}."
        elif tender_value <= 0.0:
            claude_score = 0.50
            strategic_rationale = "Skipped Claude enrichment: Tender value zero or unstated (CANNOT_EVALUATE)."
        elif include_claude:
            claude_score, strategic_rationale = self.evaluate_claude_strategic_fit(
                tender_no=tender_no,
                tender_name=tender_name,
                organization=organization,
                tender_value=tender_value,
                compliance_status=comp_status,
                ml_win_prob=ml_win_prob,
                similar_tenders=similar_tenders,
                is_override=is_override
            )
        else:
            claude_score = 0.50
            strategic_rationale = "Evaluated via deterministic compliance, LightGBM classifier, and Qdrant vector similarity."

        # 5. Composite Score Calculation
        w = self.weights
        composite = (
            w["compliance"] * comp_score +
            w["similarity"] * sim_score +
            w["ml_win_prob"] * ml_win_prob +
            w["claude"] * claude_score
        )
        composite = round(float(composite), 4)

        return {
            "tender_no": tender_no,
            "tender_name": tender_name,
            "organization": organization,
            "tender_value": tender_value,
            "composite_score": composite,
            "actual_outcome": tender_dict.get("outcome", "Unknown"),
            "score_decomposition": {
                "compliance_score": comp_score,
                "compliance_status": comp_status,
                "ml_win_prob": ml_win_prob,
                "similarity_score": sim_score,
                "claude_fit_score": claude_score,
                "composite_score": composite
            },
            "similar_tenders": similar_tenders,
            "key_drivers": key_drivers,
            "strategic_rationale": strategic_rationale,
            "disqualification_reasons": disq_reasons,
            "review_reasons": review_reasons,
            "rule_results": rule_results
        }

    def rank_tenders(
        self,
        tenders: List[Dict[str, Any]],
        top_k: int = 20,
        include_claude: bool = True,
        claude_top_n: int = 50,
        is_override: bool = False
    ) -> Dict[str, Any]:
        """
        Scores and ranks a collection of tenders.
        Claude enrichment is applied to top candidates (default 50).
        """
        logger.info(f"[PQCService] Scoring and ranking N={len(tenders)} tenders (top_k={top_k}, include_claude={include_claude}, is_override={is_override})...")

        # Step 1: Initial scoring with fast deterministic signals
        preliminary_scored = []
        for t in tenders:
            scored = self.score_single_tender(t, include_claude=False, is_override=is_override)
            preliminary_scored.append(scored)

        # Sort descending by composite score
        preliminary_scored.sort(key=lambda x: x["composite_score"], reverse=True)

        # Step 2: Claude enrichment on top eligible candidates if requested
        if include_claude and self.anthropic_api_key:
            # Sift out disqualified or zero-value tenders before LLM candidate enrichment
            eligible_indices = [
                idx for idx, item in enumerate(preliminary_scored[:top_k])
                if item["score_decomposition"]["compliance_status"] != "DISQUALIFIED" and item["tender_value"] > 0.0
            ]
            target_indices = eligible_indices[:claude_top_n]
            logger.info(f"[PQCService] Running Claude AI enrichment for {len(target_indices)} eligible top tenders...")
            rate_limited = False
            for loop_idx, idx in enumerate(target_indices):
                if rate_limited:
                    break
                item = preliminary_scored[idx]
                claude_fit, rationale = self.evaluate_claude_strategic_fit(
                    tender_no=item["tender_no"],
                    tender_name=item["tender_name"],
                    organization=item["organization"],
                    tender_value=item["tender_value"],
                    compliance_status=item["score_decomposition"]["compliance_status"],
                    ml_win_prob=item["score_decomposition"]["ml_win_prob"],
                    similar_tenders=item["similar_tenders"],
                    is_override=is_override
                )

                if rationale == "RATE_LIMIT_429":
                    logger.warning(
                        f"[PQCService] Claude API rate limit (429) hit on candidate #{loop_idx + 1}. "
                        "Safely falling back remaining candidates to neutral 0.50 baseline without delay."
                    )
                    item["score_decomposition"]["claude_fit_score"] = 0.50
                    item["strategic_rationale"] = "Claude rate limit reached; using neutral strategic baseline."
                    rate_limited = True
                    break

                item["score_decomposition"]["claude_fit_score"] = claude_fit
                item["strategic_rationale"] = rationale
                
                # Recalculate composite
                w = self.weights
                decomp = item["score_decomposition"]
                new_composite = (
                    w["compliance"] * decomp["compliance_score"] +
                    w["similarity"] * decomp["similarity_score"] +
                    w["ml_win_prob"] * decomp["ml_win_prob"] +
                    w["claude"] * decomp["claude_fit_score"]
                )
                item["composite_score"] = round(float(new_composite), 4)
                item["score_decomposition"]["composite_score"] = item["composite_score"]
                
                # Batch pacing: 0.25s delay between live calls
                if loop_idx < len(target_indices) - 1:
                    time.sleep(0.25)

            # Re-sort after Claude enrichment
            preliminary_scored.sort(key=lambda x: x["composite_score"], reverse=True)

        # Step 3: Assign ranks and slice top_k
        final_recommendations = []
        for rank_idx, item in enumerate(preliminary_scored[:top_k], start=1):
            item["rank"] = rank_idx
            final_recommendations.append(item)

        return {
            "recommendations": final_recommendations,
            "total_scored": len(tenders),
            "weights_used": self.weights,
            "timestamp": datetime.utcnow().isoformat()
        }
