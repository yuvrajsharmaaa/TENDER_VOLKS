from pydantic import BaseModel, Field
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
    documents: List[DocumentResponse] = Field(default_factory=list)

    class Config:
        from_attributes = True

# --- NEW CONFORMING WORKSPACE SCHEMAS ---

class SourceDocumentSchema(BaseModel):
    id: str
    name: str
    kind: str = "pdf"
    origin: str = "source"
    url: Optional[str] = None
    previewUrl: Optional[str] = None
    downloadable: bool = True
    openable: bool = True
    isPrimary: bool = False
    uploadedBy: Optional[str] = None

class GeneratedOutputSchema(BaseModel):
    id: str
    name: str
    kind: str
    origin: str = "generated"
    url: Optional[str] = None
    previewUrl: Optional[str] = None
    downloadable: bool = True
    openable: bool = True
    generator: str
    outputKind: str

class ExtractedLinkedPdfSchema(BaseModel):
    id: str
    name: str
    kind: str = "pdf"
    origin: str = "linked"
    url: Optional[str] = None
    previewUrl: Optional[str] = None
    downloadable: bool = True
    openable: bool = True
    extractedFromDocumentId: str
    sourcePage: Optional[int] = None
    anchorText: Optional[str] = None
    extractionConfidence: Optional[float] = None

class MentionedAttachmentSchema(BaseModel):
    id: str
    name: str
    kind: str
    origin: str = "mentioned"
    url: Optional[str] = None
    previewUrl: Optional[str] = None
    downloadable: bool = False
    openable: bool = False
    mentionText: Optional[str] = None
    sourcePage: Optional[int] = None
    resolved: bool = False

class DocumentGroupSchema(BaseModel):
    sourceDocuments: List[SourceDocumentSchema] = Field(default_factory=list)
    generatedOutputs: List[GeneratedOutputSchema] = Field(default_factory=list)
    extractedLinkedPdfs: List[ExtractedLinkedPdfSchema] = Field(default_factory=list)
    mentionedAttachments: List[MentionedAttachmentSchema] = Field(default_factory=list)

class InfoSheetFieldSchema(BaseModel):
    id: str
    label: str
    value: str
    confidence: Optional[float] = None
    critical: Optional[bool] = None
    sourcePage: Optional[int] = None
    sourceSnippet: Optional[str] = None
    status: Optional[str] = "extracted"

class InfoSheetSectionSchema(BaseModel):
    id: str
    title: str
    fields: List[InfoSheetFieldSchema] = Field(default_factory=list)

class RawPageSchema(BaseModel):
    page: int
    text: str

class TenderDetailConformingResponse(BaseModel):
    id: str
    title: str
    authorityName: str
    deadline: str
    tenderValue: str
    emdAmount: Optional[str] = None
    tenderFee: Optional[str] = None
    location: Optional[str] = None
    documents: DocumentGroupSchema
    infoSheetSections: List[InfoSheetSectionSchema] = Field(default_factory=list)
    rawTextPages: List[RawPageSchema] = Field(default_factory=list)
    parse_status: str
    parse_confidence: float
    review_status: str
    issues_count: int
