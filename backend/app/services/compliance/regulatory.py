import logging
import re
from dataclasses import dataclass, field as dc_field
from enum import Enum
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field

from backend.app.schemas.schemas import ExtractedFieldSchema

logger = logging.getLogger("compliance.regulatory")


class RuleStatus(str, Enum):
    QUALIFIED = "QUALIFIED"
    DISQUALIFIED = "DISQUALIFIED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    EXEMPT = "EXEMPT"


class ComplianceStatus(str, Enum):
    QUALIFIED = "QUALIFIED"
    DISQUALIFIED = "DISQUALIFIED"
    NEEDS_REVIEW = "NEEDS_REVIEW"


from pathlib import Path
import yaml

@dataclass
class VendorProfile:
    """Authoritative vendor profile capabilities (not subject to confidence/ambiguity routing)."""
    annual_turnover: float = 208_886_000.0  # 20.88 Crore INR default from Volks company profile
    working_capital: float = 43_642_000.0   # 4.36 Crore INR default from Volks company profile
    years_of_experience: int = 10
    held_certifications: List[str] = dc_field(default_factory=lambda: ["ISO 9001", "BIS", "ISO 14001", "CE"])
    is_insolvent: bool = False
    is_bankrupt: bool = False
    is_blacklisted: bool = False
    is_mse_registered: bool = True
    mii_class: str = "Class 1"  # "Class 1", "Class 2", "Non-Local"
    max_pbg_tolerance_pct: float = 10.0  # Max acceptable PBG percentage
    max_bid_validity_tolerance_days: int = 365  # Max acceptable bid validity tolerance ceiling (Days)
    min_bid_validity_days: int = 365  # Backward compatibility alias

    @property
    def msme_registered(self) -> bool:
        return self.is_mse_registered

    @classmethod
    def from_yaml(cls, path: Optional[Union[str, Path]] = None) -> "VendorProfile":
        if path is None:
            # Locate config/company_profile.yaml in project root
            root_dir = Path(__file__).resolve().parent.parent.parent.parent.parent
            path = root_dir / "config" / "company_profile.yaml"
        p = Path(path)
        if not p.exists():
            return cls()
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            max_bv = int(data.get("max_bid_validity_tolerance_days", 365))
            return cls(
                annual_turnover=float(data.get("avg_annual_turnover", 208_886_000.0)),
                working_capital=float(data.get("latest_net_worth", 43_642_000.0)),
                years_of_experience=10,
                held_certifications=["ISO 9001", "BIS", "ISO 14001", "CE"],
                is_insolvent=False,
                is_bankrupt=False,
                is_blacklisted=False,
                is_mse_registered=bool(data.get("msme_registered", True)),
                mii_class="Class 1",
                max_pbg_tolerance_pct=float(data.get("max_pbg_tolerance_pct", 10.0)),
                max_bid_validity_tolerance_days=max_bv,
                min_bid_validity_days=max_bv
            )
        except Exception as e:
            logger.warning(f"Could not load vendor profile from {p}: {e}. Using defaults.")
            return cls()


class RuleResult(BaseModel):
    rule_name: str
    field_name: str
    status: RuleStatus
    passed: bool
    extracted_value: Any = None
    extracted_confidence: float = 1.0
    constraint_threshold: Any = None
    reason: str


class ComplianceEvaluationResponse(BaseModel):
    tender_no: str
    overall_status: ComplianceStatus
    is_disqualified: bool
    requires_human_review: bool
    disqualification_reasons: List[str] = Field(default_factory=list)
    review_reasons: List[str] = Field(default_factory=list)
    rule_results: List[RuleResult] = Field(default_factory=list)
    evaluated_rules_count: int = 0


class RegulatoryComplianceService:
    """
    Week 7 Hard Compliance Filter (F_hard).
    Deterministic pre-classifier gate evaluating statutory and commercial eligibility rules.
    """

    CONFIDENCE_THRESHOLD: float = 0.85
    EXEMPT_STRINGS: tuple = (
        "not applicable", "exempt", "na", "n/a", "nil", "none", "not required",
        "not applicable in tender bec", "financial criteria not applicable", "exempt / not applicable"
    )

    def __init__(self, default_profile: Optional[VendorProfile] = None):
        self.default_profile = default_profile or VendorProfile.from_yaml()

    # ─────────────────────────────────────────────────────────────────────────
    # Helper Utilities
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _parse_currency(val: Any) -> Optional[float]:
        """Extracts float number from currency/numeric strings like '₹50,00,000.00' or '5000000'."""
        if val is None:
            return None
        if isinstance(val, (int, float)):
            return float(val)
        cleaned = re.sub(r"[₹$,\sINRinr/]+", "", str(val)).strip()
        try:
            return float(cleaned)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _parse_numeric(val: Any) -> Optional[float]:
        """Extracts plain float/int from strings like '120 (Days)' or '5.00%'."""
        if val is None:
            return None
        if isinstance(val, (int, float)):
            return float(val)
        m = re.search(r"[-+]?\d*\.?\d+", str(val).replace(",", ""))
        if m:
            try:
                return float(m.group(0))
            except ValueError:
                pass
        return None

    @staticmethod
    def _parse_experience_years(val: Any) -> Optional[int]:
        """
        Robustly extracts experience years with sanity bounds (1 to 30 years).
        Prevents OCR table noise (e.g. 'LR date / RC (101/103') from parsing as 101 years.
        """
        if val is None:
            return None
        if isinstance(val, int) and 1 <= val <= 30:
            return val
        if isinstance(val, float) and 1.0 <= val <= 30.0:
            return int(val)
        s = str(val).strip().lower()
        # Look for explicit "X Year(s)" or "X Yrs"
        m = re.search(r"(\d{1,2})\s*(?:years?|yrs?|y\b)", s)
        if m:
            yrs = int(m.group(1))
            return yrs if 1 <= yrs <= 30 else None
        # Plain 1 or 2 digit number
        m2 = re.search(r"\b(\d{1,2})\b", s)
        if m2:
            yrs = int(m2.group(1))
            return yrs if 1 <= yrs <= 30 else None
        return None

    @staticmethod
    def _is_exempt(val: Any) -> bool:
        if val is None:
            return False
        s = str(val).strip().lower()
        return any(ex in s for ex in RegulatoryComplianceService.EXEMPT_STRINGS)

    def _lookup_field(self, field_map: Dict[str, Any], aliases: List[str]) -> Optional[Any]:
        for a in aliases:
            if a in field_map and field_map[a] is not None:
                return field_map[a]
            # Case-insensitive / normalized match
            a_norm = a.lower().replace("_", " ").strip()
            for k, v in field_map.items():
                k_norm = k.lower().replace("_display", "").replace("_", " ").strip()
                if (k.lower().replace("_", " ").strip() == a_norm or k_norm == a_norm) and v is not None:
                    return v
        return None

    # ─────────────────────────────────────────────────────────────────────────
    # Invariant Rule Evaluator Engine
    # ─────────────────────────────────────────────────────────────────────────

    def _evaluate_rule_invariants(
        self,
        tender_no: str,
        rule_name: str,
        field_name: str,
        field_obj: Optional[Union[ExtractedFieldSchema, Dict[str, Any], Any]],
        companion_type_obj: Optional[Union[ExtractedFieldSchema, Dict[str, Any], Any]] = None,
        is_buyer_optional: bool = False
    ) -> Optional[RuleResult]:
        """
        Executes Steps 1-3 of the Invariant Pipeline:
        1. Ambiguity Gate (`source == 'ambiguous_preserved'` or composite `dict`) -> NEEDS_REVIEW
        2. Missing / Confidence Gate:
           - If buyer-optional field is completely absent/omitted -> QUALIFIED (No constraint imposed)
           - If mandatory statutory field is missing -> NEEDS_REVIEW
           - If field is present but confidence < 0.85 -> NEEDS_REVIEW
        3. Exemption Gate (`_type_display == 'Not Applicable'`) -> EXEMPT / PASSED
        """
        # Unpack field object
        val = None
        conf = 0.0
        src = None

        if isinstance(field_obj, ExtractedFieldSchema):
            val = field_obj.value
            conf = float(field_obj.confidence)
            src = field_obj.source
        elif isinstance(field_obj, dict) and ("value" in field_obj or "confidence" in field_obj):
            val = field_obj.get("value")
            conf = float(field_obj.get("confidence", 1.0))
            src = field_obj.get("source")
        else:
            val = field_obj
            conf = 1.0 if field_obj is not None else 0.0
            src = None

        # Unpack companion type object
        companion_val = None
        if isinstance(companion_type_obj, ExtractedFieldSchema):
            companion_val = companion_type_obj.value
        elif isinstance(companion_type_obj, dict) and "value" in companion_type_obj:
            companion_val = companion_type_obj.get("value")
        else:
            companion_val = companion_type_obj

        # ── Step 1: Check Multi-Source Ambiguity Conflict ────────────────────
        if src == "ambiguous_preserved" or isinstance(val, dict):
            logger.info(
                "[HARD_FILTER_AMBIGUITY_DETECTED] Tender: %s | Rule: %s | Field: %s | Payload: %r",
                tender_no, rule_name, field_name, val
            )
            return RuleResult(
                rule_name=rule_name,
                field_name=field_name,
                status=RuleStatus.NEEDS_REVIEW,
                passed=True,
                extracted_value=val,
                extracted_confidence=conf,
                reason=f"Unresolved multi-source document conflict for field '{field_name}': main_tender vs atc"
            )

        # ── Step 2: Check Missing, Section-Absence, or Low-Confidence ───────
        # Case 2a: Section/field was completely omitted by buyer in the document
        # (Indicated by None field_obj, or stubbed unanchored field with evidence 'No matching values found')
        evidence_str = str(getattr(field_obj, "evidence", "") or "")
        is_unanchored_omission = (
            field_obj is None or 
            (val is None and (conf == 0.0 or "no matching values found" in evidence_str.lower()))
        )

        if is_unanchored_omission:
            if is_buyer_optional:
                logger.info(
                    "[HARD_FILTER_UNCONSTRAINED] Tender: %s | Rule: %s | Field: %s | Reason: No constraint mandated by buyer in tender",
                    tender_no, rule_name, field_name
                )
                return RuleResult(
                    rule_name=rule_name,
                    field_name=field_name,
                    status=RuleStatus.QUALIFIED,
                    passed=True,
                    extracted_value=None,
                    extracted_confidence=1.0,
                    reason=f"No constraint mandated by buyer for '{rule_name}' in this tender"
                )
            else:
                return RuleResult(
                    rule_name=rule_name,
                    field_name=field_name,
                    status=RuleStatus.NEEDS_REVIEW,
                    passed=True,
                    extracted_value=None,
                    extracted_confidence=0.0,
                    reason=f"Mandatory statutory field '{field_name}' is missing or unextracted for rule '{rule_name}'"
                )

        # Case 2b: Field/section was detected, but value was blank / unparsed
        if val is None or str(val).strip() in ("", "None", "Not Found", "NA", "Out of Scope (Stage 1)"):
            return RuleResult(
                rule_name=rule_name,
                field_name=field_name,
                status=RuleStatus.NEEDS_REVIEW,
                passed=True,
                extracted_value=val,
                extracted_confidence=conf,
                reason=f"Field '{field_name}' within found document section was blank or unextracted for rule '{rule_name}'"
            )

        # Case 2c: Low confidence extraction
        if conf < self.CONFIDENCE_THRESHOLD:
            return RuleResult(
                rule_name=rule_name,
                field_name=field_name,
                status=RuleStatus.NEEDS_REVIEW,
                passed=True,
                extracted_value=val,
                extracted_confidence=conf,
                reason=f"Low extraction confidence ({conf:.2f} < {self.CONFIDENCE_THRESHOLD:.2f}) for rule '{rule_name}' on field '{field_name}'"
            )

        # ── Step 3: Check Exemption Handling (Section 2.5 Sentinel State) ────
        if self._is_exempt(companion_val) or self._is_exempt(val):
            return RuleResult(
                rule_name=rule_name,
                field_name=field_name,
                status=RuleStatus.EXEMPT,
                passed=True,
                extracted_value=val,
                extracted_confidence=conf,
                reason=f"Criteria explicitly declared Not Applicable / Exempt in tender BEC"
            )

        return None

    def _emit_disqualification(
        self,
        tender_no: str,
        rule_name: str,
        field_name: str,
        extracted_val: Any,
        confidence: float,
        constraint_threshold: Any,
        reason: str
    ) -> RuleResult:
        """Emits standard structured audit log for disqualification and returns RuleResult."""
        logger.warning(
            "[HARD_FILTER_DISQUALIFIED] Tender: %s | Rule: %s | Field: %s | Extracted Value: %r | Extracted Confidence: %.2f | Constraint: %r | Reason: %s",
            tender_no, rule_name, field_name, extracted_val, confidence, constraint_threshold, reason
        )
        return RuleResult(
            rule_name=rule_name,
            field_name=field_name,
            status=RuleStatus.DISQUALIFIED,
            passed=False,
            extracted_value=extracted_val,
            extracted_confidence=confidence,
            constraint_threshold=constraint_threshold,
            reason=reason
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Individual F_hard Rules
    # ─────────────────────────────────────────────────────────────────────────

    def check_min_annual_turnover(
        self, tender_no: str, field_map: Dict[str, Any], vendor: VendorProfile
    ) -> RuleResult:
        """Rule: Bidder turnover must be >= Tender Minimum Required Turnover."""
        rule_name = "MIN_ANNUAL_TURNOVER"
        field_name = "avg_annual_turnover_value_display"
        field_obj = self._lookup_field(field_map, [
            "avg_annual_turnover_value_display", "annual_avg_turnover_value",
            "avg_annual_turnover", "annual_turnover", "turnover_value",
            "Bidder Turnover", "Minimum Average Annual Turnover"
        ])
        type_obj = self._lookup_field(field_map, [
            "avg_annual_turnover_type_display", "turnover_type", "annual_avg_turnover_type"
        ])

        inv = self._evaluate_rule_invariants(tender_no, rule_name, field_name, field_obj, type_obj, is_buyer_optional=True)
        if inv is not None:
            return inv

        val_raw = field_obj.value if isinstance(field_obj, ExtractedFieldSchema) else (field_obj.get("value") if isinstance(field_obj, dict) else field_obj)
        conf = field_obj.confidence if isinstance(field_obj, ExtractedFieldSchema) else (field_obj.get("confidence", 1.0) if isinstance(field_obj, dict) else 1.0)
        req_turnover = self._parse_currency(val_raw)

        if req_turnover is None or req_turnover <= 0.0:
            return RuleResult(
                rule_name=rule_name, field_name=field_name, status=RuleStatus.QUALIFIED,
                passed=True, extracted_value=val_raw, extracted_confidence=conf,
                reason="No positive turnover constraint imposed"
            )

        # Check MSE / Startup turnover exemption grant
        mse_exemption_obj = self._lookup_field(field_map, [
            "mse_relaxation_experience_turnover", "mse_exemption_turnover", "mse_relaxation",
            "mse_exemption_for_years_of_experience_and_turnover"
        ])
        if mse_exemption_obj and vendor.msme_registered:
            val_mse = str(mse_exemption_obj.value if isinstance(mse_exemption_obj, ExtractedFieldSchema) else (mse_exemption_obj.get("value") if isinstance(mse_exemption_obj, dict) else mse_exemption_obj)).strip().lower()
            if val_mse in ("yes", "true", "1", "applicable", "exempt"):
                logger.info(
                    f"[HARD_FILTER_UNCONSTRAINED] Tender: {tender_no} | Rule: {rule_name} | "
                    f"Field: mse_relaxation_experience_turnover | Reason: Vendor is MSME registered and tender grants MSE turnover exemption"
                )
                return RuleResult(
                    rule_name=rule_name, field_name=field_name, status=RuleStatus.QUALIFIED,
                    passed=True, extracted_value=val_raw, extracted_confidence=conf,
                    reason="MSE turnover exemption applicable for registered MSME vendor"
                )

        if vendor.annual_turnover < req_turnover:
            return self._emit_disqualification(
                tender_no=tender_no, rule_name=rule_name, field_name=field_name,
                extracted_val=val_raw, confidence=conf,
                constraint_threshold=f"Vendor Turnover >= ₹{req_turnover:,.2f}",
                reason=f"Vendor turnover of ₹{vendor.annual_turnover:,.2f} is below mandatory required minimum of ₹{req_turnover:,.2f}"
            )

        return RuleResult(
            rule_name=rule_name, field_name=field_name, status=RuleStatus.QUALIFIED,
            passed=True, extracted_value=val_raw, extracted_confidence=conf,
            constraint_threshold=f"Vendor Turnover >= ₹{req_turnover:,.2f}",
            reason="Turnover requirement satisfied"
        )

    def check_min_working_capital(
        self, tender_no: str, field_map: Dict[str, Any], vendor: VendorProfile
    ) -> RuleResult:
        """Rule: Bidder working capital must be >= Tender Minimum Working Capital."""
        rule_name = "MIN_WORKING_CAPITAL"
        field_name = "working_capital_value_display"
        field_obj = self._lookup_field(field_map, [
            "working_capital_value_display", "working_capital_value", "working_capital"
        ])
        type_obj = self._lookup_field(field_map, [
            "working_capital_type_display", "working_capital_type"
        ])

        inv = self._evaluate_rule_invariants(tender_no, rule_name, field_name, field_obj, type_obj, is_buyer_optional=True)
        if inv is not None:
            return inv

        val_raw = field_obj.value if isinstance(field_obj, ExtractedFieldSchema) else (field_obj.get("value") if isinstance(field_obj, dict) else field_obj)
        conf = field_obj.confidence if isinstance(field_obj, ExtractedFieldSchema) else (field_obj.get("confidence", 1.0) if isinstance(field_obj, dict) else 1.0)
        req_wc = self._parse_currency(val_raw)

        if req_wc is None or req_wc <= 0.0:
            return RuleResult(
                rule_name=rule_name, field_name=field_name, status=RuleStatus.QUALIFIED,
                passed=True, extracted_value=val_raw, extracted_confidence=conf,
                reason="No positive working capital constraint imposed"
            )

        if vendor.working_capital < req_wc:
            return self._emit_disqualification(
                tender_no=tender_no, rule_name=rule_name, field_name=field_name,
                extracted_val=val_raw, confidence=conf,
                constraint_threshold=f"Vendor Working Capital >= ₹{req_wc:,.2f}",
                reason=f"Vendor working capital of ₹{vendor.working_capital:,.2f} is below mandatory minimum of ₹{req_wc:,.2f}"
            )

        return RuleResult(
            rule_name=rule_name, field_name=field_name, status=RuleStatus.QUALIFIED,
            passed=True, extracted_value=val_raw, extracted_confidence=conf,
            constraint_threshold=f"Vendor Working Capital >= ₹{req_wc:,.2f}",
            reason="Working capital requirement satisfied"
        )

    def check_min_experience_years(
        self, tender_no: str, field_map: Dict[str, Any], vendor: VendorProfile
    ) -> RuleResult:
        """Rule: Bidder years of past experience must be >= required criteria."""
        rule_name = "MIN_EXPERIENCE_YEARS"
        field_name = "experience_criteria_years"
        field_obj = self._lookup_field(field_map, [
            "experience_criteria_years", "eligibility_criterion_years",
            "experience_criteria", "past_experience_years", "Experience Criteria",
            "years_of_past_experience"
        ])
        type_obj = self._lookup_field(field_map, [
            "experience_criteria_type_display", "eligibility_criterion_type"
        ])

        inv = self._evaluate_rule_invariants(tender_no, rule_name, field_name, field_obj, type_obj, is_buyer_optional=True)
        if inv is not None:
            return inv

        val_raw = field_obj.value if isinstance(field_obj, ExtractedFieldSchema) else (field_obj.get("value") if isinstance(field_obj, dict) else field_obj)
        conf = field_obj.confidence if isinstance(field_obj, ExtractedFieldSchema) else (field_obj.get("confidence", 1.0) if isinstance(field_obj, dict) else 1.0)
        req_years = self._parse_experience_years(val_raw)

        if req_years is None:
            # Unparseable string (OCR noise or non-standard format) -> route to review
            return RuleResult(
                rule_name=rule_name, field_name=field_name, status=RuleStatus.NEEDS_REVIEW,
                passed=True, extracted_value=val_raw, extracted_confidence=conf,
                reason=f"Could not parse numeric years from '{val_raw}'"
            )

        # Check MSE / Startup experience exemption grant
        mse_exemption_obj = self._lookup_field(field_map, [
            "mse_relaxation_experience_turnover", "mse_exemption_turnover", "mse_relaxation",
            "mse_exemption_for_years_of_experience_and_turnover"
        ])
        if mse_exemption_obj and vendor.msme_registered:
            val_mse = str(mse_exemption_obj.value if isinstance(mse_exemption_obj, ExtractedFieldSchema) else (mse_exemption_obj.get("value") if isinstance(mse_exemption_obj, dict) else mse_exemption_obj)).strip().lower()
            if val_mse in ("yes", "true", "1", "applicable", "exempt"):
                logger.info(
                    f"[HARD_FILTER_UNCONSTRAINED] Tender: {tender_no} | Rule: {rule_name} | "
                    f"Field: mse_relaxation_experience_turnover | Reason: Vendor is MSME registered and tender grants MSE experience exemption"
                )
                return RuleResult(
                    rule_name=rule_name, field_name=field_name, status=RuleStatus.QUALIFIED,
                    passed=True, extracted_value=val_raw, extracted_confidence=conf,
                    reason="MSE experience exemption applicable for registered MSME vendor"
                )

        if vendor.years_of_experience < req_years:
            return self._emit_disqualification(
                tender_no=tender_no, rule_name=rule_name, field_name=field_name,
                extracted_val=val_raw, confidence=conf,
                constraint_threshold=f"Vendor Experience >= {req_years} years",
                reason=f"Vendor experience of {vendor.years_of_experience} years is below mandatory required {req_years} years"
            )

        return RuleResult(
            rule_name=rule_name, field_name=field_name, status=RuleStatus.QUALIFIED,
            passed=True, extracted_value=val_raw, extracted_confidence=conf,
            constraint_threshold=f"Vendor Experience >= {req_years} years",
            reason="Experience requirement satisfied"
        )

    def check_max_pbg_percentage(
        self, tender_no: str, field_map: Dict[str, Any], vendor: VendorProfile
    ) -> RuleResult:
        """Rule: Performance Bank Guarantee (PBG) percentage must not exceed statutory/vendor cap."""
        rule_name = "MAX_PBG_PERCENTAGE"
        field_name = "pbg_percentage"
        field_obj = self._lookup_field(field_map, ["pbg_percentage", "epbg_percentage", "PBG Percentage", "ePBG Percentage(%)"])
        req_flag = self._lookup_field(field_map, ["pbg_required", "epbg_required", "PBG Required", "ePBG Required"])

        # If PBG is explicitly not required, rule passes as exempt
        if req_flag and str(req_flag).lower() in ("no", "false", "0"):
            return RuleResult(
                rule_name=rule_name, field_name=field_name, status=RuleStatus.EXEMPT,
                passed=True, extracted_value="Not Required", extracted_confidence=1.0,
                reason="PBG explicitly declared Not Required"
            )

        inv = self._evaluate_rule_invariants(tender_no, rule_name, field_name, field_obj, is_buyer_optional=True)
        if inv is not None:
            return inv

        val_raw = field_obj.value if isinstance(field_obj, ExtractedFieldSchema) else (field_obj.get("value") if isinstance(field_obj, dict) else field_obj)
        conf = field_obj.confidence if isinstance(field_obj, ExtractedFieldSchema) else (field_obj.get("confidence", 1.0) if isinstance(field_obj, dict) else 1.0)
        pbg_pct = self._parse_numeric(val_raw)

        if pbg_pct is None or pbg_pct <= 0.0:
            return RuleResult(
                rule_name=rule_name, field_name=field_name, status=RuleStatus.QUALIFIED,
                passed=True, extracted_value=val_raw, extracted_confidence=conf,
                reason="No positive PBG requirement imposed"
            )

        if pbg_pct > vendor.max_pbg_tolerance_pct:
            return self._emit_disqualification(
                tender_no=tender_no, rule_name=rule_name, field_name=field_name,
                extracted_val=val_raw, confidence=conf,
                constraint_threshold=f"PBG <= {vendor.max_pbg_tolerance_pct:.1f}%",
                reason=f"Required PBG of {pbg_pct:.1f}% exceeds vendor maximum acceptable tolerance of {vendor.max_pbg_tolerance_pct:.1f}%"
            )

        return RuleResult(
            rule_name=rule_name, field_name=field_name, status=RuleStatus.QUALIFIED,
            passed=True, extracted_value=val_raw, extracted_confidence=conf,
            constraint_threshold=f"PBG <= {vendor.max_pbg_tolerance_pct:.1f}%",
            reason="PBG percentage within acceptable limits"
        )

    def check_min_bid_validity_days(
        self, tender_no: str, field_map: Dict[str, Any], vendor: VendorProfile
    ) -> RuleResult:
        """
        Rule: Buyer-demanded bid validity period must not exceed vendor maximum tolerance ceiling.
        Demanding a shorter validity (e.g. 3, 16, 20 days) is favorable and passes as QUALIFIED.
        Demanding validity > 365 days (e.g. unbounded OCR noise like 151152116) routes to NEEDS_REVIEW.
        Demanding validity > vendor.max_bid_validity_tolerance_days (loaded from config) emits DISQUALIFIED.
        """
        rule_name = "MIN_BID_VALIDITY"
        field_name = "bid_validity_days"
        field_obj = self._lookup_field(field_map, [
            "bid_validity_days", "bid_validity_days_display", "bid_validity", "bid_offer_validity",
            "Bid Validity Period", "Bid Offer Validity (Days)", "Bid Offer Validity"
        ])

        inv = self._evaluate_rule_invariants(tender_no, rule_name, field_name, field_obj, is_buyer_optional=False)
        if inv is not None:
            return inv

        val_raw = field_obj.value if isinstance(field_obj, ExtractedFieldSchema) else (field_obj.get("value") if isinstance(field_obj, dict) else field_obj)
        conf = field_obj.confidence if isinstance(field_obj, ExtractedFieldSchema) else (field_obj.get("confidence", 1.0) if isinstance(field_obj, dict) else 1.0)
        validity_days = self._parse_numeric(val_raw)

        if validity_days is None:
            return RuleResult(
                rule_name=rule_name, field_name=field_name, status=RuleStatus.NEEDS_REVIEW,
                passed=True, extracted_value=val_raw, extracted_confidence=conf,
                reason=f"Could not parse numeric bid validity days from '{val_raw}'"
            )

        # Guardrail against OCR table/concatenation corruption (> 365 days)
        if validity_days > 365:
            return RuleResult(
                rule_name=rule_name, field_name=field_name, status=RuleStatus.NEEDS_REVIEW,
                passed=True, extracted_value=val_raw, extracted_confidence=conf,
                reason=f"Extracted bid validity of {int(validity_days)} days exceeds physical 365-day year boundary (unbounded OCR extraction)"
            )

        max_tolerance = getattr(vendor, 'max_bid_validity_tolerance_days', getattr(vendor, 'min_bid_validity_days', 365))
        if validity_days > max_tolerance:
            return self._emit_disqualification(
                tender_no=tender_no, rule_name=rule_name, field_name=field_name,
                extracted_val=val_raw, confidence=conf,
                constraint_threshold=f"Bid Validity <= {max_tolerance} days",
                reason=f"Demanded bid validity of {int(validity_days)} days exceeds vendor maximum tolerance ceiling of {max_tolerance} days"
            )

        return RuleResult(
            rule_name=rule_name, field_name=field_name, status=RuleStatus.QUALIFIED,
            passed=True, extracted_value=val_raw, extracted_confidence=conf,
            constraint_threshold=f"Bid Validity <= {max_tolerance} days",
            reason="Bid validity period is within vendor tolerance ceiling"
        )

    # Alias for semantic clarity
    check_max_bid_validity_days = check_min_bid_validity_days

    def check_required_certifications(
        self, tender_no: str, field_map: Dict[str, Any], vendor: VendorProfile
    ) -> RuleResult:
        """Rule: Bidder must possess all mandatory statutory/quality certifications."""
        rule_name = "REQUIRED_CERTIFICATIONS"
        field_name = "required_documents"
        field_obj = self._lookup_field(field_map, [
            "required_documents", "certifications_required",
            "documents_required_from_seller", "Document required from seller"
        ])

        inv = self._evaluate_rule_invariants(tender_no, rule_name, field_name, field_obj, is_buyer_optional=True)
        if inv is not None:
            return inv

        val_raw = field_obj.value if isinstance(field_obj, ExtractedFieldSchema) else (field_obj.get("value") if isinstance(field_obj, dict) else field_obj)
        conf = field_obj.confidence if isinstance(field_obj, ExtractedFieldSchema) else (field_obj.get("confidence", 1.0) if isinstance(field_obj, dict) else 1.0)

        # Detect specific cert mentions (e.g. ISO 9001, BIS, CMMI, CE, RoHS)
        val_str = str(val_raw).upper()
        standard_certs = ["ISO 9001", "BIS", "ISO 14001", "ISO 27001", "CE", "CMMI"]
        required_certs = [c for c in standard_certs if c in val_str]

        if not required_certs:
            return RuleResult(
                rule_name=rule_name, field_name=field_name, status=RuleStatus.QUALIFIED,
                passed=True, extracted_value=val_raw, extracted_confidence=conf,
                reason="No specialized certification constraints detected"
            )

        missing_certs = [c for c in required_certs if c not in vendor.held_certifications]
        if missing_certs:
            return self._emit_disqualification(
                tender_no=tender_no, rule_name=rule_name, field_name=field_name,
                extracted_val=val_raw, confidence=conf,
                constraint_threshold=f"Vendor must hold: {required_certs}",
                reason=f"Vendor lacks mandatory certification(s): {missing_certs}"
            )

        return RuleResult(
            rule_name=rule_name, field_name=field_name, status=RuleStatus.QUALIFIED,
            passed=True, extracted_value=val_raw, extracted_confidence=conf,
            constraint_threshold=f"Vendor must hold: {required_certs}",
            reason="All required quality certifications held"
        )

    def check_insolvency_bankruptcy(
        self, tender_no: str, field_map: Dict[str, Any], vendor: VendorProfile
    ) -> RuleResult:
        """Rule: Disqualifies if vendor is insolvent or blacklisted under statutory declaration."""
        rule_name = "INSOLVENCY_BANKRUPTCY"
        field_name = "insolvency_clause"

        if vendor.is_insolvent or vendor.is_bankrupt or vendor.is_blacklisted:
            return self._emit_disqualification(
                tender_no=tender_no, rule_name=rule_name, field_name=field_name,
                extracted_val="Statutory Declaration", confidence=1.0,
                constraint_threshold="Vendor must be solvent and not blacklisted",
                reason="Vendor is currently insolvent, bankrupt, or blacklisted from public procurement"
            )

        return RuleResult(
            rule_name=rule_name, field_name=field_name, status=RuleStatus.QUALIFIED,
            passed=True, extracted_value="Solvent", extracted_confidence=1.0,
            constraint_threshold="Vendor must be solvent",
            reason="Vendor satisfies solvency and non-blacklisting criteria"
        )

    def check_mse_mii_compliance(
        self, tender_no: str, field_map: Dict[str, Any], vendor: VendorProfile
    ) -> RuleResult:
        """Rule: Verifies Make In India (MII) and MSE eligibility clauses."""
        rule_name = "MSE_MII_COMPLIANCE"
        field_name = "mii_purchase_preference"
        field_obj = self._lookup_field(field_map, [
            "mii_purchase_preference", "mse_purchase_preference",
            "MII Purchase Preference", "MSE Purchase Preference"
        ])

        inv = self._evaluate_rule_invariants(tender_no, rule_name, field_name, field_obj, is_buyer_optional=True)
        if inv is not None:
            return inv

        val_raw = field_obj.value if isinstance(field_obj, ExtractedFieldSchema) else (field_obj.get("value") if isinstance(field_obj, dict) else field_obj)
        conf = field_obj.confidence if isinstance(field_obj, ExtractedFieldSchema) else (field_obj.get("confidence", 1.0) if isinstance(field_obj, dict) else 1.0)
        val_lower = str(val_raw).lower()

        # If tender strictly restricts bidding to Class 1 Local Suppliers only and vendor is Non-Local
        if "class 1 only" in val_lower or "class 1 local supplier only" in val_lower:
            if vendor.mii_class not in ("Class 1", "Class 1 Local Supplier"):
                return self._emit_disqualification(
                    tender_no=tender_no, rule_name=rule_name, field_name=field_name,
                    extracted_val=val_raw, confidence=conf,
                    constraint_threshold="MII Class 1 Required",
                    reason=f"Tender strictly restricted to MII Class 1 Local Suppliers; vendor is {vendor.mii_class}"
                )

        return RuleResult(
            rule_name=rule_name, field_name=field_name, status=RuleStatus.QUALIFIED,
            passed=True, extracted_value=val_raw, extracted_confidence=conf,
            constraint_threshold="MII / MSE Compliance",
            reason="MSE/MII preferences satisfied or non-restrictive"
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Master Aggregation Pipeline
    # ─────────────────────────────────────────────────────────────────────────

    def evaluate_compliance(
        self,
        tender_no: str,
        extracted_fields: Union[Dict[str, Any], List[ExtractedFieldSchema], List[Dict[str, Any]]],
        vendor_profile: Optional[VendorProfile] = None
    ) -> ComplianceEvaluationResponse:
        """
        Evaluates all F_hard rules on a tender and aggregates findings into a single response.
        Evaluates all rules completely rather than early-halting, so human auditors capture
        every disqualifying or review-triggering violation in bulk.
        """
        vendor = vendor_profile or self.default_profile

        # Normalize extracted_fields into a dictionary keyed by field_name/label
        field_map: Dict[str, Any] = {}
        if isinstance(extracted_fields, list):
            for item in extracted_fields:
                if isinstance(item, ExtractedFieldSchema):
                    field_map[item.field_name] = item
                elif isinstance(item, dict):
                    fn = item.get("field_name") or item.get("label") or item.get("id")
                    if fn:
                        field_map[fn] = item
        elif isinstance(extracted_fields, dict):
            # Handle nested payload {"extracted_fields": [...]}
            if "extracted_fields" in extracted_fields and isinstance(extracted_fields["extracted_fields"], list):
                for item in extracted_fields["extracted_fields"]:
                    if isinstance(item, ExtractedFieldSchema):
                        field_map[item.field_name] = item
                    elif isinstance(item, dict):
                        fn = item.get("field_name") or item.get("label") or item.get("id")
                        if fn:
                            field_map[fn] = item
            else:
                field_map = extracted_fields

        # Evaluate all mandatory rules
        rule_evaluations: List[RuleResult] = [
            self.check_min_annual_turnover(tender_no, field_map, vendor),
            self.check_min_working_capital(tender_no, field_map, vendor),
            self.check_min_experience_years(tender_no, field_map, vendor),
            self.check_max_pbg_percentage(tender_no, field_map, vendor),
            self.check_min_bid_validity_days(tender_no, field_map, vendor),
            self.check_required_certifications(tender_no, field_map, vendor),
            self.check_insolvency_bankruptcy(tender_no, field_map, vendor),
            self.check_mse_mii_compliance(tender_no, field_map, vendor),
        ]

        disqualifications: List[str] = []
        review_reasons: List[str] = []

        for r in rule_evaluations:
            if r.status == RuleStatus.DISQUALIFIED:
                disqualifications.append(f"[{r.rule_name}] {r.reason}")
            elif r.status == RuleStatus.NEEDS_REVIEW:
                review_reasons.append(f"[{r.rule_name}] {r.reason}")

        # Determine overall status
        if disqualifications:
            overall_status = ComplianceStatus.DISQUALIFIED
        elif review_reasons:
            overall_status = ComplianceStatus.NEEDS_REVIEW
        else:
            overall_status = ComplianceStatus.QUALIFIED

        return ComplianceEvaluationResponse(
            tender_no=tender_no,
            overall_status=overall_status,
            is_disqualified=(overall_status == ComplianceStatus.DISQUALIFIED),
            requires_human_review=(overall_status == ComplianceStatus.NEEDS_REVIEW),
            disqualification_reasons=disqualifications,
            review_reasons=review_reasons,
            rule_results=rule_evaluations,
            evaluated_rules_count=len(rule_evaluations)
        )
