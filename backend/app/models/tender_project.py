import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime
from sqlalchemy.orm import relationship
from backend.app.db.session import Base

class TenderProject(Base):
    """
    SQLAlchemy model representing a Tender Project in the database.
    """
    __tablename__ = "tender_projects"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String(255), nullable=False, index=True)
    tender_name = Column(String(255), nullable=True)
    source_label = Column(String(255), nullable=True)
    
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    
    # One-to-many relationship with Document
    documents = relationship("Document", back_populates="tender_project", cascade="all, delete-orphan")
