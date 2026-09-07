"""
Unit tests for Anthropic Usage API Reconciliation Script (reconcile_usage.py)
"""

import os
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch
import pytest

from scripts.reconcile_usage import (
    reconcile,
    collect_internal_usage,
    fetch_anthropic_usage_report,
    MIN_FRESHNESS_LAG_MINUTES,
    DEFAULT_TOLERANCE_PCT,
)


def test_reconcile_freshness_lag_guard():
    """
    Verify requirement: Windows ending less than 10 minutes ago must be rejected
    to respect Anthropic's documented 5-minute data freshness aggregation latency.
    """
    now = datetime.now(timezone.utc)
    recent_end = (now - timedelta(minutes=5)).isoformat()
    start = (now - timedelta(hours=2)).isoformat()

    # Must exit with code 2 (guard rejection)
    code = reconcile(start_str=start, end_str=recent_end)
    assert code == 2


def test_reconcile_missing_admin_key_returns_unverified(monkeypatch):
    """
    Verify requirement: If ANTHROPIC_ADMIN_KEY is not set, explicitly return
    code 2 (NOT YET VERIFIED) rather than mocking a fake pass.
    """
    monkeypatch.delenv("ANTHROPIC_ADMIN_KEY", raising=False)

    now = datetime.now(timezone.utc)
    safe_end = (now - timedelta(minutes=15)).isoformat()
    start = (now - timedelta(hours=2)).isoformat()

    code = reconcile(start_str=start, end_str=safe_end)
    assert code == 2


def test_reconcile_calculation_and_discrepancy_detection(tmp_path, monkeypatch):
    """
    Verify requirement:
    - Sum uncached_in + cached_in + cache_create + out.
    - Check side-by-side delta.
    - Flag deltas > 2.0% as DISCREPANCY DETECTED without averaging away.
    """
    monkeypatch.setenv("ANTHROPIC_ADMIN_KEY", "sk-ant-admin-test-mock-key")

    now = datetime.now(timezone.utc)
    safe_end = (now - timedelta(minutes=15)).isoformat()
    start = (now - timedelta(hours=2)).isoformat()

    # Mock internal collected usage (Haiku: 10,000 tokens; Sonnet: 5,000 tokens)
    mock_internal = {
        "claude-haiku-4-5-20251001": {
            "uncached_input_tokens": 6000,
            "cached_input_tokens": 1000,
            "cache_creation_input_tokens": 1000,
            "output_tokens": 2000,
            "total_tokens": 10000,
        },
        "claude-sonnet-5": {
            "uncached_input_tokens": 3000,
            "cached_input_tokens": 500,
            "cache_creation_input_tokens": 500,
            "output_tokens": 1000,
            "total_tokens": 5000,
        },
    }

    # Case 1: Anthropic API returns matching tokens within 2% tolerance
    mock_api_match = {
        "claude-haiku-4-5-20251001": {
            "uncached_input_tokens": 6050,  # +0.8% delta
            "cached_input_tokens": 1000,
            "cache_creation_input_tokens": 1000,
            "output_tokens": 2000,
            "total_tokens": 10050,
        },
        "claude-sonnet-5": {
            "uncached_input_tokens": 3020,  # +0.6% delta
            "cached_input_tokens": 500,
            "cache_creation_input_tokens": 500,
            "output_tokens": 1000,
            "total_tokens": 5020,
        },
    }

    with patch("scripts.reconcile_usage.collect_internal_usage", return_value=(mock_internal, 5)):
        with patch("scripts.reconcile_usage.fetch_anthropic_usage_report", return_value=mock_api_match):
            report_file = tmp_path / "report_match.json"
            exit_code = reconcile(start_str=start, end_str=safe_end, tolerance_pct=2.0, output_path=str(report_file))
            assert exit_code == 0  # Reconciled within tolerance

    # Case 2: Anthropic API returns discrepant tokens (> 2.0% delta)
    mock_api_discrepant = {
        "claude-haiku-4-5-20251001": {
            "uncached_input_tokens": 8000,  # 25% discrepancy!
            "cached_input_tokens": 1000,
            "cache_creation_input_tokens": 1000,
            "output_tokens": 2000,
            "total_tokens": 12000,
        },
        "claude-sonnet-5": {
            "uncached_input_tokens": 3000,
            "cached_input_tokens": 500,
            "cache_creation_input_tokens": 500,
            "output_tokens": 1000,
            "total_tokens": 5000,
        },
    }

    with patch("scripts.reconcile_usage.collect_internal_usage", return_value=(mock_internal, 5)):
        with patch("scripts.reconcile_usage.fetch_anthropic_usage_report", return_value=mock_api_discrepant):
            report_file = tmp_path / "report_discrepancy.json"
            exit_code = reconcile(start_str=start, end_str=safe_end, tolerance_pct=2.0, output_path=str(report_file))
            assert exit_code == 1  # Discrepancy flagged
