import json
import re
from pathlib import Path
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from backend.app.core.constants import STORAGE_ROOT
from backend.app.models.document import Document
from backend.app.models.tender_project import TenderProject
from backend.app.models.bid_compliance import ComplianceRequirement


FIELD_ALIASES = {
    "minimum_average_annual_turnover": [
        "minimum_average_annual_turnover",
        "annual_avg_turnover_value",
        "financial_avg_turnover",
    ],
    "years_of_past_experience": [
        "years_of_past_experience",
        "eligibility_criterion_years",
    ],
    "financial_working_capital": [
        "financial_working_capital",
        "working_capital_value",
    ],
    "financial_net_worth": [
        "financial_net_worth",
        "net_worth_type_value",
    ],
    "pbg_percentage": [
        "pbg_percentage",
    ],
    "bid_validity_days": [
        "bid_validity_days",
    ],
    "mse_purchase_preference": [
        "mse_purchase_preference",
        "mse_preference_price_band_percent",
        "mse_preference_max_qty_percent",
    ],
    "mii_purchase_preference": [
        "mii_purchase_preference",
        "mii_non_applicability_reason",
    ],
    "required_documents": [
        "required_documents",
    ],
    "maf_required": [
        "maf_required",
    ],
    "inspection_required": [
        "inspection_required",
    ],
    "land_border_clause_present": [
        "land_border_clause_present",
    ],
}


def _clean(value: Any) -> Any:
    if value is None:
        return None

    if isinstance(value, str):
        value = value.strip()

        if not value:
            return None

        lowered = value.lower()

        if lowered in {
            "not found",
            "out of scope (stage 1)",
            "n/a",
            "na",
            "none",
            "not applicable",
        }:
            return None

    return value


def _numeric(value: Any) -> Any:
    value = _clean(value)

    if value is None:
        return None

    if isinstance(value, (int, float)):
        return value

    match = re.search(
        r"[-+]?\d+(?:,\d+)*(?:\.\d+)?",
        str(value),
    )

    if not match:
        return None

    try:
        return float(match.group(0).replace(",", ""))
    except ValueError:
        return None


def _load_document_fields(document: Document) -> List[Dict[str, Any]]:
    """
    Read the already-produced extraction result for a tender document.
    """
    candidate_paths = [
        STORAGE_ROOT / "jobs" / str(document.id) / "extracted_fields.json",
    ]

    if document.storage_key:
        storage_path = Path(str(document.storage_key))
        if storage_path.exists():
            candidate_paths.append(
                storage_path.parent / "extracted_fields.json"
            )

    for path in candidate_paths:
        if not path.exists():
            continue

        try:
            with open(path, "r", encoding="utf-8") as f:
                payload = json.load(f)

            fields = payload.get("extracted_fields", [])

            if isinstance(fields, list):
                return fields

        except Exception:
            continue

    return []


def _field_map(fields: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    result = {}

    for field in fields:
        name = field.get("field_name")

        if not name:
            continue

        result[str(name)] = field

    return result


def _lookup(
    field_map: Dict[str, Dict[str, Any]],
    canonical_name: str,
) -> Dict[str, Any] | None:

    for alias in FIELD_ALIASES.get(canonical_name, []):
        if alias not in field_map:
            continue

        field = field_map[alias]
        value = _clean(field.get("value"))

        if value is not None:
            return field

    return None


def _build_requirements(
    tender_project_id: str,
    field_map: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:

    requirements = []

    # ------------------------------------------------------------
    # Financial requirements
    # ------------------------------------------------------------

    turnover = _lookup(
        field_map,
        "minimum_average_annual_turnover",
    )

    if turnover:
        requirements.append({
            "requirement_code": "TENDER_TURNOVER",
            "requirement_name": "Minimum Average Annual Turnover",
            "category": "FINANCIAL",
            "description": (
                "Minimum average annual turnover required by the tender."
            ),
            "mandatory": True,
            "threshold_value": _numeric(turnover.get("value")),
            "threshold_unit": "INR",
            "verification_source": "TENDER_DOCUMENT",
            "rule_definition": {
                "operator": ">=",
                "field": "annual_turnover",
                "source_field": turnover.get("field_name"),
                "source_page": turnover.get("source_page"),
            },
        })

    working_capital = _lookup(
        field_map,
        "financial_working_capital",
    )

    if working_capital:
        requirements.append({
            "requirement_code": "TENDER_WORKING_CAPITAL",
            "requirement_name": "Minimum Working Capital",
            "category": "FINANCIAL",
            "description": "Working capital requirement extracted from tender.",
            "mandatory": True,
            "threshold_value": _numeric(
                working_capital.get("value")
            ),
            "threshold_unit": "INR",
            "verification_source": "TENDER_DOCUMENT",
            "rule_definition": {
                "operator": ">=",
                "field": "working_capital",
                "source_field": working_capital.get("field_name"),
                "source_page": working_capital.get("source_page"),
            },
        })

    net_worth = _lookup(
        field_map,
        "financial_net_worth",
    )

    if net_worth:
        requirements.append({
            "requirement_code": "TENDER_NET_WORTH",
            "requirement_name": "Minimum Net Worth",
            "category": "FINANCIAL",
            "description": "Net worth requirement extracted from tender.",
            "mandatory": True,
            "threshold_value": _numeric(
                net_worth.get("value")
            ),
            "threshold_unit": "INR",
            "verification_source": "TENDER_DOCUMENT",
            "rule_definition": {
                "operator": ">=",
                "field": "net_worth",
                "source_field": net_worth.get("field_name"),
                "source_page": net_worth.get("source_page"),
            },
        })

    # ------------------------------------------------------------
    # Experience
    # ------------------------------------------------------------

    experience = _lookup(
        field_map,
        "years_of_past_experience",
    )

    if experience:
        requirements.append({
            "requirement_code": "TENDER_EXPERIENCE",
            "requirement_name": "Minimum Past Experience",
            "category": "ELIGIBILITY",
            "description": "Minimum years of experience required.",
            "mandatory": True,
            "threshold_value": _numeric(
                experience.get("value")
            ),
            "threshold_unit": "YEARS",
            "verification_source": "TENDER_DOCUMENT",
            "rule_definition": {
                "operator": ">=",
                "field": "years_of_experience",
                "source_field": experience.get("field_name"),
                "source_page": experience.get("source_page"),
            },
        })

    # ------------------------------------------------------------
    # Bid validity / PBG
    # ------------------------------------------------------------

    bid_validity = _lookup(
        field_map,
        "bid_validity_days",
    )

    if bid_validity:
        requirements.append({
            "requirement_code": "TENDER_BID_VALIDITY",
            "requirement_name": "Bid Validity Period",
            "category": "COMMERCIAL",
            "description": "Minimum/required bid validity period.",
            "mandatory": True,
            "threshold_value": _numeric(
                bid_validity.get("value")
            ),
            "threshold_unit": "DAYS",
            "verification_source": "TENDER_DOCUMENT",
            "rule_definition": {
                "operator": ">=",
                "field": "bid_validity_days",
                "source_field": bid_validity.get("field_name"),
                "source_page": bid_validity.get("source_page"),
            },
        })

    pbg = _lookup(
        field_map,
        "pbg_percentage",
    )

    if pbg:
        requirements.append({
            "requirement_code": "TENDER_PBG",
            "requirement_name": "Performance Bank Guarantee",
            "category": "COMMERCIAL",
            "description": "Performance bank guarantee percentage.",
            "mandatory": True,
            "threshold_value": _numeric(
                pbg.get("value")
            ),
            "threshold_unit": "PERCENT",
            "verification_source": "TENDER_DOCUMENT",
            "rule_definition": {
                "operator": "=",
                "field": "pbg_percentage",
                "source_field": pbg.get("field_name"),
                "source_page": pbg.get("source_page"),
            },
        })

    # ------------------------------------------------------------
    # MSME
    # ------------------------------------------------------------

    mse = _lookup(
        field_map,
        "mse_purchase_preference",
    )

    if mse:
        requirements.append({
            "requirement_code": "TENDER_MSME",
            "requirement_name": "MSME Eligibility / Preference",
            "category": "MSME",
            "description": "MSME preference or eligibility requirement.",
            "mandatory": False,
            "threshold_value": None,
            "threshold_unit": None,
            "verification_source": "TENDER_DOCUMENT",
            "rule_definition": {
                "field": "is_msme",
                "tender_value": mse.get("value"),
                "source_field": mse.get("field_name"),
                "source_page": mse.get("source_page"),
            },
        })

    # ------------------------------------------------------------
    # Make in India
    # ------------------------------------------------------------

    mii = _lookup(
        field_map,
        "mii_purchase_preference",
    )

    if mii:
        requirements.append({
            "requirement_code": "TENDER_MII",
            "requirement_name": "Make in India / Local Content",
            "category": "LOCAL_CONTENT",
            "description": "Make in India/local content requirement.",
            "mandatory": True,
            "threshold_value": None,
            "threshold_unit": None,
            "verification_source": "TENDER_DOCUMENT",
            "rule_definition": {
                "field": "is_mii_registered",
                "tender_value": mii.get("value"),
                "source_field": mii.get("field_name"),
                "source_page": mii.get("source_page"),
            },
        })

    # ------------------------------------------------------------
    # Tender document requirements
    # ------------------------------------------------------------

    required_docs = _lookup(
        field_map,
        "required_documents",
    )

    if required_docs:
        requirements.append({
            "requirement_code": "TENDER_REQUIRED_DOCUMENTS",
            "requirement_name": "Required Bid Documents",
            "category": "DOCUMENTS",
            "description": "Documents explicitly required by the tender.",
            "mandatory": True,
            "threshold_value": None,
            "threshold_unit": None,
            "verification_source": "TENDER_DOCUMENT",
            "rule_definition": {
                "field": "required_documents",
                "required_documents": required_docs.get("value"),
                "source_field": required_docs.get("field_name"),
                "source_page": required_docs.get("source_page"),
            },
        })

    # ------------------------------------------------------------
    # MAF / inspection
    # ------------------------------------------------------------

    maf = _lookup(field_map, "maf_required")

    if maf:
        requirements.append({
            "requirement_code": "TENDER_MAF",
            "requirement_name": "OEM / Manufacturer Authorization",
            "category": "DOCUMENTS",
            "description": "Manufacturer authorization requirement.",
            "mandatory": True,
            "threshold_value": None,
            "threshold_unit": None,
            "verification_source": "TENDER_DOCUMENT",
            "rule_definition": {
                "field": "maf_required",
                "tender_value": maf.get("value"),
                "source_page": maf.get("source_page"),
            },
        })

    inspection = _lookup(
        field_map,
        "inspection_required",
    )

    if inspection:
        requirements.append({
            "requirement_code": "TENDER_INSPECTION",
            "requirement_name": "Inspection Requirement",
            "category": "TECHNICAL",
            "description": "Tender inspection requirement.",
            "mandatory": True,
            "threshold_value": None,
            "threshold_unit": None,
            "verification_source": "TENDER_DOCUMENT",
            "rule_definition": {
                "field": "inspection_required",
                "tender_value": inspection.get("value"),
                "source_page": inspection.get("source_page"),
            },
        })

    return requirements


def generate_tender_requirements(
    db: Session,
    tender_project_id: str,
) -> Dict[str, Any]:

    project = db.query(TenderProject).filter(
        TenderProject.id == tender_project_id
    ).first()

    if not project:
        raise ValueError(
            f"Tender project {tender_project_id} not found"
        )

    documents = db.query(Document).filter(
        Document.tender_project_id == tender_project_id
    ).all()

    all_fields = []

    for document in documents:
        all_fields.extend(
            _load_document_fields(document)
        )

    field_map = _field_map(all_fields)

    requirements = _build_requirements(
        tender_project_id,
        field_map,
    )

    created = []

    for item in requirements:

        existing = db.query(ComplianceRequirement).filter(
            ComplianceRequirement.tender_project_id == tender_project_id,
            ComplianceRequirement.requirement_code == item["requirement_code"],
        ).first()

        if existing:
            for key, value in item.items():
                setattr(existing, key, value)
            row = existing
        else:
            row = ComplianceRequirement(**item)
            db.add(row)

        db.flush()

        created.append({
            "id": str(row.id),
            "requirement_code": row.requirement_code,
            "requirement_name": row.requirement_name,
            "category": row.category,
            "mandatory": row.mandatory,
            "threshold_value": row.threshold_value,
            "threshold_unit": row.threshold_unit,
            "verification_source": row.verification_source,
            "rule_definition": row.rule_definition,
        })

    db.commit()

    return {
        "tender_project_id": tender_project_id,
        "tender_name": str(project.tender_name),
        "extracted_field_count": len(field_map),
        "requirements_generated": len(created),
        "requirements": created,
    }
