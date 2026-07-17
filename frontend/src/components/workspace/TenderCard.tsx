

import React from "react";
import type { TenderDetail } from "../../types/tender";
import {
  MapPin, Building2, Calendar, FileText, ArrowRight,
  ShieldCheck, ShieldAlert, Sparkles, Loader2, AlertCircle, Trash2,
} from "lucide-react";

interface TenderCardProps {
  tender: TenderDetail;
  onOpen: () => void;
  onDelete: () => void;
}

export const TenderCard: React.FC<TenderCardProps> = ({ tender, onOpen, onDelete }) => {

  /* ── Status badge ────────────────────────────────────────────── */
  const getStatusBadge = () => {
    if (tender.parse_status === "pending") {
      return (
        <span className="inline-flex items-center gap-1 bg-section-tint text-text-muted text-[10px] px-2 py-0.5 rounded-full font-mono uppercase font-bold border border-divider leading-none">
          <span className="h-10 w-10 flex items-center justify-center">
            <Loader2 className="h-5 w-5 animate-spin shrink-0" aria-hidden />
          </span>
          Queued
        </span>
      );
    }
    if (tender.parse_status === "processing") {
      return (
        <span className="inline-flex items-center gap-1 bg-blue-50 text-blue-600 text-[10px] px-2 py-0.5 rounded-full font-mono uppercase font-bold border border-blue-200 leading-none">
          <span className="h-10 w-10 flex items-center justify-center">
            <Loader2 className="h-5 w-5 animate-spin shrink-0" aria-hidden />
          </span>
          Processing
        </span>
      );
    }
    if (tender.parse_status === "failed") {
      return (
        <span className="inline-flex items-center gap-1 bg-alert-bg text-alert-text text-[10px] px-2 py-0.5 rounded-full font-mono uppercase font-bold border border-alert-text/20 leading-none">
          <span className="h-10 w-10 flex items-center justify-center">
            <AlertCircle className="h-5 w-5 shrink-0" aria-hidden />
          </span>
          Failed
        </span>
      );
    }

    const daysLeft = Math.ceil(
      (new Date(tender.deadline).getTime() - Date.now()) / (1000 * 60 * 60 * 24)
    );
    if (daysLeft > 0 && daysLeft <= 3) {
      return (
        <span className="inline-flex items-center gap-1 bg-warning-bg text-warning-text text-[10px] px-2 py-0.5 rounded-full font-mono uppercase font-bold border border-warning-text/20 leading-none">
          Closing Soon
        </span>
      );
    }
    if (daysLeft <= 0) {
      return (
        <span className="inline-flex items-center gap-1 bg-section-tint text-text-muted text-[10px] px-2 py-0.5 rounded-full font-mono uppercase font-bold border border-divider leading-none">
          Closed
        </span>
      );
    }
    return (
      <span className="inline-flex items-center gap-1 bg-[var(--color-badge-open-bg)] text-[var(--color-badge-open-text)] text-[10px] px-2 py-0.5 rounded-full font-mono uppercase font-bold leading-none">
        Open
      </span>
    );
  };

  /* Get left border color based on status */
  const getLeftBorderClass = () => {
    if (tender.parse_status === "pending") {
      return "border-divider"; // Queued - neutral
    }
    if (tender.parse_status === "processing") {
      return "border-blue-500"; // Processing - blue
    }
    if (tender.parse_status === "failed") {
      return "border-alert-text"; // Failed
    }

    const daysLeft = Math.ceil(
      (new Date(tender.deadline).getTime() - Date.now()) / (1000 * 60 * 60 * 24)
    );
    if (daysLeft > 0 && daysLeft <= 3) {
      return "border-warning-text"; // Closing Soon - amber
    }
    if (daysLeft <= 0) {
      return "border-divider"; // Closed - neutral
    }
    return "border-success-green"; // Open - green
  };

  /* ── Risk badge ──────────────────────────────────────────────── */
  const getRiskBadge = () => {
    const issues = tender.issues_count || 0;
    if (issues === 0) {
      return (
        <span className="inline-flex items-center gap-1 bg-[var(--color-badge-low-risk-bg)] text-[var(--color-badge-low-risk-text)] text-[10px] px-2 py-0.5 rounded font-mono uppercase font-bold leading-none">
          <ShieldCheck className="h-3 w-3 shrink-0" aria-hidden />
          Low Risk
        </span>
      );
    }
    if (issues === 1) {
      return (
        <span className="inline-flex items-center gap-1 bg-[var(--color-warning-bg)] text-[var(--color-warning-text)] text-[10px] px-2 py-0.5 rounded font-mono uppercase font-bold leading-none">
          <ShieldAlert className="h-3 w-3 shrink-0" aria-hidden />
          Med Risk
        </span>
      );
    }
    return (
      <span className="inline-flex items-center gap-1 bg-alert-bg text-alert-text text-[10px] px-2 py-0.5 rounded font-mono uppercase font-bold border border-alert-text/20 leading-none">
        <ShieldAlert className="h-3 w-3 shrink-0" aria-hidden />
        High Risk
      </span>
    );
  };

  /* ── AI match badge ──────────────────────────────────────────── */
  const getAIMatchBadge = () => {
    const score = Math.round(tender.parse_confidence) || 85;
    return (
      <span className="inline-flex items-center gap-1 bg-[var(--color-badge-aimatch-bg)] text-[var(--color-badge-aimatch-text)] text-[10px] px-2 py-0.5 rounded font-mono uppercase font-bold leading-none">
        <Sparkles className="h-3 w-3 shrink-0" aria-hidden />
        AI {score}%
      </span>
    );
  };

  /* ── Derived values ──────────────────────────────────────────── */
  const closesDate = new Date(tender.deadline).toLocaleDateString("en-IN", {
    day: "numeric",
    month: "short",
    year: "2-digit",
  });

  const updatedTime = (() => {
    if (!tender.updated_at) return "Recently";
    const d = new Date(tender.updated_at);
    if (isNaN(d.getTime())) return tender.updated_at;
    const diffH = Math.floor((Date.now() - d.getTime()) / 36e5);
    if (diffH < 1) return "Just now";
    if (diffH < 24) return `${diffH}h ago`;
    return d.toLocaleDateString("en-IN", { day: "numeric", month: "short" });
  })();

  const docCount =
    (tender.documents?.sourceDocuments?.length || 0) +
    (tender.documents?.generatedOutputs?.length || 0) +
    (tender.documents?.extractedLinkedPdfs?.length || 0) +
    (tender.documents?.mentionedAttachments?.length || 0);

  const locationLabel =
    tender.location || [tender.location_city, tender.location_state].filter(Boolean).join(", ") || "—";

  /* ── Render ──────────────────────────────────────────────────── */
  return (
    <article
      onClick={onOpen}
      onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onOpen(); } }}
      tabIndex={0}
      role="button"
      aria-label={`View tender: ${tender.title}`}
      className={`
        group bg-card-bg border-l-3 border-l-[${getLeftBorderClass()}] border border-divider/60 rounded-[10px] p-5 flex flex-col gap-3.5
        cursor-pointer select-none outline-none
        shadow-[0_1px_3px_rgba(0,0,0,0.02),0_4px_12px_rgba(0,0,0,0.03)]
        hover:border-success-green/40 hover:-translate-y-0.5
        hover:shadow-[0_8px_24px_rgba(227,85,47,0.08)]
        focus-visible:ring-2 focus-visible:ring-success-green/50 focus-visible:ring-offset-2 focus-visible:ring-offset-app-bg
        transition-all duration-200
        @media(prefers-reduced-motion:reduce){transition-none}
      `}
    >
      {/* Badges row */}
      <div className="flex flex-wrap items-center gap-1.5">
        {getStatusBadge()}
        {getRiskBadge()}
        {getAIMatchBadge()}
      </div>

      {/* Title + reference */}
      <div className="space-y-1 min-w-0">
        <h3
          title={tender.title}
          className="text-[15px] font-semibold text-[var(--color-title-text)] leading-snug line-clamp-2
            group-hover:text-success-green transition-colors duration-150 font-sans"
        >
          {tender.title}
        </h3>
        <p className="text-[12px] font-normal text-[var(--color-text-meta)] font-mono tracking-wider uppercase truncate">
          {tender.reference_number ? `Ref: ${tender.reference_number}` : `ID: ${tender.id}`}
        </p>
      </div>

      {/* Meta row */}
      <div className="flex flex-wrap items-center gap-y-1.5 gap-x-4 text-[12px] text-[var(--color-text-meta)] border-b border-divider/30 pb-3 font-sans">
        <div className="flex items-center gap-1.5 min-w-0" title={tender.authorityName}>
          <div className="h-10 w-10 flex items-center justify-center">
            <Building2 className="h-5 w-5 text-[var(--color-text-meta)] shrink-0" aria-hidden />
          </div>
          <span className="truncate max-w-[160px]">{tender.authorityName}</span>
        </div>
        <div className="flex items-center gap-1.5" title={locationLabel}>
          <div className="h-10 w-10 flex items-center justify-center">
            <MapPin className="h-5 w-5 text-[var(--color-text-meta)] shrink-0" aria-hidden />
          </div>
          <span className="truncate max-w-[120px]">{locationLabel}</span>
        </div>
        <div className="flex items-center gap-1.5">
          <div className="h-10 w-10 flex items-center justify-center">
            <Calendar className="h-5 w-5 text-[var(--color-text-meta)] shrink-0" aria-hidden />
          </div>
          <span>Closes {closesDate}</span>
        </div>
      </div>

      {/* Financials row */}
      <div className="flex items-center gap-2 flex-wrap text-[12px] text-[var(--color-text-meta)]">
        {tender.emdAmount && (
          <span className="bg-panel-bg text-[var(--color-text-meta)] font-semibold px-2 py-1 rounded-lg border border-divider font-mono numeric-nums">
            EMD&nbsp;{tender.emdAmount}
          </span>
        )}
        <span className="flex items-center gap-1 text-[var(--color-text-meta)]">
          <div className="h-10 w-10 flex items-center justify-center">
            <FileText className="h-5 w-5 text-[var(--color-text-meta)] shrink-0" aria-hidden />
          </div>
          {docCount} doc{docCount !== 1 ? "s" : ""}
        </span>
        <span className="ml-auto bg-[var(--color-price-bg)] text-[var(--color-price-text)] font-bold px-2 py-1 rounded-full border border-[var(--color-price-bg)/20] font-mono numeric-nums">
          ₹&nbsp;{tender.tenderValue}
        </span>
      </div>

      {/* Footer */}
      <div className="border-t border-divider/40 pt-3 flex items-center justify-between mt-auto">
        <span className="text-[10px] text-[var(--color-text-meta)] font-mono uppercase tracking-wider">
          {updatedTime}
        </span>
        <div className="flex items-center gap-3">
          <button
            type="button"
            aria-label={`Open details for ${tender.title}`}
            onClick={(e) => { e.stopPropagation(); onOpen(); }}
            className="flex items-center gap-1 px-3 py-1.5 bg-[var(--color-gray-50)] border border-[var(--color-divider)] rounded-[8px] text-sm font-medium text-[var(--color-text-secondary)] hover:bg-[var(--color-gray-50)]/80 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-success-green/50"
          >
            View Tender
            <ArrowRight className="h-3.5 w-3.5 group-hover:translate-x-0.5 transition-transform duration-150" aria-hidden />
          </button>
          <button
            type="button"
            aria-label={`Delete tender: ${tender.title}`}
            onClick={(e) => {
              e.stopPropagation();
              if (confirm(`Are you sure you want to delete "${tender.title}"?`)) {
                onDelete();
              }
            }}
            className="flex items-center gap-1 rounded-[8px] text-sm font-medium text-[var(--color-text-muted)] hover:text-[var(--color-alert-text)] transition-colors"
          >
            <Trash2 className="h-3.5 w-3.5" aria-hidden />
            Delete
          </button>
        </div>
      </div>
    </article>
  );
};

export default TenderCard;
