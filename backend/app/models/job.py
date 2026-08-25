import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, Text, Integer
from backend.app.db.session import Base
from backend.app.core.constants import JobStatus

class Job(Base):
    """
    SQLAlchemy model representing a tender processing job in PostgreSQL.
    """
    __tablename__ = "jobs"
    
    job_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    status = Column(String(50), default=JobStatus.PENDING.value, nullable=False, index=True)
    original_filename = Column(String(255), nullable=True)
    file_path = Column(String(512), nullable=True)
    pdf_path = Column(String(512), nullable=True)
    result_path = Column(String(512), nullable=True)
    page_count = Column(Integer, nullable=True)
    error_message = Column(Text, nullable=True)
    retry_count = Column(Integer, default=0, nullable=False)
    email_recipient = Column(String(255), nullable=True)
    tender_id = Column(String(255), nullable=True)
    
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

