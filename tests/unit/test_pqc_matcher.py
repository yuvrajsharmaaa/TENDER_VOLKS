from datetime import date, timedelta
import pytest

from backend.app.services.pqr_credential_matcher import (
    CandidateCredential,
    PqcMatchResult,
    compute_thresholds,
    is_within_window,
    has_valid_document,
    normalize_scope,
    match_credentials,
)


def test_compute_thresholds():
    tv = 10_000_000.0  # 1 Crore
    thresholds = compute_thresholds(tv)
    assert thresholds["eighty_pct"] == 8_000_000.0
    assert thresholds["fifty_pct"] == 5_000_000.0
    assert thresholds["forty_pct"] == 4_000_000.0
    assert thresholds["threshold_80"] == 8_000_000.0


def test_is_within_window():
    deadline = date(2026, 9, 15)

    # 3 years ago -> within window
    assert is_within_window(date(2023, 5, 10), deadline, years=7) is True

    # Exactly 6.9 years ago -> within window
    assert is_within_window(date(2019, 10, 1), deadline, years=7) is True

    # 8 years ago -> outside window
    assert is_within_window(date(2018, 1, 1), deadline, years=7) is False

    # Future date relative to deadline -> outside window
    assert is_within_window(date(2026, 10, 1), deadline, years=7) is False

    # None / Missing -> False
    assert is_within_window(None, deadline, years=7) is False

    # String date parsing
    assert is_within_window("2024-03-20", "2026-09-15", years=7) is True
    assert is_within_window("2015-01-01", "2026-09-15", years=7) is False


def test_has_valid_document():
    # Valid documents
    assert has_valid_document({"po": "pqr-po/123.pdf", "completion": None}) is True
    assert has_valid_document({"completion": "pqr-completion/abc.pdf"}) is True

    # Invalid / empty documents
    assert has_valid_document({}) is False
    assert has_valid_document(None) is False
    assert has_valid_document({"po": None, "completion": "", "perf": "nan"}) is False
    assert has_valid_document({"po": "none", "completion": "[]", "perf": "null"}) is False


def test_normalize_scope_clusters():
    # Ni-Cd Batteries
    assert normalize_scope("NI-CD") == "NICD_BATTERY"
    assert normalize_scope("NICD Battery Bank") == "NICD_BATTERY"
    assert normalize_scope("NI CD BATTERY BANK") == "NICD_BATTERY"
    assert normalize_scope("NICAD") == "NICD_BATTERY"

    # VRLA Batteries
    assert normalize_scope("VRLA") == "VRLA_BATTERY"
    assert normalize_scope("SMF Battery Bank") == "VRLA_BATTERY"
    assert normalize_scope("Sealed Maintenance Free Battery") == "VRLA_BATTERY"

    # VRF Air Conditioning
    assert normalize_scope("VRF WITH AHU & TFA") == "VRF_AC"
    assert normalize_scope("VRV System") == "VRF_AC"

    # General AC Units
    assert normalize_scope("Supply and installation of Ductable AC units") == "AC_UNIT"
    assert normalize_scope("Split AC") == "AC_UNIT"
    assert normalize_scope("Package AC Unit") == "AC_UNIT"
    assert normalize_scope("Chiller Plant") == "AC_UNIT"
    assert normalize_scope("SAC") == "AC_UNIT"
    assert normalize_scope("Air Conditioner Units") == "AC_UNIT"

    # Ceiling Fans
    assert normalize_scope("Ceiling Fan procurement") == "CEILING_FAN"
    assert normalize_scope("Ventilation Fans") == "CEILING_FAN"

    # AMC Services
    assert normalize_scope("Annual Maintenance Contract for HVAC") == "AMC_SERVICE"
    assert normalize_scope("Comprehensive AMC") == "AMC_SERVICE"

    # Solar Systems
    assert normalize_scope("Roof Top Grid SPV Solar Power Plant") == "SOLAR_SYSTEM"
    assert normalize_scope("Solar Power System") == "SOLAR_SYSTEM"

    # Unmatched fallback
    assert normalize_scope("General Civil Construction") == "OTHER"


def test_single_80_percent_qualification():
    deadline = date(2026, 9, 15)
    candidates = [
        CandidateCredential(
            id=1,
            project_name="GAIL Hazira Battery Installation",
            value=8_500_000.0,
            item="NICD",
            item_category="NICD_BATTERY",
            completion_date=date(2024, 6, 1),
            document_paths={"po": "pqr-po/1.pdf"},
        ),
        CandidateCredential(
            id=2,
            project_name="IOCL Panipat Battery Supply",
            value=4_500_000.0,
            item="NICD",
            item_category="NICD_BATTERY",
            completion_date=date(2023, 4, 1),
            document_paths={"completion": "pqr-completion/2.pdf"},
        ),
    ]

    result = match_credentials(
        tender_value=10_000_000.0,  # 80% = 8,000,000
        tender_scope_text="Supply of Ni-Cd Battery Bank",
        tender_deadline=deadline,
        candidates=candidates,
        is_msme=True,
        msme_relaxation_applicable=False,
    )

    assert result.qualifies is True
    assert result.strategy == "1x80%"
    assert len(result.matched_credentials) == 1
    assert result.matched_credentials[0].id == 1
    assert "satisfies the 80% single-work criterion" in result.rationale


def test_pair_50_percent_qualification():
    deadline = date(2026, 9, 15)
    candidates = [
        CandidateCredential(
            id=1,
            project_name="AAI Surat Ductable AC",
            value=6_000_000.0,  # Below 80% (8M), but >= 50% (5M)
            item="Ductable AC",
            item_category="AC_UNIT",
            completion_date=date(2024, 2, 1),
            document_paths={"po": "pqr-po/10.pdf"},
        ),
        CandidateCredential(
            id=2,
            project_name="NTPC Dadri Split AC",
            value=5_500_000.0,  # >= 50% (5M)
            item="Split AC",
            item_category="AC_UNIT",
            completion_date=date(2023, 8, 1),
            document_paths={"completion": "pqr-completion/20.pdf"},
        ),
        CandidateCredential(
            id=3,
            project_name="Small AC Repair",
            value=1_000_000.0,
            item="Window AC",
            item_category="AC_UNIT",
            completion_date=date(2025, 1, 1),
            document_paths={"performance": "pqr-perf/30.pdf"},
        ),
    ]

    result = match_credentials(
        tender_value=10_000_000.0,  # 50% = 5,000,000
        tender_scope_text="Supply and installation of Central/Ductable AC",
        tender_deadline=deadline,
        candidates=candidates,
        is_msme=True,
        msme_relaxation_applicable=False,
    )

    assert result.qualifies is True
    assert result.strategy == "2x50%"
    assert len(result.matched_credentials) == 2
    matched_ids = [c.id for c in result.matched_credentials]
    assert matched_ids == [1, 2]
    assert "individually satisfy the 50% criterion" in result.rationale


def test_triplet_40_percent_qualification():
    deadline = date(2026, 9, 15)
    candidates = [
        CandidateCredential(
            id=1,
            project_name="VRLA Bank Project 1",
            value=4_500_000.0,  # >= 40% (4M)
            item="VRLA",
            item_category="VRLA_BATTERY",
            completion_date=date(2024, 1, 1),
            document_paths={"po": "pqr-po/1.pdf"},
        ),
        CandidateCredential(
            id=2,
            project_name="VRLA Bank Project 2",
            value=4_200_000.0,  # >= 40% (4M)
            item="VRLA",
            item_category="VRLA_BATTERY",
            completion_date=date(2023, 5, 1),
            document_paths={"completion": "pqr-completion/2.pdf"},
        ),
        CandidateCredential(
            id=3,
            project_name="VRLA Bank Project 3",
            value=4_100_000.0,  # >= 40% (4M)
            item="SMF",
            item_category="VRLA_BATTERY",
            completion_date=date(2022, 11, 1),
            document_paths={"performance": "pqr-perf/3.pdf"},
        ),
    ]

    result = match_credentials(
        tender_value=10_000_000.0,  # 40% = 4,000,000
        tender_scope_text="Procurement of VRLA Battery Banks",
        tender_deadline=deadline,
        candidates=candidates,
        is_msme=True,
        msme_relaxation_applicable=False,
    )

    assert result.qualifies is True
    assert result.strategy == "3x40%"
    assert len(result.matched_credentials) == 3
    assert "each individually satisfy the 40% criterion" in result.rationale


def test_msme_relaxation_qualification():
    deadline = date(2026, 9, 15)
    candidates = [
        CandidateCredential(
            id=1,
            project_name="Moderate Ceiling Fan Order",
            value=2_000_000.0,  # 20 Lakhs: below 40% (4M), but clears 15% floor (1.5M)
            item="Ceiling Fan",
            item_category="CEILING_FAN",
            completion_date=date(2024, 3, 1),
            document_paths={"po": "pqr-po/fan.pdf"},
        )
    ]

    result = match_credentials(
        tender_value=10_000_000.0,
        tender_scope_text="Supply of Energy Efficient Ceiling Fans",
        tender_deadline=deadline,
        candidates=candidates,
        is_msme=True,
        msme_relaxation_applicable=True,  # Buyer grants MSME experience relaxation
    )

    assert result.qualifies is True
    assert result.strategy == "MSME_RELAXED"
    assert len(result.matched_credentials) == 1
    assert "vendor qualifies under MSME relaxation" in result.rationale
    assert "satisfies the 15% MSME floor criterion" in result.rationale


def test_msme_relaxation_floor_rejection_for_trivially_small_order():
    deadline = date(2026, 9, 15)
    candidates = [
        CandidateCredential(
            id=1,
            project_name="Tiny Ceiling Fan Order",
            value=200_000.0,  # 2 Lakhs on a 1 Crore tender (only 2% of tender value)
            item="Ceiling Fan",
            item_category="CEILING_FAN",
            completion_date=date(2024, 3, 1),
            document_paths={"po": "pqr-po/fan.pdf"},
        )
    ]

    result = match_credentials(
        tender_value=10_000_000.0,  # 15% floor is 15 Lakhs (1.5M)
        tender_scope_text="Supply of Energy Efficient Ceiling Fans",
        tender_deadline=deadline,
        candidates=candidates,
        is_msme=True,
        msme_relaxation_applicable=True,
    )

    # Disqualified because the past order falls below the mandatory 15% MSME floor
    assert result.qualifies is False
    assert result.strategy == "NO_MATCH"
    assert "falls below the required 15% MSME floor" in result.rationale



def test_no_match_returns_closest_candidates():
    deadline = date(2026, 9, 15)
    candidates = [
        CandidateCredential(
            id=1,
            project_name="Ceiling Fan Order A",
            value=1_500_000.0,  # 15 Lakhs
            item="Ceiling Fan",
            item_category="CEILING_FAN",
            completion_date=date(2024, 1, 1),
            document_paths={"po": "pqr-po/1.pdf"},
        ),
        CandidateCredential(
            id=2,
            project_name="Ceiling Fan Order B",
            value=1_200_000.0,  # 12 Lakhs
            item="Ceiling Fan",
            item_category="CEILING_FAN",
            completion_date=date(2023, 6, 1),
            document_paths={"completion": "pqr-completion/2.pdf"},
        ),
    ]

    result = match_credentials(
        tender_value=10_000_000.0,  # 40% is 4M, neither reaches 4M
        tender_scope_text="Ceiling Fans for Railway Stations",
        tender_deadline=deadline,
        candidates=candidates,
        is_msme=False,  # Not MSME or no relaxation
        msme_relaxation_applicable=False,
    )

    assert result.qualifies is False
    assert result.strategy == "NO_MATCH"
    assert len(result.matched_credentials) == 2  # Returns closest candidates
    assert len(result.closest_candidates) == 2
    assert "No credentials met the 80%" in result.rationale
    assert "Closest candidate was 'Ceiling Fan Order A'" in result.rationale


def test_seven_year_cutoff_disqualification():
    deadline = date(2026, 9, 15)
    candidates = [
        CandidateCredential(
            id=1,
            project_name="Ancient High-Value Order",
            value=9_000_000.0,  # Huge value >= 80%
            item="NICD",
            item_category="NICD_BATTERY",
            completion_date=date(2017, 1, 1),  # Completed > 9 years ago!
            document_paths={"po": "pqr-po/old.pdf"},
        )
    ]

    result = match_credentials(
        tender_value=10_000_000.0,
        tender_scope_text="Ni-Cd Battery Tender",
        tender_deadline=deadline,
        candidates=candidates,
        is_msme=False,
        msme_relaxation_applicable=False,
    )

    # Disqualified due to exceeding 7-year window
    assert result.qualifies is False
    assert result.strategy == "NO_MATCH"


def test_missing_document_disqualification():
    deadline = date(2026, 9, 15)
    candidates = [
        CandidateCredential(
            id=1,
            project_name="Order without Verified Documents",
            value=9_000_000.0,  # Huge value >= 80%
            item="NICD",
            item_category="NICD_BATTERY",
            completion_date=date(2024, 1, 1),
            document_paths={"po": None, "completion": "", "performance": "null"},  # No valid document!
        )
    ]

    result = match_credentials(
        tender_value=10_000_000.0,
        tender_scope_text="Ni-Cd Battery Tender",
        tender_deadline=deadline,
        candidates=candidates,
        is_msme=False,
        msme_relaxation_applicable=False,
    )

    # Disqualified due to lack of linked documents
    assert result.qualifies is False
    assert result.strategy == "NO_MATCH"


def test_scope_mismatch_filtering():
    deadline = date(2026, 9, 15)
    candidates = [
        CandidateCredential(
            id=1,
            project_name="Large AC Unit Order",
            value=9_000_000.0,  # 90 Lakhs
            item="Ductable AC",
            item_category="AC_UNIT",
            completion_date=date(2024, 1, 1),
            document_paths={"po": "pqr-po/ac.pdf"},
        )
    ]

    # Tender is for Battery Bank, candidate is AC Unit
    result = match_credentials(
        tender_value=10_000_000.0,
        tender_scope_text="Supply of Ni-Cd Battery Bank",
        tender_deadline=deadline,
        candidates=candidates,
        is_msme=False,
        msme_relaxation_applicable=False,
    )

    assert result.qualifies is False
    assert result.strategy == "NO_MATCH"


def test_plain_dictionary_input_tolerance():
    deadline = "2026-09-15"
    raw_candidates = [
        {
            "id": 101,
            "project_name": "VRF System Project",
            "value": 8_500_000.0,
            "item": "VRF",
            "item_category": "VRF_AC",
            "completion_date": "2024-05-10",
            "po_document": "pqr-po/101.pdf",
            "sap_gem_po_document": None,
            "completion_document": None,
            "performance_certificate": None,
        }
    ]

    result = match_credentials(
        tender_value=10_000_000.0,
        tender_scope_text="VRF Air Conditioning System",
        tender_deadline=deadline,
        candidates=raw_candidates,
    )

    assert result.qualifies is True
    assert result.strategy == "1x80%"
    assert result.matched_credentials[0].id == 101
    assert result.to_dict()["strategy"] == "1x80%"
