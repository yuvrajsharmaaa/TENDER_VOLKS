"""
Core Standalone PQC Past-Performance Credential Matcher.

Implements standard Indian PSU/government past-performance qualification rules:
  1. Threshold calculation: 80%, 50%, and 40% of estimated tender value.
  2. Candidate filtering:
     - completion_date within 7 years of tender submission deadline.
     - At least one real (non-null) linked document.
     - item_category matches tender scope of work via keyword-based scope normalization.
  3. Evaluation priority:
     - 1x80%: Single credential >= 80% threshold.
     - 2x50%: At least 2 credentials each individually >= 50% threshold.
     - 3x40%: At least 3 credentials each individually >= 40% threshold.
     - MSME_RELAXED: If vendor is MSME and tender grants MSME relaxation.
     - NO_MATCH: Returns closest candidates and audit rationale.

Completely decoupled from database sessions and API endpoints.
"""

from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timedelta
from typing import Optional, Union, List, Dict, Any
import re


@dataclass
class CandidateCredential:
    id: int
    project_name: str
    value: float
    item: str
    item_category: str
    completion_date: Optional[date]
    document_paths: Dict[str, Any] = field(default_factory=dict)  # {"po": path, "completion": ..., "performance": ...}

    @classmethod
    def from_record(cls, record: Any) -> "CandidateCredential":
        """
        Converts a dictionary, SQLAlchemy model, or existing CandidateCredential
        into a canonical CandidateCredential instance.
        """
        if isinstance(record, cls):
            return record

        def _get(key: str, default: Any = None) -> Any:
            if isinstance(record, dict):
                return record.get(key, default)
            return getattr(record, key, default)

        # Parse numeric value
        raw_val = _get("value", 0.0)
        try:
            val_f = float(raw_val) if raw_val is not None else 0.0
        except (ValueError, TypeError):
            val_f = 0.0

        # Parse completion date
        raw_date = _get("completion_date")
        comp_date = _parse_date_safe(raw_date)

        # Check if flagged as corrupted date (e.g. year 5024)
        if _get("completion_date_flagged", False) or _get("completion_date_flag", False):
            comp_date = None

        # Build document paths dictionary
        doc_paths = _get("document_paths")
        if not isinstance(doc_paths, dict) or not doc_paths:
            doc_paths = {
                "po": _get("po_document"),
                "sap_gem_po": _get("sap_gem_po_document"),
                "completion": _get("completion_document"),
                "performance": _get("performance_certificate"),
            }

        return cls(
            id=int(_get("id", 0) or 0),
            project_name=str(_get("project_name", "") or _get("client", "") or "Untitled Project").strip(),
            value=val_f,
            item=str(_get("item", "") or "").strip(),
            item_category=str(_get("item_category", "") or "").strip(),
            completion_date=comp_date,
            document_paths=doc_paths,
        )


@dataclass
class PqcMatchResult:
    qualifies: bool
    strategy: str  # "1x80%" | "2x50%" | "3x40%" | "MSME_RELAXED" | "NO_MATCH"
    matched_credentials: List[CandidateCredential]
    thresholds_required: Dict[str, float]
    rationale: str
    target_scope: str = ""
    eligible_count: int = 0

    @property
    def closest_candidates(self) -> List[CandidateCredential]:
        """Returns closest candidates if no match was found."""
        return self.matched_credentials if not self.qualifies else []

    def to_dict(self) -> Dict[str, Any]:
        """Serializes result into a plain Python dictionary."""
        return {
            "qualifies": self.qualifies,
            "strategy": self.strategy,
            "matched_credentials": [asdict(c) for c in self.matched_credentials],
            "thresholds_required": self.thresholds_required,
            "rationale": self.rationale,
            "target_scope": self.target_scope,
            "eligible_count": self.eligible_count,
            "closest_candidates": [asdict(c) for c in self.closest_candidates],
        }


def _parse_date_safe(val: Any) -> Optional[date]:
    """Safely extracts a datetime.date object from date, datetime, or ISO string."""
    if val is None:
        return None
    if isinstance(val, date) and not isinstance(val, datetime):
        return val
    if isinstance(val, datetime):
        return val.date()
    val_str = str(val).strip()
    if not val_str or val_str.lower() in ("nan", "none", "null", "nat", ""):
        return None
    try:
        # Match YYYY-MM-DD or parse ISO
        match = re.search(r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})", val_str)
        if match:
            y, m, d = int(match.group(1)), int(match.group(2)), int(match.group(3))
            if y > 2100 or y < 1970:
                return None  # reject corrupted years
            return date(y, m, d)
        return datetime.fromisoformat(val_str).date()
    except Exception:
        return None


def compute_thresholds(tender_value: float, msme_floor_pct: float = 0.15) -> Dict[str, float]:
    """
    Given a tender's estimated value, computes the standard Indian PSU thresholds:
      - 80% for single order
      - 50% for two orders each
      - 40% for three orders each
      - msme_floor (default 15%) minimum floor for MSME-relaxed past performance
    """
    try:
        tv = float(tender_value) if tender_value is not None else 0.0
    except (ValueError, TypeError):
        tv = 0.0

    return {
        "eighty_pct": round(tv * 0.80, 2),
        "fifty_pct": round(tv * 0.50, 2),
        "forty_pct": round(tv * 0.40, 2),
        "msme_floor": round(tv * msme_floor_pct, 2),
        "threshold_80": round(tv * 0.80, 2),
        "threshold_50": round(tv * 0.50, 2),
        "threshold_40": round(tv * 0.40, 2),
        "threshold_msme_floor": round(tv * msme_floor_pct, 2),
    }


def is_within_window(
    completion_date: Optional[Union[date, datetime, str]],
    deadline: Union[date, datetime, str],
    years: int = 7
) -> bool:
    """
    Checks if completion_date falls within the 7-year recency window prior to the submission deadline:
      (deadline - 7 years) <= completion_date <= deadline
    Returns False if completion_date is missing, unparseable, or completed after the deadline.
    """
    comp_d = _parse_date_safe(completion_date)
    dead_d = _parse_date_safe(deadline)

    if comp_d is None or dead_d is None:
        return False

    # A future completion date relative to the deadline cannot qualify as past completed performance
    if comp_d > dead_d:
        return False

    # 7 years window: 365 * years days (plus 2 leap year days safety allowance)
    earliest_date = dead_d - timedelta(days=int(365.25 * years))
    return comp_d >= earliest_date


def has_valid_document(document_paths: Optional[Dict[str, Any]]) -> bool:
    """
    Verifies that candidate record has at least one real, non-null, non-empty linked document.
    """
    if not document_paths or not isinstance(document_paths, dict):
        return False

    for v in document_paths.values():
        if v is None:
            continue
        v_str = str(v).strip()
        if v_str and v_str.lower() not in ("none", "null", "nan", "[]", "{}"):
            return True
    return False


def normalize_scope(text: str) -> str:
    """
    Lightweight, deterministic keyword normalizer that maps scope strings or
    credential item/item_category fields into canonical domain clusters.
    
    Clusters derived from actual historical procurement corpus:
      - NICD_BATTERY
      - VRLA_BATTERY
      - OTHER_BATTERY (Lithium-ion, OPzS, Plante, Tubular)
      - CHARGER_UPS (Battery Chargers, FCBC, SMPS, UPS, Inverters)
      - VRF_AC
      - AC_UNIT (Split, Window, Ductable, Package, Central, Cassette, Precision, Chillers, AHU)
      - CEILING_FAN
      - AMC_SERVICE (Annual Maintenance Contracts, O&M, Servicing)
      - SOLAR_SYSTEM (SPV, Rooftop Solar, Solar Plants)
      - SPARES (Spares and consumables)
      - OTHER (Unmatched fallback)
    """
    if not text:
        return "OTHER"

    # Normalize whitespace, uppercase, and punctuation
    t = re.sub(r"[\s\-_]+", " ", str(text).upper()).strip()

    # 1. AMC & Maintenance Services (prioritized so 'AMC of AC units' classifies as AMC)
    if any(k in t for k in ["AMC", "ANNUAL MAINTENANCE", "CAMC", "O&M", "COMPREHENSIVE MAINTENANCE", "OPERATION AND MAINTENANCE"]):
        return "AMC_SERVICE"

    # 2. Ni-Cd Batteries
    if any(k in t for k in ["NI CD", "NICD", "NICAD", "NICKEL CADMIUM"]):
        return "NICD_BATTERY"

    # 3. VRLA / SMF Batteries
    if any(k in t for k in ["VRLA", "SMF", "SEALED MAINTENANCE FREE", "VALVE REGULATED"]):
        return "VRLA_BATTERY"

    # 4. Other Battery Chemistries (Lithium, OPzS, Tubular)
    if any(k in t for k in ["OPZS", "LI ION", "LITHIUM", "LMLA", "TUBULAR BATTERY", "PLANTE"]):
        return "OTHER_BATTERY"

    # 5. Chargers & UPS / Power Conditioning
    if any(k in t for k in ["FCBC", "SMPS", "CHARGER", "UPS", "INVERTER", "CONVERTER"]):
        return "CHARGER_UPS"

    # 6. VRF / VRV Air Conditioning
    if any(k in t for k in ["VRF", "VRV", "VARIABLE REFRIGERANT"]):
        return "VRF_AC"

    # 7. Ceiling Fans & Ventilation
    if any(k in t for k in ["CEILING FAN", "EXHAUST FAN", "VENTILATION"]) or re.search(r"\bFANS?\b", t):
        return "CEILING_FAN"

    # 8. General AC Units & HVAC Systems
    ac_keywords = [
        "SPLIT AC", "DUCTABLE AC", "PACKAGE AC", "WINDOW AC", "CASSETTE AC",
        "PRECISION AC", "TOWER AC", "CHILLER", "COOLING TOWER", "AHU",
        "HVAC", "SAC", "WAC", "AIR CONDITION", "AC UNIT", "SPACEMAKER",
        "AIRCOOLED", "CONDENSING UNIT"
    ]
    if any(k in t for k in ac_keywords) or re.search(r"\bAC\b|\bACS\b|\bAIRCONDITIONER\b", t):
        return "AC_UNIT"

    # 9. Solar Power Systems
    if any(k in t for k in ["SOLAR", "SPV", "PHOTOVOLTAIC", "ROOFTOP GRID"]):
        return "SOLAR_SYSTEM"

    # 10. Spares & Consumables
    if any(k in t for k in ["SPARES", "SPARE PARTS"]):
        return "SPARES"

    return "OTHER"


def _is_scope_match(cand_cat: str, target_cat: str, cand_raw_item: str, tender_raw_scope: str) -> bool:
    """
    Determines if candidate scope matches target scope:
      1. Exact canonical category match.
      2. If target is 'OTHER', accept as broad scope.
      3. Fallback check for direct keyword overlap between raw scope and item.
    """
    if target_cat == "OTHER":
        return True
    if cand_cat == target_cat:
        return True

    # Check if target category is AC_UNIT and candidate is VRF_AC (acceptable in broad HVAC tenders)
    if target_cat == "AC_UNIT" and cand_cat == "VRF_AC":
        return True

    # Fallback: check if raw text contains target keywords
    if cand_raw_item and tender_raw_scope:
        norm_cand = normalize_scope(cand_raw_item)
        if norm_cand == target_cat:
            return True

    return False


def match_credentials(
    tender_value: float,
    tender_scope_text: str,
    tender_deadline: Union[date, datetime, str],
    candidates: List[Union[CandidateCredential, Dict[str, Any], Any]],
    is_msme: bool = True,
    msme_relaxation_applicable: bool = False,
    msme_floor_pct: float = 0.15,
) -> PqcMatchResult:
    """
    Pure in-memory, standalone PQC credential matching function implementing standard
    Indian PSU/government procurement past-performance evaluation rules.

    Parameters:
      - tender_value: Estimated tender value in INR.
      - tender_scope_text: Tender title, scope of work description, or category string.
      - tender_deadline: Tender submission deadline / due date.
      - candidates: List of CandidateCredential objects, dicts, or ORM rows.
      - is_msme: Whether the bidding vendor is MSME/MSE registered (default True for Volks).
      - msme_relaxation_applicable: Whether the buyer/tender explicitly grants MSME
        relaxation on past-experience or turnover criteria.
      - msme_floor_pct: Minimum percentage floor of tender value required for MSME
        qualification (default 0.15 = 15%). Prevents trivially small orders from qualifying.

    Returns:
      - PqcMatchResult containing qualification status, strategy, matched records,
        computed thresholds, and human-readable audit rationale.
    """
    thresholds = compute_thresholds(tender_value, msme_floor_pct=msme_floor_pct)
    target_category = normalize_scope(tender_scope_text)
    parsed_deadline = _parse_date_safe(tender_deadline) or date.today()

    # Normalize all input candidate records into CandidateCredential dataclasses
    normalized_candidates: List[CandidateCredential] = [
        CandidateCredential.from_record(c) for c in candidates
    ]

    # Filter: recency window + valid document + matching scope
    eligible: List[CandidateCredential] = []
    for c in normalized_candidates:
        cand_cat = normalize_scope(c.item_category) if c.item_category else normalize_scope(c.item)
        within_win = is_within_window(c.completion_date, parsed_deadline, years=7)
        has_doc = has_valid_document(c.document_paths)
        scope_matched = _is_scope_match(cand_cat, target_category, c.item, tender_scope_text)

        if within_win and has_doc and scope_matched:
            eligible.append(c)

    # Sort candidates by value descending
    eligible.sort(key=lambda c: c.value, reverse=True)
    all_sorted = sorted(normalized_candidates, key=lambda c: c.value, reverse=True)

    # CASE A: No eligible candidates after filtering
    if not eligible:
        scope_candidates = [
            c for c in all_sorted
            if _is_scope_match(normalize_scope(c.item_category or c.item), target_category, c.item, tender_scope_text)
        ]
        closest = scope_candidates[:3] if scope_candidates else all_sorted[:3]
        msme_note = (
            f" (MSME relaxation is applicable, but requires at least one verified credential meeting the "
            f"{int(msme_floor_pct * 100)}% floor of ₹{thresholds['msme_floor']:,.2f})."
            if (is_msme and msme_relaxation_applicable) else ""
        )
        return PqcMatchResult(
            qualifies=False,
            strategy="NO_MATCH",
            matched_credentials=closest,
            thresholds_required=thresholds,
            rationale=(
                f"No past credential completed within 7 years of {parsed_deadline.isoformat()} matches "
                f"scope '{target_category}' with valid linked documents.{msme_note}"
            ),
            target_scope=target_category,
            eligible_count=0,
        )

    # CASE B: Try 1x80% Single Order
    eighty_thresh = thresholds["eighty_pct"]
    for c in eligible:
        if c.value >= eighty_thresh:
            return PqcMatchResult(
                qualifies=True,
                strategy="1x80%",
                matched_credentials=[c],
                thresholds_required=thresholds,
                rationale=(
                    f"Work Order '{c.project_name}' (₹{c.value:,.2f}) alone satisfies the 80% single-work "
                    f"criterion (₹{eighty_thresh:,.2f} required) based on matching scope ({target_category})."
                ),
                target_scope=target_category,
                eligible_count=len(eligible),
            )

    # CASE C: Try 2x50% Pair
    fifty_thresh = thresholds["fifty_pct"]
    qualifying_50 = [c for c in eligible if c.value >= fifty_thresh]
    if len(qualifying_50) >= 2:
        pair = qualifying_50[:2]
        return PqcMatchResult(
            qualifies=True,
            strategy="2x50%",
            matched_credentials=pair,
            thresholds_required=thresholds,
            rationale=(
                f"Work Orders '{pair[0].project_name}' (₹{pair[0].value:,.2f}) and '{pair[1].project_name}' "
                f"(₹{pair[1].value:,.2f}) each individually satisfy the 50% criterion "
                f"(₹{fifty_thresh:,.2f} required each) based on matching scope ({target_category})."
            ),
            target_scope=target_category,
            eligible_count=len(eligible),
        )

    # CASE D: Try 3x40% Triplet
    forty_thresh = thresholds["forty_pct"]
    qualifying_40 = [c for c in eligible if c.value >= forty_thresh]
    if len(qualifying_40) >= 3:
        triplet = qualifying_40[:3]
        names_str = ", ".join(f"'{t.project_name}' (₹{t.value:,.2f})" for t in triplet)
        return PqcMatchResult(
            qualifies=True,
            strategy="3x40%",
            matched_credentials=triplet,
            thresholds_required=thresholds,
            rationale=(
                f"Three work orders [{names_str}] each individually satisfy the 40% criterion "
                f"(₹{forty_thresh:,.2f} required each) based on matching scope ({target_category})."
            ),
            target_scope=target_category,
            eligible_count=len(eligible),
        )

    # CASE E: MSME Relaxation Exception (with non-trivial minimum floor requirement)
    if is_msme and msme_relaxation_applicable:
        msme_floor_val = thresholds["msme_floor"]
        qualifying_msme = [c for c in eligible if c.value >= msme_floor_val]
        if qualifying_msme:
            top_match = qualifying_msme[:1]
            return PqcMatchResult(
                qualifies=True,
                strategy="MSME_RELAXED",
                matched_credentials=top_match,
                thresholds_required=thresholds,
                rationale=(
                    f"Standard 1x80%/2x50%/3x40% thresholds not met, but vendor qualifies under MSME relaxation: "
                    f"Work Order '{top_match[0].project_name}' (₹{top_match[0].value:,.2f}) satisfies the "
                    f"{int(msme_floor_pct * 100)}% MSME floor criterion (₹{msme_floor_val:,.2f} required) "
                    f"based on matching scope ({target_category})."
                ),
                target_scope=target_category,
                eligible_count=len(eligible),
            )
        else:
            # All eligible credentials fall below the required MSME floor (trivially small)
            closest = eligible[:3]
            top_c = eligible[0]
            return PqcMatchResult(
                qualifies=False,
                strategy="NO_MATCH",
                matched_credentials=closest,
                thresholds_required=thresholds,
                rationale=(
                    f"No credentials met standard 80% (₹{eighty_thresh:,.2f}), 50% (₹{fifty_thresh:,.2f} x2), "
                    f"or 40% (₹{forty_thresh:,.2f} x3) criteria for scope '{target_category}'. "
                    f"While MSME relaxation is applicable, top credential '{top_c.project_name}' (₹{top_c.value:,.2f}) "
                    f"falls below the required {int(msme_floor_pct * 100)}% MSME floor (₹{msme_floor_val:,.2f} required on tender value ₹{tender_value:,.2f})."
                ),
                target_scope=target_category,
                eligible_count=len(eligible),
            )

    # CASE F: No Match (standard criteria not met and no MSME relaxation)
    closest = eligible[:3]
    top_c = eligible[0]
    return PqcMatchResult(
        qualifies=False,
        strategy="NO_MATCH",
        matched_credentials=closest,
        thresholds_required=thresholds,
        rationale=(
            f"No credentials met the 80% (₹{eighty_thresh:,.2f}), 50% (₹{fifty_thresh:,.2f} x2), or "
            f"40% (₹{forty_thresh:,.2f} x3) criteria for scope '{target_category}'. "
            f"Closest candidate was '{top_c.project_name}' at ₹{top_c.value:,.2f}."
        ),
        target_scope=target_category,
        eligible_count=len(eligible),
    )
