from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

class TenderProjectCreate(BaseModel):
    """Schema for creating a new Tender Project."""
    project_id: str
    tender_name: Optional[str] = None
    source_label: Optional[str] = None

class DocumentResponse(BaseModel):
    """Schema for document metadata response."""
    document_id: str
    original_filename: str
    mime_type: str
    size_bytes: int
    upload_status: str
    processing_status: str
    document_type: Optional[str] = None

    class Config:
        from_attributes = True

class TenderProjectResponse(BaseModel):
    """Schema for general Tender Project response."""
    tender_project_id: str
    project_id: str
    tender_name: Optional[str] = None
    source_label: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class TenderProjectDetailResponse(BaseModel):
    """Schema for Tender Project details, including all linked documents."""
    tender_project_id: str
    project_id: str
    tender_name: Optional[str] = None
    source_label: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    documents: List[DocumentResponse] = []

    class Config:
        from_attributes = True
