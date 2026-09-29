import logging
logger = logging.getLogger("backend.app.api.routes.compliance")
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.models.bid_compliance import (
    Bidder,
    BidSubmission,
    BidderDocument,
    ComplianceRequirement,
    VerificationCheck,
    ComplianceResult,
    RiskAssessment,
    AuditEvent,
)
from backend.app.models.tender_project import TenderProject


router = APIRouter(
    prefix="/compliance",
    tags=["SIH Bid Compliance"],
)


def utc_now():
    return datetime.now(timezone.utc)


# ============================================================
# REQUEST SCHEMAS
# ============================================================

class BidderCreate(BaseModel):
    legal_name: str
    trade_name: Optional[str] = None
    gstin: Optional[str] = None
    pan: Optional[str] = None
    udyam_number: Optional[str] = None
    cin: Optional[str] = None
    nsic_number: Optional[str] = None
    startup_india_id: Optional[str] = None
    is_msme: bool = False
    is_startup: bool = False
    is_mii_registered: bool = False


class BidSubmissionCreate(BaseModel):
    bidder_id: str
    tender_project_id: str
    submission_reference: Optional[str] = None


class ComplianceRequirementCreate(BaseModel):
    tender_project_id: str
    requirement_code: str
    requirement_name: str
    category: str
    description: Optional[str] = None
    mandatory: bool = True
    threshold_value: Optional[float] = None
    threshold_unit: Optional[str] = None
    verification_source: Optional[str] = None
    rule_definition: Optional[dict] = None


class FinalDecisionRequest(BaseModel):
    decision: str
    officer_name: str
    reason: str


# ============================================================
# PROCUREMENT OFFICER FINAL DECISION
# ============================================================

@router.post("/bids/{submission_id}/final-decision")
def record_final_decision(
    submission_id: str,
    payload: FinalDecisionRequest,
    db: Session = Depends(get_db),
):
    """
    Record the Procurement Officer's final decision.

    Supported decisions:
      - QUALIFIED
      - DISQUALIFIED
      - CLARIFICATION_REQUIRED

    This endpoint does not automatically determine the decision.
    The Procurement Officer remains the final decision-maker.
    """

    allowed_decisions = {
        "QUALIFIED",
        "DISQUALIFIED",
        "CLARIFICATION_REQUIRED",
    }

    decision = payload.decision.strip().upper()

    if decision not in allowed_decisions:
        raise HTTPException(
            status_code=400,
            detail=(
                "Invalid decision. Allowed values: "
                "QUALIFIED, DISQUALIFIED, CLARIFICATION_REQUIRED."
            ),
        )

    officer_name = payload.officer_name.strip()
    reason = payload.reason.strip()

    if not officer_name:
        raise HTTPException(
            status_code=400,
            detail="Officer name is required.",
        )

    if not reason:
        raise HTTPException(
            status_code=400,
            detail="Decision reason is required.",
        )

    submission = (
        db.query(BidSubmission)
        .filter(BidSubmission.id == submission_id)
        .first()
    )

    if not submission:
        raise HTTPException(
            status_code=404,
            detail="Bid submission not found",
        )

    previous_decision = submission.final_decision
    previous_status = submission.status

    submission.final_decision = decision
    submission.final_decision_by = officer_name
    submission.final_decision_reason = reason

    if decision == "QUALIFIED":
        submission.status = "QUALIFIED"
    elif decision == "DISQUALIFIED":
        submission.status = "DISQUALIFIED"
    else:
        submission.status = "CLARIFICATION_REQUIRED"

    audit_event = AuditEvent(
        submission_id=submission_id,
        event_type="FINAL_DECISION",
        actor=officer_name,
        description=(
            f"Procurement Officer recorded final decision: {decision}. "
            f"Reason: {reason}"
        ),
        source="PROCUREMENT_OFFICER",
        before_value={
            "final_decision": previous_decision,
            "status": previous_status,
        },
        after_value={
            "final_decision": decision,
            "status": submission.status,
            "final_decision_by": officer_name,
            "final_decision_reason": reason,
        },
        event_metadata={
            "decision_timestamp": utc_now().isoformat(),
        },
    )

    db.add(audit_event)
    db.commit()
    db.refresh(submission)

    return {
        "submission_id": submission.id,
        "status": submission.status,
        "final_decision": submission.final_decision,
        "final_decision_by": submission.final_decision_by,
        "final_decision_reason": submission.final_decision_reason,
        "recorded_at": utc_now().isoformat(),
    }


# ============================================================
# BIDDER
# ============================================================

@router.post("/bidders", status_code=201)
def create_bidder(
    payload: BidderCreate,
    db: Session = Depends(get_db),
):
    """
    Create a bidder/vendor master profile.
    """

    bidder = Bidder(
        id=str(uuid.uuid4()),
        legal_name=payload.legal_name,
        trade_name=payload.trade_name,
        gstin=payload.gstin,
        pan=payload.pan,
        udyam_number=payload.udyam_number,
        cin=payload.cin,
        nsic_number=payload.nsic_number,
        startup_india_id=payload.startup_india_id,
        is_msme=payload.is_msme,
        is_startup=payload.is_startup,
        is_mii_registered=payload.is_mii_registered,
        created_at=utc_now(),
        updated_at=utc_now(),
    )

    db.add(bidder)

    try:
        db.commit()
        db.refresh(bidder)
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Failed to create bidder",
        )

    return {
        "id": bidder.id,
        "legal_name": bidder.legal_name,
        "trade_name": bidder.trade_name,
        "gstin": bidder.gstin,
        "pan": bidder.pan,
        "udyam_number": bidder.udyam_number,
        "cin": bidder.cin,
        "nsic_number": bidder.nsic_number,
        "startup_india_id": bidder.startup_india_id,
        "is_msme": bidder.is_msme,
        "is_startup": bidder.is_startup,
        "is_mii_registered": bidder.is_mii_registered,
        "blacklisted": bidder.blacklisted,
        "debarred": bidder.debarred,
        "created_at": bidder.created_at,
    }


@router.get("/bidders/{bidder_id}")
def get_bidder(
    bidder_id: str,
    db: Session = Depends(get_db),
):
    bidder = (
        db.query(Bidder)
        .filter(Bidder.id == bidder_id)
        .first()
    )

    if not bidder:
        raise HTTPException(
            status_code=404,
            detail="Bidder not found",
        )

    return {
        "id": bidder.id,
        "legal_name": bidder.legal_name,
        "trade_name": bidder.trade_name,
        "gstin": bidder.gstin,
        "pan": bidder.pan,
        "udyam_number": bidder.udyam_number,
        "cin": bidder.cin,
        "nsic_number": bidder.nsic_number,
        "startup_india_id": bidder.startup_india_id,
        "is_msme": bidder.is_msme,
        "is_startup": bidder.is_startup,
        "is_mii_registered": bidder.is_mii_registered,
        "blacklisted": bidder.blacklisted,
        "debarred": bidder.debarred,
        "profile_data": bidder.profile_data,
        "created_at": bidder.created_at,
        "updated_at": bidder.updated_at,
    }


# ============================================================
# BID SUBMISSION
# ============================================================

@router.post("/bids", status_code=201)
def create_bid_submission(
    payload: BidSubmissionCreate,
    db: Session = Depends(get_db),
):
    """
    Create a bidder submission against an existing tender.
    """

    bidder = (
        db.query(Bidder)
        .filter(Bidder.id == payload.bidder_id)
        .first()
    )

    if not bidder:
        raise HTTPException(
            status_code=404,
            detail="Bidder not found",
        )

    tender = (
        db.query(TenderProject)
        .filter(TenderProject.id == payload.tender_project_id)
        .first()
    )

    if not tender:
        raise HTTPException(
            status_code=404,
            detail="Tender project not found",
        )

    submission = BidSubmission(
        id=str(uuid.uuid4()),
        bidder_id=payload.bidder_id,
        tender_project_id=payload.tender_project_id,
        submission_reference=payload.submission_reference,
        status="RECEIVED",
        created_at=utc_now(),
        updated_at=utc_now(),
    )

    db.add(submission)

    audit = AuditEvent(
        id=str(uuid.uuid4()),
        submission_id=submission.id,
        event_type="BID_SUBMISSION_CREATED",
        actor="system",
        description="Bid submission created",
        source="compliance_api",
        after_value={
            "status": "RECEIVED",
            "bidder_id": payload.bidder_id,
            "tender_project_id": payload.tender_project_id,
        },
        created_at=utc_now(),
    )

    db.add(audit)

    try:
        db.commit()
        db.refresh(submission)
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Failed to create bid submission",
        )

    return {
        "id": submission.id,
        "bidder_id": submission.bidder_id,
        "tender_project_id": submission.tender_project_id,
        "submission_reference": submission.submission_reference,
        "status": submission.status,
        "compliance_score": submission.compliance_score,
        "risk_level": submission.risk_level,
        "final_decision": submission.final_decision,
        "created_at": submission.created_at,
    }


@router.get("/bids/{submission_id}")
def get_bid_submission(
    submission_id: str,
    db: Session = Depends(get_db),
):
    submission = (
        db.query(BidSubmission)
        .filter(BidSubmission.id == submission_id)
        .first()
    )

    if not submission:
        raise HTTPException(
            status_code=404,
            detail="Bid submission not found",
        )

    bidder = submission.bidder

    return {
        "id": submission.id,
        "status": submission.status,
        "submission_reference": submission.submission_reference,
        "bidder": {
            "id": bidder.id,
            "legal_name": bidder.legal_name,
            "trade_name": bidder.trade_name,
            "gstin": bidder.gstin,
            "pan": bidder.pan,
            "udyam_number": bidder.udyam_number,
        },
        "tender_project_id": submission.tender_project_id,
        "compliance_score": submission.compliance_score,
        "risk_level": submission.risk_level,
        "ai_recommendation": submission.ai_recommendation,
        "final_decision": submission.final_decision,
        "final_decision_by": submission.final_decision_by,
        "final_decision_reason": submission.final_decision_reason,
        "submitted_at": submission.submitted_at,
        "created_at": submission.created_at,
    }


# ============================================================
# BIDDER DOCUMENTS
# ============================================================

@router.post("/bids/{submission_id}/documents", status_code=201)
def register_bidder_document(
    submission_id: str,
    document_name: str,
    document_type: Optional[str] = None,
    storage_path: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    Register a bidder document.

    Actual file/OCR processing will be connected to the existing
    OCR pipeline in the next phase.
    """

    submission = (
        db.query(BidSubmission)
        .filter(BidSubmission.id == submission_id)
        .first()
    )

    if not submission:
        raise HTTPException(
            status_code=404,
            detail="Bid submission not found",
        )

    document = BidderDocument(
        id=str(uuid.uuid4()),
        submission_id=submission_id,
        document_name=document_name,
        document_type=document_type,
        storage_path=storage_path,
        ocr_status="PENDING",
        extraction_status="PENDING",
        created_at=utc_now(),
        updated_at=utc_now(),
    )

    db.add(document)

    audit = AuditEvent(
        id=str(uuid.uuid4()),
        submission_id=submission_id,
        event_type="BIDDER_DOCUMENT_REGISTERED",
        actor="system",
        description=f"Bidder document registered: {document_name}",
        source="compliance_api",
        after_value={
            "document_id": document.id,
            "document_name": document_name,
            "document_type": document_type,
        },
        created_at=utc_now(),
    )

    db.add(audit)

    try:
        db.commit()
        db.refresh(document)
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Failed to register bidder document",
        )

    return {
        "id": document.id,
        "submission_id": document.submission_id,
        "document_name": document.document_name,
        "document_type": document.document_type,
        "storage_path": document.storage_path,
        "ocr_status": document.ocr_status,
        "extraction_status": document.extraction_status,
        "document_confidence": document.document_confidence,
        "is_valid": document.is_valid,
        "created_at": document.created_at,
    }


@router.get("/bids/{submission_id}/documents")
def list_bidder_documents(
    submission_id: str,
    db: Session = Depends(get_db),
):
    submission = (
        db.query(BidSubmission)
        .filter(BidSubmission.id == submission_id)
        .first()
    )

    if not submission:
        raise HTTPException(
            status_code=404,
            detail="Bid submission not found",
        )

    documents = (
        db.query(BidderDocument)
        .filter(BidderDocument.submission_id == submission_id)
        .order_by(BidderDocument.created_at.desc())
        .all()
    )

    return [
        {
            "id": d.id,
            "document_name": d.document_name,
            "document_type": d.document_type,
            "storage_path": d.storage_path,
            "ocr_status": d.ocr_status,
            "extraction_status": d.extraction_status,
            "extracted_data": d.extracted_data,
            "document_confidence": d.document_confidence,
            "is_valid": d.is_valid,
            "validation_reason": d.validation_reason,
            "created_at": d.created_at,
        }
        for d in documents
    ]


# ============================================================
# TENDER REQUIREMENTS
# ============================================================

@router.post("/requirements", status_code=201)
def create_compliance_requirement(
    payload: ComplianceRequirementCreate,
    db: Session = Depends(get_db),
):
    tender = (
        db.query(TenderProject)
        .filter(TenderProject.id == payload.tender_project_id)
        .first()
    )

    if not tender:
        raise HTTPException(
            status_code=404,
            detail="Tender project not found",
        )

    requirement = ComplianceRequirement(
        id=str(uuid.uuid4()),
        tender_project_id=payload.tender_project_id,
        requirement_code=payload.requirement_code,
        requirement_name=payload.requirement_name,
        category=payload.category,
        description=payload.description,
        mandatory=payload.mandatory,
        threshold_value=payload.threshold_value,
        threshold_unit=payload.threshold_unit,
        verification_source=payload.verification_source,
        rule_definition=payload.rule_definition,
        created_at=utc_now(),
    )

    db.add(requirement)

    try:
        db.commit()
        db.refresh(requirement)
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Failed to create compliance requirement",
        )

    return {
        "id": requirement.id,
        "tender_project_id": requirement.tender_project_id,
        "requirement_code": requirement.requirement_code,
        "requirement_name": requirement.requirement_name,
        "category": requirement.category,
        "description": requirement.description,
        "mandatory": requirement.mandatory,
        "threshold_value": requirement.threshold_value,
        "threshold_unit": requirement.threshold_unit,
        "verification_source": requirement.verification_source,
        "rule_definition": requirement.rule_definition,
    }


@router.get("/tenders/{tender_project_id}/requirements")
def list_requirements(
    tender_project_id: str,
    db: Session = Depends(get_db),
):
    requirements = (
        db.query(ComplianceRequirement)
        .filter(
            ComplianceRequirement.tender_project_id
            == tender_project_id
        )
        .order_by(ComplianceRequirement.created_at.asc())
        .all()
    )

    return [
        {
            "id": r.id,
            "requirement_code": r.requirement_code,
            "requirement_name": r.requirement_name,
            "category": r.category,
            "description": r.description,
            "mandatory": r.mandatory,
            "threshold_value": r.threshold_value,
            "threshold_unit": r.threshold_unit,
            "verification_source": r.verification_source,
            "rule_definition": r.rule_definition,
        }
        for r in requirements
    ]


# ============================================================
# COMPLIANCE DASHBOARD
# ============================================================

@router.get("/bids/{submission_id}/dashboard")
def get_compliance_dashboard(
    submission_id: str,
    db: Session = Depends(get_db),
):
    submission = (
        db.query(BidSubmission)
        .filter(BidSubmission.id == submission_id)
        .first()
    )

    if not submission:
        raise HTTPException(
            status_code=404,
            detail="Bid submission not found",
        )

    results = (
        db.query(ComplianceResult)
        .filter(
            ComplianceResult.submission_id == submission_id,
            ~ComplianceResult.requirement_code.like("EXTERNAL_%"),
        )
        .all()
    )

    documents = (
        db.query(BidderDocument)
        .filter(
            BidderDocument.submission_id == submission_id
        )
        .all()
    )

    verifications = (
        db.query(VerificationCheck)
        .filter(
            VerificationCheck.submission_id == submission_id
        )
        .all()
    )

    risk = (
        db.query(RiskAssessment)
        .filter(
            RiskAssessment.submission_id == submission_id
        )
        .first()
    )

    return {
        "submission": {
            "id": submission.id,
            "status": submission.status,
            "compliance_score": submission.compliance_score,
            "risk_level": submission.risk_level,
            "final_decision": submission.final_decision,
        },
        "documents": {
            "total": len(documents),
            "processed": sum(
                1 for d in documents
                if d.extraction_status == "COMPLETED"
            ),
            "valid": sum(
                1 for d in documents
                if d.is_valid is True
            ),
        },
        "compliance": {
            "total": len(results),
            "passed": sum(
                1 for r in results
                if r.passed is True
            ),
            "failed": sum(
                1 for r in results
                if r.status == "FAILED"
            ),
            "needs_review": sum(
                1 for r in results
                if r.status == "NEEDS_REVIEW"
            ),
            "results": [
                {
                    "requirement_code": r.requirement_code,
                    "requirement_name": r.requirement_name,
                    "status": r.status,
                    "passed": r.passed,
                    "mandatory": r.mandatory,
                    "confidence": r.confidence,
                    "reason": r.reason,
                    "evidence": r.evidence,
                    "ai_explanation": r.ai_explanation,
                }
                for r in results
            ],
        },
        "verification": {
            "total": len(verifications),
            "passed": sum(
                1 for v in verifications
                if v.status == "VERIFIED"
            ),
            "failed": sum(
                1 for v in verifications
                if v.status == "FAILED"
            ),
            "mismatches": sum(
                1 for v in verifications
                if v.mismatch_detected is True
            ),
        },
        "risk": (
            {
                "risk_level": risk.risk_level,
                "risk_score": risk.risk_score,
                "compliance_score": risk.compliance_score,
                "critical_issues": risk.critical_issues,
                "warnings": risk.warnings,
                "passed_checks": risk.passed_checks,
                "risk_factors": risk.risk_factors,
                "ai_summary": risk.ai_summary,
                "ai_recommendation": risk.ai_recommendation,
                "ai_analysis": (
                    risk.risk_factors.get("ai_analysis")
                    if isinstance(risk.risk_factors, dict)
                    else None
                ),
            }
            if risk
            else None
        ),
    }


# ============================================================
# AUDIT TRAIL
# ============================================================

@router.get("/bids/{submission_id}/audit")
def get_audit_trail(
    submission_id: str,
    db: Session = Depends(get_db),
):
    events = (
        db.query(AuditEvent)
        .filter(
            AuditEvent.submission_id == submission_id
        )
        .order_by(AuditEvent.created_at.desc())
        .all()
    )

    return [
        {
            "id": event.id,
            "event_type": event.event_type,
            "actor": event.actor,
            "description": event.description,
            "source": event.source,
            "before_value": event.before_value,
            "after_value": event.after_value,
            "event_metadata": event.event_metadata,
            "created_at": event.created_at,
        }
        for event in events
    ]


# ==============================================================================
# BIDDER DOCUMENT UPLOAD + OCR
# ==============================================================================

from fastapi import UploadFile, File, Form


@router.post("/bids/{submission_id}/documents/upload", status_code=201)
async def upload_bidder_document(
    submission_id: str,
    file: UploadFile = File(...),
    document_type: str = Form("OTHER"),
    db: Session = Depends(get_db)
):
    """
    Upload a bidder compliance document, store it in MinIO,
    register it as a BidderDocument, create an OCR job and
    dispatch the existing OCR engine through Celery.
    """
    import uuid
    from pathlib import Path

    from backend.app.core.constants import STORAGE_ROOT, JobStatus
    from backend.app.models.bid_compliance import (
        BidSubmission,
        BidderDocument,
        AuditEvent,
    )
    from backend.app.services.storage import (
        upload_file_to_minio,
        StorageError,
    )
    from backend.app.repositories.job_repository import create_job
    from backend.app.api.routes.tenders import _run_bidder_document_ocr

    # ------------------------------------------------------------------
    # 1. Validate submission
    # ------------------------------------------------------------------
    submission = db.query(BidSubmission).filter(
        BidSubmission.id == submission_id
    ).first()

    if not submission:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "submission_not_found",
                "message": f"Bid submission {submission_id} not found"
            }
        )

    # ------------------------------------------------------------------
    # 2. Validate uploaded file
    # ------------------------------------------------------------------
    filename = Path(file.filename or "document.pdf").name

    if not filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail={
                "error": "invalid_file_type",
                "message": "Only PDF bidder documents are currently supported."
            }
        )

    if file.content_type not in (
        "application/pdf",
        "application/octet-stream",
        None,
    ):
        raise HTTPException(
            status_code=400,
            detail={
                "error": "invalid_content_type",
                "message": f"Unsupported content type: {file.content_type}"
            }
        )

    file_bytes = await file.read()

    MAX_FILE_SIZE = 20 * 1024 * 1024

    if not file_bytes:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "empty_file",
                "message": "Uploaded file is empty."
            }
        )

    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail={
                "error": "file_too_large",
                "message": "Maximum bidder document size is 20 MB."
            }
        )

    # ------------------------------------------------------------------
    # 3. Create document UUID
    # ------------------------------------------------------------------
    document_id = str(uuid.uuid4())

    # Keep object IDs unique while giving MinIO a meaningful hierarchy.
    storage_key = (
        f"bidder/"
        f"{submission_id}/"
        f"documents/"
        f"{document_id}/"
        f"{filename}"
    )

    # ------------------------------------------------------------------
    # 4. Upload to MinIO
    # ------------------------------------------------------------------
    try:
        upload_file_to_minio(
            file_bytes=file_bytes,
            content_type="application/pdf",
            original_filename=filename,
            custom_key=storage_key
        )
    except StorageError as e:
        logger.error(
            f"[BIDDER_UPLOAD] MinIO upload failed: {e}",
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail={
                "error": "storage_error",
                "message": "Failed to store bidder document."
            }
        )

    # ------------------------------------------------------------------
    # 5. Persist local copy for the Celery worker
    # ------------------------------------------------------------------
    job_dir = STORAGE_ROOT / "jobs" / document_id
    job_dir.mkdir(parents=True, exist_ok=True)

    pdf_path = job_dir / "original.pdf"

    try:
        with open(pdf_path, "wb") as f:
            f.write(file_bytes)
    except Exception as e:
        logger.error(
            f"[BIDDER_UPLOAD] Local document persistence failed: {e}",
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail={
                "error": "local_storage_error",
                "message": "Failed to prepare bidder document for OCR."
            }
        )

    # ------------------------------------------------------------------
    # 6. Create BidderDocument
    # ------------------------------------------------------------------
    bidder_document = BidderDocument(
        id=document_id,
        submission_id=submission_id,
        document_name=filename,
        document_type=document_type.upper(),
        storage_path=storage_key,
        ocr_status="QUEUED",
        extraction_status="PENDING",
        is_valid=None,
    )

    db.add(bidder_document)

    # ------------------------------------------------------------------
    # 7. Create Job record
    # ------------------------------------------------------------------
    try:
        create_job(
            job_id=document_id,
            filename=filename,
            pdf_path=str(pdf_path),
            status=JobStatus.QUEUED,
            db=db
        )

        db.commit()
        db.refresh(bidder_document)

    except Exception as e:
        db.rollback()

        logger.error(
            f"[BIDDER_UPLOAD] Database persistence failed: {e}",
            exc_info=True
        )

        raise HTTPException(
            status_code=500,
            detail={
                "error": "database_error",
                "message": "Failed to register bidder document."
            }
        )

    # ------------------------------------------------------------------
    # 8. Audit event
    # ------------------------------------------------------------------
    audit = AuditEvent(
        submission_id=submission_id,
        event_type="BIDDER_DOCUMENT_UPLOADED",
        actor="system",
        description=(
            f"Bidder compliance document '{filename}' uploaded "
            f"and queued for OCR."
        ),
        source="compliance_upload_api",
        event_metadata={
            "document_id": document_id,
            "document_type": document_type.upper(),
            "storage_key": storage_key,
            "job_id": document_id,
        },
    )

    db.add(audit)
    db.commit()

    # ------------------------------------------------------------------
    # 9. Dispatch OCR
    # ------------------------------------------------------------------
    try:
        _run_bidder_document_ocr.delay(document_id)
    except Exception as e:
        logger.error(
            f"[BIDDER_UPLOAD] Failed to queue OCR task: {e}",
            exc_info=True
        )

        bidder_document.ocr_status = "FAILED"
        bidder_document.extraction_status = "FAILED"
        bidder_document.validation_reason = (
            f"OCR task could not be queued: {e}"
        )

        db.commit()

        raise HTTPException(
            status_code=500,
            detail={
                "error": "queue_error",
                "message": "Document was stored but OCR could not be queued."
            }
        )

    return {
        "document_id": bidder_document.id,
        "submission_id": submission_id,
        "document_name": bidder_document.document_name,
        "document_type": bidder_document.document_type,
        "storage_path": bidder_document.storage_path,
        "ocr_status": bidder_document.ocr_status,
        "extraction_status": bidder_document.extraction_status,
        "job_id": document_id,
        "message": "Bidder document uploaded and queued for OCR processing."
    }


# ==============================================================================
# COMPLIANCE EVALUATION
# ==============================================================================

@router.post("/bids/{submission_id}/evaluate")
async def evaluate_bid_compliance(
    submission_id: str,
    db: Session = Depends(get_db),
):
    """
    Runs the bidder compliance engine against extracted bidder documents,
    bidder profile data and eligibility flags.
    """
    from backend.app.services.bid_compliance_engine import evaluate_submission

    try:
        return evaluate_submission(
            db=db,
            submission_id=submission_id,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=404,
            detail=str(e),
        )
    except Exception as e:
        logger.error(
            f"Compliance evaluation failed for {submission_id}: {e}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail={
                "error": "compliance_evaluation_failed",
                "message": str(e),
            },
        )


# ==============================================================================
# EXTERNAL VERIFICATION
# ==============================================================================

@router.post("/bids/{submission_id}/verify-external")
async def verify_external_sources(
    submission_id: str,
    db: Session = Depends(get_db),
):
    """
    Runs all applicable external verification adapters for a bidder.
    Demo adapters are used where live government APIs are not configured.
    """

    from backend.app.models.bid_compliance import (
        BidSubmission,
        Bidder,
        VerificationCheck,
        ComplianceResult,
        AuditEvent,
    )
    from backend.app.services.external_verification import verify_bidder

    submission = db.query(BidSubmission).filter(
        BidSubmission.id == submission_id
    ).first()

    if not submission:
        raise HTTPException(
            status_code=404,
            detail="Bid submission not found"
        )

    bidder = db.query(Bidder).filter(
        Bidder.id == submission.bidder_id
    ).first()

    if not bidder:
        raise HTTPException(
            status_code=404,
            detail="Bidder not found"
        )

    responses = verify_bidder(bidder)
    checks = []

    for response in responses:

        code = f"EXTERNAL_{response.source}"

        # Avoid duplicate records when re-running verification.
        check = db.query(VerificationCheck).filter(
            VerificationCheck.submission_id == submission_id,
            VerificationCheck.requirement_code == code,
        ).first()

        if not check:
            check = VerificationCheck(
                submission_id=submission_id,
                requirement_code=code,
            )
            db.add(check)

        check.verification_type = "EXTERNAL_PORTAL"
        check.source = response.source
        check.status = response.status
        check.verified_value = response.verified_value
        check.submitted_value = response.identifier
        check.confidence = response.confidence
        check.mismatch_detected = response.status in {
            "FAILED",
            "NOT_FOUND",
        }
        check.explanation = response.explanation
        check.evidence = response.evidence

        checks.append({
            "requirement_code": code,
            "source": response.source,
            "identifier": response.identifier,
            "status": response.status,
            "confidence": response.confidence,
            "verified_value": response.verified_value,
            "explanation": response.explanation,
        })

    # Convert external verification results into ComplianceResult records.
    # NOT_CONFIGURED sources are retained for transparency but excluded
    # from the mandatory compliance score because the adapter did not run.
    for response in responses:
        code = f"EXTERNAL_{response.source}"

        passed = response.status == "VERIFIED"

        if response.status == "VERIFIED":
            result_status = "QUALIFIED"
        elif response.status == "FAILED":
            result_status = "DISQUALIFIED"
        elif response.status == "NOT_FOUND":
            result_status = "NEEDS_REVIEW"
        else:
            result_status = "NEEDS_REVIEW"

        result = db.query(ComplianceResult).filter(
            ComplianceResult.submission_id == submission_id,
            ComplianceResult.requirement_code == code,
        ).first()

        if not result:
            result = ComplianceResult(
                submission_id=submission_id,
                requirement_code=code,
            )
            db.add(result)

        result.requirement_name = (
            f"External {response.source} Verification"
        )
        result.status = result_status
        result.passed = passed
        result.mandatory = response.status != "NOT_CONFIGURED"
        result.extracted_value = response.identifier
        result.expected_value = response.verified_value
        result.confidence = response.confidence
        result.reason = response.explanation
        result.evidence = response.evidence
        result.ai_explanation = (
            f"External verification via {response.source}: "
            f"{response.explanation}"
        )

    audit = AuditEvent(
        submission_id=submission_id,
        event_type="EXTERNAL_VERIFICATION_COMPLETED",
        actor="system",
        description=(
            f"External verification completed across "
            f"{len(responses)} configured sources."
        ),
        source="external_verification_engine",
        event_metadata={
            "sources": [response.source for response in responses],
            "environment": "DEMO",
        },
    )

    db.add(audit)
    db.flush()

    # Re-run the common compliance/risk calculation so external
    # verification participates in the overall assessment.
    from backend.app.services.bid_compliance_engine import evaluate_submission

    evaluation = evaluate_submission(
        db=db,
        submission_id=submission_id,
    )

    return {
        "submission_id": submission_id,
        "environment": "DEMO",
        "total_checks": len(checks),
        "checks": checks,
        "evaluation": evaluation,
    }


# ==============================================================================
# TENDER REQUIREMENT GENERATION
# ==============================================================================

@router.post("/tenders/{tender_project_id}/generate-requirements")
async def generate_tender_compliance_requirements(
    tender_project_id: str,
    db: Session = Depends(get_db),
):
    """
    Generates normalized compliance requirements from the tender's
    existing OCR/extraction output.
    """
    from backend.app.services.tender_requirement_engine import (
        generate_tender_requirements,
    )

    try:
        return generate_tender_requirements(
            db=db,
            tender_project_id=tender_project_id,
        )

    except ValueError as e:
        raise HTTPException(
            status_code=404,
            detail=str(e),
        )

    except Exception as e:
        logger.error(
            f"Tender requirement generation failed: {e}",
            exc_info=True,
        )

        raise HTTPException(
            status_code=500,
            detail={
                "error": "requirement_generation_failed",
                "message": str(e),
            },
        )


@router.post("/bids/{submission_id}/evaluate-full")
def evaluate_full_bid_compliance(
    submission_id: str,
    db: Session = Depends(get_db),
):
    from backend.app.services.tender_bid_compliance import evaluate_tender_requirements
    from backend.app.services.bid_compliance_engine import evaluate_submission
    from backend.app.services.bid_compliance_ai_service import BidComplianceAIService
    from backend.app.models.bid_compliance import (
        BidSubmission,
        RiskAssessment,
    )

    # 1. Evaluate tender-specific requirements
    tender_result = evaluate_tender_requirements(
        db=db,
        submission_id=submission_id,
    )

    # 2. Run existing document/external verification engine
    engine_result = evaluate_submission(
        db=db,
        submission_id=submission_id,
    )

    tender_results = tender_result.get("results", [])
    external_checks = engine_result.get("checks", [])

    # External verification can resolve tender checks that initially
    # appear as NEEDS_REVIEW, e.g. GST, blacklist and debarment.
    external_by_code = {
        check.get("requirement_code"): check
        for check in external_checks
    }

    merged_checks = []

    for result in tender_results:
        item = dict(result)
        code = item.get("requirement_code")
        external = external_by_code.get(code)

        if external and external.get("status") == "PASSED":
            item["status"] = "PASSED"
            item["passed"] = True
            item["reason"] = (
                "Tender requirement verified by the external verification engine."
            )
            item["verification"] = external

        merged_checks.append(item)

    # Add any external checks that are not already represented by
    # a tender requirement.
    tender_codes = {
        item.get("requirement_code")
        for item in merged_checks
    }

    for check in external_checks:
        code = check.get("requirement_code")
        if code not in tender_codes:
            merged_checks.append({
                "requirement_code": code,
                "status": check.get("status", "NEEDS_REVIEW"),
                "passed": check.get("status") == "PASSED",
                "mandatory": True,
                "reason": check.get("explanation"),
                "verification": check,
            })

    # 3. Calculate the final compliance result from the merged checks.
    passed_checks = [
        x for x in merged_checks
        if x.get("status") == "PASSED"
    ]

    failed_checks = [
        x for x in merged_checks
        if x.get("status") == "FAILED"
    ]

    review_checks = [
        x for x in merged_checks
        if x.get("status") == "NEEDS_REVIEW"
    ]

    mandatory_checks = [
        x for x in merged_checks
        if x.get("mandatory", True)
    ]

    mandatory_passed = [
        x for x in mandatory_checks
        if x.get("status") == "PASSED"
    ]

    mandatory_failed = [
        x for x in mandatory_checks
        if x.get("status") == "FAILED"
    ]

    mandatory_review = [
        x for x in mandatory_checks
        if x.get("status") == "NEEDS_REVIEW"
    ]

    mandatory_total = len(mandatory_checks)

    compliance_score = round(
        (len(mandatory_passed) / mandatory_total) * 100,
        2,
    ) if mandatory_total else 0.0

    # Mandatory failure takes priority over review status.
    if mandatory_failed:
        risk_level = "HIGH"
    elif mandatory_review:
        risk_level = "MEDIUM"
    else:
        risk_level = "LOW"

    if mandatory_failed:
        failed_names = [
            x.get("requirement_name", x.get("requirement_code"))
            for x in mandatory_failed
        ]
        recommendation = (
            "Mandatory compliance issues remain unresolved: "
            + ", ".join(failed_names)
            + ". Procurement Officer review is required before final decision."
        )
    elif mandatory_review:
        review_names = [
            x.get("requirement_name", x.get("requirement_code"))
            for x in mandatory_review
        ]
        recommendation = (
            "Mandatory requirements still need verification: "
            + ", ".join(review_names)
            + ". Procurement Officer review is required before final decision."
        )
    else:
        recommendation = (
            "All evaluated mandatory requirements passed. "
            "Procurement Officer should complete the final decision."
        )

    overall_result = {
        "submission_id": submission_id,
        "compliance_score": compliance_score,
        "risk_level": risk_level,
        "passed": len(passed_checks),
        "failed": len(failed_checks),
        "needs_review": len(review_checks),
        "total": len(merged_checks),
        "mandatory_passed": len(mandatory_passed),
        "mandatory_failed": len(mandatory_failed),
        "mandatory_needs_review": len(mandatory_review),
        "mandatory_total": mandatory_total,
        "recommendation": recommendation,
        "checks": merged_checks,
    }

    # 4. Generate AI explanation from the deterministic compliance findings.
    compliance_ai = BidComplianceAIService()

    ai_analysis = compliance_ai.explain(
        submission_id=submission_id,
        compliance_score=compliance_score,
        risk_level=risk_level,
        checks=merged_checks,
    )

    overall_result["ai_analysis"] = ai_analysis

    # 5. Persist the final score/risk to the bid submission.
    submission = (
        db.query(BidSubmission)
        .filter(BidSubmission.id == submission_id)
        .first()
    )

    if submission:
        submission.compliance_score = compliance_score
        submission.risk_level = risk_level
        submission.ai_recommendation = recommendation

    # 5. Persist the final risk assessment.
    risk = (
        db.query(RiskAssessment)
        .filter(RiskAssessment.submission_id == submission_id)
        .first()
    )

    if risk:
        risk.compliance_score = compliance_score
        risk.risk_level = risk_level
        risk.risk_score = round(100.0 - compliance_score, 2)
        risk.critical_issues = len(mandatory_failed)
        risk.warnings = len(mandatory_review)
        risk.passed_checks = len(mandatory_passed)
        risk.risk_factors = {
            "mandatory_failed": len(mandatory_failed),
            "mandatory_review": len(mandatory_review),
            "mandatory_passed": len(mandatory_passed),
            "mandatory_total": mandatory_total,
            "optional_failed": len([
                x for x in failed_checks
                if not x.get("mandatory", True)
            ]),
            "optional_review": len([
                x for x in review_checks
                if not x.get("mandatory", True)
            ]),
            "ai_analysis": ai_analysis,
        }
        risk.ai_summary = (
            f"Full bid compliance evaluation completed. "
            f"{len(mandatory_passed)}/{mandatory_total} mandatory checks passed."
        )
        risk.ai_recommendation = recommendation

    db.commit()

    return {
        "submission_id": submission_id,
        "tender_requirements": tender_result,
        "overall_compliance": overall_result,
    }
