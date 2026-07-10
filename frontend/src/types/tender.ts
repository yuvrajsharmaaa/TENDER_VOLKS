// Types mirror the real backend response shapes exactly.
// See backend/app/api/routes/tenders.py (Pydantic response models) and
// backend/app/api/jobs.py (extracted_fields.json shape written by
// backend/app/services/field_extractor.py).

export type UploadStatus = "uploaded" | "failed";
export type ProcessingStatus = "pending" | "processing" | "completed" | "failed";

export interface TenderDocument {
  document_id: string;
  original_filename: string;
  mime_type: string | null;
  size_bytes: number;
  upload_status: UploadStatus;
  processing_status: ProcessingStatus;
  document_type: string | null;
  error_message?: string | null;
}

export interface TenderProject {
  tender_project_id: string;
  project_id: string;
  tender_name: string;
  source_label: string | null;
  created_at: string;
  updated_at: string;
}

export interface TenderProjectDetail extends TenderProject {
  documents: TenderDocument[];
}

export interface SourceBlock {
  page_number: number;
  block_id: string;
  region_id: string | null;
  text: string;
  bounding_box: { x1: number; y1: number; x2: number; y2: number };
}

export interface ExtractedField {
  field_name: string;
  value: string;
  confidence: number;
  source_page: number;
  evidence: string;
  source_blocks: SourceBlock[];
}

export interface ProductItem {
  product_name: string;
  normalized_category: string;
  raw_text: string;
  quantity: string | null;
  unit: string | null;
  technical_specification: string | null;
  brand_or_oem_if_present: string | null;
  page_number: number;
  confidence: number;
  evidence_text: string;
}

export interface ExtractedFieldsResult {
  job_id: string;
  original_filename: string;
  page_count: number;
  extracted_fields: ExtractedField[];
  extracted_products?: ProductItem[];
}

export interface ProcessCompleteResult {
  tender_information_id: number;
  tender_project_id: string;
  document_id: string;
  csv_filename: string;
  csv_url: string;
  message: string;
}
