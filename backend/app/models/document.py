import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from backend.app.db.session import Base

class Document(Base):
    """
    SQLAlchemy model representing an uploaded document metadata linked to a Tender Project.
    """
    __tablename__ = "documents"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tender_project_id = Column(String(36), ForeignKey("tender_projects.id", ondelete="CASCADE"), nullable=False, index=True)
    
    original_filename = Column(String(255), nullable=False)
    storage_bucket = Column(String(255), nullable=False)
    storage_key = Column(String(512), nullable=False)
    mime_type = Column(String(100), nullable=False)
    size_bytes = Column(Integer, nullable=False)
    upload_status = Column(String(50), default="uploaded", nullable=False)
    processing_status = Column(String(50), default="pending", nullable=False)
    document_type = Column(String(100), nullable=True)
    
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    
    # Relationship to TenderProject
    tender_project = relationship("TenderProject", back_populates="documents")
