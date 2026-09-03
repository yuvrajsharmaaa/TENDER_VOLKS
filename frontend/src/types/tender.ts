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
  source?: string;
  resolution_source?: string;
  resolution_layer?: string;
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
  status_summary?: {
    OK?: number;
    OK_FALLBACK?: number;
    NOT_APPLICABLE?: number;
    MISSING?: number;
  };
  missing_fields?: string[];
  field_statuses?: Record<string, string>;
  updated_at: string;
}
export type PreviewDocument = SourceDocumentItem | GeneratedOutputItem | ExtractedLinkedPdfItem | MentionedAttachmentItem;

// ─────────────────────────────────────────────────────────────────────────────
// PQC Multi-Signal Recommendation System Types
// ─────────────────────────────────────────────────────────────────────────────

export interface ScoreDecomposition {
  compliance_score: number;
  compliance_status: "QUALIFIED" | "NEEDS_REVIEW" | "DISQUALIFIED" | string;
  ml_win_prob: number;
  similarity_score: number;
  claude_fit_score: number;
  composite_score: number;
}

export interface SimilarTenderItem {
  tender_no: string;
  tender_name?: string;
  similarity: number;
  outcome: string;
  organization?: string;
  key_overlap?: string;
}

export interface ScoredTender {
  rank: number;
  tender_no: string;
  tender_name: string;
  organization: string;
  tender_value: number;
  composite_score: number;
  score_decomposition: ScoreDecomposition;
  similar_tenders?: SimilarTenderItem[];
  key_drivers?: string[];
  strategic_rationale?: string;
  disqualification_reasons?: string[];
  review_reasons?: string[];
}

export interface PQCRecommendationRequest {
  top_k?: number;
  include_claude?: boolean;
  source?: "db" | "dataset";
  is_override?: boolean;
}

export interface PQCRecommendationResponse {
  recommendations: ScoredTender[];
  total_scored: number;
  weights_used: {
    compliance: number;
    similarity: number;
    ml_win_prob: number;
    claude: number;
    [key: string]: number;
  };
  timestamp: string;
}

// ─────────────────────────────────────────────────────────────────────────────
// PQC Past-Performance Credential Matcher Types (Read-Only)
// ─────────────────────────────────────────────────────────────────────────────

export interface MatchedCredential {
  id: number;
  project_name: string;
  value: number;
  item?: string;
  item_category?: string;
  completion_date?: string | null;
  document_paths?: {
    po?: string | null;
    sap_gem_po?: string | null;
    completion?: string | null;
    performance?: string | null;
    [key: string]: string | null | undefined;
  };
}

export interface PQCCredentialRecommendationResponse {
  tender_id: string;
  tender_name?: string | null;
  estimated_value: number;
  value_is_estimated: boolean;
  scope_of_work: string;
  submission_deadline?: string | null;
  msme_relaxation_applicable: boolean;
  is_msme_vendor: boolean;
  qualification_status: "QUALIFIED" | "DISQUALIFIED" | string;
  qualifies: boolean;
  strategy_used: "1x80%" | "2x50%" | "3x40%" | "MSME_RELAXED" | "NO_MATCH" | string;
  matched_credentials: MatchedCredential[];
  closest_candidates: MatchedCredential[];
  computed_thresholds: {
    eighty_pct?: number;
    fifty_pct?: number;
    forty_pct?: number;
    msme_floor?: number;
    [key: string]: number | undefined;
  };
  rationale: string;
  target_scope?: string;
  eligible_count?: number;
  total_candidates_evaluated?: number;
  data_source?: string;
  read_only: boolean;
}

