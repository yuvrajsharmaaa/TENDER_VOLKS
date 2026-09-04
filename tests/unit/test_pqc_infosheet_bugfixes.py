import math
import numpy as np
import pytest
from unittest.mock import patch, MagicMock

from backend.app.services.normalizer import parse_money, derive_presence_flag
from backend.app.services.pqc_recommendation_service import PQCRecommendationService
from backend.app.services.tender_mapper import map_internal_to_db_payload, build_infosheet_data, FIELD_STATUS_OK_FALLBACK


def test_parse_money_cr_word_boundary():
    """Bug 11: Ensure words with 'cr' like credit/criteria don't trigger crore multiplier."""
    # "credit" should not be treated as "crore"
    val = parse_money("5 credit terms")
    assert val == 5.0

    val2 = parse_money("Criteria 10 units")
    assert val2 == 10.0

    # Explicit 'cr' or 'crore' as word should trigger crore multiplier
    val_cr = parse_money("Rs. 2 cr")
    assert val_cr == 20000000.0

    val_crore = parse_money("Rs. 1.5 crore")
    assert val_crore == 15000000.0

    val_lakh = parse_money("Rs. 5 lakh")
    assert val_lakh == 500000.0


def test_derive_presence_flag_zeros():
    """Ensure zero/empty values return 'No'."""
    assert derive_presence_flag(0) == "No"
    assert derive_presence_flag(0.0) == "No"
    assert derive_presence_flag("0") == "No"
    assert derive_presence_flag("0.0") == "No"
    assert derive_presence_flag("0.00") == "No"
    assert derive_presence_flag("₹0.00") == "No"
    assert derive_presence_flag("Nil") == "No"
    assert derive_presence_flag(None) == "No"
    assert derive_presence_flag("") == "No"
    assert derive_presence_flag("Not Found") == "No"
    assert derive_presence_flag(False) == "No"

    assert derive_presence_flag(100) == "Yes"
    assert derive_presence_flag(5.0) == "Yes"
    assert derive_presence_flag("5000") == "Yes"
    assert derive_presence_flag(True) == "Yes"


def test_map_internal_to_db_payload_zero_amounts():
    """Ensure zero amounts for EMD, Fee, PBG, SD map to 'No' instead of false positive 'Yes'."""
    data = {
        "tender_value": 500000.0,
        "emd_amount": 0.0,
        "fee_amount": 0.0,
        "processing_fee_amount": 0.0,
        "pbg_pct": 0.0,
        "sd_pct": 0.0,
        "max_ld_pct": 0.0,
        "custom_rules": None,
        "maf_req_raw": None,
        "courier_address": None
    }
    payload = map_internal_to_db_payload(data, tender_id=123)
    assert payload["emd_required"] == "No"
    assert payload["tender_fee_required"] == "No"
    assert payload["processing_fee_required"] == "No"
    assert payload["pbg_required"] == "No"
    assert payload["sd_required"] == "No"
    assert payload["ld_required"] == "No"


def test_pqc_feature_vector_nan_resilience():
    """Bug 1: Ensure NaN or string 'nan' inputs do not contaminate feature dataframe."""
    service = PQCRecommendationService()
    row_with_nans = {
        "tender_value": float("nan"),
        "estimated_cost": float("nan"),
        "emd_amount": float("nan"),
        "avg_annual_turnover_value": float("nan"),
        "pbg_percentage": float("nan"),
        "pbg_duration": float("nan"),
        "max_ld_percentage": float("nan"),
        "delivery_time_supply": float("nan"),
        "delivery_time_supply_days": float("nan"),
        "bid_validity_days": float("nan"),
        "organization": None
    }
    feat_df = service.engineer_single_feature_vector(row_with_nans)
    assert not feat_df.isna().any().any(), f"NaN found in feature dataframe:\n{feat_df.isna().sum()}"
    assert feat_df["pbg_duration_months"].iloc[0] == 0.0
    assert feat_df["max_ld_cap_percent"].iloc[0] == 0.0
    assert feat_df["delivery_time_supply_days"].iloc[0] == 0.0
    assert feat_df["bid_validity_days_bounded"].iloc[0] == 90.0


def test_pqc_claude_rate_limit_updates_remaining_candidates():
    """Bug 3: Ensure Claude 429 rate limit correctly updates all remaining candidates in target_indices."""
    service = PQCRecommendationService(anthropic_api_key="test_key")
    tenders = [
        {"tender_no": f"T{i}", "tender_name": f"Tender {i}", "organization": "IOCL", "tender_value": 1000000.0}
        for i in range(5)
    ]

    # Mock evaluate_claude_strategic_fit: returns 0.90 for first tender, then "RATE_LIMIT_429" for second
    mock_responses = [
        (0.90, "Strong fit"),
        (0.50, "RATE_LIMIT_429")
    ]
    with patch.object(service, "evaluate_claude_strategic_fit", side_effect=mock_responses) as mock_fit:
        result = service.rank_tenders(tenders, top_k=5, include_claude=True, claude_top_n=5)
        recs = result["recommendations"]
        assert len(recs) == 5

        # First candidate should have received 0.90
        assert recs[0]["score_decomposition"]["claude_fit_score"] == 0.90
        assert recs[0]["strategic_rationale"] == "Strong fit"

        # Subsequent candidates must have been updated to neutral 0.50 with rate limit rationale
        for r in recs[1:]:
            assert r["score_decomposition"]["claude_fit_score"] == 0.50
            assert "rate limit" in r["strategic_rationale"].lower()


def test_infosheet_delivery_time_sanity_bounds():
    """Bug 5: Ensure delivery times below 7 days are discarded as misparses while valid numbers pass."""
    # Under 7 days (misparsed clause number) -> Flagged as MISSING in infosheet
    text_invalid = "Delivery Period: 2 Days for submission of clarifications"
    res_invalid = build_infosheet_data([], page_texts=[{"text": text_invalid}])
    assert res_invalid["delivery_time_supply_display"] == "⚠️ MISSING"

    # Valid 50 days (previously hardcoded excluded) -> Should now be preserved
    text_valid_50 = "Delivery Period: 50 Days from order placement"
    res_valid_50 = build_infosheet_data([], page_texts=[{"text": text_valid_50}])
    assert res_valid_50["delivery_time_supply_display"] == "50 Days"


def test_infosheet_bounded_fallback_status():
    """Bug 7 & 8: Verify evaluate_bounded_fallback assigns pay_fb_meta and c2_fb_meta."""
    sections = []
    text_with_payment_only_in_body = (
        "Some clause text\n"
        "Terms of supply: 80% on receipt\n"
        "Nodal officer: Shri A. K. Sharma, General Manager\n"
    )
    res = build_infosheet_data(sections, page_texts=[{"text": text_with_payment_only_in_body}])
    statuses = res.get("_info_sheet_statuses", {})
    assert "payment_terms_supply_display" in statuses
    assert "client_name_2_display" in statuses
