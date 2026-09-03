import React, { useState, useEffect } from "react";
import { apiService } from "../../services/api";
import type { PQCCredentialRecommendationResponse, MatchedCredential } from "../../types/tender";
import { 
  ShieldCheck, 
  CheckCircle2, 
  XCircle, 
  FileText, 
  ExternalLink, 
  Loader2, 
  AlertCircle,
  HelpCircle 
} from "lucide-react";

interface PQCCredentialsCardProps {
  tenderId: string;
  referenceNumber?: string;
  className?: string;
}

export const PQCCredentialsCard: React.FC<PQCCredentialsCardProps> = ({
  tenderId,
  referenceNumber,
  className = ""
}) => {
  const [data, setData] = useState<PQCCredentialRecommendationResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const primaryId = (tenderId || "").trim();
    const fallbackId = (referenceNumber || "").trim();

    if (!primaryId && !fallbackId) {
      setData(null);
      setLoading(false);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);

    const fetchCredentials = async () => {
      try {
        if (primaryId) {
          try {
            const res = await apiService.getPQCCredentials(primaryId);
            if (!cancelled) {
              setData(res);
              setLoading(false);
              return;
            }
          } catch (primaryErr) {
            // If primary ID failed and fallback exists, try fallback ID
            if (fallbackId && fallbackId !== primaryId) {
              const resFallback = await apiService.getPQCCredentials(fallbackId);
              if (!cancelled) {
                setData(resFallback);
                setLoading(false);
                return;
              }
            } else {
              throw primaryErr;
            }
          }
        } else if (fallbackId) {
          const res = await apiService.getPQCCredentials(fallbackId);
          if (!cancelled) {
            setData(res);
            setLoading(false);
            return;
          }
        }
      } catch (err: any) {
        if (!cancelled) {
          console.warn(`[PQCCredentialsCard] Could not fetch PQC credentials:`, err);
          setError(err?.message || "Failed to load PQC qualification data");
          setLoading(false);
        }
      }
    };

    fetchCredentials();

    return () => {
      cancelled = true;
    };
  }, [tenderId, referenceNumber]);

  const formatINR = (val?: number): string => {
    if (val == null || isNaN(val)) return "₹0";
    return new Intl.NumberFormat("en-IN", {
      style: "currency",
      currency: "INR",
      maximumFractionDigits: 0
    }).format(val);
  };

  const getDocumentPath = (cred: MatchedCredential): string | null => {
    const paths = cred.document_paths || {};
    return paths.completion || paths.po || paths.sap_gem_po || paths.performance || null;
  };

  if (loading) {
    return (
      <div className={`bg-card-bg border border-divider rounded-xl p-4 shadow-xs select-none ${className}`}>
        <div className="flex items-center gap-2 text-text-muted text-xs font-mono">
          <Loader2 className="h-3.5 w-3.5 animate-spin text-emerald-600" />
          <span>Evaluating PQC credentials against historical records...</span>
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className={`bg-card-bg border border-divider rounded-xl p-3.5 select-none ${className}`}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-xs font-medium text-text-muted">
            <AlertCircle className="h-3.5 w-3.5 text-amber-500 shrink-0" />
            <span>PQC Evaluation unavailable for this tender record.</span>
          </div>
          <span className="text-[10px] font-mono text-text-muted">ID: {tenderId}</span>
        </div>
      </div>
    );
  }

  const isCannotEvaluate = 
    data.qualification_status === "CANNOT_EVALUATE" || 
    data.strategy_used === "VALUE_UNKNOWN" || 
    data.estimated_value <= 0;

  const isQualified = !isCannotEvaluate && (data.qualifies || data.qualification_status === "QUALIFIED");

  const credentialsToDisplay: MatchedCredential[] = isCannotEvaluate
    ? []
    : (isQualified ? data.matched_credentials.slice(0, 3) : (data.closest_candidates || []).slice(0, 3));

  return (
    <div className={`bg-card-bg border border-divider rounded-xl p-4 shadow-xs select-none ${className}`}>
      {/* ── Header: Title & Badges ─────────────────────────────── */}
      <div className="flex flex-wrap items-center justify-between gap-2 pb-3 mb-3 border-b border-divider">
        <div className="flex items-center gap-2">
          <ShieldCheck className="h-4 w-4 text-emerald-600 shrink-0" />
          <h3 className="text-xs font-bold uppercase tracking-wider text-text-primary">
            PQC Past Performance Evaluation
          </h3>
        </div>

        <div className="flex items-center gap-2">
          {/* Qualification Badge */}
          {isCannotEvaluate ? (
            <div className="px-2.5 py-1 rounded-full text-xs font-semibold flex items-center gap-1.5 border shadow-2xs bg-slate-100 text-slate-700 border-slate-300 dark:bg-slate-800 dark:text-slate-300 dark:border-slate-700">
              <HelpCircle className="h-3.5 w-3.5 text-slate-500 shrink-0" />
              <span>CANNOT EVALUATE • VALUE UNKNOWN</span>
            </div>
          ) : isQualified ? (
            <div className="px-2.5 py-1 rounded-full text-xs font-semibold flex items-center gap-1.5 border shadow-2xs bg-emerald-50 text-emerald-700 border-emerald-300 dark:bg-emerald-950/40 dark:text-emerald-300 dark:border-emerald-800">
              <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600 dark:text-emerald-400 shrink-0" />
              <span>QUALIFIED • {data.strategy_used}</span>
            </div>
          ) : (
            <div className="px-2.5 py-1 rounded-full text-xs font-semibold flex items-center gap-1.5 border shadow-2xs bg-rose-50 text-rose-700 border-rose-300 dark:bg-rose-950/40 dark:text-rose-300 dark:border-rose-800">
              <XCircle className="h-3.5 w-3.5 text-rose-600 dark:text-rose-400 shrink-0" />
              <span>DISQUALIFIED • {data.strategy_used || "NO_MATCH"}</span>
            </div>
          )}

          <span className="text-[10px] uppercase font-mono px-2 py-0.5 rounded bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400 border border-divider">
            Read-Only
          </span>
        </div>
      </div>

      {/* ── Matched Past Credentials List ──────────────────────── */}
      <div className="mb-3 space-y-2">
        {isCannotEvaluate ? (
          <div className="p-3 text-xs text-text-muted border border-dashed border-divider rounded-lg bg-surface/20 flex items-center gap-2.5">
            <AlertCircle className="h-4 w-4 text-slate-400 shrink-0" />
            <span>
              Tender estimated value could not be extracted from tender documents. Statutory thresholds (1x80%, 2x50%, 3x40%) require a known tender value to compute past-performance qualification.
            </span>
          </div>
        ) : (
          <>
            <div className="flex items-center justify-between text-[11px] font-semibold text-text-muted">
              <span>{isQualified ? "Matched Qualifying Past Works:" : "Closest Evaluated Work Orders:"}</span>
              <span className="text-[10px] font-mono text-text-muted">
                {credentialsToDisplay.length} of {data.total_candidates_evaluated || 30} records
              </span>
            </div>

            {credentialsToDisplay.length > 0 ? (
              <div className="divide-y divide-divider/60 border border-divider rounded-lg bg-surface/30 overflow-hidden">
                {credentialsToDisplay.map((cred, idx) => {
                  const docPath = getDocumentPath(cred);
                  return (
                    <div
                      key={cred.id || idx}
                      className="px-3.5 py-2.5 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 hover:bg-section-tint/50 transition-colors"
                    >
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <span className="text-[10px] font-mono text-text-muted">#{idx + 1}</span>
                          <p className="text-xs font-semibold text-text-primary truncate" title={cred.project_name}>
                            {cred.project_name}
                          </p>
                          {(cred.item_category || cred.item) && (
                            <span className="text-[9px] font-mono px-1.5 py-0.2 rounded bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 border border-divider/60 shrink-0">
                              {cred.item_category || cred.item}
                            </span>
                          )}
                        </div>
                      </div>

                      <div className="flex items-center justify-between sm:justify-end gap-3 shrink-0">
                        <span className="text-xs font-mono font-semibold text-gold-text">
                          {formatINR(cred.value)}
                        </span>

                        {docPath ? (
                          <a
                            href={`/tenders/pqc-documents/view?path=${encodeURIComponent(docPath)}`}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center gap-1 text-[11px] font-semibold text-blue-600 dark:text-blue-400 hover:text-blue-800 hover:underline shrink-0 cursor-pointer"
                            title={`View ${docPath}`}
                          >
                            <FileText className="h-3 w-3" />
                            <span>View Document</span>
                            <ExternalLink className="h-2.5 w-2.5 opacity-60" />
                          </a>
                        ) : (
                          <span className="text-[10px] text-text-muted italic">No doc</span>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="p-3 text-center text-xs text-text-muted border border-dashed border-divider rounded-lg">
                No past project records met the technical criteria.
              </div>
            )}
          </>
        )}
      </div>


      {/* ── Plain-English Rationale Text ───────────────────────── */}
      <div className="bg-slate-50 dark:bg-slate-900/50 border border-slate-200 dark:border-slate-800 rounded-lg p-3">
        <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400 mb-1">
          Rationale
        </p>
        <p className="text-xs text-slate-700 dark:text-slate-300 leading-relaxed font-sans">
          {data.rationale}
        </p>
      </div>
    </div>
  );
};
