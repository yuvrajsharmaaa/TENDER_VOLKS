from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

class BoundingBox(BaseModel):
    x1: int
    y1: int
    x2: int
    y2: int

# Schema for raw_ocr.json
class OCRBlockSchema(BaseModel):
    block_id: str
    text: str
    confidence: float
    bounding_box: BoundingBox
    page_number: int

class RawOCRResponse(BaseModel):
    job_id: str
    original_filename: str
    page_count: int
    processing_time_seconds: float
    pages: Dict[str, List[OCRBlockSchema]] # Keys are stringified page numbers like "1", "2"

# Schema for layout.json
class LayoutRegionSchema(BaseModel):
    region_id: str
    region_type: str
    bounding_box: BoundingBox
    page_number: int
    contained_block_ids: List[str]
    reading_order_index: int
    text_content: str
    confidence: Optional[float] = None
    table_structure: Optional[Dict[str, Any]] = None

class LayoutResponse(BaseModel):
    job_id: str
    original_filename: str
    page_count: int
    processing_time_seconds: float
    pages: Dict[str, List[LayoutRegionSchema]]

# Schema for extracted_fields.json
class SourceBlockRef(BaseModel):
    page_number: int
    block_id: Optional[str] = None
    region_id: Optional[str] = None
    text: str
    bounding_box: Optional[BoundingBox] = None

class ExtractedFieldSchema(BaseModel):
    field_name: str
    value: str
    confidence: float
    source_page: int
    evidence: str
    source_blocks: List[SourceBlockRef]

class ExtractedFieldsResponse(BaseModel):
    job_id: str
    original_filename: str
    page_count: int
    extracted_fields: List[ExtractedFieldSchema]
