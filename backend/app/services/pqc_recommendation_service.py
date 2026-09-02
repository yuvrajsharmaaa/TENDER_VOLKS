import os
import json
import time
import logging
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

logger = logging.getLogger("pqc_recommendation_service")
ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
load_dotenv(ROOT_DIR / ".env.dev")

DEFAULT_WEIGHTS = {
    "compliance": 0.35,
    "similarity": 0.35,
    "ml_win_prob": 0.15,
    "groq": 0.15
}


class PQCRecommendationService:
    """
    4-Signal PQC Tender Recommendation and Ranking Service:
      Signal 1 (0.35): Deterministic Statutory & Commercial Compliance (F_hard rules passed / 8)
      Signal 2 (0.15): Persisted LightGBM 16-feature ML win probability (tiebreaker)
      Signal 3 (0.35): Qdrant Top-5 Nearest-Neighbor historical win rate (Won / Total)
      Signal 4 (0.15): Groq LLM (llama-3.1-8b-instant) strategic fit score (0.0 to 1.0)
    """

    def __init__(
        self,
        weights: Optional[Dict[str, float]] = None,
        model_path: Optional[Union[str, Path]] = None,
        vendor_profile: Optional[VendorProfile] = None,
        groq_model: Optional[str] = None,
        groq_api_key: Optional[str] = None
    ):
        self.weights = weights or DEFAULT_WEIGHTS.copy()
        self.vendor_profile = vendor_profile or VendorProfile.from_yaml()
        self.compliance_service = RegulatoryComplianceService(default_profile=self.vendor_profile)
        
        # Load ML model artifact
        self.model_path = Path(model_path or (ROOT_DIR / "artifacts" / "lgbm_win_predictor.joblib"))
        self.model = None
        self.feature_cols = []
        self._load_ml_model()

        # Groq configuration
        self.groq_model = groq_model or os.getenv("GROQ_MODEL", "qwen/qwen3.6-27b")
        self.groq_api_key = groq_api_key or os.getenv("GROQ_API_KEY", os.getenv("LLM_API_KEY", ""))
        self.groq_url = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1/chat/completions")

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
                    "tender_name": t.get("tender_name", t["tender_no"]),
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
    # SIGNAL 4: GROQ LLM STRATEGIC FIT (TOP-50 ONLY)
    # =========================================================================
    def evaluate_groq_strategic_fit(
        self,
        tender_no: str,
        tender_name: str,
        organization: str,
        tender_value: float,
        compliance_status: str,
        ml_win_prob: float,
        similar_tenders: List[Dict[str, Any]],
        timeout: float = 12.0
    ) -> Tuple[float, str]:
        """
        Calls Groq API (llama-3.1-8b-instant) to assess qualitative strategic fit (0.0 to 1.0).
        Safely defaults to 0.50 on any failure or missing key.
        """
        if not self.groq_api_key or self.groq_api_key == "disabled":
            logger.error("[PQCService] Groq API key is empty or disabled! Returning 0.50 neutral fallback.")
            print("[PQCService] Groq API key is empty or disabled! Returning 0.50 neutral fallback.")
            return 0.50, "Groq LLM enrichment offline; using neutral baseline."

        headers = {
            "Authorization": f"Bearer {self.groq_api_key}",
            "Content-Type": "application/json"
        }

        system_prompt = (
            "You are a strategic bidding analyst for Volks Energie (an Indian electrical power systems vendor). "
            "Evaluate the commercial and strategic fit of the following tender on a scale of 0.0 to 1.0.\n"
            "Return ONLY a valid JSON object:\n"
            "{\n"
            '  "strategic_fit": <float between 0.0 and 1.0>,\n'
            '  "strategic_rationale": "<1-2 sentence concise executive explanation>"\n'
            "}"
        )

        user_content = f"""Tender Number: {tender_no}
Title: {tender_name}
Authority: {organization}
Estimated Value: INR {tender_value:,.2f}
Compliance Status: {compliance_status}
ML Win Probability: {ml_win_prob:.1%}
Top Historical Similar Tenders:
{json.dumps(similar_tenders[:3], indent=2)}
"""

        payload = {
            "model": self.groq_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"}
        }

        try:
            with httpx.Client(timeout=timeout) as client:
                resp = client.post(self.groq_url, headers=headers, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    raw_content = data["choices"][0]["message"]["content"]
                    try:
                        content = json.loads(raw_content)
                    except Exception as json_err:
                        logger.error(
                            f"[PQCService] Groq JSON parsing failed for tender {tender_no}: {json_err} | Raw content: {raw_content!r}\n"
                            f"Traceback:\n{traceback.format_exc()}"
                        )
                        return 0.50, f"Groq response parsing error ({json_err})."

                    fit = float(content.get("strategic_fit", 0.50))
                    fit = min(max(fit, 0.0), 1.0)
                    rationale = str(content.get("strategic_rationale", "Strategic fit evaluated by Groq AI."))
                    return round(fit, 4), rationale
                else:
                    err_details = f"[PQCService] Groq API returned HTTP {resp.status_code} for tender {tender_no}: {resp.text}"
                    logger.error(err_details)
                    return 0.50, f"Groq enrichment unavailable (HTTP {resp.status_code})."
        except Exception as e:
            tb = traceback.format_exc()
            err_details = f"[PQCService] Groq call failed for {tender_no}: {type(e).__name__}: {e}\nTraceback:\n{tb}"
            logger.error(err_details)
            return 0.50, f"Groq evaluation defaulted ({e})."

    # =========================================================================
    # COMPOSITE SCORING & MULTI-TENDER RANKING
    # =========================================================================
    def score_single_tender(
        self,
        tender_dict: Dict[str, Any],
        include_groq: bool = False,
        org_win_rate: float = 0.0,
        incumbent_buyer: int = 0
    ) -> Dict[str, Any]:
        """
        Computes all 4 signals and composite score for a single tender.
        """
        tender_no = str(tender_dict.get("tender_no", "UNKNOWN"))
        tender_name = str(tender_dict.get("tender_name") or tender_no)
        organization = str(tender_dict.get("organization") or tender_dict.get("client") or tender_dict.get("department") or "Unknown Authority")
        
        raw_val = tender_dict.get("tender_value") or tender_dict.get("estimated_cost") or 0.0
        try:
            tender_value = float(raw_val) if raw_val is not None else 0.0
        except (ValueError, TypeError):
            tender_value = 0.0

        # 1. Signal 1: Compliance
        comp_score, comp_status, disq_reasons, review_reasons, rule_results = self.evaluate_compliance_signal(tender_no, tender_dict)

        # 2. Signal 2: ML Win Probability
        feat_df = self.engineer_single_feature_vector(tender_dict, org_win_rate=org_win_rate, incumbent_buyer=incumbent_buyer)
        ml_win_prob, key_drivers = self.predict_ml_win_probability(feat_df)

        # 3. Signal 3: Similarity Track Record
        sim_score, avg_sim, similar_tenders = self.evaluate_similarity_signal(tender_dict, top_k=5)

        # 4. Signal 4: Groq Strategic Fit (default 0.50 if not requested)
        groq_score = 0.50
        strategic_rationale = "Evaluated via deterministic compliance, LightGBM classifier, and Qdrant vector similarity."
        if include_groq:
            groq_score, strategic_rationale = self.evaluate_groq_strategic_fit(
                tender_no=tender_no,
                tender_name=tender_name,
                organization=organization,
                tender_value=tender_value,
                compliance_status=comp_status,
                ml_win_prob=ml_win_prob,
                similar_tenders=similar_tenders
            )

        # 5. Composite Score Calculation
        w = self.weights
        composite = (
            w["compliance"] * comp_score +
            w["similarity"] * sim_score +
            w["ml_win_prob"] * ml_win_prob +
            w["groq"] * groq_score
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
                "groq_fit_score": groq_score,
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
        include_groq: bool = True,
        groq_top_n: int = 50
    ) -> Dict[str, Any]:
        """
        Scores and ranks a collection of tenders.
        Groq enrichment is applied only to the top candidates to preserve latency and rate limits.
        """
        logger.info(f"[PQCService] Scoring and ranking N={len(tenders)} tenders (top_k={top_k}, include_groq={include_groq})...")

        # Step 1: Initial scoring with Groq=0.50 (fast, <2 seconds for 600 tenders)
        preliminary_scored = []
        for t in tenders:
            scored = self.score_single_tender(t, include_groq=False)
            preliminary_scored.append(scored)

        # Sort descending by composite score
        preliminary_scored.sort(key=lambda x: x["composite_score"], reverse=True)

        # Step 2: Groq enrichment on top_n if requested
        if include_groq and self.groq_api_key:
            target_n = min(len(preliminary_scored), groq_top_n)
            logger.info(f"[PQCService] Running Groq LLM enrichment for top {target_n} tenders...")
            for idx in range(target_n):
                item = preliminary_scored[idx]
                groq_fit, rationale = self.evaluate_groq_strategic_fit(
                    tender_no=item["tender_no"],
                    tender_name=item["tender_name"],
                    organization=item["organization"],
                    tender_value=item["tender_value"],
                    compliance_status=item["score_decomposition"]["compliance_status"],
                    ml_win_prob=item["score_decomposition"]["ml_win_prob"],
                    similar_tenders=item["similar_tenders"]
                )
                item["score_decomposition"]["groq_fit_score"] = groq_fit
                item["strategic_rationale"] = rationale
                
                # Recalculate composite
                w = self.weights
                decomp = item["score_decomposition"]
                new_composite = (
                    w["compliance"] * decomp["compliance_score"] +
                    w["similarity"] * decomp["similarity_score"] +
                    w["ml_win_prob"] * decomp["ml_win_prob"] +
                    w["groq"] * decomp["groq_fit_score"]
                )
                item["composite_score"] = round(float(new_composite), 4)
                item["score_decomposition"]["composite_score"] = item["composite_score"]
                
                # Respect rate limits
                if idx < target_n - 1:
                    time.sleep(0.05)

            # Re-sort after Groq enrichment
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
