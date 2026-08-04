

import React from "react";
import type { TenderDetail } from "../../types/tender";
import {
  MapPin, Building2, Calendar, FileText, ArrowRight,
  ShieldCheck, ShieldAlert, Loader2, AlertCircle,
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
        <span className="inline-flex items-center gap-1 bg-gray-100 text-gray-700 text-xs px-2.5 py-0.5 rounded-full font-medium leading-none">
          <Loader2 className="h-3 w-3 animate-spin shrink-0 text-gray-500" aria-hidden />
          Queued
        </span>
      );
    }
    if (tender.parse_status === "processing") {
      return (
        <span className="inline-flex items-center gap-1 bg-[#EFF6FF] text-[#1D4ED8] text-xs px-2.5 py-0.5 rounded-full font-medium leading-none">
          <Loader2 className="h-3 w-3 animate-spin shrink-0 text-[#2563EB]" aria-hidden />
          Processing
        </span>
      );
    }
    if (tender.parse_status === "failed") {
      return (
        <span className="inline-flex items-center gap-1 bg-[#FEE2E2] text-[#DC2626] text-xs px-2.5 py-0.5 rounded-full font-medium leading-none">
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
        <span className="inline-flex items-center gap-1 bg-[#FFFBEB] text-[#B45309] text-xs px-2.5 py-0.5 rounded-full font-medium leading-none">
          Closing Soon
        </span>
      );
    }
    if (daysLeft <= 0) {
      return (
        <span className="inline-flex items-center gap-1 bg-gray-100 text-gray-600 text-xs px-2.5 py-0.5 rounded-full font-medium leading-none">
          Closed
        </span>
      );
    }
    return (
      <span className="inline-flex items-center gap-1 bg-[#EFF6FF] text-[#1D4ED8] text-xs px-2.5 py-0.5 rounded-full font-medium leading-none">
        Open
      </span>
    );
  };

  /* ── Risk badge ──────────────────────────────────────────────── */
  const getRiskBadge = () => {
    const issues = tender.issues_count || 0;
    if (issues === 0) {
      return (
        <span className="inline-flex items-center gap-1 bg-[#ECFDF5] text-[#047857] text-xs px-2.5 py-0.5 rounded-full font-medium leading-none">
          <ShieldCheck className="h-3 w-3 shrink-0" aria-hidden />
          Low Risk
        </span>
      );
    }
    if (issues === 1) {
      return (
        <span className="inline-flex items-center gap-1 bg-[#FFFBEB] text-[#D97706] text-xs px-2.5 py-0.5 rounded-full font-medium leading-none">
          <ShieldAlert className="h-3 w-3 shrink-0" aria-hidden />
          Med Risk
        </span>
      );
    }
    return (
      <span className="inline-flex items-center gap-1 bg-[#FEE2E2] text-[#DC2626] text-xs px-2.5 py-0.5 rounded-full font-medium leading-none">
        <ShieldAlert className="h-3 w-3 shrink-0" aria-hidden />
        High Risk
      </span>
    );
  };

  /* ── Match score badge ──────────────────────────────────────────── */
  const getAIMatchBadge = () => {
    const score = Math.round(tender.parse_confidence) || 85;
    return (
      <span className="inline-flex items-center gap-1 text-xs px-2.5 py-0.5 rounded-full font-medium leading-none bg-[#F5F3FF] text-[#6D28D9]">
        Match {score}%
      </span>
    );
  };

  /* ── Status left border accent ─────────────────────────────── */
  const getBorderAccent = () => {
    const daysLeft = Math.ceil(
      (new Date(tender.deadline).getTime() - Date.now()) / (1000 * 60 * 60 * 24)
    );
    if (daysLeft > 0 && daysLeft <= 3) {
      return "border-l-[3px] border-l-[#D97706]";
    }
    if (tender.issues_count === 0) {
      return "border-l-[3px] border-l-[#047857]";
    }
    return "border-l-[3px] border-l-[#2563EB]";
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
      className={`group bg-white border border-divider rounded-[10px] p-5 flex flex-col gap-3.5
        cursor-pointer select-none outline-none ${getBorderAccent()}
        shadow-xs hover:border-gray-300 hover:shadow-sm
        focus-visible:ring-2 focus-visible:ring-blue-500/40 focus-visible:ring-offset-2
        transition-all duration-150`}
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
          className="text-[15px] font-semibold text-[#111827] leading-snug line-clamp-2
            group-hover:text-blue-600 transition-colors duration-150 font-sans"
        >
          {tender.title}
        </h3>
        <p className="text-xs text-[#6B7280] font-mono truncate">
          {tender.reference_number ? `Ref: ${tender.reference_number}` : `ID: ${tender.id}`}
        </p>
      </div>

      {/* Meta row */}
      <div className="flex flex-wrap items-center gap-y-1.5 gap-x-4 text-xs text-[#6B7280] border-b border-divider/60 pb-3 font-sans">
        <div className="flex items-center gap-1.5 min-w-0" title={tender.authorityName}>
          <Building2 className="h-3.5 w-3.5 text-gray-400 shrink-0" aria-hidden />
          <span className="truncate max-w-[160px]">{tender.authorityName}</span>
        </div>
        <div className="flex items-center gap-1.5" title={locationLabel}>
          <MapPin className="h-3.5 w-3.5 text-gray-400 shrink-0" aria-hidden />
          <span className="truncate max-w-[120px]">{locationLabel}</span>
        </div>
        <div className="flex items-center gap-1.5">
          <Calendar className="h-3.5 w-3.5 text-gray-400 shrink-0" aria-hidden />
          <span>Closes {closesDate}</span>
        </div>
      </div>

      {/* Financials row */}
      <div className="flex items-center justify-between gap-2 text-xs">
        <div className="flex items-center gap-2 flex-wrap">
          {tender.emdAmount && (
            <span className="bg-gray-100 text-gray-700 font-medium px-2 py-0.5 rounded-md border border-gray-200 font-mono text-[11px]">
              EMD {tender.emdAmount}
            </span>
          )}
          <span className="flex items-center gap-1 text-gray-500">
            <FileText className="h-3.5 w-3.5 text-gray-400 shrink-0" aria-hidden />
            {docCount} doc{docCount !== 1 ? "s" : ""}
          </span>
        </div>

        {/* Right-weighted Price Badge */}
        <span className="bg-[#FFFBEB] text-[#B45309] font-semibold px-2.5 py-1 rounded-full font-mono tabular-nums text-xs shrink-0">
          ₹ {tender.tenderValue}
        </span>
      </div>

      {/* Footer */}
      <div className="border-t border-divider/60 pt-3 flex items-center justify-between mt-auto">
        <span className="text-xs text-[#9CA3AF] font-mono">
          {updatedTime}
        </span>
        <div className="flex items-center gap-3">
          <button
            type="button"
            aria-label={`Delete tender: ${tender.title}`}
            onClick={(e) => {
              e.stopPropagation();
              if (confirm(`Are you sure you want to delete "${tender.title}"?`)) {
                onDelete();
              }
            }}
            className="text-xs text-[#9CA3AF] hover:text-[#EF4444] transition-colors font-medium cursor-pointer"
          >
            Delete
          </button>
          <button
            type="button"
            aria-label={`Open details for ${tender.title}`}
            onClick={(e) => { e.stopPropagation(); onOpen(); }}
            className="px-3 py-1.5 bg-gray-50 border border-gray-200 rounded-[6px] text-xs font-medium text-gray-700 hover:bg-gray-100 transition-colors flex items-center gap-1 cursor-pointer"
          >
            <span>View Tender</span>
            <ArrowRight className="h-3.5 w-3.5 text-gray-500 group-hover:translate-x-0.5 transition-transform duration-150" aria-hidden />
          </button>
        </div>
      </div>
    </article>
  );
};

export default TenderCard;
