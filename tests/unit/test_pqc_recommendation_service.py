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
    assert service.weights["claude"] == 0.15
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


def test_claude_fallback_safety(mock_vendor_profile, sample_tender):
    # Test that Claude gracefully defaults to 0.50 on failure or offline
    service = PQCRecommendationService(
        vendor_profile=mock_vendor_profile,
        anthropic_api_key="invalid_test_key"
    )
    fit, rationale = service.evaluate_claude_strategic_fit(
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


def test_claude_mocked_success(mock_vendor_profile, sample_tender):
    from unittest.mock import MagicMock, patch
    service = PQCRecommendationService(
        vendor_profile=mock_vendor_profile,
        anthropic_api_key="sk-ant-mock-key"
    )
    mock_content_block = MagicMock()
    mock_content_block.text = '{"strategic_fit": 0.88, "strategic_rationale": "Strong strategic fit for HT panel manufacturing."}'
    mock_msg = MagicMock()
    mock_msg.content = [mock_content_block]

    with patch("anthropic.Anthropic") as MockAnthropic:
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_msg
        MockAnthropic.return_value = mock_client

        fit, rationale = service.evaluate_claude_strategic_fit(
            tender_no=sample_tender["tender_no"],
            tender_name=sample_tender["tender_name"],
            organization=sample_tender["organization"],
            tender_value=sample_tender["tender_value"],
            compliance_status="QUALIFIED",
            ml_win_prob=0.65,
            similar_tenders=[]
        )
        assert fit == 0.88
        assert "Strong strategic fit" in rationale


def test_score_single_tender(mock_vendor_profile, sample_tender):
    service = PQCRecommendationService(vendor_profile=mock_vendor_profile)
    scored = service.score_single_tender(sample_tender, include_claude=False)
    
    assert "tender_no" in scored
    assert "composite_score" in scored
    assert "score_decomposition" in scored
    
    decomp = scored["score_decomposition"]
    expected_composite = round(
        0.35 * decomp["compliance_score"] +
        0.35 * decomp["similarity_score"] +
        0.15 * decomp["ml_win_prob"] +
        0.15 * decomp["claude_fit_score"],
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
    result = service.rank_tenders(tenders, top_k=2, include_claude=False)
    assert "recommendations" in result
    assert len(result["recommendations"]) == 2
    assert result["recommendations"][0]["rank"] == 1
    assert result["recommendations"][1]["rank"] == 2
    # GAIL tender should rank higher than disqualified tender
    assert result["recommendations"][0]["tender_no"] == "GEM/2026/B/7306631"


def test_pydantic_schema_validation(mock_vendor_profile, sample_tender):
    service = PQCRecommendationService(vendor_profile=mock_vendor_profile)
    result = service.rank_tenders([sample_tender], top_k=1, include_claude=False)
    response_obj = PQCRecommendationResponse(**result)
    assert response_obj.total_scored == 1
    assert len(response_obj.recommendations) == 1
    assert response_obj.recommendations[0].rank == 1
    assert response_obj.weights_used["compliance"] == 0.35
    assert response_obj.weights_used["claude"] == 0.15


def test_nan_title_serialization_fallback_to_tender_no(mock_vendor_profile):
    """
    Regression Test: Ensures a DataFrame row with a NaN title resolves to tender_no,
    and never leaks the literal string 'nan' into the serialized response.
    """
    import numpy as np
    import pandas as pd
    from backend.app.schemas.pqc_recommendation import resolve_tender_title

    service = PQCRecommendationService(vendor_profile=mock_vendor_profile)
    df_row = pd.DataFrame([{
        "tender_no": "GEM/2026/B/7317018",
        "tender_name": np.nan,
        "organization": "GAIL (India) Limited",
        "tender_value": 5000000.0
    }]).iloc[0].to_dict()

    scored = service.score_single_tender(df_row, include_claude=False)
    assert scored["tender_name"] == "GEM/2026/B/7317018"
    assert scored["tender_name"] != "nan"

    result = service.rank_tenders([df_row], top_k=1, include_claude=False)
    response_obj = PQCRecommendationResponse(**result)
    raw_json = response_obj.model_dump_json(indent=2)
    
    assert response_obj.recommendations[0].tender_name == "GEM/2026/B/7317018"
    assert '"nan"' not in raw_json
    assert 'NaN' not in raw_json


def test_nan_title_serialization_fallback_to_untitled(mock_vendor_profile):
    """
    Regression Test: Ensures that if both tender_name and tender_no are NaN/missing,
    the title falls back strictly to 'Untitled Tender', not 'nan' or 'Not specified'.
    """
    import numpy as np
    import pandas as pd

    service = PQCRecommendationService(vendor_profile=mock_vendor_profile)
    df_row = pd.DataFrame([{
        "tender_no": np.nan,
        "tender_name": np.nan,
        "organization": np.nan,
        "tender_value": np.nan
    }]).iloc[0].to_dict()

    scored = service.score_single_tender(df_row, include_claude=False)
    assert scored["tender_name"] == "Untitled Tender"
    assert scored["tender_name"] != "nan"
    assert scored["tender_name"] != "Not specified"

    result = service.rank_tenders([df_row], top_k=1, include_claude=False)
    response_obj = PQCRecommendationResponse(**result)
    raw_json = response_obj.model_dump_json(indent=2)
    
    assert response_obj.recommendations[0].tender_name == "Untitled Tender"
    assert response_obj.recommendations[0].organization == "Unknown Authority"
    assert response_obj.recommendations[0].tender_value == 0.0
    assert '"nan"' not in raw_json
    assert 'NaN' not in raw_json


def test_claude_cache_hit_and_staleness(mock_vendor_profile, sample_tender, tmp_path):
    from unittest.mock import MagicMock, patch
    cache_file = tmp_path / "test_fit_cache.sqlite3"
    service = PQCRecommendationService(
        vendor_profile=mock_vendor_profile,
        anthropic_api_key="sk-ant-mock-key",
        cache_db_path=cache_file
    )

    mock_content = MagicMock()
    mock_content.text = '{"strategic_fit": 0.85, "strategic_rationale": "First run score."}'
    mock_msg = MagicMock()
    mock_msg.content = [mock_content]

    with patch("anthropic.Anthropic") as MockAnthropic:
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_msg
        MockAnthropic.return_value = mock_client

        # Call 1: Cache miss -> calls API
        fit1, rat1 = service.evaluate_claude_strategic_fit(
            tender_no=sample_tender["tender_no"],
            tender_name=sample_tender["tender_name"],
            organization=sample_tender["organization"],
            tender_value=sample_tender["tender_value"],
            compliance_status="QUALIFIED",
            ml_win_prob=0.65,
            similar_tenders=[]
        )
        assert fit1 == 0.85
        assert mock_client.messages.create.call_count == 1

        # Call 2: Identical payload -> Cache hit (0 API calls!)
        fit2, rat2 = service.evaluate_claude_strategic_fit(
            tender_no=sample_tender["tender_no"],
            tender_name=sample_tender["tender_name"],
            organization=sample_tender["organization"],
            tender_value=sample_tender["tender_value"],
            compliance_status="QUALIFIED",
            ml_win_prob=0.65,
            similar_tenders=[]
        )
        assert fit2 == 0.85
        assert rat2 == rat1
        # Call count remains 1!
        assert mock_client.messages.create.call_count == 1

        # Call 3: Modified value -> Staleness detected (hash mismatch) -> Calls API
        mock_content.text = '{"strategic_fit": 0.72, "strategic_rationale": "Updated value score."}'
        fit3, rat3 = service.evaluate_claude_strategic_fit(
            tender_no=sample_tender["tender_no"],
            tender_name=sample_tender["tender_name"],
            organization=sample_tender["organization"],
            tender_value=sample_tender["tender_value"] + 5000000.0,
            compliance_status="QUALIFIED",
            ml_win_prob=0.65,
            similar_tenders=[]
        )
        assert fit3 == 0.72
        assert mock_client.messages.create.call_count == 2


def test_claude_is_override_bypasses_cache_read_and_write(mock_vendor_profile, sample_tender, tmp_path):
    from unittest.mock import MagicMock, patch
    from backend.app.services.claude_fit_cache import ClaudeFitCache
    cache_file = tmp_path / "test_override_cache.sqlite3"
    service = PQCRecommendationService(
        vendor_profile=mock_vendor_profile,
        anthropic_api_key="sk-ant-mock-key",
        cache_db_path=cache_file
    )

    # Pre-seed persistent cache with baseline 0.60
    base_hash = ClaudeFitCache.compute_payload_hash(
        tender_no=sample_tender["tender_no"],
        tender_name=sample_tender["tender_name"],
        organization=sample_tender["organization"],
        tender_value=sample_tender["tender_value"],
        compliance_status="QUALIFIED",
        ml_win_prob=0.65,
        similar_tenders=[]
    )
    service.cache.set(
        tender_no=sample_tender["tender_no"],
        data_hash=base_hash,
        strategic_fit=0.60,
        strategic_rationale="Persisted ground truth baseline."
    )

    # Run with is_override=True and mock returning 0.95
    mock_content = MagicMock()
    mock_content.text = '{"strategic_fit": 0.95, "strategic_rationale": "What-if simulation fit."}'
    mock_msg = MagicMock()
    mock_msg.content = [mock_content]

    with patch("anthropic.Anthropic") as MockAnthropic:
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_msg
        MockAnthropic.return_value = mock_client

        fit, rat = service.evaluate_claude_strategic_fit(
            tender_no=sample_tender["tender_no"],
            tender_name=sample_tender["tender_name"],
            organization=sample_tender["organization"],
            tender_value=sample_tender["tender_value"],
            compliance_status="QUALIFIED",
            ml_win_prob=0.65,
            similar_tenders=[],
            is_override=True
        )

        # 1. Bypassed cache read: returned live 0.95 instead of cached 0.60
        assert fit == 0.95
        assert "What-if" in rat
        assert mock_client.messages.create.call_count == 1

        # 2. Bypassed cache write: persistent cache MUST still store original 0.60
        cached_entry = service.cache.get(sample_tender["tender_no"], base_hash)
        assert cached_entry is not None
        assert cached_entry[0] == 0.60
        assert cached_entry[1] == "Persisted ground truth baseline."


def test_claude_short_circuit_disqualified(mock_vendor_profile):
    from unittest.mock import patch
    service = PQCRecommendationService(vendor_profile=mock_vendor_profile)

    disqualified_tender = {
        "tender_no": "GEM/2026/B/8888888",
        "tender_name": "Disqualified High Turnover Tender",
        "organization": "GAIL",
        "tender_value": 100_000_000.0,
        "avg_annual_turnover_value": 500_000_000.0,  # Exceeds vendor turnover -> Disqualified
        "pbg_percentage": 25.0,  # Exceeds cap
    }

    with patch.object(service, "evaluate_claude_strategic_fit") as mock_eval:
        scored = service.score_single_tender(disqualified_tender, include_claude=True)
        assert scored["score_decomposition"]["compliance_status"] == "DISQUALIFIED"
        assert scored["score_decomposition"]["claude_fit_score"] == 0.0
        assert "Skipped Claude enrichment: Disqualified" in scored["strategic_rationale"]
        # Claude API was completely short-circuited!
        assert mock_eval.call_count == 0


def test_claude_short_circuit_zero_value(mock_vendor_profile):
    from unittest.mock import patch
    service = PQCRecommendationService(vendor_profile=mock_vendor_profile)

    zero_val_tender = {
        "tender_no": "GEM/2026/B/7777777",
        "tender_name": "Zero Value Incomplete Tender",
        "organization": "GAIL",
        "tender_value": 0.0,
    }

    with patch.object(service, "evaluate_claude_strategic_fit") as mock_eval:
        scored = service.score_single_tender(zero_val_tender, include_claude=True)
        assert scored["score_decomposition"]["claude_fit_score"] == 0.50
        assert "CANNOT_EVALUATE" in scored["strategic_rationale"]
        # Claude API was completely short-circuited!
        assert mock_eval.call_count == 0


def test_claude_retry_backoff_on_transient_failure(mock_vendor_profile, sample_tender, tmp_path):
    from unittest.mock import MagicMock, patch
    service = PQCRecommendationService(
        vendor_profile=mock_vendor_profile,
        anthropic_api_key="sk-ant-mock-key",
        cache_db_path=tmp_path / "test_retry.sqlite3"
    )

    mock_content = MagicMock()
    mock_content.text = '{"strategic_fit": 0.81, "strategic_rationale": "Recovered after retry."}'
    mock_success_msg = MagicMock()
    mock_success_msg.content = [mock_content]

    with patch("anthropic.Anthropic") as MockAnthropic:
        mock_client = MagicMock()
        # Attempt 0 fails with transient error, Attempt 1 succeeds
        mock_client.messages.create.side_effect = [
            RuntimeError("Transient 503 Service Unavailable"),
            mock_success_msg
        ]
        MockAnthropic.return_value = mock_client

        with patch("time.sleep") as mock_sleep:
            fit, rat = service.evaluate_claude_strategic_fit(
                tender_no=sample_tender["tender_no"],
                tender_name=sample_tender["tender_name"],
                organization=sample_tender["organization"],
                tender_value=sample_tender["tender_value"],
                compliance_status="QUALIFIED",
                ml_win_prob=0.65,
                similar_tenders=[]
            )

            assert fit == 0.81
            assert "Recovered" in rat
            assert mock_client.messages.create.call_count == 2
            # Verify exponential backoff delay of 1.0s was called
            mock_sleep.assert_called_with(1.0)

