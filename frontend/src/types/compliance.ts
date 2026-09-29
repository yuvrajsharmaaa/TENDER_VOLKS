export type ComplianceStatus =
  | "PASSED"
  | "FAILED"
  | "NEEDS_REVIEW"
  | "QUALIFIED"
  | string;

export interface BidderSummary {
  id: string;
  legal_name: string;
  trade_name?: string | null;
  gstin?: string | null;
  pan?: string | null;
  udyam_number?: string | null;
}

export interface BidSubmission {
  id: string;
  status: string;
  submission_reference: string;
  bidder: BidderSummary;
  tender_project_id: string;
  compliance_score: number | null;
  risk_level: string | null;
  ai_recommendation?: string | null;
  final_decision?: string | null;
  final_decision_by?: string | null;
  final_decision_reason?: string | null;
  submitted_at?: string | null;
  created_at?: string | null;
}

export interface ComplianceResult {
  requirement_code: string;
  requirement_name: string;
  status: ComplianceStatus;
  passed: boolean;
  mandatory: boolean;
  confidence?: number | null;
  reason?: string | null;
  evidence?: Record<string, unknown> | null;
  ai_explanation?: string | null;
  submitted?: unknown;
  expected?: unknown;
}

export interface BidComplianceAIAnalysis {
  available: boolean;
  summary: string;
  key_findings: string[];
  missing_evidence: string[];
  inconsistencies: string[];
  risk_reasoning: string[];
  officer_recommendation: string;
}

export interface ComplianceDashboardData {
  submission: {
    id: string;
    status: string;
    compliance_score: number | null;
    risk_level: string | null;
    final_decision: string | null;
  };
  documents: {
    total: number;
    processed: number;
    valid: number;
  };
  compliance: {
    total: number;
    passed: number;
    failed: number;
    needs_review: number;
    results: ComplianceResult[];
  };
  verification: {
    total: number;
    passed: number;
    failed: number;
    mismatches: number;
  };
  risk: {
    risk_level: string;
    risk_score: number;
    compliance_score: number;
    critical_issues: number;
    warnings: number;
    passed_checks: number;
    risk_factors?: Record<string, unknown>;
    ai_summary?: string | null;
    ai_recommendation?: string | null;
    ai_analysis?: BidComplianceAIAnalysis | null;
  } | null;
}

export interface BidderDocument {
  id: string;
  document_name: string;
  document_type: string;
  storage_path?: string | null;
  ocr_status: string;
  extraction_status: string;
  extracted_data?: Record<string, unknown> | null;
  document_confidence?: number | null;
  is_valid?: boolean | null;
  validation_reason?: string | null;
  created_at?: string | null;
}

export interface AuditEvent {
  id: string;
  event_type: string;
  actor: string;
  description: string;
  source?: string | null;
  before_value?: unknown;
  after_value?: unknown;
  event_metadata?: Record<string, unknown> | null;
  created_at: string;
}

export interface ExternalVerificationCheck {
  requirement_code: string;
  source: string;
  identifier: string;
  status: string;
  confidence: number;
  verified_value?: Record<string, unknown> | null;
  explanation?: string | null;
}

export interface ExternalVerificationResponse {
  submission_id: string;
  environment: string;
  total_checks: number;
  checks: ExternalVerificationCheck[];
  evaluation?: unknown;
}

export interface FullComplianceResponse {
  submission_id: string;
  tender_requirements: {
    submission_id: string;
    tender_project_id: string;
    requirements_checked: number;
    results: ComplianceResult[];
  };
  overall_compliance: {
    submission_id: string;
    compliance_score: number;
    risk_level: string;
    passed: number;
    failed: number;
    needs_review: number;
    total: number;
    mandatory_passed: number;
    mandatory_failed: number;
    mandatory_needs_review: number;
    mandatory_total: number;
    recommendation: string;
    checks: ComplianceResult[];
    ai_analysis?: BidComplianceAIAnalysis | null;
  };
}
