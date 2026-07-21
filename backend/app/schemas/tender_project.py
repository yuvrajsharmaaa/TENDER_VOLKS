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

class TenderUploadResponse(BaseModel):
    """Unified response schema for file uploads across workspace and direct APIs."""
    job_id: str
    file_id: str
    tender_id: str
    status: str = "pending"
    original_filename: str
    message: Optional[str] = "Upload complete and processing queued."

class TenderProcessRequest(BaseModel):
    """Unified request schema for triggering tender processing."""
    job_id: Optional[str] = None
    file_id: Optional[str] = None
    tender_id: Optional[str] = None
    email: Optional[str] = None
    email_recipient: Optional[str] = None

    def resolved_job_id(self) -> Optional[str]:
        val = self.job_id or self.file_id or self.tender_id
        return str(val) if val is not None else None

    def resolved_email(self) -> Optional[str]:
        return self.email or self.email_recipient

class TenderProcessResponse(BaseModel):
    """Unified response schema for triggering tender processing."""
    job_id: str
    file_id: str
    tender_id: str
    status: str = "processing"
    message: Optional[str] = "Tender processing triggered successfully."

class JobStatusResponse(BaseModel):
    """Unified response schema for job status tracking."""
    job_id: str
    file_id: str
    tender_id: str
    status: str
    original_filename: str
    created_at: Optional[str] = None
    completed_at: Optional[str] = None
    workspace_url: Optional[str] = None
    error_message: Optional[str] = None

