import json
import re
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from backend.app.models.bid_compliance import (
    BidSubmission,
    BidderDocument,
    ComplianceRequirement,
    ComplianceResult,
    AuditEvent,
)


REVIEW_CONFIDENCE = 0.85


def _norm(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value).strip().lower())


def _number(value: Any) -> Optional[float]:
    if value is None:
        return None

    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).replace(",", "").replace("₹", "").strip()

    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return None

    try:
        return float(match.group(0))
    except ValueError:
        return None


def _profile_value(profile: Dict[str, Any], *keys: str) -> Any:
    normalized = {
        _norm(k).replace(" ", "_"): v
        for k, v in profile.items()
    }

    for key in keys:
        value = normalized.get(_norm(key).replace(" ", "_"))
        if value not in (None, ""):
            return value

    return None


def _document_values(documents: List[BidderDocument]) -> Dict[str, Any]:
    result: Dict[str, Any] = {}

    for doc in documents:
        doc_type = _norm(doc.document_type).upper()

        result.setdefault("document_types", set()).add(doc_type)

        extracted = doc.extracted_data or {}

        if isinstance(extracted, str):
            try:
                extracted = json.loads(extracted)
            except Exception:
                extracted = {}

        fields = extracted.get("fields", {}) if isinstance(extracted, dict) else {}

        if not isinstance(fields, dict):
            fields = {}

        for key, value in fields.items():
            if value not in (None, ""):
                result[key] = value

    return result


def _has_document(documents: List[BidderDocument], keywords: List[str]) -> bool:
    for doc in documents:
        name = _norm(doc.document_name)
        doc_type = _norm(doc.document_type)

        combined = f"{name} {doc_type}"

        if any(keyword in combined for keyword in keywords):
            return True

    return False


def _split_documents(value: Any) -> List[str]:
    if value is None:
        return []

    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]

    if isinstance(value, dict):
        values = value.get("documents") or value.get("required_documents") or []
        if isinstance(values, list):
            return [str(x).strip() for x in values if str(x).strip()]

    text = str(value)

    return [
        part.strip()
        for part in re.split(r"[,;\n|]", text)
        if part.strip()
    ]


def _document_requirement_met(
    required_document: str,
    documents: List[BidderDocument],
) -> bool:
    key = _norm(required_document)

    aliases = {
        "gst": ["gst", "gst_certificate", "gst registration"],
        "gst certificate": ["gst", "gst_certificate"],
        "pan": ["pan", "pan_card"],
        "pan card": ["pan", "pan_card"],
        "udyam": ["udyam", "msme"],
        "msme": ["udyam", "msme"],
        "msme certificate": ["udyam", "msme"],
        "mca": ["mca", "cin"],
        "cin": ["mca", "cin"],
        "experience certificate": ["experience"],
        "financial statement": ["financial", "balance_sheet"],
        "turnover certificate": ["turnover", "ca_certificate"],
        "oem authorization": ["oem", "maf", "authorization"],
        "maf": ["maf", "oem", "authorization"],
        "inspection certificate": ["inspection"],
    }

    keywords = aliases.get(key)

    if keywords:
        return _has_document(documents, keywords)

    return _has_document(
        documents,
        [key.replace(" ", "_"), key],
    )


def _requirement_evidence(
    requirement: ComplianceRequirement,
    submission: BidSubmission,
    profile: Dict[str, Any],
    documents: List[BidderDocument],
    doc_values: Dict[str, Any],
) -> Dict[str, Any]:
    code = requirement.requirement_code

    if code == "TENDER_TURNOVER":
        value = _profile_value(
            profile,
            "annual_turnover",
            "average_annual_turnover",
            "minimum_average_annual_turnover",
            "turnover",
        )
        return {
            "submitted": value,
            "numeric": _number(value),
            "source": "bidder.profile_data",
        }

    if code == "TENDER_WORKING_CAPITAL":
        value = _profile_value(
            profile,
            "working_capital",
            "financial_working_capital",
        )
        return {
            "submitted": value,
            "numeric": _number(value),
            "source": "bidder.profile_data",
        }

    if code == "TENDER_NET_WORTH":
        value = _profile_value(
            profile,
            "net_worth",
            "financial_net_worth",
        )
        return {
            "submitted": value,
            "numeric": _number(value),
            "source": "bidder.profile_data",
        }

    if code == "TENDER_EXPERIENCE":
        value = _profile_value(
            profile,
            "years_of_experience",
            "past_experience_years",
            "experience_years",
        )
        return {
            "submitted": value,
            "numeric": _number(value),
            "source": "bidder.profile_data",
        }

    if code == "TENDER_BID_VALIDITY":
        value = _profile_value(
            profile,
            "bid_validity_days",
            "validity_days",
        )
        return {
            "submitted": value,
            "numeric": _number(value),
            "source": "bid_submission/profile",
        }

    if code == "TENDER_PBG":
        value = _profile_value(
            profile,
            "pbg_percentage",
            "performance_bank_guarantee_percentage",
            "pbg",
        )
        return {
            "submitted": value,
            "numeric": _number(value),
            "source": "bidder.profile_data",
        }

    if code == "TENDER_MSME":
        value = profile.get("is_msme", getattr(submission.bidder, "is_msme", None))
        return {
            "submitted": value,
            "boolean": bool(value),
            "source": "bidder.profile",
        }

    if code == "TENDER_MII":
        value = profile.get(
            "is_mii_registered",
            getattr(submission.bidder, "is_mii_registered", None),
        )
        return {
            "submitted": value,
            "boolean": bool(value),
            "source": "bidder.profile",
        }

    if code == "TENDER_REQUIRED_DOCUMENTS":
        required = _split_documents(requirement.threshold_value)

        if not required:
            rule = requirement.rule_definition or {}
            required = _split_documents(
                rule.get("required_documents")
                or rule.get("raw_value")
            )

        missing = [
            document
            for document in required
            if not _document_requirement_met(document, documents)
        ]

        return {
            "submitted": list(doc_values.get("document_types", set())),
            "required_documents": required,
            "missing_documents": missing,
            "source": "bidder.documents",
        }

    if code == "TENDER_MAF":
        present = _has_document(
            documents,
            ["maf", "oem", "manufacturer", "authorization"],
        )

        return {
            "submitted": present,
            "boolean": present,
            "source": "bidder.documents",
        }

    if code == "TENDER_INSPECTION":
        present = _has_document(
            documents,
            ["inspection", "inspection_certificate"],
        )

        return {
            "submitted": present,
            "boolean": present,
            "source": "bidder.documents",
        }

    return {
        "submitted": None,
        "source": "not_mapped",
    }


def _evaluate_requirement(
    requirement: ComplianceRequirement,
    evidence: Dict[str, Any],
) -> Dict[str, Any]:
    code = requirement.requirement_code
    mandatory = bool(requirement.mandatory)

    threshold = _number(requirement.threshold_value)

    submitted_number = evidence.get("numeric")

    if code in {
        "TENDER_TURNOVER",
        "TENDER_WORKING_CAPITAL",
        "TENDER_NET_WORTH",
        "TENDER_EXPERIENCE",
        "TENDER_BID_VALIDITY",
        "TENDER_PBG",
    }:
        if submitted_number is None or threshold is None:
            return {
                "status": "NEEDS_REVIEW",
                "passed": False,
                "reason": "Required bidder evidence is missing or could not be interpreted.",
            }

        if submitted_number >= threshold:
            return {
                "status": "PASSED",
                "passed": True,
                "reason": f"Bidder value {submitted_number} meets tender threshold {threshold}.",
            }

        return {
            "status": "FAILED",
            "passed": False,
            "reason": f"Bidder value {submitted_number} is below tender threshold {threshold}.",
        }

    if code in {"TENDER_MSME", "TENDER_MII"}:
        if "boolean" not in evidence:
            return {
                "status": "NEEDS_REVIEW",
                "passed": False,
                "reason": "Bidder registration/preference status is unavailable.",
            }

        if evidence["boolean"]:
            return {
                "status": "PASSED",
                "passed": True,
                "reason": "Bidder satisfies the tender's stated registration/preference condition.",
            }

        return {
            "status": "NEEDS_REVIEW" if not mandatory else "FAILED",
            "passed": False,
            "reason": (
                "Bidder does not claim the stated registration/preference status. "
                "Procurement-officer review is required to determine applicability."
            ),
        }

    if code == "TENDER_REQUIRED_DOCUMENTS":
        missing = evidence.get("missing_documents", [])

        if not evidence.get("required_documents"):
            return {
                "status": "NEEDS_REVIEW",
                "passed": False,
                "reason": "Tender required-document list was not sufficiently extracted.",
            }

        if not missing:
            return {
                "status": "PASSED",
                "passed": True,
                "reason": "All extracted mandatory tender documents are present.",
            }

        return {
            "status": "FAILED" if mandatory else "NEEDS_REVIEW",
            "passed": False,
            "reason": f"Missing required documents: {', '.join(missing)}",
        }

    if code in {"TENDER_MAF", "TENDER_INSPECTION"}:
        if evidence.get("boolean"):
            return {
                "status": "PASSED",
                "passed": True,
                "reason": "Required supporting evidence is present.",
            }

        return {
            "status": "FAILED" if mandatory else "NEEDS_REVIEW",
            "passed": False,
            "reason": "Required supporting evidence was not found in bidder documents.",
        }

    return {
        "status": "NEEDS_REVIEW",
        "passed": False,
        "reason": "Tender requirement is not yet mapped to an automated bidder check.",
    }


def evaluate_tender_requirements(
    db: Session,
    submission_id: str,
) -> Dict[str, Any]:
    submission = (
        db.query(BidSubmission)
        .filter(BidSubmission.id == submission_id)
        .first()
    )

    if not submission:
        raise ValueError("Bid submission not found")

    bidder = submission.bidder

    profile = bidder.profile_data or {}

    if not isinstance(profile, dict):
        profile = {}

    profile.setdefault("is_msme", bidder.is_msme)
    profile.setdefault("is_mii_registered", bidder.is_mii_registered)

    documents = (
        db.query(BidderDocument)
        .filter(BidderDocument.submission_id == submission_id)
        .all()
    )

    doc_values = _document_values(documents)

    requirements = (
        db.query(ComplianceRequirement)
        .filter(
            ComplianceRequirement.tender_project_id
            == submission.tender_project_id
        )
        .order_by(ComplianceRequirement.requirement_code.asc())
        .all()
    )

    results = []

    for requirement in requirements:
        evidence = _requirement_evidence(
            requirement,
            submission,
            profile,
            documents,
            doc_values,
        )

        evaluation = _evaluate_requirement(
            requirement,
            evidence,
        )

        result = (
            db.query(ComplianceResult)
            .filter(
                ComplianceResult.submission_id == submission_id,
                ComplianceResult.requirement_code
                == requirement.requirement_code,
            )
            .first()
        )

        if not result:
            result = ComplianceResult(
                submission_id=submission_id,
                requirement_code=requirement.requirement_code,
            )
            db.add(result)

        result.requirement_name = requirement.requirement_name
        result.status = evaluation["status"]
        result.passed = evaluation["passed"]
        result.mandatory = requirement.mandatory
        result.extracted_value = evidence.get("submitted")

        expected = requirement.threshold_value

        if not expected:
            rule = requirement.rule_definition or {}

            if requirement.requirement_code == "TENDER_REQUIRED_DOCUMENTS":
                expected = json.dumps(
                    evidence.get("required_documents", [])
                )

            else:
                expected = rule.get("raw_value")

        result.expected_value = expected
        result.confidence = 1.0 if evidence.get("submitted") is not None else 0.0
        result.reason = evaluation["reason"]
        result.evidence = {
            "source": evidence.get("source"),
            "submitted": evidence.get("submitted"),
            "expected": expected,
            "missing_documents": evidence.get("missing_documents", []),
        }
        result.ai_explanation = (
            "Tender-specific deterministic compliance evaluation. "
            "Use procurement-officer review for NEEDS_REVIEW cases."
        )

        db.add(
            AuditEvent(
                submission_id=submission_id,
                event_type="TENDER_REQUIREMENT_EVALUATED",
                actor="system",
                description=(
                    f"{requirement.requirement_code}: "
                    f"{evaluation['status']} - {evaluation['reason']}"
                ),
                source="tender_bid_compliance_engine",
                after_value=evaluation["status"],
                event_metadata={
                    "requirement_code": requirement.requirement_code,
                },
            )
        )

        results.append(
            {
                "requirement_code": requirement.requirement_code,
                "requirement_name": requirement.requirement_name,
                "status": evaluation["status"],
                "passed": evaluation["passed"],
                "mandatory": requirement.mandatory,
                "submitted": evidence.get("submitted"),
                "expected": expected,
                "reason": evaluation["reason"],
            }
        )

    db.commit()

    return {
        "submission_id": submission_id,
        "tender_project_id": str(submission.tender_project_id),
        "requirements_checked": len(results),
        "results": results,
    }
