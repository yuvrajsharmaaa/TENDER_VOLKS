import re
from typing import Any, Dict, Optional, Tuple

from sqlalchemy.orm import Session

from backend.app.models.bid_compliance import (
    BidSubmission,
    Bidder,
    BidderDocument,
    ComplianceRequirement,
    VerificationCheck,
    ComplianceResult,
    RiskAssessment,
    AuditEvent,
)


def _norm(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


def _field_value(fields: Dict[str, Any], name: str) -> Any:
    item = fields.get(name)
    if isinstance(item, dict):
        return item.get("value")
    return item


def _field_confidence(fields: Dict[str, Any], name: str) -> float:
    item = fields.get(name)
    if isinstance(item, dict):
        return float(item.get("confidence", 0.0) or 0.0)
    return 0.0


def _document_fields(document: BidderDocument) -> Dict[str, Any]:
    data = document.extracted_data or {}
    fields = data.get("fields", {})
    return fields if isinstance(fields, dict) else {}


def _compare(
    submitted: Any,
    expected: Any,
    confidence: float,
) -> Tuple[str, bool, str]:

    if submitted in (None, "", "Not Found"):
        return (
            "NEEDS_REVIEW",
            False,
            "Required value was not extracted from the submitted document.",
        )

    if expected in (None, "", "Not Found"):
        return (
            "NEEDS_REVIEW",
            False,
            "Expected bidder profile value is missing.",
        )

    if confidence < 0.85:
        return (
            "NEEDS_REVIEW",
            False,
            f"Extraction confidence {confidence:.2f} is below the 0.85 threshold.",
        )

    if _norm(submitted) == _norm(expected):
        return (
            "PASSED",
            True,
            "Submitted document value matches the registered bidder profile.",
        )

    return (
        "FAILED",
        False,
        f"Mismatch detected: submitted value '{submitted}' does not match "
        f"registered bidder value '{expected}'.",
    )


DOCUMENT_RULES = {
    "GST_CERTIFICATE": {
        "code": "GST_REGISTRATION",
        "name": "GST Registration",
        "field": "gstin",
        "bidder_field": "gstin",
        "category": "STATUTORY",
        "verification_source": "GST_DOCUMENT",
    },
    "PAN_CARD": {
        "code": "PAN_MATCH",
        "name": "PAN Verification",
        "field": "pan",
        "bidder_field": "pan",
        "category": "STATUTORY",
        "verification_source": "PAN_DOCUMENT",
    },
    "PAN_CERTIFICATE": {
        "code": "PAN_MATCH",
        "name": "PAN Verification",
        "field": "pan",
        "bidder_field": "pan",
        "category": "STATUTORY",
        "verification_source": "PAN_DOCUMENT",
    },
    "UDYAM_CERTIFICATE": {
        "code": "UDYAM_MATCH",
        "name": "Udyam/MSME Verification",
        "field": "udyam_number",
        "bidder_field": "udyam_number",
        "category": "MSME",
        "verification_source": "UDYAM_DOCUMENT",
    },
    "MSME_CERTIFICATE": {
        "code": "UDYAM_MATCH",
        "name": "Udyam/MSME Verification",
        "field": "udyam_number",
        "bidder_field": "udyam_number",
        "category": "MSME",
        "verification_source": "UDYAM_DOCUMENT",
    },
    "CIN_CERTIFICATE": {
        "code": "CIN_MATCH",
        "name": "CIN Verification",
        "field": "cin",
        "bidder_field": "cin",
        "category": "CORPORATE",
        "verification_source": "MCA_DOCUMENT",
    },
    "MCA_CERTIFICATE": {
        "code": "CIN_MATCH",
        "name": "CIN Verification",
        "field": "cin",
        "bidder_field": "cin",
        "category": "CORPORATE",
        "verification_source": "MCA_DOCUMENT",
    },
}


def _ensure_requirement(
    db: Session,
    submission: BidSubmission,
    rule: Dict[str, Any],
) -> ComplianceRequirement:

    requirement = db.query(ComplianceRequirement).filter(
        ComplianceRequirement.tender_project_id == submission.tender_project_id,
        ComplianceRequirement.requirement_code == rule["code"],
    ).first()

    if requirement:
        return requirement

    requirement = ComplianceRequirement(
        tender_project_id=submission.tender_project_id,
        requirement_code=rule["code"],
        requirement_name=rule["name"],
        category=rule["category"],
        description=f"Automated verification for {rule['name']}.",
        mandatory=True,
        verification_source=rule["verification_source"],
        rule_definition={
            "engine": "bid_compliance_engine",
            "document_type": None,
        },
    )

    db.add(requirement)
    db.flush()

    return requirement


def _upsert_verification(
    db: Session,
    submission_id: str,
    rule_code: str,
    status: str,
    submitted: Any,
    expected: Any,
    confidence: float,
    mismatch: bool,
    explanation: str,
    evidence: Any,
    source: str,
):

    row = db.query(VerificationCheck).filter(
        VerificationCheck.submission_id == submission_id,
        VerificationCheck.requirement_code == rule_code,
    ).first()

    if not row:
        row = VerificationCheck(
            submission_id=submission_id,
            requirement_code=rule_code,
        )
        db.add(row)

    row.verification_type = "DOCUMENT_TO_PROFILE"
    row.source = source
    row.status = status
    row.verified_value = expected
    row.submitted_value = submitted
    row.confidence = confidence
    row.mismatch_detected = mismatch
    row.explanation = explanation
    row.evidence = evidence


def _upsert_result(
    db: Session,
    submission_id: str,
    rule_code: str,
    rule_name: str,
    status: str,
    passed: bool,
    mandatory: bool,
    extracted: Any,
    expected: Any,
    confidence: float,
    reason: str,
    evidence: Any,
    ai_explanation: str,
):

    row = db.query(ComplianceResult).filter(
        ComplianceResult.submission_id == submission_id,
        ComplianceResult.requirement_code == rule_code,
    ).first()

    if not row:
        row = ComplianceResult(
            submission_id=submission_id,
            requirement_code=rule_code,
        )
        db.add(row)

    row.requirement_name = rule_name
    row.status = status
    row.passed = passed
    row.mandatory = mandatory
    row.extracted_value = extracted
    row.expected_value = expected
    row.confidence = confidence
    row.reason = reason
    row.evidence = evidence
    row.ai_explanation = ai_explanation


def evaluate_submission(
    db: Session,
    submission_id: str,
) -> Dict[str, Any]:

    submission = db.query(BidSubmission).filter(
        BidSubmission.id == submission_id
    ).first()

    if not submission:
        raise ValueError(f"Bid submission {submission_id} not found")

    bidder = db.query(Bidder).filter(
        Bidder.id == submission.bidder_id
    ).first()

    if not bidder:
        raise ValueError(
            f"Bidder {submission.bidder_id} not found"
        )

    documents = db.query(BidderDocument).filter(
        BidderDocument.submission_id == submission_id
    ).all()

    evaluated = []

    # ---------------------------------------------------------------
    # 1. Document -> Bidder profile verification
    # ---------------------------------------------------------------
    for document in documents:

        if document.extraction_status != "COMPLETED":
            continue

        document_type = str(
            document.document_type or "OTHER"
        ).upper()

        rule = DOCUMENT_RULES.get(document_type)

        if not rule:
            continue

        requirement = _ensure_requirement(
            db,
            submission,
            rule,
        )

        rule["document_type"] = document_type

        fields = _document_fields(document)

        submitted = _field_value(
            fields,
            rule["field"],
        )

        confidence = _field_confidence(
            fields,
            rule["field"],
        )

        expected = getattr(
            bidder,
            rule["bidder_field"],
            None,
        )

        status, passed, reason = _compare(
            submitted,
            expected,
            confidence,
        )

        mismatch = status == "FAILED"

        evidence = {
            "document_id": str(document.id),
            "document_name": document.document_name,
            "document_type": document_type,
            "field": rule["field"],
            "source": "bidder_document_extraction",
        }

        _upsert_verification(
            db=db,
            submission_id=submission_id,
            rule_code=rule["code"],
            status=status,
            submitted=submitted,
            expected=expected,
            confidence=confidence,
            mismatch=mismatch,
            explanation=reason,
            evidence=evidence,
            source=rule["verification_source"],
        )

        _upsert_result(
            db=db,
            submission_id=submission_id,
            rule_code=rule["code"],
            rule_name=rule["name"],
            status=(
                "QUALIFIED"
                if passed
                else "DISQUALIFIED"
                if status == "FAILED"
                else "NEEDS_REVIEW"
            ),
            passed=passed,
            mandatory=requirement.mandatory,
            extracted=submitted,
            expected=expected,
            confidence=confidence,
            reason=reason,
            evidence=evidence,
            ai_explanation=(
                f"{rule['name']} was evaluated by deterministic "
                f"document-to-profile verification. {reason}"
            ),
        )

        evaluated.append({
            "requirement_code": rule["code"],
            "status": status,
            "passed": passed,
        })

        # -----------------------------------------------------------
        # GST certificate status check
        # -----------------------------------------------------------
        if document_type == "GST_CERTIFICATE":
            status_rule = {
                "code": "GST_STATUS_ACTIVE",
                "name": "GST Registration Status",
                "category": "STATUTORY",
                "verification_source": "GST_DOCUMENT",
            }

            status_requirement = _ensure_requirement(
                db,
                submission,
                status_rule,
            )

            submitted_status = _field_value(
                fields,
                "registration_status",
            )

            status_confidence = _field_confidence(
                fields,
                "registration_status",
            )

            if submitted_status in (None, "", "Not Found"):
                check_status = "NEEDS_REVIEW"
                check_passed = False
                check_reason = "GST registration status was not extracted."
            elif status_confidence < 0.85:
                check_status = "NEEDS_REVIEW"
                check_passed = False
                check_reason = "GST registration status has insufficient confidence."
            elif _norm(submitted_status) == "active":
                check_status = "PASSED"
                check_passed = True
                check_reason = "GST registration status is Active."
            else:
                check_status = "FAILED"
                check_passed = False
                check_reason = (
                    f"GST registration status is '{submitted_status}', "
                    "not Active."
                )

            evidence = {
                "document_id": str(document.id),
                "field": "registration_status",
                "source": "bidder_document_extraction",
            }

            _upsert_verification(
                db=db,
                submission_id=submission_id,
                rule_code=status_rule["code"],
                status=check_status,
                submitted=submitted_status,
                expected="Active",
                confidence=status_confidence,
                mismatch=not check_passed,
                explanation=check_reason,
                evidence=evidence,
                source="GST_DOCUMENT",
            )

            _upsert_result(
                db=db,
                submission_id=submission_id,
                rule_code=status_rule["code"],
                rule_name=status_rule["name"],
                status=(
                    "QUALIFIED"
                    if check_passed
                    else "DISQUALIFIED"
                    if check_status == "FAILED"
                    else "NEEDS_REVIEW"
                ),
                passed=check_passed,
                mandatory=status_requirement.mandatory,
                extracted=submitted_status,
                expected="Active",
                confidence=status_confidence,
                reason=check_reason,
                evidence=evidence,
                ai_explanation=check_reason,
            )

            evaluated.append({
                "requirement_code": status_rule["code"],
                "status": check_status,
                "passed": check_passed,
            })

    # ---------------------------------------------------------------
    # 2. Blacklist / debarment profile checks
    # ---------------------------------------------------------------
    sanctions = [
        (
            "BLACKLIST_STATUS",
            "Blacklisting Status",
            bool(bidder.blacklisted),
            "Bidder profile does not indicate blacklisting."
            if not bidder.blacklisted
            else "Bidder profile indicates blacklisting."
        ),
        (
            "DEBARMENT_STATUS",
            "Debarment Status",
            bool(bidder.debarred),
            "Bidder profile does not indicate debarment."
            if not bidder.debarred
            else "Bidder profile indicates debarment."
        ),
    ]

    for code, name, flagged, reason in sanctions:

        rule = {
            "code": code,
            "name": name,
            "category": "ELIGIBILITY",
            "verification_source": "BIDDER_PROFILE",
        }

        requirement = _ensure_requirement(
            db,
            submission,
            rule,
        )

        passed = not flagged
        status = "PASSED" if passed else "FAILED"

        evidence = {
            "source": "bidder_profile",
            "bidder_id": str(bidder.id),
            "field": code,
        }

        _upsert_verification(
            db=db,
            submission_id=submission_id,
            rule_code=code,
            status=status,
            submitted=flagged,
            expected=False,
            confidence=1.0,
            mismatch=flagged,
            explanation=reason,
            evidence=evidence,
            source="BIDDER_PROFILE",
        )

        _upsert_result(
            db=db,
            submission_id=submission_id,
            rule_code=code,
            rule_name=name,
            status="QUALIFIED" if passed else "DISQUALIFIED",
            passed=passed,
            mandatory=requirement.mandatory,
            extracted=flagged,
            expected=False,
            confidence=1.0,
            reason=reason,
            evidence=evidence,
            ai_explanation=reason,
        )

        evaluated.append({
            "requirement_code": code,
            "status": status,
            "passed": passed,
        })

    db.flush()

    # ---------------------------------------------------------------
    # 3. Calculate compliance score
    # ---------------------------------------------------------------
    mandatory_results = db.query(ComplianceResult).filter(
        ComplianceResult.submission_id == submission_id,
        ComplianceResult.mandatory == True,
    ).all()

    passed_count = sum(
        1 for result in mandatory_results
        if result.passed is True
    )

    failed_count = sum(
        1 for result in mandatory_results
        if result.status == "DISQUALIFIED"
    )

    review_count = sum(
        1 for result in mandatory_results
        if result.status == "NEEDS_REVIEW"
    )

    total_count = len(mandatory_results)

    score = (
        round((passed_count / total_count) * 100, 2)
        if total_count
        else None
    )

    if failed_count:
        risk_level = "HIGH"
    elif review_count:
        risk_level = "MEDIUM"
    elif score is not None and score >= 85:
        risk_level = "LOW"
    elif score is not None and score >= 70:
        risk_level = "MEDIUM"
    else:
        risk_level = "HIGH"

    critical_issues = [
        result.reason
        for result in mandatory_results
        if result.status == "DISQUALIFIED"
    ]

    warnings = [
        result.reason
        for result in mandatory_results
        if result.status == "NEEDS_REVIEW"
    ]

    risk = db.query(RiskAssessment).filter(
        RiskAssessment.submission_id == submission_id
    ).first()

    if not risk:
        risk = RiskAssessment(
            submission_id=submission_id,
        )
        db.add(risk)

    risk.risk_level = risk_level
    risk.risk_score = (
        100 - score
        if score is not None
        else 100
    )
    risk.compliance_score = score
    risk.critical_issues = failed_count
    risk.warnings = len(warnings)
    risk.passed_checks = passed_count
    risk.risk_factors = {
        "failed_checks": failed_count,
        "needs_review": review_count,
        "mandatory_checks": total_count,
    }

    if failed_count:
        recommendation = (
            "Manual officer review required. One or more mandatory "
            "compliance checks failed."
        )
    elif review_count:
        recommendation = (
            "Manual officer review required. Some mandatory checks "
            "could not be conclusively verified."
        )
    else:
        recommendation = (
            "All currently evaluated mandatory checks passed. "
            "Procurement Officer should complete the final decision."
        )

    risk.ai_summary = (
        f"Compliance evaluation completed for bidder "
        f"{bidder.legal_name}. "
        f"{passed_count}/{total_count} mandatory checks passed."
    )
    risk.ai_recommendation = recommendation

    submission.compliance_score = score
    submission.risk_level = risk_level
    submission.ai_recommendation = recommendation

    audit = AuditEvent(
        submission_id=submission_id,
        event_type="COMPLIANCE_EVALUATED",
        actor="system",
        description=(
            f"Automated compliance evaluation completed: "
            f"{passed_count}/{total_count} mandatory checks passed."
        ),
        source="bid_compliance_engine",
        event_metadata={
            "score": score,
            "risk_level": risk_level,
            "passed": passed_count,
            "failed": failed_count,
            "needs_review": review_count,
        },
    )

    db.add(audit)
    db.commit()

    return {
        "submission_id": submission_id,
        "compliance_score": score,
        "risk_level": risk_level,
        "passed": passed_count,
        "failed": failed_count,
        "needs_review": review_count,
        "total": total_count,
        "recommendation": recommendation,
        "checks": evaluated,
    }
