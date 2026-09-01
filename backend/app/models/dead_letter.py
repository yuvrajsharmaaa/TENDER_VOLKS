import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, Text, Integer, JSON
from backend.app.db.session import Base

class DeadLetterRecord(Base):
    """
    SQLAlchemy model representing a dead-lettered job/task in PostgreSQL.
    """
    __tablename__ = "dead_letter_records"
    
    dlq_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    task_id = Column(String(255), nullable=False, index=True)
    task_name = Column(String(255), nullable=False, index=True)
    payload = Column(JSON, nullable=True)
    error_type = Column(String(255), nullable=False)
    error_message = Column(Text, nullable=False)
    stack_trace = Column(Text, nullable=True)
    attempt_count = Column(Integer, default=1, nullable=False)
    status = Column(String(50), default="PENDING", nullable=False, index=True)
    resolution_notes = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
