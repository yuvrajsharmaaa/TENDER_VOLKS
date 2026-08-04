import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, Text
from backend.app.db.session import Base

class Job(Base):
    """
    SQLAlchemy model representing an automated page-aware tender processing job.
    """
    __tablename__ = "jobs"
    
    job_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    status = Column(String(50), default="PENDING", nullable=False)
    file_path = Column(String(512), nullable=True)
    email_recipient = Column(String(255), nullable=True)
    error_message = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
