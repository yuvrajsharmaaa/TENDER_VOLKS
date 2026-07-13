export type DocumentOrigin = "source" | "generated" | "linked" | "mentioned";
export type DocumentKind = "pdf" | "xlsx" | "csv" | "doc" | "unknown";
export type ReviewState = "default" | "selected" | "reviewed" | "missing" | "unresolved";

export interface BaseDocumentItem {
  id: string;
  name: string;
  kind: DocumentKind;
  origin: DocumentOrigin;
  url?: string;
  previewUrl?: string;
  downloadable?: boolean;
  openable?: boolean;
  createdAt?: string;
  reviewState?: ReviewState;
}

export interface SourceDocumentItem extends BaseDocumentItem {
  origin: "source";
  isPrimary: boolean;
  uploadedBy?: string;
}

export interface GeneratedOutputItem extends BaseDocumentItem {
  origin: "generated";
  generator: "ocr" | "parser" | "system";
  outputKind: "info_sheet" | "summary" | "csv_export" | "review_report";
}

export interface ExtractedLinkedPdfItem extends BaseDocumentItem {
  origin: "linked";
  extractedFromDocumentId: string;
  sourcePage?: number;
  anchorText?: string;
  extractionConfidence?: number;
}

export interface MentionedAttachmentItem extends BaseDocumentItem {
  origin: "mentioned";
  mentionText?: string;
  sourcePage?: number;
  resolved: boolean;
}

export interface TenderDocuments {
  sourceDocuments: SourceDocumentItem[];
  generatedOutputs: GeneratedOutputItem[];
  extractedLinkedPdfs: ExtractedLinkedPdfItem[];
  mentionedAttachments: MentionedAttachmentItem[];
}

export interface InfoSheetField {
  id: string;
  label: string;
  value: string;
  confidence?: number;
  critical?: boolean;
  sourcePage?: number;
  sourceSnippet?: string;
  status?: "extracted" | "verified" | "edited" | "missing";
}

export interface InfoSheetSection {
  id: string;
  title: string;
  fields: InfoSheetField[];
}

export interface TenderDetail {
  id: string;
  title: string;
  authorityName: string;
  department?: string;
  deadline: string;
  tenderValue: string;
  emdAmount?: string;
  tenderFee?: string;
  location?: string;
  description?: string;
  documents: TenderDocuments;
  infoSheetArtifactId?: string;
  selectedDocumentId?: string;
  infoSheetSections: InfoSheetSection[];
  rawTextPages?: Array<{ page: number; text: string }>;
  raw_ocr_text?: string;
  reference_number?: string;
  publish_date?: string;
  reviewFlags?: Array<{
    id: string;
    type: "missing_field" | "low_confidence" | "unresolved_document";
    label: string;
    severity: "low" | "medium" | "high";
    status: "open" | "resolved";
  }>;
  parse_status: "pending" | "processing" | "completed" | "failed";
  parse_confidence: number;
  review_status: "unreviewed" | "reviewing" | "completed";
  reviewer_name: string | null;
  issues_count: number;
  location_city: string;
  location_state: string;
  sector: string;
  snippet: string;
  updated_at: string;
}
export type PreviewDocument = SourceDocumentItem | GeneratedOutputItem | ExtractedLinkedPdfItem | MentionedAttachmentItem;
