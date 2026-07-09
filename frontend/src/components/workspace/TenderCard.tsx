import React from "react";
import type { TenderDetail } from "../../types/tender";
import {
  MapPin, Building2, Calendar, FileText, ArrowRight,
  ShieldCheck, ShieldAlert, Sparkles, Loader2, AlertCircle,
} from "lucide-react";

interface TenderCardProps {
  tender: TenderDetail;
  onOpen: () => void;
}

export const TenderCard: React.FC<TenderCardProps> = ({ tender, onOpen }) => {

  /* ── Status badge ────────────────────────────────────────────── */
  const getStatusBadge = () => {
    if (tender.parse_status === "pending") {
      return (
        <span className="inline-flex items-center gap-1 bg-section-tint text-text-muted text-[10px] px-2 py-0.5 rounded font-mono uppercase font-bold border border-divider leading-none">
          <Loader2 className="h-3 w-3 animate-spin shrink-0" aria-hidden />
          Queued
        </span>
      );
    }
    if (tender.parse_status === "processing") {
      return (
        <span className="inline-flex items-center gap-1 bg-blue-50 text-blue-600 text-[10px] px-2 py-0.5 rounded font-mono uppercase font-bold border border-blue-200 leading-none">
          <Loader2 className="h-3 w-3 animate-spin shrink-0" aria-hidden />
          Processing
        </span>
      );
    }
    if (tender.parse_status === "failed") {
      return (
        <span className="inline-flex items-center gap-1 bg-alert-bg text-alert-text text-[10px] px-2 py-0.5 rounded font-mono uppercase font-bold border border-alert-text/20 leading-none">
          <AlertCircle className="h-3 w-3 shrink-0" aria-hidden />
          Failed
        </span>
      );
    }

    const daysLeft = Math.ceil(
      (new Date(tender.deadline).getTime() - Date.now()) / (1000 * 60 * 60 * 24)
    );
    if (daysLeft > 0 && daysLeft <= 3) {
      return (
        <span className="inline-flex items-center gap-1 bg-warning-bg text-warning-text text-[10px] px-2 py-0.5 rounded font-mono uppercase font-bold border border-warning-text/20 leading-none">
          Closing Soon
        </span>
      );
    }
    if (daysLeft <= 0) {
      return (
        <span className="inline-flex items-center gap-1 bg-section-tint text-text-muted text-[10px] px-2 py-0.5 rounded font-mono uppercase font-bold border border-divider leading-none">
          Closed
        </span>
      );
    }
    return (
      <span className="inline-flex items-center gap-1 bg-selected-green-bg text-success-green text-[10px] px-2 py-0.5 rounded font-mono uppercase font-bold border border-selected-green-border leading-none">
        Open
      </span>
    );
  };

  /* ── Risk badge ──────────────────────────────────────────────── */
  const getRiskBadge = () => {
    const issues = tender.issues_count || 0;
    if (issues === 0) {
      return (
        <span className="inline-flex items-center gap-1 bg-selected-green-bg text-success-green text-[10px] px-2 py-0.5 rounded font-mono uppercase font-bold border border-selected-green-border leading-none">
          <ShieldCheck className="h-3 w-3 shrink-0" aria-hidden />
          Low Risk
        </span>
      );
    }
    if (issues === 1) {
      return (
        <span className="inline-flex items-center gap-1 bg-warning-bg text-warning-text text-[10px] px-2 py-0.5 rounded font-mono uppercase font-bold border border-warning-text/20 leading-none">
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
    const cls =
      score >= 80
        ? "text-success-green bg-selected-green-bg border-selected-green-border"
        : "text-warning-text bg-warning-bg border-warning-text/20";
    return (
      <span className={`inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded font-mono uppercase font-bold border leading-none ${cls}`}>
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
      className="group bg-card-bg border border-divider/60 rounded-2xl p-5 flex flex-col gap-3.5
        cursor-pointer select-none outline-none
        shadow-[0_1px_3px_rgba(0,0,0,0.02),0_4px_12px_rgba(0,0,0,0.03)]
        hover:border-success-green/40 hover:-translate-y-0.5
        hover:shadow-[0_8px_24px_rgba(62,142,99,0.06)]
        focus-visible:ring-2 focus-visible:ring-success-green/50 focus-visible:ring-offset-2 focus-visible:ring-offset-app-bg
        transition-all duration-200
        @media(prefers-reduced-motion:reduce){transition:none}"
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
          className="text-[15px] font-bold text-text-primary leading-snug line-clamp-2
            group-hover:text-success-green transition-colors duration-150 font-sans"
        >
          {tender.title}
        </h3>
        <p className="text-[10px] text-text-disabled font-mono tracking-wider uppercase truncate">
          {tender.reference_number ? `Ref: ${tender.reference_number}` : `ID: ${tender.id}`}
        </p>
      </div>

      {/* Meta row */}
      <div className="flex flex-wrap items-center gap-y-1.5 gap-x-4 text-[11px] text-text-secondary border-b border-divider/30 pb-3 font-sans">
        <div className="flex items-center gap-1.5 min-w-0" title={tender.authorityName}>
          <Building2 className="h-3.5 w-3.5 text-text-muted shrink-0" aria-hidden />
          <span className="truncate max-w-[160px]">{tender.authorityName}</span>
        </div>
        <div className="flex items-center gap-1.5" title={locationLabel}>
          <MapPin className="h-3.5 w-3.5 text-text-muted shrink-0" aria-hidden />
          <span className="truncate max-w-[120px]">{locationLabel}</span>
        </div>
        <div className="flex items-center gap-1.5">
          <Calendar className="h-3.5 w-3.5 text-text-muted shrink-0" aria-hidden />
          <span>Closes {closesDate}</span>
        </div>
      </div>

      {/* Financials row */}
      <div className="flex items-center gap-2 flex-wrap text-[11px]">
        <span className="bg-gold-bg text-gold-text font-bold px-2 py-1 rounded-lg border border-gold-fill/20 font-mono">
          ₹&nbsp;{tender.tenderValue}
        </span>
        {tender.emdAmount && (
          <span className="bg-panel-bg text-text-secondary font-semibold px-2 py-1 rounded-lg border border-divider font-mono">
            EMD&nbsp;{tender.emdAmount}
          </span>
        )}
        <span className="flex items-center gap-1 text-text-muted ml-auto">
          <FileText className="h-3.5 w-3.5 text-text-disabled shrink-0" aria-hidden />
          {docCount} doc{docCount !== 1 ? "s" : ""}
        </span>
      </div>

      {/* Footer */}
      <div className="border-t border-divider/40 pt-3 flex items-center justify-between mt-auto">
        <span className="text-[10px] text-text-muted font-mono uppercase tracking-wider">
          {updatedTime}
        </span>
        <button
          type="button"
          aria-label={`Open details for ${tender.title}`}
          onClick={(e) => { e.stopPropagation(); onOpen(); }}
          className="flex items-center gap-1 text-[11px] font-bold text-success-green hover:text-cta-green transition-colors"
        >
          View Tender
          <ArrowRight className="h-3.5 w-3.5 group-hover:translate-x-0.5 transition-transform duration-150" aria-hidden />
        </button>
      </div>
    </article>
  );
};

export default TenderCard;
