import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    String,
    Text,
    DateTime,
    Float,
    Boolean,
    Integer,
    ForeignKey,
    JSON,
)
from sqlalchemy.orm import relationship

from backend.app.db.session import Base


def utc_now():
    return datetime.now(timezone.utc)


class Bidder(Base):
    """
    SIH 26100 - Bidder / Vendor master profile.
    Stores bidder identity and government-registration information.
    """
    __tablename__ = "bidders"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    legal_name = Column(String(500), nullable=False, index=True)
    trade_name = Column(String(500), nullable=True)

    gstin = Column(String(50), nullable=True, index=True)
    pan = Column(String(50), nullable=True, index=True)
    udyam_number = Column(String(100), nullable=True, index=True)

    cin = Column(String(100), nullable=True)
    nsic_number = Column(String(100), nullable=True)
    startup_india_id = Column(String(100), nullable=True)

    is_msme = Column(Boolean, default=False, nullable=False)
    is_startup = Column(Boolean, default=False, nullable=False)
    is_mii_registered = Column(Boolean, default=False, nullable=False)

    blacklisted = Column(Boolean, default=False, nullable=False)
    debarred = Column(Boolean, default=False, nullable=False)

    profile_data = Column(JSON, nullable=True)

    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    submissions = relationship(
        "BidSubmission",
        back_populates="bidder",
        cascade="all, delete-orphan",
    )


class BidSubmission(Base):
    """
    Represents a bidder's submission against a tender.
    """
    __tablename__ = "bid_submissions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    bidder_id = Column(
        String(36),
        ForeignKey("bidders.id"),
        nullable=False,
        index=True,
    )

    tender_project_id = Column(
        String(36),
        ForeignKey("tender_projects.id"),
        nullable=False,
        index=True,
    )

    submission_reference = Column(String(255), nullable=True, index=True)

    status = Column(
        String(50),
        default="RECEIVED",
        nullable=False,
    )

    compliance_score = Column(Float, nullable=True)
    risk_level = Column(String(50), nullable=True)

    ai_recommendation = Column(Text, nullable=True)

    final_decision = Column(String(50), nullable=True)
    final_decision_by = Column(String(255), nullable=True)
    final_decision_reason = Column(Text, nullable=True)

    submitted_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    bidder = relationship("Bidder", back_populates="submissions")

    documents = relationship(
        "BidderDocument",
        back_populates="submission",
        cascade="all, delete-orphan",
    )

    compliance_results = relationship(
        "ComplianceResult",
        back_populates="submission",
        cascade="all, delete-orphan",
    )

    risk_assessment = relationship(
        "RiskAssessment",
        back_populates="submission",
        uselist=False,
        cascade="all, delete-orphan",
    )

    audit_events = relationship(
        "AuditEvent",
        back_populates="submission",
        cascade="all, delete-orphan",
    )


class BidderDocument(Base):
    """
    Document submitted by a bidder.
    Supports OCR/extraction and document-to-requirement mapping.
    """
    __tablename__ = "bidder_documents"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    submission_id = Column(
        String(36),
        ForeignKey("bid_submissions.id"),
        nullable=False,
        index=True,
    )

    document_name = Column(String(500), nullable=False)
    document_type = Column(String(100), nullable=True)

    storage_path = Column(String(1000), nullable=True)

    ocr_status = Column(String(50), default="PENDING", nullable=False)
    extraction_status = Column(String(50), default="PENDING", nullable=False)

    extracted_data = Column(JSON, nullable=True)

    document_confidence = Column(Float, nullable=True)

    is_valid = Column(Boolean, nullable=True)
    validation_reason = Column(Text, nullable=True)

    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    submission = relationship("BidSubmission", back_populates="documents")


class ComplianceRequirement(Base):
    """
    A compliance requirement extracted from the tender.
    """
    __tablename__ = "compliance_requirements"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    tender_project_id = Column(
        String(36),
        ForeignKey("tender_projects.id"),
        nullable=False,
        index=True,
    )

    requirement_code = Column(String(100), nullable=False, index=True)
    requirement_name = Column(String(500), nullable=False)

    category = Column(String(100), nullable=False)

    description = Column(Text, nullable=True)

    mandatory = Column(Boolean, default=True, nullable=False)

    threshold_value = Column(Float, nullable=True)
    threshold_unit = Column(String(100), nullable=True)

    verification_source = Column(String(255), nullable=True)

    rule_definition = Column(JSON, nullable=True)

    created_at = Column(DateTime, default=utc_now, nullable=False)


class VerificationCheck(Base):
    """
    Verification against bidder documents or an external authority/source.
    """
    __tablename__ = "verification_checks"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    submission_id = Column(
        String(36),
        ForeignKey("bid_submissions.id"),
        nullable=False,
        index=True,
    )

    requirement_code = Column(String(100), nullable=False, index=True)

    verification_type = Column(String(100), nullable=False)
    source = Column(String(255), nullable=True)

    status = Column(
        String(50),
        default="PENDING",
        nullable=False,
    )

    verified_value = Column(JSON, nullable=True)
    submitted_value = Column(JSON, nullable=True)

    confidence = Column(Float, nullable=True)

    mismatch_detected = Column(Boolean, default=False, nullable=False)
    explanation = Column(Text, nullable=True)

    evidence = Column(JSON, nullable=True)

    checked_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)


class ComplianceResult(Base):
    """
    Final requirement-level compliance result.
    """
    __tablename__ = "compliance_results"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    submission_id = Column(
        String(36),
        ForeignKey("bid_submissions.id"),
        nullable=False,
        index=True,
    )

    requirement_code = Column(String(100), nullable=False, index=True)
    requirement_name = Column(String(500), nullable=False)

    status = Column(
        String(50),
        default="NEEDS_REVIEW",
        nullable=False,
    )

    passed = Column(Boolean, nullable=True)
    mandatory = Column(Boolean, default=True, nullable=False)

    extracted_value = Column(JSON, nullable=True)
    expected_value = Column(JSON, nullable=True)

    confidence = Column(Float, nullable=True)

    reason = Column(Text, nullable=True)
    evidence = Column(JSON, nullable=True)

    ai_explanation = Column(Text, nullable=True)

    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    submission = relationship(
        "BidSubmission",
        back_populates="compliance_results",
    )


class RiskAssessment(Base):
    """
    Overall bid risk assessment.
    """
    __tablename__ = "risk_assessments"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    submission_id = Column(
        String(36),
        ForeignKey("bid_submissions.id"),
        nullable=False,
        unique=True,
        index=True,
    )

    risk_level = Column(String(50), nullable=False)

    risk_score = Column(Float, nullable=False)

    compliance_score = Column(Float, nullable=True)

    critical_issues = Column(Integer, default=0, nullable=False)
    warnings = Column(Integer, default=0, nullable=False)
    passed_checks = Column(Integer, default=0, nullable=False)

    risk_factors = Column(JSON, nullable=True)

    ai_summary = Column(Text, nullable=True)
    ai_recommendation = Column(Text, nullable=True)

    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    submission = relationship(
        "BidSubmission",
        back_populates="risk_assessment",
    )


class AuditEvent(Base):
    """
    Immutable-style audit record for every important verification/action.
    """
    __tablename__ = "audit_events"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    submission_id = Column(
        String(36),
        ForeignKey("bid_submissions.id"),
        nullable=True,
        index=True,
    )

    event_type = Column(String(100), nullable=False)
    actor = Column(String(255), nullable=True)

    description = Column(Text, nullable=False)

    source = Column(String(255), nullable=True)

    before_value = Column(JSON, nullable=True)
    after_value = Column(JSON, nullable=True)

    event_metadata = Column(JSON, nullable=True)

    created_at = Column(DateTime, default=utc_now, nullable=False)

    submission = relationship(
        "BidSubmission",
        back_populates="audit_events",
    )
import uuid
