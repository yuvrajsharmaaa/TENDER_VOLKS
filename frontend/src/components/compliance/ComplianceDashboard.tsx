import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  ClipboardCheck,
  FileCheck2,
  FileWarning,
  History,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
  Upload,
  XCircle,
} from "lucide-react";

import { apiService } from "../../services/api";
import type {
  AuditEvent,
  BidderDocument,
  BidSubmission,
  ComplianceDashboardData,
  ComplianceResult,
  ExternalVerificationCheck,
} from "../../types/compliance";

const DEMO_SUBMISSION_ID =
  "a3414dfa-0d06-4d93-a72e-1092902ea514";

function statusLabel(status: string) {
  if (status === "QUALIFIED" || status === "PASSED") return "PASSED";
  if (status === "FAILED") return "FAILED";
  return "NEEDS REVIEW";
}

function statusClasses(status: string) {
  const normalized = statusLabel(status);

  if (normalized === "PASSED") {
    return "bg-emerald-50 text-emerald-700 border-emerald-200";
  }

  if (normalized === "FAILED") {
    return "bg-red-50 text-red-700 border-red-200";
  }

  return "bg-amber-50 text-amber-700 border-amber-200";
}

function StatusBadge({ status }: { status: string }) {
  const normalized = statusLabel(status);

  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-[10px] font-bold uppercase tracking-wide ${statusClasses(
        status
      )}`}
    >
      {normalized === "PASSED" ? (
        <CheckCircle2 className="h-3 w-3" />
      ) : normalized === "FAILED" ? (
        <XCircle className="h-3 w-3" />
      ) : (
        <AlertTriangle className="h-3 w-3" />
      )}
      {normalized}
    </span>
  );
}

function MetricCard({
  label,
  value,
  caption,
  icon,
}: {
  label: string;
  value: string | number;
  caption: string;
  icon: React.ReactNode;
}) {
  return (
    <div data-premium-compliance="true" className="rounded-2xl border border-divider bg-white p-4 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-text-muted">
            {label}
          </p>
          <p className="mt-2 text-2xl font-semibold tracking-tight">
            {value}
          </p>
          <p className="mt-1 text-[11px] text-text-muted">{caption}</p>
        </div>
        <div className="rounded-xl bg-section-tint p-2.5 text-text-secondary">
          {icon}
        </div>
      </div>
    </div>
  );
}

function EvidenceText({ result }: { result: ComplianceResult }) {
  const evidence = result.evidence || {};
  const missing = Array.isArray(evidence.missing_documents)
    ? evidence.missing_documents.join(", ")
    : "";

  if (missing) return `Missing: ${missing}`;

  if (typeof result.reason === "string" && result.reason.length > 0) {
    return result.reason;
  }

  return "No additional evidence available.";
}

export default function ComplianceDashboard({
  submissionId = DEMO_SUBMISSION_ID,
}: {
  submissionId?: string;
}) {
  const [submission, setSubmission] = useState<BidSubmission | null>(null);
  const [dashboard, setDashboard] =
    useState<ComplianceDashboardData | null>(null);
  const [documents, setDocuments] = useState<BidderDocument[]>([]);
  const [audit, setAudit] = useState<AuditEvent[]>([]);
  const [externalChecks, setExternalChecks] = useState<
    ExternalVerificationCheck[]
  >([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<
    "evaluate" | "verify" | "decision" | null
  >(null);
  const [officerName, setOfficerName] = useState("");
  const [decisionReason, setDecisionReason] = useState("");
  const [error, setError] = useState<string | null>(null);

  const loadDashboard = async () => {
    setLoading(true);
    setError(null);

    try {
      const [submissionData, dashboardData, documentData, auditData] =
        await Promise.all([
          apiService.getBidSubmission(submissionId),
          apiService.getBidComplianceDashboard(submissionId),
          apiService.getBidDocuments(submissionId),
          apiService.getBidAudit(submissionId),
        ]);

      setSubmission(submissionData);
      setDashboard(dashboardData);
      setDocuments(documentData);
      setAudit(auditData);
    } catch (err) {
      console.error(err);
      setError(
        err instanceof Error
          ? err.message
          : "Unable to load compliance dashboard."
      );
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadDashboard();
  }, [submissionId]);

  const runEvaluation = async () => {
    setActionLoading("evaluate");
    setError(null);

    try {
      await apiService.evaluateFullBidCompliance(submissionId);
      await loadDashboard();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Evaluation failed."
      );
    } finally {
      setActionLoading(null);
    }
  };

  const runExternalVerification = async () => {
    setActionLoading("verify");
    setError(null);

    try {
      const response = await apiService.verifyExternalSources(submissionId);
      setExternalChecks(response.checks);
      await loadDashboard();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "External verification failed."
      );
    } finally {
      setActionLoading(null);
    }
  };

  const recordDecision = async (
    decision: "QUALIFIED" | "DISQUALIFIED" | "CLARIFICATION_REQUIRED"
  ) => {
    const name = officerName.trim();
    const reason = decisionReason.trim();

    if (!name) {
      setError("Please enter the Procurement Officer name.");
      return;
    }

    if (!reason) {
      setError("Please enter a reason for the decision.");
      return;
    }

    setActionLoading("decision");
    setError(null);

    try {
      await apiService.recordFinalDecision(
        submissionId,
        decision,
        name,
        reason
      );

      await loadDashboard();
      setDecisionReason("");
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Unable to record the final decision."
      );
    } finally {
      setActionLoading(null);
    }
  };

  const missingDocuments = useMemo(() => {
    const required = dashboard?.compliance.results.find(
      (item) => item.requirement_code === "TENDER_REQUIRED_DOCUMENTS"
    );

    const missing = required?.evidence?.missing_documents;

    return Array.isArray(missing)
      ? missing.map(String)
      : [];
  }, [dashboard]);

  if (loading && !dashboard) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="flex items-center gap-3 rounded-xl border border-divider bg-white px-5 py-4 text-sm text-text-secondary shadow-sm">
          <RefreshCw className="h-4 w-4 animate-spin" />
          Loading bid compliance workspace...
        </div>
      </div>
    );
  }

  if (error && !dashboard) {
    return (
      <div className="flex-1 p-6">
        <div className="mx-auto max-w-4xl rounded-2xl border border-red-200 bg-red-50 p-6">
          <div className="flex items-center gap-3 text-red-700">
            <ShieldAlert className="h-5 w-5" />
            <h2 className="font-semibold">Compliance dashboard unavailable</h2>
          </div>
          <p className="mt-2 text-sm text-red-600">{error}</p>
          <button
            type="button"
            onClick={() => void loadDashboard()}
            className="mt-4 rounded-lg bg-white px-4 py-2 text-xs font-semibold text-red-700 shadow-sm ring-1 ring-red-200"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  if (!dashboard || !submission) return null;

  const bidder = submission.bidder;
  const score = dashboard.submission.compliance_score ?? 0;
  const risk = dashboard.risk;
  const aiAnalysis = risk?.ai_analysis;

  return (
    <div className="flex-1 min-h-0 overflow-y-auto bg-app-bg">
      <div className="mx-auto max-w-[1500px] space-y-5 p-6 pb-10">

        {/* Header */}
        <section className="rounded-2xl border border-divider bg-white p-5 shadow-sm">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <div className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-[0.14em] text-text-muted">
                <ClipboardCheck className="h-3.5 w-3.5" />
                Bid Compliance Verification
              </div>

              <h1 className="mt-2 text-xl font-semibold tracking-tight">
                {bidder.legal_name}
              </h1>

              <p className="mt-1 text-xs text-text-secondary">
                Submission {submission.submission_reference} · Tender Project{" "}
                {submission.tender_project_id}
              </p>
            </div>

            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => void runExternalVerification()}
                disabled={actionLoading !== null}
                className="inline-flex items-center gap-2 rounded-lg border border-divider bg-white px-3 py-2 text-xs font-semibold text-text-secondary shadow-sm hover:bg-gray-50 disabled:opacity-50"
              >
                <ShieldCheck className="h-3.5 w-3.5" />
                {actionLoading === "verify"
                  ? "Verifying..."
                  : "Verify Sources"}
              </button>

              <button
                type="button"
                onClick={() => void runEvaluation()}
                disabled={actionLoading !== null}
                className="inline-flex items-center gap-2 rounded-lg bg-[#587266] px-3.5 py-2 text-xs font-semibold text-white shadow-sm hover:bg-[#34483F] disabled:opacity-50"
              >
                <RefreshCw
                  className={`h-3.5 w-3.5 ${
                    actionLoading === "evaluate" ? "animate-spin" : ""
                  }`}
                />
                {actionLoading === "evaluate"
                  ? "Evaluating..."
                  : "Run Full Evaluation"}
              </button>
            </div>
          </div>

          {error && (
            <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-xs text-amber-800">
              {error}
            </div>
          )}
        </section>

        {/* AI Compliance Analysis */}
        {aiAnalysis?.available && (
          <section className="rounded-2xl border border-divider bg-white p-5 shadow-sm">
            <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
              <div>
                <div className="flex items-center gap-2">
                  <ShieldCheck className="h-4 w-4 text-[#587266]" />
                  <h2 className="text-sm font-semibold">
                    AI Compliance Analysis
                  </h2>
                </div>
                <p className="mt-1 text-xs text-text-muted">
                  Groq-generated explanation grounded in the deterministic
                  compliance findings.
                </p>
              </div>

              <span className="inline-flex w-fit items-center rounded-full border border-emerald-200 bg-emerald-50 px-2.5 py-1 text-[10px] font-bold uppercase tracking-wide text-emerald-700">
                AI Analysis Available
              </span>
            </div>

            <div className="mt-5 rounded-xl bg-section-tint p-4">
              <p className="text-sm leading-6 text-text-secondary">
                {aiAnalysis.summary}
              </p>
            </div>

            <div className="mt-5 grid grid-cols-1 gap-4 lg:grid-cols-2">
              <div className="rounded-xl border border-divider p-4">
                <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-text-muted">
                  Key Findings
                </p>
                <div className="mt-3 space-y-2">
                  {aiAnalysis.key_findings.length > 0 ? (
                    aiAnalysis.key_findings.map((item, index) => (
                      <div
                        key={`finding-${index}`}
                        className="flex gap-2 text-xs leading-5 text-text-secondary"
                      >
                        <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[#587266]" />
                        <span>{item}</span>
                      </div>
                    ))
                  ) : (
                    <p className="text-xs text-text-muted">
                      No additional findings.
                    </p>
                  )}
                </div>
              </div>

              <div className="rounded-xl border border-divider p-4">
                <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-text-muted">
                  Missing Evidence
                </p>
                <div className="mt-3 space-y-2">
                  {aiAnalysis.missing_evidence.length > 0 ? (
                    aiAnalysis.missing_evidence.map((item, index) => (
                      <div
                        key={`missing-${index}`}
                        className="flex gap-2 text-xs leading-5 text-text-secondary"
                      >
                        <FileWarning className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-600" />
                        <span>{item}</span>
                      </div>
                    ))
                  ) : (
                    <p className="text-xs text-text-muted">
                      No missing evidence identified.
                    </p>
                  )}
                </div>
              </div>

              <div className="rounded-xl border border-divider p-4">
                <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-text-muted">
                  Inconsistencies
                </p>
                <div className="mt-3 space-y-2">
                  {aiAnalysis.inconsistencies.length > 0 ? (
                    aiAnalysis.inconsistencies.map((item, index) => (
                      <div
                        key={`inconsistency-${index}`}
                        className="flex gap-2 text-xs leading-5 text-text-secondary"
                      >
                        <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-600" />
                        <span>{item}</span>
                      </div>
                    ))
                  ) : (
                    <p className="text-xs text-text-muted">
                      No supported inconsistencies detected.
                    </p>
                  )}
                </div>
              </div>

              <div className="rounded-xl border border-divider p-4">
                <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-text-muted">
                  Risk Reasoning
                </p>
                <div className="mt-3 space-y-2">
                  {aiAnalysis.risk_reasoning.length > 0 ? (
                    aiAnalysis.risk_reasoning.map((item, index) => (
                      <div
                        key={`risk-${index}`}
                        className="flex gap-2 text-xs leading-5 text-text-secondary"
                      >
                        <ShieldAlert className="mt-0.5 h-3.5 w-3.5 shrink-0 text-red-600" />
                        <span>{item}</span>
                      </div>
                    ))
                  ) : (
                    <p className="text-xs text-text-muted">
                      No additional risk reasoning.
                    </p>
                  )}
                </div>
              </div>
            </div>

            <div className="mt-4 rounded-xl border border-divider bg-white p-4">
              <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-text-muted">
                Officer Review Guidance
              </p>
              <p className="mt-2 text-xs leading-5 text-text-secondary">
                {aiAnalysis.officer_recommendation}
              </p>
            </div>
          </section>
        )}

        {/* Bidder identity */}
        <section className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          <div className="rounded-2xl border border-divider bg-white p-5 shadow-sm lg:col-span-2">
            <div className="flex items-center gap-2">
              <ShieldCheck className="h-4 w-4 text-text-secondary" />
              <h2 className="text-sm font-semibold">Bidder Profile</h2>
            </div>

            <div className="mt-4 grid grid-cols-2 gap-4 md:grid-cols-4">
              {[
                ["Legal Name", bidder.legal_name],
                ["Trade Name", bidder.trade_name || "—"],
                ["GSTIN", bidder.gstin || "—"],
                ["PAN", bidder.pan || "—"],
                ["Udyam", bidder.udyam_number || "—"],
                ["Submission", submission.submission_reference],
                ["Status", submission.status],
                ["Decision", submission.final_decision || "Pending"],
              ].map(([label, value]) => (
                <div key={label}>
                  <p className="text-[9px] font-bold uppercase tracking-wide text-text-muted">
                    {label}
                  </p>
                  <p className="mt-1 break-words text-xs font-medium text-text-primary">
                    {value}
                  </p>
                </div>
              ))}
            </div>
          </div>

          <div className="rounded-2xl border border-divider bg-white p-5 shadow-sm">
            <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-text-muted">
              Compliance Score
            </p>

            <div className="mt-2 flex items-end gap-2">
              <span className="text-4xl font-semibold tracking-tight">
                {score.toFixed(2)}%
              </span>
              <span className="pb-1 text-[11px] text-text-muted">
                mandatory checks
              </span>
            </div>

            <div className="mt-4 h-2 overflow-hidden rounded-full bg-gray-100">
              <div
                className="h-full rounded-full bg-[#587266]"
                style={{ width: `${Math.min(score, 100)}%` }}
              />
            </div>

            <div className="mt-3 flex items-center justify-between">
              <span className="text-[10px] text-text-muted">Risk level</span>
              <span
                className={`rounded-full px-2.5 py-1 text-[10px] font-bold ${
                  risk?.risk_level === "HIGH"
                    ? "bg-red-50 text-red-700"
                    : risk?.risk_level === "MEDIUM"
                      ? "bg-amber-50 text-amber-700"
                      : "bg-emerald-50 text-emerald-700"
                }`}
              >
                {risk?.risk_level || "UNASSESSED"}
              </span>
            </div>
          </div>
        </section>

        {/* KPI row */}
        <section className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <MetricCard
            label="Passed"
            value={dashboard.compliance.passed}
            caption="Tender checks"
            icon={<CheckCircle2 className="h-4 w-4" />}
          />
          <MetricCard
            label="Failed"
            value={dashboard.compliance.failed}
            caption="Tender checks"
            icon={<XCircle className="h-4 w-4" />}
          />
          <MetricCard
            label="Review"
            value={dashboard.compliance.needs_review}
            caption="Needs officer review"
            icon={<AlertTriangle className="h-4 w-4" />}
          />
          <MetricCard
            label="Documents"
            value={`${dashboard.documents.valid}/${dashboard.documents.total}`}
            caption="Valid bidder documents"
            icon={<FileCheck2 className="h-4 w-4" />}
          />
        </section>

        {/* Main content */}
        <section className="rounded-2xl border border-divider bg-white shadow-sm">
          <div className="flex items-center justify-between border-b border-divider px-5 py-4">
            <div>
              <h2 className="text-sm font-semibold">Compliance Requirements</h2>
              <p className="mt-1 text-[11px] text-text-muted">
                {dashboard.compliance.total} tender-specific requirements evaluated
              </p>
            </div>
            <span className="text-[10px] font-semibold text-text-muted">
              Mandatory score: {risk?.passed_checks ?? 0}/{dashboard.risk?.passed_checks && risk ? (risk.passed_checks + risk.critical_issues + risk.warnings) : "—"}
            </span>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full min-w-[900px] text-left">
              <thead className="bg-section-tint">
                <tr className="border-b border-divider">
                  {[
                    "Requirement",
                    "Type",
                    "Status",
                    "Confidence",
                    "Evidence / Reason",
                  ].map((head) => (
                    <th
                      key={head}
                      className="px-5 py-3 text-[9px] font-bold uppercase tracking-[0.1em] text-text-muted"
                    >
                      {head}
                    </th>
                  ))}
                </tr>
              </thead>

              <tbody>
                {dashboard.compliance.results.map((result) => (
                  <tr
                    key={result.requirement_code}
                    className="border-b border-divider/70 last:border-0"
                  >
                    <td className="px-5 py-4">
                      <p className="text-xs font-semibold">
                        {result.requirement_name}
                      </p>
                      <p className="mt-1 font-mono text-[9px] text-text-muted">
                        {result.requirement_code}
                      </p>
                    </td>

                    <td className="px-5 py-4">
                      <span
                        className={`rounded-md border px-2 py-1 text-[9px] font-bold ${
                          result.mandatory
                            ? "border-red-100 bg-red-50 text-red-600"
                            : "border-divider bg-gray-50 text-text-muted"
                        }`}
                      >
                        {result.mandatory ? "MANDATORY" : "OPTIONAL"}
                      </span>
                    </td>

                    <td className="px-5 py-4">
                      <StatusBadge status={result.status} />
                    </td>

                    <td className="px-5 py-4 font-mono text-xs">
                      {result.confidence != null
                        ? `${Math.round(result.confidence * 100)}%`
                        : "—"}
                    </td>

                    <td className="max-w-[480px] px-5 py-4 text-xs text-text-secondary">
                      <p>{EvidenceText({ result })}</p>
                      {result.ai_explanation && (
                        <p className="mt-1 text-[10px] text-text-muted">
                          {result.ai_explanation}
                        </p>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        {/* Missing docs + risk */}
        <section className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <div className="rounded-2xl border border-red-200 bg-white shadow-sm">
            <div className="border-b border-divider px-5 py-4">
              <div className="flex items-center gap-2">
                <FileWarning className="h-4 w-4 text-red-500" />
                <h2 className="text-sm font-semibold">Missing Documents</h2>
              </div>
            </div>

            <div className="p-5">
              {missingDocuments.length === 0 ? (
                <div className="flex items-center gap-2 text-sm text-emerald-700">
                  <CheckCircle2 className="h-4 w-4" />
                  No missing mandatory documents detected.
                </div>
              ) : (
                <div className="space-y-2">
                  {missingDocuments.map((name) => (
                    <div
                      key={name}
                      className="flex items-center gap-3 rounded-xl border border-red-100 bg-red-50 px-3 py-3"
                    >
                      <XCircle className="h-4 w-4 shrink-0 text-red-500" />
                      <span className="text-xs font-medium text-red-800">
                        {name}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          <div className="rounded-2xl border border-divider bg-white shadow-sm">
            <div className="border-b border-divider px-5 py-4">
              <div className="flex items-center gap-2">
                <ShieldAlert className="h-4 w-4 text-text-secondary" />
                <h2 className="text-sm font-semibold">Risk Assessment</h2>
              </div>
            </div>

            <div className="space-y-4 p-5">
              <div className="flex items-center justify-between">
                <span className="text-xs text-text-secondary">
                  Risk score
                </span>
                <span className="text-sm font-semibold">
                  {risk?.risk_score?.toFixed(2) ?? "—"}
                </span>
              </div>

              <div className="flex items-center justify-between">
                <span className="text-xs text-text-secondary">
                  Critical issues
                </span>
                <span className="text-sm font-semibold">
                  {risk?.critical_issues ?? 0}
                </span>
              </div>

              <div className="flex items-center justify-between">
                <span className="text-xs text-text-secondary">
                  Warnings
                </span>
                <span className="text-sm font-semibold">
                  {risk?.warnings ?? 0}
                </span>
              </div>

              <div className="rounded-xl bg-section-tint p-4">
                <p className="text-[10px] font-bold uppercase tracking-wide text-text-muted">
                  AI Recommendation
                </p>
                <p className="mt-2 text-xs leading-relaxed text-text-secondary">
                  {risk?.ai_recommendation ||
                    submission.ai_recommendation ||
                    "No recommendation available."}
                </p>
              </div>
            </div>
          </div>
        </section>

        {/* Documents + Verification */}
        <section className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <div className="rounded-2xl border border-divider bg-white shadow-sm">
            <div className="border-b border-divider px-5 py-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Upload className="h-4 w-4 text-text-secondary" />
                  <h2 className="text-sm font-semibold">Bidder Documents</h2>
                </div>
                <span className="text-[10px] text-text-muted">
                  {documents.length} uploaded
                </span>
              </div>
            </div>

            <div className="divide-y divide-divider/70">
              {documents.length === 0 ? (
                <div className="p-5 text-xs text-text-muted">
                  No bidder documents uploaded.
                </div>
              ) : (
                documents.map((doc) => (
                  <div
                    key={doc.id}
                    className="flex items-center justify-between gap-4 px-5 py-4"
                  >
                    <div className="min-w-0">
                      <p className="truncate text-xs font-semibold">
                        {doc.document_name}
                      </p>
                      <p className="mt-1 text-[10px] text-text-muted">
                        {doc.document_type} · OCR {doc.ocr_status}
                      </p>
                    </div>

                    <span
                      className={`shrink-0 rounded-full px-2 py-1 text-[9px] font-bold ${
                        doc.is_valid
                          ? "bg-emerald-50 text-emerald-700"
                          : "bg-red-50 text-red-700"
                      }`}
                    >
                      {doc.is_valid ? "VALID" : "INVALID"}
                    </span>
                  </div>
                ))
              )}
            </div>
          </div>

          <div className="rounded-2xl border border-divider bg-white shadow-sm">
            <div className="border-b border-divider px-5 py-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <ShieldCheck className="h-4 w-4 text-text-secondary" />
                  <h2 className="text-sm font-semibold">
                    External Verification
                  </h2>
                </div>

                <span className="text-[10px] font-semibold text-text-muted">
                  {dashboard.verification.passed}/{dashboard.verification.total} verified
                </span>
              </div>
            </div>

            <div className="divide-y divide-divider/70">
              {externalChecks.length === 0 ? (
                <div className="p-5">
                  <p className="text-xs text-text-secondary">
                    Run external verification to load source-level verification
                    evidence.
                  </p>
                  <button
                    type="button"
                    onClick={() => void runExternalVerification()}
                    className="mt-3 rounded-lg border border-divider bg-white px-3 py-2 text-[11px] font-semibold shadow-sm"
                  >
                    Verify now
                  </button>
                </div>
              ) : (
                externalChecks.map((check) => (
                  <div
                    key={`${check.source}-${check.identifier}`}
                    className="flex items-center justify-between gap-4 px-5 py-4"
                  >
                    <div>
                      <p className="text-xs font-semibold">
                        {check.source}
                      </p>
                      <p className="mt-1 font-mono text-[9px] text-text-muted">
                        {check.identifier}
                      </p>
                    </div>
                    <div className="text-right">
                      <StatusBadge
                        status={
                          check.status === "VERIFIED"
                            ? "PASSED"
                            : check.status
                        }
                      />
                      <p className="mt-1 text-[9px] text-text-muted">
                        {Math.round(check.confidence * 100)}% confidence
                      </p>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </section>

        {/* Audit */}
        <section className="rounded-2xl border border-divider bg-white shadow-sm">
          <div className="border-b border-divider px-5 py-4">
            <div className="flex items-center gap-2">
              <History className="h-4 w-4 text-text-secondary" />
              <h2 className="text-sm font-semibold">Audit Trail</h2>
            </div>
          </div>

          <div className="divide-y divide-divider/70">
            {audit.length === 0 ? (
              <div className="p-5 text-xs text-text-muted">
                No audit events recorded yet.
              </div>
            ) : (
              audit.map((event) => (
                <div
                  key={event.id}
                  className="flex gap-4 px-5 py-4"
                >
                  <div className="mt-0.5 h-7 w-7 shrink-0 rounded-full bg-section-tint flex items-center justify-center">
                    <History className="h-3.5 w-3.5 text-text-secondary" />
                  </div>

                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="text-xs font-semibold">
                        {event.event_type}
                      </p>
                      <span className="text-[9px] text-text-muted">
                        {new Date(event.created_at).toLocaleString()}
                      </span>
                    </div>
                    <p className="mt-1 text-xs text-text-secondary">
                      {event.description}
                    </p>
                    <p className="mt-1 text-[9px] text-text-muted">
                      Actor: {event.actor} · Source: {event.source || "system"}
                    </p>
                  </div>
                </div>
              ))
            )}
          </div>
        </section>

        {/* Procurement Officer decision */}
        <section className="rounded-2xl border border-divider bg-white p-5 shadow-sm">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <div className="flex items-center gap-2">
                <ClipboardCheck className="h-4 w-4 text-text-secondary" />
                <h2 className="text-sm font-semibold">
                  Procurement Officer Review
                </h2>
              </div>
              <p className="mt-1 max-w-3xl text-xs leading-relaxed text-text-muted">
                Record the authorized officer&apos;s final procedural decision
                after reviewing the automated compliance evidence.
              </p>
            </div>

            {submission.final_decision && (
              <div className="text-right">
                <p className="text-[9px] font-bold uppercase tracking-[0.12em] text-text-muted">
                  Current Decision
                </p>
                <div className="mt-1">
                  <StatusBadge status={submission.final_decision} />
                </div>
              </div>
            )}
          </div>

          {submission.final_decision && (
            <div className="mt-4 rounded-xl bg-section-tint p-4">
              <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
                <div>
                  <p className="text-[9px] font-bold uppercase tracking-[0.12em] text-text-muted">
                    Recorded By
                  </p>
                  <p className="mt-1 text-xs font-medium">
                    {submission.final_decision_by || "—"}
                  </p>
                </div>
                <div className="md:col-span-2">
                  <p className="text-[9px] font-bold uppercase tracking-[0.12em] text-text-muted">
                    Decision Reason
                  </p>
                  <p className="mt-1 text-xs leading-5 text-text-secondary">
                    {submission.final_decision_reason || "—"}
                  </p>
                </div>
              </div>
            </div>
          )}

          <div className="mt-5 grid grid-cols-1 gap-4 lg:grid-cols-3">
            <div className="lg:col-span-1">
              <label className="text-[10px] font-bold uppercase tracking-[0.12em] text-text-muted">
                Officer Name
              </label>
              <input
                value={officerName}
                onChange={(event) => setOfficerName(event.target.value)}
                placeholder="e.g. Procurement Officer"
                className="mt-2 w-full rounded-lg border border-divider bg-white px-3 py-2.5 text-xs outline-none placeholder:text-text-muted focus:border-[#587266]"
              />
            </div>

            <div className="lg:col-span-2">
              <label className="text-[10px] font-bold uppercase tracking-[0.12em] text-text-muted">
                Decision Reason
              </label>
              <textarea
                value={decisionReason}
                onChange={(event) => setDecisionReason(event.target.value)}
                rows={3}
                placeholder="Enter the evidence-based reason for the officer decision."
                className="mt-2 w-full resize-none rounded-lg border border-divider bg-white px-3 py-2.5 text-xs leading-5 outline-none placeholder:text-text-muted focus:border-[#587266]"
              />
            </div>
          </div>

          <div className="mt-4 flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => void recordDecision("QUALIFIED")}
              disabled={actionLoading !== null}
              className="inline-flex items-center gap-2 rounded-lg border border-emerald-200 bg-emerald-50 px-3.5 py-2.5 text-xs font-semibold text-emerald-700 hover:bg-emerald-100 disabled:opacity-50"
            >
              <CheckCircle2 className="h-3.5 w-3.5" />
              Mark Qualified
            </button>

            <button
              type="button"
              onClick={() => void recordDecision("CLARIFICATION_REQUIRED")}
              disabled={actionLoading !== null}
              className="inline-flex items-center gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3.5 py-2.5 text-xs font-semibold text-amber-700 hover:bg-amber-100 disabled:opacity-50"
            >
              <AlertTriangle className="h-3.5 w-3.5" />
              Request Clarification
            </button>

            <button
              type="button"
              onClick={() => void recordDecision("DISQUALIFIED")}
              disabled={actionLoading !== null}
              className="inline-flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-3.5 py-2.5 text-xs font-semibold text-red-700 hover:bg-red-100 disabled:opacity-50"
            >
              <XCircle className="h-3.5 w-3.5" />
              Mark Disqualified
            </button>

            {actionLoading === "decision" && (
              <span className="inline-flex items-center gap-2 px-2 text-xs text-text-muted">
                <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                Recording decision...
              </span>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
