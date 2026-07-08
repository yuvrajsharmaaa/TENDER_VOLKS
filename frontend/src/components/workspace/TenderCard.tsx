import React from "react";
import type { TenderDetail } from "../../types/tender";
import { MapPin, Building2, Calendar, FileText, ArrowRight, ShieldCheck, ShieldAlert, Sparkles, Loader2, AlertCircle } from "lucide-react";

interface TenderCardProps {
  tender: TenderDetail;
  onOpen: () => void;
}

export const TenderCard: React.FC<TenderCardProps> = ({ tender, onOpen }) => {
  
  // Status Badge Helper
  const getStatusBadge = () => {
    if (tender.parse_status === "pending") {
      return (
        <span className="inline-flex items-center gap-1 bg-section-tint text-text-muted text-[10px] px-2 py-0.5 rounded font-mono uppercase font-bold border border-divider">
          <Loader2 className="h-3 w-3 animate-spin shrink-0" />
          <span>Queued</span>
        </span>
      );
    }
    if (tender.parse_status === "processing") {
      return (
        <span className="inline-flex items-center gap-1 bg-blue-50 text-blue-600 text-[10px] px-2 py-0.5 rounded font-mono uppercase font-bold border border-blue-200">
          <Loader2 className="h-3 w-3 animate-spin shrink-0" />
          <span>Processing</span>
        </span>
      );
    }
    if (tender.parse_status === "failed") {
      return (
        <span className="inline-flex items-center gap-1 bg-alert-bg text-alert-text text-[10px] px-2 py-0.5 rounded font-mono uppercase font-bold border border-alert-text/20">
          <AlertCircle className="h-3 w-3 shrink-0" />
          <span>Failed</span>
        </span>
      );
    }
    
    // Deadline calculation
    const daysLeft = Math.ceil((new Date(tender.deadline).getTime() - Date.now()) / (1000 * 60 * 60 * 24));
    if (daysLeft > 0 && daysLeft <= 3) {
      return (
        <span className="inline-flex items-center gap-1 bg-warning-bg text-warning-text text-[10px] px-2 py-0.5 rounded font-mono uppercase font-bold border border-warning-text/20">
          <span>Closing Soon</span>
        </span>
      );
    }
    if (daysLeft <= 0) {
      return (
        <span className="inline-flex items-center gap-1 bg-section-tint text-text-muted text-[10px] px-2 py-0.5 rounded font-mono uppercase font-bold border border-divider">
          <span>Closed</span>
        </span>
      );
    }
    
    return (
      <span className="inline-flex items-center gap-1 bg-selected-green-bg text-success-green text-[10px] px-2 py-0.5 rounded font-mono uppercase font-bold border border-selected-green-border">
        <span>Open</span>
      </span>
    );
  };

  // Risk Badge Helper
  const getRiskBadge = () => {
    const issues = tender.issues_count || 0;
    if (issues === 0) {
      return (
        <span className="inline-flex items-center gap-1 bg-selected-green-bg text-success-green text-[10px] px-2 py-0.5 rounded font-mono uppercase font-bold border border-selected-green-border">
          <ShieldCheck className="h-3 w-3 text-success-green shrink-0" />
          <span>Low Risk</span>
        </span>
      );
    }
    if (issues === 1) {
      return (
        <span className="inline-flex items-center gap-1 bg-warning-bg text-warning-text text-[10px] px-2 py-0.5 rounded font-mono uppercase font-bold border border-warning-text/20">
          <ShieldAlert className="h-3 w-3 text-warning-text shrink-0" />
          <span>Med Risk</span>
        </span>
      );
    }
    return (
      <span className="inline-flex items-center gap-1 bg-alert-bg text-alert-text text-[10px] px-2 py-0.5 rounded font-mono uppercase font-bold border border-alert-text/20">
        <ShieldAlert className="h-3 w-3 text-alert-text shrink-0" />
        <span>High Risk</span>
      </span>
    );
  };

  // AI Match Score component
  const getAIMatchScore = () => {
    const score = Math.round(tender.parse_confidence) || 85;
    const colorClass = score >= 80 ? "text-success-green bg-selected-green-bg border-selected-green-border" : "text-warning-text bg-warning-bg border-warning-text/20";
    return (
      <span className={`inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded font-mono uppercase font-bold border ${colorClass}`}>
        <Sparkles className="h-3 w-3 shrink-0" />
        <span>AI Match: {score}%</span>
      </span>
    );
  };

  // Format Dates
  const closesDate = new Date(tender.deadline).toLocaleDateString("en-US", {
    day: "numeric",
    month: "short"
  });

  const updatedTime = tender.updated_at || "Recent";

  // Document Count
  const docCount = 
    (tender.documents?.sourceDocuments?.length || 0) + 
    (tender.documents?.generatedOutputs?.length || 0) + 
    (tender.documents?.extractedLinkedPdfs?.length || 0) +
    (tender.documents?.mentionedAttachments?.length || 0);

  return (
    <div 
      onClick={onOpen}
      className="bg-card-bg border border-divider/60 rounded-2xl p-6 hover:border-success-green/40 hover:-translate-y-0.5 transition-all duration-250 cursor-pointer shadow-[0_1px_3px_rgba(0,0,0,0.02),0_4px_12px_rgba(0,0,0,0.03)] hover:shadow-[0_8px_24px_rgba(62,142,99,0.06)] flex flex-col gap-4 select-none relative group"
    >
      {/* Top Badges Row */}
      <div className="flex flex-wrap items-center gap-2">
        {getStatusBadge()}
        {getRiskBadge()}
        {getAIMatchScore()}
      </div>

      {/* Main Title & Reference Code */}
      <div className="space-y-1">
        <h3 className="text-[17px] font-bold text-text-primary leading-snug group-hover:text-success-green transition-colors font-sans line-clamp-2" title={tender.title}>
          {tender.title}
        </h3>
        <p className="text-[11px] text-text-muted font-mono tracking-wider uppercase">
          Reference: {tender.id}
        </p>
      </div>

      {/* Meta Icons Row */}
      <div className="flex flex-wrap items-center gap-y-2 gap-x-4 text-xs text-text-secondary border-b border-divider/30 pb-3 font-sans">
        <div className="flex items-center gap-1.5 min-w-0" title="Authority Department">
          <Building2 className="h-3.5 w-3.5 text-text-muted shrink-0" />
          <span className="truncate max-w-[150px]">{tender.authorityName}</span>
        </div>
        <div className="flex items-center gap-1.5" title="Location Code">
          <MapPin className="h-3.5 w-3.5 text-text-muted shrink-0" />
          <span>{tender.location || `${tender.location_city}, ${tender.location_state}`}</span>
        </div>
        <div className="flex items-center gap-1.5" title="Closing Submission End Date">
          <Calendar className="h-3.5 w-3.5 text-text-muted shrink-0" />
          <span>Closes: {closesDate}</span>
        </div>
      </div>

      {/* Financials & Documents row */}
      <div className="flex items-center justify-between text-xs font-sans">
        <div className="flex items-center gap-2.5 flex-wrap">
          <span className="bg-gold-bg text-gold-text font-bold px-2.5 py-0.8 rounded-lg border border-gold-fill/20 font-mono text-[11px]">
            Est: {tender.tenderValue}
          </span>
          {tender.emdAmount && (
            <span className="bg-panel-bg text-text-secondary font-semibold px-2.5 py-0.8 rounded-lg border border-divider font-mono text-[11px]">
              EMD: {tender.emdAmount}
            </span>
          )}
          <span className="flex items-center gap-1 text-[11px] text-text-muted font-medium">
            <FileText className="h-3.5 w-3.5 text-text-disabled" />
            <span>{docCount} docs</span>
          </span>
        </div>
      </div>

      {/* Footer updated & View link */}
      <div className="border-t border-divider/40 pt-3.5 flex items-center justify-between mt-auto">
        <span className="text-[10px] text-text-muted font-mono uppercase tracking-wider">
          Updated: {updatedTime}
        </span>
        <button 
          className="text-xs text-success-green hover:text-cta-green font-bold flex items-center gap-1 transition-colors select-none"
          onClick={(e) => {
            e.stopPropagation();
            onOpen();
          }}
        >
          <span>View Tender</span>
          <ArrowRight className="h-3.5 w-3.5 group-hover:translate-x-0.5 transition-transform" />
        </button>
      </div>
    </div>
  );
};
export default TenderCard;
