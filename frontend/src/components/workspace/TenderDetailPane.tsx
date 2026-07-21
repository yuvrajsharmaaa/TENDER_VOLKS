import React, { useState, useEffect } from "react";
import type { 
  TenderDetail, 
  DocumentOrigin, 
  PreviewDocument, 
  SourceDocumentItem, 
  GeneratedOutputItem, 
  ExtractedLinkedPdfItem, 
  MentionedAttachmentItem,
  InfoSheetField 
} from "../../types/tender";
import { PDFPreviewPane } from "./PDFPreviewPane";
import { InfoSheetPanel } from "./InfoSheetPanel";
import { DocumentsPanel } from "./DocumentsPanel";
import { OCRPreviewPanel } from "./OCRPreviewPanel";
import { ArrowLeft, Download, AlertTriangle, CheckCircle2, RefreshCw, Eye, Table, Trash2 } from "lucide-react";
import { handleSecureDownload } from "../../services/api";

interface TenderDetailPaneProps {
  tender: TenderDetail;
  onBack: () => void;
  onUpdateField: (fieldId: string, value: string) => void;
  onVerifyField: (fieldId: string) => void;
  onMarkReviewed: () => void;
  onRetryParse: () => void;
  onLinkDocument: (docId: string, file: File) => void;
  onDelete: () => void;
}

export const TenderDetailPane: React.FC<TenderDetailPaneProps> = ({
  tender,
  onBack,
  onUpdateField,
  onVerifyField,
  onMarkReviewed,
  onRetryParse,
  onLinkDocument,
  onDelete
}) => {
  const [activeTab, setActiveTab] = useState<"summary" | "documents" | "info" | "ocr" | "review">("info");
  
  // Track selected document ID and origin group
  const [selectedDocId, setSelectedDocId] = useState<string>("");
  const [selectedDocType, setSelectedDocType] = useState<DocumentOrigin>("source");

  // Sync selected doc when tender or its documents change
  useEffect(() => {
    const sourceDocs = tender.documents?.sourceDocuments || [];
    const genOutputs = tender.documents?.generatedOutputs || [];
    const linkedPdfs = tender.documents?.extractedLinkedPdfs || [];
    const mentioned = tender.documents?.mentionedAttachments || [];

    const isStillPresent = 
      (selectedDocType === "source" && sourceDocs.some(d => d.id === selectedDocId)) ||
      (selectedDocType === "generated" && genOutputs.some(d => d.id === selectedDocId)) ||
      (selectedDocType === "linked" && linkedPdfs.some(d => d.id === selectedDocId)) ||
      (selectedDocType === "mentioned" && mentioned.some(d => d.id === selectedDocId));

    if (isStillPresent && selectedDocId) {
      return; 
    }

    const primarySource = sourceDocs.find(d => d.isPrimary);
    if (primarySource) {
      setSelectedDocId(primarySource.id);
      setSelectedDocType("source");
    } else if (sourceDocs.length > 0) {
      setSelectedDocId(sourceDocs[0].id);
      setSelectedDocType("source");
    } else if (genOutputs.length > 0) {
      setSelectedDocId(genOutputs[0].id);
      setSelectedDocType("generated");
    } else if (linkedPdfs.length > 0) {
      setSelectedDocId(linkedPdfs[0].id);
      setSelectedDocType("linked");
    } else if (mentioned.length > 0) {
      setSelectedDocId(mentioned[0].id);
      setSelectedDocType("mentioned");
    } else {
      setSelectedDocId("");
      setSelectedDocType("source");
    }
  }, [
    tender.id,
    tender.documents?.sourceDocuments?.length,
    tender.documents?.generatedOutputs?.length,
    tender.documents?.extractedLinkedPdfs?.length,
    tender.documents?.mentionedAttachments?.length
  ]);

  const getActiveDocument = (): PreviewDocument | undefined => {
    if (selectedDocType === "source") {
      return tender.documents.sourceDocuments.find((d: SourceDocumentItem) => d.id === selectedDocId) || tender.documents.sourceDocuments[0];
    }
    if (selectedDocType === "generated") {
      return tender.documents.generatedOutputs.find((d: GeneratedOutputItem) => d.id === selectedDocId);
    }
    if (selectedDocType === "linked") {
      return tender.documents.extractedLinkedPdfs.find((d: ExtractedLinkedPdfItem) => d.id === selectedDocId);
    }
    if (selectedDocType === "mentioned") {
      return tender.documents.mentionedAttachments.find((d: MentionedAttachmentItem) => d.id === selectedDocId);
    }
    return tender.documents.sourceDocuments[0];
  };

  const activeDoc = getActiveDocument();
  const isProcessing = tender.parse_status === "processing" || tender.parse_status === "pending";

  const getTenderIssues = () => {
    const list: string[] = [];
    tender.infoSheetSections.forEach((sec) => {
      const lowConf = sec.fields.filter(f => f.confidence && f.confidence < 70 && f.status === "extracted");
      const missingCrit = sec.fields.filter(f => f.critical && f.status === "missing");
      if (lowConf.length > 0) list.push(`${lowConf.length} low-confidence field(s) in ${sec.title}`);
      if (missingCrit.length > 0) list.push(`${missingCrit.length} missing critical field(s) in ${sec.title}`);
    });

    const unresolved = tender.documents.mentionedAttachments.filter((d: MentionedAttachmentItem) => !d.resolved);
    if (unresolved.length > 0) list.push(`${unresolved.length} missing/unresolved document link(s)`);
    
    return list;
  };

  const issues = getTenderIssues();
  const linkedInfoSheetFile = tender.documents.generatedOutputs.find((o: GeneratedOutputItem) => o.outputKind === "info_sheet");

  const handleSelectDocument = (id: string, origin: DocumentOrigin) => {
    setSelectedDocId(id);
    setSelectedDocType(origin);
  };

  return (
    <div className="flex-1 flex flex-col min-h-0 bg-app-bg select-none">
      {/* Detail Page Toolbar Header */}
      <div className="bg-panel-bg border-b border-divider px-6 py-4 flex items-center justify-between gap-4 shrink-0">
        <div className="flex items-center gap-3 min-w-0">
          <button
            onClick={onBack}
            className="p-1.8 bg-input-bg border border-divider hover:bg-section-tint text-text-secondary hover:text-text-primary rounded-lg transition-colors shrink-0"
          >
            <ArrowLeft className="h-4.5 w-4.5" />
          </button>
          <div className="min-w-0">
            <h2 className="text-sm font-bold text-text-primary truncate font-sans tracking-tight" title={tender.title}>
              {tender.title}
            </h2>
            <div className="flex items-center gap-2 text-xs text-text-muted font-mono mt-0.5">
              <span>REF: {tender.reference_number || tender.id}</span>
              <span>•</span>
              <span className="truncate">{tender.authorityName}</span>
            </div>
          </div>
        </div>

        {/* Action Panel */}
        <div className="flex items-center gap-2 shrink-0">
          <button
            onClick={() => {
              if (confirm(`Are you sure you want to delete "${tender.title}"?`)) {
                onDelete();
              }
            }}
            disabled={isProcessing}
            className="px-3 py-1.8 bg-input-bg border border-divider hover:bg-red-50 text-red-500 hover:text-red-700 disabled:opacity-50 text-xs font-semibold rounded-lg flex items-center gap-1.5 transition-colors cursor-pointer"
          >
            <Trash2 className="h-3.5 w-3.5" />
            <span>Delete</span>
          </button>

          <button
            onClick={onRetryParse}
            disabled={isProcessing}
            className="px-3 py-1.8 bg-input-bg border border-divider hover:bg-section-tint text-text-secondary hover:text-text-primary disabled:opacity-50 text-xs font-semibold rounded-lg flex items-center gap-1.5 transition-colors"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${isProcessing ? "animate-spin" : ""}`} />
            <span>Reparse</span>
          </button>

          <button
            onClick={() => {
              alert(`Downloading CSV Reports:\n1. tender_${tender.id}_summary.csv\n2. tender_${tender.id}_evidence.csv`);
            }}
            className="px-3 py-1.8 bg-input-bg border border-divider hover:bg-section-tint text-text-secondary hover:text-text-primary text-xs font-semibold rounded-lg flex items-center gap-1.5 transition-colors"
          >
            <Download className="h-3.5 w-3.5" />
            <span>Export Reports</span>
          </button>

          {tender.review_status !== "completed" ? (
            <button
              onClick={onMarkReviewed}
              disabled={isProcessing}
              className="px-3 py-1.8 bg-success-green hover:bg-cta-green text-panel-bg disabled:opacity-50 text-xs font-bold rounded-lg flex items-center gap-1.5 transition-colors shadow-sm"
            >
              <CheckCircle2 className="h-3.5 w-3.5 stroke-[2.5]" />
              <span>Mark Reviewed</span>
            </button>
          ) : (
            <div className="px-3 py-1.8 bg-selected-green-bg border border-selected-green-border text-success-green text-xs font-semibold rounded-lg flex items-center gap-1.5">
              <CheckCircle2 className="h-3.5 w-3.5" />
              <span>Reviewed by {tender.reviewer_name}</span>
            </div>
          )}
        </div>
      </div>

      {/* 50/50 Desktop Split Layout */}
      <div className="flex-1 grid grid-cols-1 lg:grid-cols-2 gap-4 p-4 min-h-0 overflow-hidden">
        
        {/* Left Side: Summary Cards + Structured Data Tabs */}
        <div className="flex flex-col bg-panel-bg border border-divider rounded-xl overflow-hidden min-h-0">
          
          {/* Top highlight summary grid matching ContraVault */}
          <div className="bg-card-bg px-5 py-4 border-b border-divider grid grid-cols-2 md:grid-cols-4 gap-3.5 shrink-0 select-none">
            {/* Bid Deadline */}
            <div className="space-y-1">
              <span className="text-[10px] text-text-muted font-bold uppercase tracking-wider">Bid Deadline</span>
              <p className="text-xs font-mono text-text-primary">
                {tender.deadline
                  ? new Date(tender.deadline).toLocaleDateString("en-US", {
                      day: "2-digit",
                      month: "short",
                      year: "numeric"
                    })
                  : "Not Found"}
              </p>
            </div>

            {/* Tender Value */}
            <div className="space-y-1">
              <span className="text-[10px] text-text-muted font-bold uppercase tracking-wider">Tender Value</span>
              <p className="text-xs font-mono font-semibold text-gold-text">
                {tender.tenderValue}
              </p>
            </div>

            {/* EMD Deposit */}
            <div className="space-y-1">
              <span className="text-[10px] text-text-muted font-bold uppercase tracking-wider">EMD Deposit</span>
              <p className="text-xs font-mono text-text-primary">
                {tender.emdAmount || "Exempted"}
              </p>
            </div>

            {/* Location */}
            <div className="space-y-1">
              <span className="text-[10px] text-text-muted font-bold uppercase tracking-wider">Location</span>
              <p className="text-xs font-mono text-text-primary truncate" title={tender.location || `${tender.location_city}, ${tender.location_state}`}>
                {tender.location || `${tender.location_city}, ${tender.location_state}`}
              </p>
            </div>
          </div>

          {/* Tabs menu bar */}
          <div className="bg-card-bg border-b border-divider flex p-1 gap-1 shrink-0">
            <button
              onClick={() => setActiveTab("info")}
              className={`flex-1 py-2 text-center text-xs font-bold rounded-lg transition-colors ${
                activeTab === "info" ? "bg-panel-bg text-success-green shadow-sm" : "text-text-muted hover:text-text-secondary"
              }`}
            >
              Info Sheet
            </button>
            <button
              onClick={() => setActiveTab("documents")}
              className={`flex-1 py-2 text-center text-xs font-bold rounded-lg transition-colors flex items-center justify-center gap-1.5 ${
                activeTab === "documents" ? "bg-panel-bg text-success-green shadow-sm" : "text-text-muted hover:text-text-secondary"
              }`}
            >
              <span>Documents ({
                tender.documents.sourceDocuments.length + 
                tender.documents.generatedOutputs.length + 
                tender.documents.extractedLinkedPdfs.length + 
                tender.documents.mentionedAttachments.length
              })</span>
              {tender.documents.mentionedAttachments.some((d: MentionedAttachmentItem) => !d.resolved) && (
                <span className="h-1.5 w-1.5 rounded-full bg-warning-text animate-ping"></span>
              )}
            </button>
            <button
              onClick={() => setActiveTab("summary")}
              className={`flex-1 py-2 text-center text-xs font-bold rounded-lg transition-colors ${
                activeTab === "summary" ? "bg-panel-bg text-success-green shadow-sm" : "text-text-muted hover:text-text-secondary"
              }`}
            >
              Synopsis
            </button>
            <button
              onClick={() => setActiveTab("ocr")}
              className={`flex-1 py-2 text-center text-xs font-bold rounded-lg transition-colors ${
                activeTab === "ocr" ? "bg-panel-bg text-success-green shadow-sm" : "text-text-muted hover:text-text-secondary"
              }`}
            >
              OCR Text
            </button>
            <button
              onClick={() => setActiveTab("review")}
              className={`flex-1 py-2 text-center text-xs font-bold rounded-lg transition-colors ${
                activeTab === "review" ? "bg-panel-bg text-success-green shadow-sm" : "text-text-muted hover:text-text-secondary"
              }`}
            >
              Checklist
            </button>
          </div>

          {/* Active Tab Viewport */}
          <div className="flex-1 p-5 overflow-hidden min-h-0 flex flex-col">
            {isProcessing ? (
              <div className="flex-1 flex flex-col items-center justify-center text-text-muted space-y-4">
                <LoaderSkeleton />
                <span className="text-xs font-mono">Parsing document elements & reading text...</span>
              </div>
            ) : (
              <div className="flex-1 overflow-auto min-h-0">
                {/* Synopsis Panel */}
                {activeTab === "summary" && (
                  <div className="space-y-5">
                    {/* Issues panel */}
                    {issues.length > 0 && (
                      <div className="bg-alert-bg border border-alert-text/10 rounded-lg p-4 space-y-2">
                        <h4 className="text-xs font-semibold text-alert-text flex items-center gap-1.5 uppercase tracking-wide">
                          <AlertTriangle className="h-4 w-4" />
                          <span>Validation issues flagged</span>
                        </h4>
                        <ul className="list-disc pl-4 text-xs text-text-secondary space-y-1.5 leading-relaxed">
                          {issues.map((issue, idx) => (
                            <li key={idx}>{issue}</li>
                          ))}
                        </ul>
                      </div>
                    )}

                    <div className="space-y-4">
                      <h4 className="text-xs font-bold text-text-muted uppercase tracking-widest border-b border-divider pb-2">
                        Extraction Scope Metadata
                      </h4>
                      <table className="w-full text-xs">
                        <tbody className="divide-y divide-divider/40">
                          <tr>
                            <td className="py-3 font-semibold text-text-secondary w-1/3">Issuing Authority</td>
                            <td className="py-3 text-text-primary">{tender.authorityName}</td>
                          </tr>
                          <tr>
                            <td className="py-3 font-semibold text-text-secondary">Tender Reference ID</td>
                            <td className="py-3 text-text-primary font-mono">{tender.reference_number || tender.id}</td>
                          </tr>
                          <tr>
                            <td className="py-3 font-semibold text-text-secondary">Location Details</td>
                            <td className="py-3 text-text-primary">{tender.location || `${tender.location_city}, ${tender.location_state}`}</td>
                          </tr>
                          <tr>
                            <td className="py-3 font-semibold text-text-secondary">Publish Date</td>
                            <td className="py-3 text-text-primary">
                              {tender.publish_date ? new Date(tender.publish_date).toLocaleString("en-IN") : "N/A"}
                            </td>
                          </tr>
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}

                {/* Documents Panel */}
                {activeTab === "documents" && (
                  <DocumentsPanel
                    documents={tender.documents}
                    onLinkDocument={onLinkDocument}
                    selectedDocId={selectedDocId}
                    onSelectDocument={handleSelectDocument}
                  />
                )}

                {/* Info Sheet Panel */}
                {activeTab === "info" && (
                  <div className="space-y-4">
                    {/* Excel Deliverable box */}
                    {linkedInfoSheetFile && (
                      <div className="bg-card-bg border border-divider rounded-lg p-3.5 flex items-center justify-between select-none shadow-sm border-l-4 border-l-success-green">
                        <div className="flex items-center gap-3">
                          <Table className="h-5 w-5 text-success-green shrink-0" />
                          <div className="leading-tight">
                            <p className="text-xs font-bold text-text-primary truncate max-w-[200px] md:max-w-xs">{linkedInfoSheetFile.name}</p>
                            <p className="text-[9px] text-text-muted mt-0.5">OCR Generated Output • Confidence: {tender.parse_confidence}%</p>
                          </div>
                        </div>
                        <div className="flex gap-2">
                          <button
                            onClick={() => {
                              setSelectedDocId(linkedInfoSheetFile.id);
                              setSelectedDocType("generated");
                              setActiveTab("documents");
                            }}
                            className="px-2.5 py-1.2 bg-input-bg border border-divider hover:bg-section-tint text-text-secondary hover:text-text-primary text-[10px] font-bold rounded-lg transition-colors flex items-center gap-1"
                          >
                            <Eye className="h-3 w-3" />
                            <span>Preview Sheet</span>
                          </button>
                          <button
                            onClick={async () => {
                              if (linkedInfoSheetFile.url) {
                                try {
                                  await handleSecureDownload(linkedInfoSheetFile.url, linkedInfoSheetFile.name);
                                } catch (err: any) {
                                  alert(err.message || "Failed to download spreadsheet.");
                                }
                              }
                            }}
                            className="px-2.5 py-1.2 bg-success-green hover:bg-cta-green text-panel-bg text-[10px] font-bold rounded-lg transition-colors flex items-center gap-1 shadow-sm cursor-pointer"
                          >
                            <Download className="h-3 w-3" />
                            <span>Excel</span>
                          </button>
                        </div>
                      </div>
                    )}

                    <InfoSheetPanel
                      sections={tender.infoSheetSections}
                      onUpdateField={onUpdateField}
                      onVerifyField={onVerifyField}
                    />
                  </div>
                )}

                {/* OCR Text Panel */}
                {activeTab === "ocr" && <OCRPreviewPanel rawText={tender.rawTextPages?.map(p => p.text).join("\n") || tender.raw_ocr_text || ""} />}

                {/* Checklist Panel */}
                {activeTab === "review" && (
                  <div className="space-y-4 font-sans">
                    <div className="bg-card-bg p-4 border border-divider rounded-lg space-y-3">
                      <h4 className="text-xs font-semibold text-text-primary">Review Checklist Control</h4>
                      <p className="text-[11px] text-text-secondary">
                        Check off verification steps below to clear alerts and confirm extraction status validity.
                      </p>
                    </div>

                    <div className="space-y-2">
                      <div className="flex items-center gap-3 p-3 bg-input-bg border border-divider rounded-lg select-none">
                        <input
                          type="checkbox"
                          checked={tender.review_status === "completed" || tender.infoSheetSections.every((sec) => sec.fields.every(f => f.status === "verified"))}
                          readOnly
                          className="h-4.5 w-4.5 accent-success-green rounded border-divider cursor-pointer shrink-0"
                        />
                        <div className="text-xs">
                          <p className="font-semibold text-text-primary">Validate extracted values</p>
                          <p className="text-[10px] text-text-secondary mt-0.5">Ensure all info sheet rows match primary document details.</p>
                        </div>
                      </div>

                      <div className="flex items-center gap-3 p-3 bg-input-bg border border-divider rounded-lg select-none">
                        <input
                          type="checkbox"
                          checked={tender.documents.mentionedAttachments.every((d: MentionedAttachmentItem) => d.resolved)}
                          readOnly
                          className="h-4.5 w-4.5 accent-success-green rounded border-divider cursor-pointer shrink-0"
                        />
                        <div className="text-xs">
                          <p className="font-semibold text-text-primary">Resolve supporting documents</p>
                          <p className="text-[10px] text-text-secondary mt-0.5">All referenced attachments must be uploaded or ignored.</p>
                        </div>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        {/* Right Side: PDF Preview Pane docked */}
        <div className="min-h-0 h-full">
          <PDFPreviewPane activeDoc={activeDoc} infoSheetFields={tender.infoSheetSections.reduce((acc: InfoSheetField[], sec) => [...acc, ...sec.fields], [])} />
        </div>
      </div>
    </div>
  );
};

const LoaderSkeleton = () => (
  <div className="w-full space-y-4">
    <div className="h-4 bg-section-tint rounded w-1/3 animate-pulse"></div>
    <div className="space-y-2">
      <div className="h-8 bg-section-tint rounded animate-pulse"></div>
      <div className="h-8 bg-section-tint rounded animate-pulse"></div>
      <div className="h-8 bg-section-tint rounded animate-pulse"></div>
    </div>
  </div>
);
export default TenderDetailPane;
