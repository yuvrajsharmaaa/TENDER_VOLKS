import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import pytest
from unittest.mock import MagicMock, patch
import pandas as pd

from backend.app.services.pqc_recommendation_service import PQCRecommendationService, DEFAULT_WEIGHTS
from backend.app.schemas.pqc_recommendation import (
    PQCRecommendationRequest,
    PQCRecommendationResponse,
    ScoredTender,
    ScoreDecomposition
)
from backend.app.services.compliance.regulatory import VendorProfile


@pytest.fixture
def mock_vendor_profile():
    return VendorProfile(
        annual_turnover=208_886_000.0,
        working_capital=43_642_000.0,
        years_of_experience=10,
        held_certifications=["ISO 9001", "BIS", "ISO 14001", "CE"],
        is_mse_registered=True
    )


@pytest.fixture
def sample_tender():
    return {
        "tender_no": "GEM/2026/B/7306631",
        "tender_name": "Supply and Installation of 11kV HT Switchgear Panels",
        "organization": "GAIL INDIA LIMITED",
        "tender_value": 4_500_000.0,
        "emd_amount": 90_000.0,
        "avg_annual_turnover_value": 15_000_000.0,
        "pbg_percentage": 5.0,
        "pbg_duration": 18.0,
        "max_ld_percentage": 5.0,
        "delivery_time_supply": 60.0,
        "bid_validity_days": 90.0,
        "mse_purchase_preference": "Yes",
        "mii_purchase_preference": "Yes",
        "outcome": "Won"
    }


def test_pqc_service_weights_initialization(mock_vendor_profile):
    service = PQCRecommendationService(vendor_profile=mock_vendor_profile)
    assert service.weights["compliance"] == 0.35
    assert service.weights["similarity"] == 0.35
    assert service.weights["ml_win_prob"] == 0.15
    assert service.weights["groq"] == 0.15
    assert sum(service.weights.values()) == 1.0


def test_evaluate_compliance_signal(mock_vendor_profile, sample_tender):
    service = PQCRecommendationService(vendor_profile=mock_vendor_profile)
    comp_score, comp_status, disq, rev, rules = service.evaluate_compliance_signal(
        sample_tender["tender_no"],
        sample_tender
    )
    assert comp_score >= 0.0 and comp_score <= 1.0
    assert comp_status in ["QUALIFIED", "NEEDS_REVIEW", "DISQUALIFIED"]
    assert len(rules) >= 7


def test_engineer_single_feature_vector(mock_vendor_profile, sample_tender):
    service = PQCRecommendationService(vendor_profile=mock_vendor_profile)
    feat_df = service.engineer_single_feature_vector(sample_tender, org_win_rate=0.4, incumbent_buyer=1)
    assert isinstance(feat_df, pd.DataFrame)
    assert len(feat_df) == 1
    assert "emd_ratio" in feat_df.columns
    assert "is_incumbent_psu" in feat_df.columns
    assert feat_df["is_incumbent_psu"].iloc[0] == 1  # GAIL is in incumbent PSU list


def test_predict_ml_win_probability(mock_vendor_profile, sample_tender):
    service = PQCRecommendationService(vendor_profile=mock_vendor_profile)
    feat_df = service.engineer_single_feature_vector(sample_tender)
    prob, drivers = service.predict_ml_win_probability(feat_df)
    assert 0.0 <= prob <= 1.0
    assert len(drivers) > 0


def test_groq_fallback_safety(mock_vendor_profile, sample_tender):
    # Test that Groq gracefully defaults to 0.50 on failure or offline
    service = PQCRecommendationService(
        vendor_profile=mock_vendor_profile,
        groq_api_key="invalid_test_key"
    )
    fit, rationale = service.evaluate_groq_strategic_fit(
        tender_no=sample_tender["tender_no"],
        tender_name=sample_tender["tender_name"],
        organization=sample_tender["organization"],
        tender_value=sample_tender["tender_value"],
        compliance_status="QUALIFIED",
        ml_win_prob=0.65,
        similar_tenders=[]
    )
    assert fit == 0.50
    assert len(rationale) > 0


def test_score_single_tender(mock_vendor_profile, sample_tender):
    service = PQCRecommendationService(vendor_profile=mock_vendor_profile)
    scored = service.score_single_tender(sample_tender, include_groq=False)
    
    assert "tender_no" in scored
    assert "composite_score" in scored
    assert "score_decomposition" in scored
    
    decomp = scored["score_decomposition"]
    expected_composite = round(
        0.35 * decomp["compliance_score"] +
        0.35 * decomp["similarity_score"] +
        0.15 * decomp["ml_win_prob"] +
        0.15 * decomp["groq_fit_score"],
        4
    )
    assert abs(scored["composite_score"] - expected_composite) < 1e-3


def test_rank_multiple_tenders(mock_vendor_profile, sample_tender):
    service = PQCRecommendationService(vendor_profile=mock_vendor_profile)
    tenders = [
        sample_tender,
        {
            "tender_no": "GEM/2026/B/9999999",
            "tender_name": "Non-compliant High Value Tender",
            "organization": "UNKNOWN PRIVATE ENTITY",
            "tender_value": 500_000_000.0,
            "avg_annual_turnover_value": 500_000_000.0,  # Exceeds vendor turnover -> Disqualified
            "pbg_percentage": 25.0,  # Exceeds PBG cap -> Disqualified
            "outcome": "Lost"
        }
    ]
    result = service.rank_tenders(tenders, top_k=2, include_groq=False)
    assert "recommendations" in result
    assert len(result["recommendations"]) == 2
    assert result["recommendations"][0]["rank"] == 1
    assert result["recommendations"][1]["rank"] == 2
    # GAIL tender should rank higher than disqualified tender
    assert result["recommendations"][0]["tender_no"] == "GEM/2026/B/7306631"


def test_pydantic_schema_validation(mock_vendor_profile, sample_tender):
    service = PQCRecommendationService(vendor_profile=mock_vendor_profile)
    result = service.rank_tenders([sample_tender], top_k=1, include_groq=False)
    response_obj = PQCRecommendationResponse(**result)
    assert response_obj.total_scored == 1
    assert len(response_obj.recommendations) == 1
    assert response_obj.recommendations[0].rank == 1
    assert response_obj.weights_used["compliance"] == 0.35
