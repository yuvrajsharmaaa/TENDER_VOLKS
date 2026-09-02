from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Numeric, Boolean, Date, DateTime, Text
from backend.app.db.session import Base


class PQRCredential(Base):
    """
    SQLAlchemy model representing the pqr_credentials table.
    Stores historical past performance records and resolved local document paths.
    """
    __tablename__ = "pqr_credentials"

    id = Column(Integer, primary_key=True, autoincrement=False)
    team_id = Column(Integer, nullable=True)
    team_name = Column(String(255), nullable=True)
    project_name = Column(String(500), nullable=True)
    value = Column(Numeric(15, 2), nullable=True)
    item = Column(String(255), nullable=True)
    item_category = Column(String(255), nullable=True)
    po_date = Column(Date, nullable=True)
    sap_gem_po_date = Column(Date, nullable=True)
    completion_date = Column(Date, nullable=True)
    completion_date_flagged = Column(Boolean, default=False, nullable=False)
    remarks = Column(Text, nullable=True)

    # Resolved local document paths (or NULL if non-existent / omitted)
    po_document = Column(Text, nullable=True)
    sap_gem_po_document = Column(Text, nullable=True)
    completion_document = Column(Text, nullable=True)
    performance_certificate = Column(Text, nullable=True)

    created_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=True)

    def __repr__(self):
        return f"<PQRCredential(id={self.id}, project_name='{self.project_name}', value={self.value})>"
