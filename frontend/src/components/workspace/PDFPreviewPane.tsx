import React, { useState } from "react";
import { FileText, ExternalLink, AlertTriangle, Table, Download } from "lucide-react";
import type { InfoSheetField } from "../../types/tender";

interface PDFPreviewPaneProps {
  activeDoc: any; // PreviewDocument
  title: string;
  infoSheetFields: InfoSheetField[];
}

export const PDFPreviewPane: React.FC<PDFPreviewPaneProps> = ({ activeDoc, title, infoSheetFields }) => {
  const [zoom, setZoom] = useState(100);
  const [page, setPage] = useState(1);

  if (!activeDoc) {
    return (
      <div className="h-full flex flex-col items-center justify-center bg-card-bg border border-divider rounded-xl p-8 text-center text-text-muted select-none">
        <FileText className="h-16 w-16 text-text-disabled mb-4" />
        <h4 className="text-sm font-bold text-text-secondary mb-1">No Document Selected</h4>
        <p className="text-xs text-text-muted max-w-xs leading-relaxed">
          Select a file from the Left Documents workspace panel to review its contents.
        </p>
      </div>
    );
  }

  const isXlsxOutput = activeDoc.kind === "xlsx" || activeDoc.kind === "csv" || activeDoc.outputKind === "info_sheet";
  const isMentionedUnresolved = activeDoc.origin === "mentioned" && !activeDoc.resolved;
  const isPdf = activeDoc.kind === "pdf" && activeDoc.url;

  return (
    <div className="h-full flex flex-col bg-section-tint border border-divider rounded-xl overflow-hidden shadow-sm">
      {/* Top toolbar */}
      <div className="bg-card-bg px-4 py-2.5 border-b border-divider flex items-center justify-between gap-4 shrink-0 select-none">
        <div className="flex items-center gap-2 overflow-hidden">
          {isXlsxOutput ? (
            <Table className="h-4 w-4 text-emerald-600 shrink-0" />
          ) : (
            <FileText className="h-4 w-4 text-success-green shrink-0" />
          )}
          <span className="text-xs font-bold text-text-secondary truncate font-sans" title={activeDoc.name}>
            {activeDoc.name}
          </span>
          <span className="text-[9px] bg-panel-bg text-text-muted px-1.5 py-0.2 rounded border border-divider font-mono uppercase font-bold shrink-0">
            {activeDoc.origin}
          </span>
        </div>

        {/* Toolbar controls */}
        <div className="flex items-center gap-3 shrink-0">
          {isPdf && (
            <>
              <div className="flex items-center gap-1 text-[11px] text-text-secondary bg-panel-bg px-2 py-1 rounded border border-divider">
                <span>Page</span>
                <input
                  type="number"
                  value={page}
                  onChange={(e) => setPage(Math.max(1, parseInt(e.target.value) || 1))}
                  className="w-8 bg-transparent text-center border-none text-text-primary focus:outline-none font-mono font-bold"
                />
                <span className="text-text-muted">of 12</span>
              </div>

              <div className="flex items-center bg-panel-bg rounded border border-divider">
                <button
                  onClick={() => setZoom(prev => Math.max(prev - 25, 50))}
                  className="p-1.5 hover:bg-section-tint text-text-secondary hover:text-text-primary transition-colors text-xs font-bold"
                >
                  -
                </button>
                <span className="text-[10px] font-mono font-bold text-text-secondary px-1">{zoom}%</span>
                <button
                  onClick={() => setZoom(prev => Math.min(prev + 25, 200))}
                  className="p-1.5 hover:bg-section-tint text-text-secondary hover:text-text-primary transition-colors text-xs font-bold"
                >
                  +
                </button>
              </div>
            </>
          )}

          {activeDoc.url && activeDoc.url !== "#" && (
            <a
              href={activeDoc.url}
              target="_blank"
              rel="noopener noreferrer"
              className="p-1.5 bg-panel-bg border border-divider hover:bg-section-tint text-text-secondary hover:text-text-primary rounded transition-colors"
              title="Open in new tab"
            >
              <ExternalLink className="h-3.5 w-3.5" />
            </a>
          )}
        </div>
      </div>

      {/* Viewport content */}
      <div className="flex-1 bg-section-tint overflow-auto p-6 flex justify-center items-start">
        
        {/* Case 1: PDF Document sheet viewer */}
        {isPdf && (
          <div
            style={{ width: `${zoom}%`, maxWidth: "800px" }}
            className="bg-panel-bg border border-divider rounded-md shadow-sm p-8 min-h-[700px] flex flex-col justify-between select-text transition-all relative font-sans text-text-secondary animate-fadeIn"
          >
            <div className="absolute top-0 left-0 right-0 h-1 bg-success-green/60"></div>
            
            <div className="space-y-5">
              {/* Document Header */}
              <div className="border-b border-divider/60 pb-3">
                <span className="text-[9px] font-mono tracking-widest text-text-muted uppercase">
                  {activeDoc.origin === "linked" ? `DISCOVERED LINK AT PAGE ${activeDoc.sourcePage} ` : "PRIMARY SOURCE DOC "} 
                  | Page {page} of 12
                </span>
                <h2 className="text-sm font-bold text-text-primary mt-1 font-serif leading-snug">
                  {activeDoc.name.toUpperCase()}
                </h2>
                {activeDoc.anchorText && (
                  <p className="text-[10px] text-text-muted mt-2 bg-input-bg border border-divider/50 p-2.5 rounded italic leading-relaxed">
                    Source Anchor context: "{activeDoc.anchorText}" (Extraction confidence: {activeDoc.extractionConfidence || 95}%)
                  </p>
                )}
              </div>

              {/* Text pages content */}
              <div className="space-y-4 text-xs leading-relaxed text-text-primary font-serif">
                <p>
                  <strong className="text-text-primary font-sans">1. INVITATION:</strong> This document represents the detailed specification sheets for Raipur-Bilaspur Expressway major bridge construction contract bindings. Bids must conform to Chhattisgarh PWD local guidelines and satisfy minimum average audit figures.
                </p>
                
                {activeDoc.isPrimary && (
                  <div className="bg-selected-green-bg/60 border border-selected-green-border rounded p-3.5 my-2 space-y-1 font-sans border-l-4 border-l-success-green">
                    <span className="text-[9px] font-bold text-success-green uppercase tracking-wide">Extracted Coordinate Reference [Confidence 97%]</span>
                    <p className="text-[11px] text-text-secondary leading-relaxed">
                      Estimated Project Cost: <span className="bg-gold-bg text-gold-text font-mono font-bold px-1.5 py-0.5 rounded border border-gold-fill/20">
                        {title.includes("Drainage") ? "INR 1.65 Crore" : "INR 2.44 Crores"}
                      </span>.
                    </p>
                    <p className="text-[11px] text-text-secondary leading-relaxed">
                      EMD Deposit requirement: <span className="bg-gold-bg text-gold-text font-mono font-bold px-1.5 py-0.5 rounded border border-gold-fill/20">
                        {title.includes("Drainage") ? "INR 3,20,000/-" : "INR 4,88,000/-"}
                      </span>. Exemption is allowed for registered MSE/NSIC companies upon validation.
                    </p>
                  </div>
                )}

                <p>
                  <strong className="text-text-primary font-sans">2. SUBMISSIONS:</strong> Ensure compliance with all schedule dates. Checklists should be certified by competent authorities.
                </p>
              </div>
            </div>

            <div className="border-t border-divider/60 pt-4 flex justify-between items-center text-[9px] font-mono text-text-muted">
              <span>{activeDoc.name}</span>
              <span>VERIFY CAREFULLY</span>
            </div>
          </div>
        )}

        {/* Case 2: XLSX / Spreadsheet Grid view */}
        {isXlsxOutput && (
          <div className="w-full max-w-2xl bg-panel-bg border border-divider rounded-lg shadow-sm overflow-hidden flex flex-col font-sans select-none animate-fadeIn">
            {/* Sheet Tabs Header */}
            <div className="bg-card-bg border-b border-divider px-4 py-2.5 flex items-center justify-between text-xs text-text-secondary">
              <span className="font-bold flex items-center gap-1.5">
                <Table className="h-4.5 w-4.5 text-emerald-600" />
                <span>Spreadsheet Artifact Preview — extracted_fields_schema</span>
              </span>
              <span className="text-[10px] text-text-muted font-mono">Format: Microsoft Excel (.xlsx)</span>
            </div>

            {/* Grid Table */}
            <div className="overflow-x-auto p-4 bg-panel-bg">
              <table className="w-full border-collapse border border-divider text-left text-xs font-mono">
                <thead>
                  <tr className="bg-section-tint text-text-secondary border-b border-divider font-sans">
                    <th className="py-2 px-3 border-r border-divider w-8 text-center text-[10px] font-bold bg-section-tint/60"></th>
                    <th className="py-2 px-3 border-r border-divider text-text-primary text-[10px] uppercase font-bold">Field Name (Column A)</th>
                    <th className="py-2 px-3 border-r border-divider text-text-primary text-[10px] uppercase font-bold">Extracted Value (Column B)</th>
                    <th className="py-2 px-3 text-text-primary text-[10px] uppercase font-bold">Confidence (Column C)</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-divider">
                  {infoSheetFields.length === 0 ? (
                    <tr>
                      <td colSpan={4} className="py-8 text-center text-text-muted font-sans font-medium">
                        Info Sheet data is empty or pending extraction processing.
                      </td>
                    </tr>
                  ) : (
                    infoSheetFields.map((field, idx) => (
                      <tr key={field.id} className="hover:bg-section-tint/30 transition-colors">
                        <td className="py-2 px-3 border-r border-divider text-center text-[10px] text-text-muted font-sans font-bold bg-section-tint/40 w-8 select-none">
                          {idx + 1}
                        </td>
                        <td className="py-2 px-3 border-r border-divider font-sans font-semibold text-text-secondary">
                          {field.label}
                        </td>
                        <td className="py-2 px-3 border-r border-divider text-text-primary break-all">
                          {field.value || <span className="text-alert-text italic font-sans">[Missing]</span>}
                        </td>
                        <td className="py-2 px-3 text-text-secondary font-sans font-medium">
                          <span className={field.confidence && field.confidence < 70 ? "text-warning-text font-bold" : "text-success-green"}>
                            {field.confidence || 90}%
                          </span>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
            
            {/* Sheet footer tabs */}
            <div className="bg-card-bg border-t border-divider px-4 py-2 flex gap-4 text-[10px] font-sans font-bold text-text-secondary select-none">
              <span className="text-emerald-600 border-b-2 border-emerald-600 px-2 py-0.5">InfoSheet</span>
              <span className="text-text-disabled cursor-not-allowed px-2 py-0.5">RawData</span>
              <span className="text-text-disabled cursor-not-allowed px-2 py-0.5">EvidenceLogs</span>
            </div>
          </div>
        )}

        {/* Case 3: Mentioned Unresolved Placeholder */}
        {isMentionedUnresolved && (
          <div className="max-w-md w-full bg-panel-bg border border-warning-bg rounded-xl p-6 shadow-sm flex flex-col items-center justify-center text-center font-sans space-y-4 select-none animate-fadeIn bg-warning-bg/10">
            <AlertTriangle className="h-12 w-12 text-warning-text animate-pulse" />
            <div>
              <h4 className="text-sm font-bold text-warning-text uppercase tracking-wide">Mentioned Attachment Unresolved</h4>
              <p className="text-xs text-text-secondary mt-2 leading-relaxed">
                The document <strong>"{activeDoc.name}"</strong> is mentioned on Page {activeDoc.sourcePage || 8} in the following context:
              </p>
              <div className="bg-panel-bg border border-divider/60 p-3.5 rounded-lg text-xs italic text-text-secondary my-3.5 leading-relaxed text-left border-l-2 border-l-warning-text/60">
                "{activeDoc.mentionText || "Referenced corrigendum file for dimensions changes."}"
              </div>
              <p className="text-[11px] text-text-muted leading-relaxed">
                To resolve this mention and unlock interactive preview reviews, please click the <strong>"Link File"</strong> button in the left panel to upload this document.
              </p>
            </div>
          </div>
        )}

        {/* Case 4: Fallback generic document view */}
        {!isPdf && !isXlsxOutput && !isMentionedUnresolved && (
          <div className="h-full flex flex-col items-center justify-center bg-card-bg border border-divider rounded-xl p-8 text-center text-text-muted select-none w-full max-w-sm animate-fadeIn">
            <FileText className="h-12 w-12 text-text-disabled mb-3" />
            <h4 className="text-sm font-bold text-text-secondary mb-1">Preview Unavailable</h4>
            <p className="text-xs text-text-muted leading-relaxed mb-4">
              Inline visual reviews are not supported for this file format ({activeDoc.kind}). You can download this document to inspect it locally.
            </p>
            {activeDoc.url && activeDoc.url !== "#" && (
              <a
                href={activeDoc.url}
                onClick={() => alert(`Downloading ${activeDoc.name}...`)}
                className="px-4 py-2 bg-success-green hover:bg-cta-green text-panel-bg text-xs font-bold rounded-lg transition-colors shadow-sm flex items-center gap-1.5"
              >
                <Download className="h-3.5 w-3.5" />
                <span>Download Document</span>
              </a>
            )}
          </div>
        )}

      </div>
    </div>
  );
};
export default PDFPreviewPane;
