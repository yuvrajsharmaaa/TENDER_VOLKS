from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class ScoreDecomposition(BaseModel):
    compliance_score: float = Field(description="Deterministic hard compliance score (0.0 to 1.0, rules passed / 8)")
    compliance_status: str = Field(description="QUALIFIED, NEEDS_REVIEW, or DISQUALIFIED")
    ml_win_prob: float = Field(description="LightGBM predicted win probability (0.0 to 1.0)")
    similarity_score: float = Field(description="Qdrant top-5 nearest-neighbor historical win rate (0.0 to 1.0)")
    groq_fit_score: float = Field(description="Groq LLM strategic fit score (0.0 to 1.0)")
    composite_score: float = Field(description="Weighted multi-signal composite score (0.0 to 1.0)")


class SimilarTenderItem(BaseModel):
    tender_no: str = Field(description="Historical tender reference number")
    tender_name: Optional[str] = Field(default="", description="Historical tender title")
    similarity: float = Field(description="Cosine similarity metric (0.0 to 1.0)")
    outcome: str = Field(description="Won, Lost, or Pending")
    organization: Optional[str] = Field(default="Unknown", description="Procuring organization")
    key_overlap: Optional[str] = Field(default="", description="Key commercial or technical commonalities")


class ScoredTender(BaseModel):
    rank: int = Field(description="Recommendation rank (#1 is highest composite fit)")
    tender_no: str = Field(description="Tender reference number")
    tender_name: str = Field(description="Tender title or category")
    organization: str = Field(description="Procuring authority / PSU")
    tender_value: float = Field(description="Estimated tender value in INR")
    composite_score: float = Field(description="Final composite recommendation score")
    score_decomposition: ScoreDecomposition = Field(description="Breakdown across all 4 individual signal scores")
    similar_tenders: List[SimilarTenderItem] = Field(default_factory=list, description="Top nearest historical tender precedents")
    key_drivers: List[str] = Field(default_factory=list, description="Top positive and negative driving factors")
    strategic_rationale: Optional[str] = Field(default=None, description="Executive strategic summary and bid rationale")
    disqualification_reasons: List[str] = Field(default_factory=list, description="Mandatory failure reasons if disqualified")
    review_reasons: List[str] = Field(default_factory=list, description="Reasons requiring manual estimator review")


class PQCRecommendationRequest(BaseModel):
    top_k: int = Field(default=20, ge=1, le=100, description="Number of top ranked tenders to return")
    include_groq: bool = Field(default=True, description="Whether to run Groq LLM qualitative enrichment on top candidates")
    source: Optional[str] = Field(default="db", description="Data source: 'db' for active workspace or 'dataset' for backtest pool")


class PQCRecommendationResponse(BaseModel):
    recommendations: List[ScoredTender] = Field(description="Ranked list of recommended tenders with score decomposition")
    total_scored: int = Field(description="Total population of tenders evaluated")
    weights_used: Dict[str, float] = Field(description="Signal weights applied in composite ranking")
    timestamp: str = Field(description="ISO UTC execution timestamp")
