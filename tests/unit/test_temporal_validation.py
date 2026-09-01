import pytest
import numpy as np
import pandas as pd
from scripts.train_predictive_engine import (
    wilson_ci,
    sanitize_and_engineer_features,
    run_temporal_validation
)


def test_wilson_ci_computation():
    # 0 wins out of 10
    low, high = wilson_ci(0, 10)
    assert low == 0.0
    assert high > 0.0

    # 32 wins out of 165
    low_32, high_32 = wilson_ci(32, 165)
    assert 0.13 < low_32 < 0.16
    assert 0.24 < high_32 < 0.28

    # 100% wins
    low_100, high_100 = wilson_ci(50, 50)
    assert low_100 > 0.90
    assert high_100 == 1.0


def test_numeric_sanitization_and_imputation_flag():
    profile = {
        "company_name": "VOLKS ENERGIE PRIVATE LIMITED",
        "avg_annual_turnover": 208886000.0,
        "latest_net_worth": 43642000.0,
        "msme_registered": True,
        "incumbent_psu_list": ["IOCL", "AAI", "GAIL", "HPCL"]
    }

    mock_df = pd.DataFrame([
        {
            "tender_no": "GEM/2025/B/VALID1",
            "organization": "GAIL",
            "department": None,
            "client": None,
            "publish_date": "2025-01-01",
            "bid_submission_end_date": "2025-01-15",
            "extraction_timestamp": "2025-01-01",
            "tender_value": "5000000.0",  # Valid ₹50 Lakhs
            "estimated_cost": None,
            "bid_validity_days": "90",
            "emd_amount": "100000.0",
            "avg_annual_turnover_value": "10000000.0",
            "pbg_percentage": "5.0",
            "pbg_duration": "12",
            "max_ld_percentage": "10.0",
            "delivery_time_supply": "30",
            "maf_required": "No",
            "reverse_auction_applicable": "No",
            "mse_purchase_preference": "Yes",
            "mii_purchase_preference": "Yes",
            "is_won": 1,
            "outcome": "Won"
        },
        {
            "tender_no": "GEM/2025/B/CORRUPTED_HAL",
            "organization": "HAL",
            "department": None,
            "client": None,
            "publish_date": "2025-02-01",
            "bid_submission_end_date": "2025-02-15",
            "extraction_timestamp": "2025-02-01",
            "tender_value": "123456789012.0",  # 12-digit SAP code > 100 Cr
            "estimated_cost": None,
            "bid_validity_days": "151152116",  # Unbounded OCR noise
            "emd_amount": "5000000000.0",      # Exceeds 10 Cr
            "avg_annual_turnover_value": "0.0",
            "pbg_percentage": "0.0",
            "pbg_duration": "0",
            "max_ld_percentage": "0.0",
            "delivery_time_supply": "0",
            "maf_required": "No",
            "reverse_auction_applicable": "No",
            "mse_purchase_preference": "No",
            "mii_purchase_preference": "No",
            "is_won": 0,
            "outcome": "Lost"
        }
    ])

    df_out, feature_cols = sanitize_and_engineer_features(mock_df, profile)

    # Check tender 1 (Valid)
    row_1 = df_out.iloc[0]
    assert bool(row_1['tender_value_imputed']) is False
    assert row_1['clean_tender_value'] == 5000000.0
    assert row_1['bid_validity_days_bounded'] == 90.0
    assert row_1['is_incumbent_psu'] == 1  # GAIL is in incumbent_psu_list

    # Check tender 2 (Corrupted)
    row_2 = df_out.iloc[1]
    assert bool(row_2['tender_value_imputed']) is True
    assert row_2['clean_tender_value'] <= 1_000_000_000.0  # Bounded to clean median
    assert row_2['bid_validity_days_bounded'] <= 365.0      # Clipped to 365 max
    assert row_2['emd_amount_bounded'] <= 100_000_000.0    # Clipped to 10 Cr max


def test_leak_free_authority_win_rate():
    profile = {
        "company_name": "VOLKS ENERGIE PRIVATE LIMITED",
        "avg_annual_turnover": 208886000.0,
        "latest_net_worth": 43642000.0,
        "msme_registered": True,
        "incumbent_psu_list": ["IOCL"]
    }

    # Chronologically ordered sequence of 3 tenders for IOCL
    mock_seq = pd.DataFrame([
        {
            "tender_no": "T1", "organization": "IOCL", "department": None, "client": None,
            "publish_date": "2024-01-01", "bid_submission_end_date": "2024-01-15", "extraction_timestamp": "2024-01-01",
            "tender_value": "100000.0", "estimated_cost": None, "bid_validity_days": "90", "emd_amount": "0",
            "avg_annual_turnover_value": "0", "pbg_percentage": "0", "pbg_duration": "0", "max_ld_percentage": "0",
            "delivery_time_supply": "0", "maf_required": "No", "reverse_auction_applicable": "No",
            "mse_purchase_preference": "No", "mii_purchase_preference": "No", "is_won": 1, "outcome": "Won"
        },
        {
            "tender_no": "T2", "organization": "IOCL", "department": None, "client": None,
            "publish_date": "2024-06-01", "bid_submission_end_date": "2024-06-15", "extraction_timestamp": "2024-06-01",
            "tender_value": "100000.0", "estimated_cost": None, "bid_validity_days": "90", "emd_amount": "0",
            "avg_annual_turnover_value": "0", "pbg_percentage": "0", "pbg_duration": "0", "max_ld_percentage": "0",
            "delivery_time_supply": "0", "maf_required": "No", "reverse_auction_applicable": "No",
            "mse_purchase_preference": "No", "mii_purchase_preference": "No", "is_won": 0, "outcome": "Lost"
        },
        {
            "tender_no": "T3", "organization": "IOCL", "department": None, "client": None,
            "publish_date": "2025-01-01", "bid_submission_end_date": "2025-01-15", "extraction_timestamp": "2025-01-01",
            "tender_value": "100000.0", "estimated_cost": None, "bid_validity_days": "90", "emd_amount": "0",
            "avg_annual_turnover_value": "0", "pbg_percentage": "0", "pbg_duration": "0", "max_ld_percentage": "0",
            "delivery_time_supply": "0", "maf_required": "No", "reverse_auction_applicable": "No",
            "mse_purchase_preference": "No", "mii_purchase_preference": "No", "is_won": 1, "outcome": "Won"
        }
    ])

    df_res, _ = sanitize_and_engineer_features(mock_seq, profile)

    # T1: 0 prior tenders -> authority_win_rate = 0.0, incumbent_buyer_status = 0
    assert df_res.iloc[0]['authority_win_rate'] == 0.0
    assert df_res.iloc[0]['incumbent_buyer_status'] == 0

    # T2: 1 prior tender (Won) -> authority_win_rate = 1.0 (1/1), incumbent_buyer_status = 1
    assert df_res.iloc[1]['authority_win_rate'] == 1.0
    assert df_res.iloc[1]['incumbent_buyer_status'] == 1

    # T3: 2 prior tenders (1 Won, 1 Lost) -> authority_win_rate = 0.5 (1/2), incumbent_buyer_status = 1
    assert df_res.iloc[2]['authority_win_rate'] == 0.5
    assert df_res.iloc[2]['incumbent_buyer_status'] == 1
