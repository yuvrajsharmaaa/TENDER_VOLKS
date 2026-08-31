import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship
from backend.app.db.session import Base

class TenderOutcome(Base):
    """
    SQLAlchemy model representing the public.tender_outcomes table.
    Decouples outcome labels (Won, Lost, Do Not Bid, Pending, Needs Review)
    from extracted tender_information data.
    """
    __tablename__ = "tender_outcomes"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tender_no = Column(String(255), unique=True, nullable=False, index=True)
    tender_id = Column(Integer, ForeignKey("tender_information.tender_id", ondelete="SET NULL"), nullable=True, index=True)
    outcome = Column(String(50), nullable=False, index=True)  # Won, Lost, Do Not Bid, Pending, Needs Review
    label_source = Column(String(100), nullable=False, default="outcome_labels_review_xlsx")
    split_status = Column(String(50), nullable=False, default="not_applicable")  # not_applicable, unsplit_pending_profile
    
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Optional relationship to TenderInformation
    tender_information = relationship(
        "TenderInformation",
        primaryjoin="foreign(TenderOutcome.tender_id) == TenderInformation.tender_id",
        uselist=False,
        viewonly=True
    )
