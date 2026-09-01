import pytest
import logging
from backend.app.services.compliance.regulatory import (
    RegulatoryComplianceService,
    VendorProfile,
    RuleStatus,
    ComplianceStatus,
)
from backend.app.schemas.schemas import ExtractedFieldSchema


@pytest.fixture
def service():
    return RegulatoryComplianceService()


@pytest.fixture
def default_vendor():
    return VendorProfile(
        annual_turnover=50_000_000.0,      # 5 Crore
        working_capital=10_000_000.0,      # 1 Crore
        years_of_experience=5,
        held_certifications=["ISO 9001", "BIS", "ISO 14001", "CE"],
        is_insolvent=False,
        is_bankrupt=False,
        is_blacklisted=False,
        is_mse_registered=True,
        mii_class="Class 1",
        max_pbg_tolerance_pct=10.0,
        max_bid_validity_tolerance_days=180,
        min_bid_validity_days=180
    )


# =============================================================================
# 1. MIN_ANNUAL_TURNOVER RULE TESTS (ALL 5 OUTCOMES)
# =============================================================================

def test_turnover_normal_pass(service, default_vendor):
    fields = {
        "avg_annual_turnover_value_display": ExtractedFieldSchema(
            field_name="avg_annual_turnover_value_display",
            value="₹20,00,000.00",
            confidence=0.95,
            source_page=1,
            evidence="Annual Turnover: Rs 20 Lakhs",
            source_blocks=[]
        ),
        "avg_annual_turnover_type_display": "INR"
    }
    res = service.check_min_annual_turnover("GEM/TEST/001", fields, default_vendor)
    assert res.status == RuleStatus.QUALIFIED
    assert res.passed is True


def test_turnover_normal_disqualify(service, default_vendor, caplog):
    fields = {
        "avg_annual_turnover_value_display": ExtractedFieldSchema(
            field_name="avg_annual_turnover_value_display",
            value="₹10,00,00,000.00",  # 10 Crore (Vendor only has 5 Crore)
            confidence=0.98,
            source_page=1,
            evidence="Min Turnover Rs 1000 Lakhs",
            source_blocks=[]
        ),
        "avg_annual_turnover_type_display": "INR"
    }
    with caplog.at_level(logging.WARNING):
        res = service.check_min_annual_turnover("GEM/TEST/002", fields, default_vendor)
    assert res.status == RuleStatus.DISQUALIFIED
    assert res.passed is False
    assert "[HARD_FILTER_DISQUALIFIED]" in caplog.text
    assert "GEM/TEST/002" in caplog.text
    assert "MIN_ANNUAL_TURNOVER" in caplog.text


def test_turnover_exempt_pass_section_2_5(service, default_vendor):
    """Section 2.5: 'Not Applicable' paired type display must PASS without false numeric disqualification."""
    fields = {
        "avg_annual_turnover_value_display": ExtractedFieldSchema(
            field_name="avg_annual_turnover_value_display",
            value="₹0.00",  # Placeholder stub from BEC exemption rule
            confidence=0.99,  # High confidence extraction of exemption
            source_page=2,
            evidence="Financial Criteria: Not Applicable",
            source_blocks=[]
        ),
        "avg_annual_turnover_type_display": ExtractedFieldSchema(
            field_name="avg_annual_turnover_type_display",
            value="Not Applicable",
            confidence=0.99,
            source_page=2,
            evidence="Financial Criteria: Not Applicable",
            source_blocks=[]
        )
    }
    res = service.check_min_annual_turnover("GEM/TEST/003", fields, default_vendor)
    assert res.status == RuleStatus.EXEMPT
    assert res.passed is True
    assert "Not Applicable / Exempt" in res.reason


def test_turnover_ambiguous_preserved_needs_review(service, default_vendor):
    """Section 2.5: Ambiguous composite dict must route to NEEDS_REVIEW, never crash or compare dict."""
    fields = {
        "avg_annual_turnover_value_display": ExtractedFieldSchema(
            field_name="avg_annual_turnover_value_display",
            value={"main_tender": "₹50,00,000", "atc": "₹1,00,00,000"},
            confidence=0.90,
            source="ambiguous_preserved",
            source_page=1,
            evidence="Conflicting turnover clauses in main doc vs ATC",
            source_blocks=[]
        )
    }
    res = service.check_min_annual_turnover("GEM/TEST/004", fields, default_vendor)
    assert res.status == RuleStatus.NEEDS_REVIEW
    assert res.passed is True
    assert "Unresolved multi-source document conflict" in res.reason


def test_turnover_low_confidence_needs_review(service, default_vendor):
    """Confidence < 0.85 must route to NEEDS_REVIEW."""
    fields = {
        "avg_annual_turnover_value_display": ExtractedFieldSchema(
            field_name="avg_annual_turnover_value_display",
            value="₹80,00,000.00",
            confidence=0.62,  # Scanned degradation below 0.85
            source_page=1,
            evidence="turnover blurry table",
            source_blocks=[]
        )
    }
    res = service.check_min_annual_turnover("GEM/TEST/005", fields, default_vendor)
    assert res.status == RuleStatus.NEEDS_REVIEW
    assert "Low extraction confidence" in res.reason


# =============================================================================
# 2. MAX_PBG_PERCENTAGE RULE TESTS (ALL 5 OUTCOMES)
# =============================================================================

def test_pbg_normal_pass(service, default_vendor):
    fields = {
        "pbg_percentage": ExtractedFieldSchema(
            field_name="pbg_percentage",
            value=5.0,
            confidence=0.95,
            source_page=1,
            evidence="ePBG Percentage 5.00%",
            source_blocks=[]
        )
    }
    res = service.check_max_pbg_percentage("GEM/TEST/PBG1", fields, default_vendor)
    assert res.status == RuleStatus.QUALIFIED
    assert res.passed is True


def test_pbg_normal_disqualify(service, default_vendor, caplog):
    fields = {
        "pbg_percentage": ExtractedFieldSchema(
            field_name="pbg_percentage",
            value=15.0,  # Exceeds max tolerance 10.0%
            confidence=0.92,
            source_page=1,
            evidence="ePBG Percentage 15.00%",
            source_blocks=[]
        )
    }
    with caplog.at_level(logging.WARNING):
        res = service.check_max_pbg_percentage("GEM/TEST/PBG2", fields, default_vendor)
    assert res.status == RuleStatus.DISQUALIFIED
    assert res.passed is False
    assert "[HARD_FILTER_DISQUALIFIED]" in caplog.text
    assert "MAX_PBG_PERCENTAGE" in caplog.text


def test_pbg_exempt_pass(service, default_vendor):
    fields = {
        "pbg_required": "No",
        "pbg_percentage": ExtractedFieldSchema(
            field_name="pbg_percentage",
            value="0.0",
            confidence=1.0,
            source_page=1,
            evidence="ePBG Required: No",
            source_blocks=[]
        )
    }
    res = service.check_max_pbg_percentage("GEM/TEST/PBG3", fields, default_vendor)
    assert res.status == RuleStatus.EXEMPT
    assert res.passed is True


def test_pbg_ambiguous_preserved_needs_review(service, default_vendor):
    fields = {
        "pbg_percentage": ExtractedFieldSchema(
            field_name="pbg_percentage",
            value={"main_tender": 3.0, "atc": 10.0},
            confidence=0.88,
            source="ambiguous_preserved",
            source_page=1,
            evidence="PBG discrepancy",
            source_blocks=[]
        )
    }
    res = service.check_max_pbg_percentage("GEM/TEST/PBG4", fields, default_vendor)
    assert res.status == RuleStatus.NEEDS_REVIEW
    assert "Unresolved multi-source document conflict" in res.reason


def test_pbg_low_confidence_needs_review(service, default_vendor):
    fields = {
        "pbg_percentage": ExtractedFieldSchema(
            field_name="pbg_percentage",
            value="5.0",
            confidence=0.50,  # Below 0.85
            source_page=1,
            evidence="blurry PBG",
            source_blocks=[]
        )
    }
    res = service.check_max_pbg_percentage("GEM/TEST/PBG5", fields, default_vendor)
    assert res.status == RuleStatus.NEEDS_REVIEW
    assert "Low extraction confidence" in res.reason


# =============================================================================
# 3. MIN_BID_VALIDITY RULE TESTS (ALL 5 OUTCOMES)
# =============================================================================

def test_bid_validity_normal_pass(service, default_vendor):
    # Short validity (e.g. 15 or 120 days <= 180 days) is favorable and QUALIFIED
    fields = {
        "bid_validity_days": ExtractedFieldSchema(
            field_name="bid_validity_days",
            value="120 (Days)",
            confidence=0.99,
            source_page=1,
            evidence="Bid Validity: 120",
            source_blocks=[]
        )
    }
    res = service.check_min_bid_validity_days("GEM/TEST/BV1", fields, default_vendor)
    assert res.status == RuleStatus.QUALIFIED
    assert res.passed is True


def test_bid_validity_short_favorable_pass(service, default_vendor):
    # Demanding short validity (e.g. 3, 16, 20 days) is favorable to vendor -> QUALIFIED
    fields = {
        "bid_validity_days": ExtractedFieldSchema(
            field_name="bid_validity_days",
            value=15,
            confidence=0.95,
            source_page=1,
            evidence="Bid Validity: 15 Days",
            source_blocks=[]
        )
    }
    res = service.check_min_bid_validity_days("GEM/TEST/BV1_SHORT", fields, default_vendor)
    assert res.status == RuleStatus.QUALIFIED
    assert res.passed is True


def test_bid_validity_normal_disqualify(service, default_vendor, caplog):
    # Exceeding vendor tolerance ceiling (e.g. 240 days > 180 days) -> DISQUALIFIED
    fields = {
        "bid_validity_days": ExtractedFieldSchema(
            field_name="bid_validity_days",
            value=240,  # Vendor max tolerance ceiling is 180 days
            confidence=0.95,
            source_page=1,
            evidence="Bid Validity: 240 Days",
            source_blocks=[]
        )
    }
    with caplog.at_level(logging.WARNING):
        res = service.check_min_bid_validity_days("GEM/TEST/BV2", fields, default_vendor)
    assert res.status == RuleStatus.DISQUALIFIED
    assert res.passed is False
    assert "[HARD_FILTER_DISQUALIFIED]" in caplog.text
    assert "MIN_BID_VALIDITY" in caplog.text


def test_bid_validity_ocr_boundary_needs_review(service, default_vendor):
    # Concatenated OCR table noise (> 365 days) -> NEEDS_REVIEW
    fields = {
        "bid_validity_days": ExtractedFieldSchema(
            field_name="bid_validity_days",
            value="151152116",  # OCR noise exceeding 365
            confidence=0.95,
            source_page=1,
            evidence="Bid Validity: 151152116",
            source_blocks=[]
        )
    }
    res = service.check_min_bid_validity_days("GEM/TEST/BV_OCR_ERR", fields, default_vendor)
    assert res.status == RuleStatus.NEEDS_REVIEW
    assert res.passed is True
    assert "exceeds physical 365-day year boundary" in res.reason


def test_bid_validity_ambiguous_preserved_needs_review(service, default_vendor):
    fields = {
        "bid_validity_days": ExtractedFieldSchema(
            field_name="bid_validity_days",
            value={"main_tender": 90, "atc": 180},
            confidence=0.88,
            source="ambiguous_preserved",
            source_page=1,
            evidence="Bid validity clash",
            source_blocks=[]
        )
    }
    res = service.check_min_bid_validity_days("GEM/TEST/BV3", fields, default_vendor)
    assert res.status == RuleStatus.NEEDS_REVIEW


def test_bid_validity_low_confidence_needs_review(service, default_vendor):
    fields = {
        "bid_validity_days": ExtractedFieldSchema(
            field_name="bid_validity_days",
            value="90",
            confidence=0.45,  # Scanned low confidence
            source_page=1,
            evidence="blurry validity",
            source_blocks=[]
        )
    }
    res = service.check_min_bid_validity_days("GEM/TEST/BV4", fields, default_vendor)
    assert res.status == RuleStatus.NEEDS_REVIEW


# =============================================================================
# 4. REQUIRED_CERTIFICATIONS & SOLVENCY TESTS
# =============================================================================

def test_certifications_pass_and_disqualify(service, default_vendor, caplog):
    # Pass when holding ISO 9001
    fields_pass = {
        "required_documents": ExtractedFieldSchema(
            field_name="required_documents",
            value="Bidder must submit ISO 9001 and BIS certificate",
            confidence=0.95,
            source_page=3,
            evidence="Certification list",
            source_blocks=[]
        )
    }
    res_pass = service.check_required_certifications("GEM/TEST/CERT1", fields_pass, default_vendor)
    assert res_pass.status == RuleStatus.QUALIFIED

    # Disqualify when requiring CMMI (not in default vendor profile)
    fields_fail = {
        "required_documents": ExtractedFieldSchema(
            field_name="required_documents",
            value="Mandatory CMMI Level 5 and ISO 9001",
            confidence=0.95,
            source_page=3,
            evidence="Certification list",
            source_blocks=[]
        )
    }
    with caplog.at_level(logging.WARNING):
        res_fail = service.check_required_certifications("GEM/TEST/CERT2", fields_fail, default_vendor)
    assert res_fail.status == RuleStatus.DISQUALIFIED
    assert "CMMI" in res_fail.reason
    assert "[HARD_FILTER_DISQUALIFIED]" in caplog.text


def test_insolvency_disqualification(service, default_vendor, caplog):
    insolvent_vendor = VendorProfile(is_insolvent=True)
    with caplog.at_level(logging.WARNING):
        res = service.check_insolvency_bankruptcy("GEM/TEST/INS1", {}, insolvent_vendor)
    assert res.status == RuleStatus.DISQUALIFIED
    assert res.passed is False
    assert "[HARD_FILTER_DISQUALIFIED]" in caplog.text
    assert "INSOLVENCY_BANKRUPTCY" in caplog.text


# =============================================================================
# 5. AGGREGATED EVALUATION PIPELINE TEST
# =============================================================================

def test_evaluate_compliance_aggregation(service, default_vendor):
    # Tender with 1 exempt field, 1 low confidence field, and valid parameters
    extracted = [
        ExtractedFieldSchema(
            field_name="avg_annual_turnover_value_display",
            value="₹0.00",
            confidence=0.99,
            source_page=1,
            evidence="BEC NA",
            source_blocks=[]
        ),
        ExtractedFieldSchema(
            field_name="avg_annual_turnover_type_display",
            value="Not Applicable",
            confidence=0.99,
            source_page=1,
            evidence="BEC NA",
            source_blocks=[]
        ),
        ExtractedFieldSchema(
            field_name="bid_validity_days",
            value="90",
            confidence=0.95,
            source_page=1,
            evidence="Validity 90",
            source_blocks=[]
        ),
        ExtractedFieldSchema(
            field_name="pbg_percentage",
            value=3.0,
            confidence=0.90,
            source_page=1,
            evidence="PBG 3%",
            source_blocks=[]
        ),
        ExtractedFieldSchema(
            field_name="working_capital_value_display",
            value="₹10,00,000",
            confidence=0.60,  # Low confidence triggers review
            source_page=1,
            evidence="Low conf working capital",
            source_blocks=[]
        )
    ]

    resp = service.evaluate_compliance("GEM/2026/B/TESTAGG", extracted, default_vendor)
    assert resp.overall_status == ComplianceStatus.NEEDS_REVIEW
    assert resp.is_disqualified is False
    assert resp.requires_human_review is True
    assert len(resp.review_reasons) >= 1
    assert resp.evaluated_rules_count == 8


def test_evaluate_compliance_all_qualified(service, default_vendor):
    """Proves F_hard passes a fully extracted, fully compliant tender to QUALIFIED (pre-classifier gate pass)."""
    fully_compliant_fields = [
        ExtractedFieldSchema(
            field_name="avg_annual_turnover_value_display",
            value="₹25,00,000.00",
            confidence=0.95,
            source_page=1,
            evidence="Annual Turnover 25L",
            source_blocks=[]
        ),
        ExtractedFieldSchema(
            field_name="avg_annual_turnover_type_display",
            value="INR",
            confidence=0.95,
            source_page=1,
            evidence="Turnover type",
            source_blocks=[]
        ),
        ExtractedFieldSchema(
            field_name="working_capital_value_display",
            value="₹5,00,000.00",
            confidence=0.92,
            source_page=1,
            evidence="Working Capital 5L",
            source_blocks=[]
        ),
        ExtractedFieldSchema(
            field_name="experience_criteria_years",
            value="3 Years",
            confidence=0.95,
            source_page=1,
            evidence="3 years experience required",
            source_blocks=[]
        ),
        ExtractedFieldSchema(
            field_name="pbg_percentage",
            value=3.0,
            confidence=0.90,
            source_page=1,
            evidence="PBG 3%",
            source_blocks=[]
        ),
        ExtractedFieldSchema(
            field_name="bid_validity_days",
            value="90",
            confidence=0.98,
            source_page=1,
            evidence="Bid Validity 90 days",
            source_blocks=[]
        ),
        ExtractedFieldSchema(
            field_name="required_documents",
            value="ISO 9001 and BIS certificates required",
            confidence=0.95,
            source_page=1,
            evidence="Certifications",
            source_blocks=[]
        ),
        ExtractedFieldSchema(
            field_name="mii_purchase_preference",
            value="Preference given to Class 1 and Class 2 Local Suppliers",
            confidence=0.90,
            source_page=1,
            evidence="MII Clause",
            source_blocks=[]
        )
    ]

    resp = service.evaluate_compliance("GEM/2026/B/FULLY_QUALIFIED", fully_compliant_fields, default_vendor)
    assert resp.overall_status == ComplianceStatus.QUALIFIED
    assert resp.is_disqualified is False
    assert resp.requires_human_review is False
    assert len(resp.disqualification_reasons) == 0
    assert len(resp.review_reasons) == 0
    assert resp.evaluated_rules_count == 8
    assert all(r.status in (RuleStatus.QUALIFIED, RuleStatus.EXEMPT) for r in resp.rule_results)


def test_unconstrained_buyer_optional_rules_auto_qualify(service, default_vendor, caplog):
    """
    Explicit test for unconstrained auto-qualify path:
    When a buyer omits optional clauses (turnover, working capital, PBG, experience),
    the rules must evaluate to QUALIFIED and emit [HARD_FILTER_UNCONSTRAINED] logs.
    """
    unconstrained_tender = [
        ExtractedFieldSchema(
            field_name="bid_validity_days",
            value="90",
            confidence=0.98,
            source_page=1,
            evidence="Validity 90",
            source_blocks=[]
        )
    ]
    with caplog.at_level(logging.INFO):
        resp = service.evaluate_compliance("GEM/2026/B/UNCONSTRAINED_TENDER", unconstrained_tender, default_vendor)

    assert resp.overall_status == ComplianceStatus.QUALIFIED
    assert resp.is_disqualified is False
    assert resp.requires_human_review is False
    assert "[HARD_FILTER_UNCONSTRAINED]" in caplog.text
    assert "MIN_ANNUAL_TURNOVER" in caplog.text


def test_blank_field_in_found_section_routes_to_needs_review(service, default_vendor):
    """
    Differentiates section-not-found vs blank field in found section:
    If a section was detected in the document but its value is empty/blank,
    it must route to NEEDS_REVIEW (not auto-qualify).
    """
    found_section_with_blank_field = {
        "bid_validity_days": "90",
        # Turnover section exists in document, but value is blank/unextracted
        "avg_annual_turnover_value_display": ExtractedFieldSchema(
            field_name="avg_annual_turnover_value_display",
            value="",  # Blank field within found section
            confidence=0.90,
            source_page=1,
            evidence="Turnover row found but empty",
            source_blocks=[]
        )
    }
    resp = service.evaluate_compliance("GEM/2026/B/BLANK_SECTION", found_section_with_blank_field, default_vendor)
    assert resp.overall_status == ComplianceStatus.NEEDS_REVIEW
    assert any("blank or unextracted" in r for r in resp.review_reasons)


def test_five_corrected_bid_validity_tenders(service):
    """
    Verifies that the 5 previously affected tenders now resolve correctly
    under the corrected MIN_BID_VALIDITY tolerance ceiling:
    - 7591613 (3 days): QUALIFIED
    - 6442619 (20 days): QUALIFIED
    - 7021103 (16 days): QUALIFIED
    - 6887044 (358 days): QUALIFIED under 365d tolerance
    - 7041307 (151152116 days): NEEDS_REVIEW (unbounded OCR noise)
    """
    profile = VendorProfile.from_yaml()  # Loads max_bid_validity_tolerance_days=365
    
    # 1. 7591613 (3 days)
    resp_1 = service.evaluate_compliance("GEM/2026/B/7591613", {"bid_validity_days": "3"}, profile)
    assert resp_1.overall_status == ComplianceStatus.QUALIFIED
    
    # 2. 6442619 (20 days)
    resp_2 = service.evaluate_compliance("GEM/2025/B/6442619", {"bid_validity_days": "20"}, profile)
    assert resp_2.overall_status == ComplianceStatus.QUALIFIED
    
    # 3. 7021103 (16 days)
    resp_3 = service.evaluate_compliance("GEM/2025/B/7021103", {"bid_validity_days": "16"}, profile)
    assert resp_3.overall_status == ComplianceStatus.QUALIFIED
    
    # 4. 6887044 (358 days <= 365)
    resp_4 = service.evaluate_compliance("GEM/2025/B/6887044", {"bid_validity_days": "358"}, profile)
    assert resp_4.overall_status == ComplianceStatus.QUALIFIED
    
    # 5. 7041307 (151152116 days > 365)
    resp_5 = service.evaluate_compliance("GEM/2025/B/7041307", {"bid_validity_days": "151152116"}, profile)
    assert resp_5.overall_status == ComplianceStatus.NEEDS_REVIEW
    assert any("exceeds physical 365-day year boundary" in r for r in resp_5.review_reasons)


def test_mse_turnover_experience_exemption_pass(service, default_vendor):
    """
    Verifies that an MSME registered vendor passes turnover & experience rules
    when the buyer grants MSE turnover/experience relaxation in the tender.
    """
    # Vendor turnover is 20.88 Cr, buyer demands 50 Cr turnover + 10 yrs experience,
    # but tender has MSE relaxation = Yes
    field_map = {
        "avg_annual_turnover_value_display": "500000000.0",  # ₹50 Cr (> 20.88 Cr)
        "experience_criteria_years": "10",                  # 10 yrs (> 5 yrs)
        "mse_relaxation_experience_turnover": "Yes"
    }
    
    turnover_res = service.check_min_annual_turnover("GEM/2025/B/MSE_EXEMPT", field_map, default_vendor)
    assert turnover_res.passed is True
    assert turnover_res.status == RuleStatus.QUALIFIED
    assert "MSE turnover exemption" in turnover_res.reason

    exp_res = service.check_min_experience_years("GEM/2025/B/MSE_EXEMPT", field_map, default_vendor)
    assert exp_res.passed is True
    assert exp_res.status == RuleStatus.QUALIFIED
    assert "MSE experience exemption" in exp_res.reason
