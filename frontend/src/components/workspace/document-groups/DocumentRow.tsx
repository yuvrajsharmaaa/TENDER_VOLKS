import React, { useRef } from "react";
import { FileText, Link2, Upload, ExternalLink, HelpCircle, FileCheck } from "lucide-react";

interface DocumentRowProps {
  doc: any; // SourceDocumentItem | GeneratedOutputItem | ExtractedLinkedPdfItem | MentionedAttachmentItem
  isSelected: boolean;
  onClick: () => void;
  onLinkFile?: (file: File) => void;
}

export const DocumentRow: React.FC<DocumentRowProps> = ({
  doc,
  isSelected,
  onClick,
  onLinkFile
}) => {
  const fileInputRef = useRef<HTMLInputElement>(null);

  const getIcon = () => {
    if (doc.origin === "generated") {
      return <FileCheck className="h-4.5 w-4.5 shrink-0 text-success-green" />;
    }
    if (doc.origin === "linked") {
      return <Link2 className={`h-4 w-4 shrink-0 ${isSelected ? "text-success-green" : "text-text-secondary"}`} />;
    }
    if (doc.origin === "mentioned") {
      return <HelpCircle className={`h-4.5 w-4.5 shrink-0 ${doc.resolved ? "text-success-green" : "text-warning-text"}`} />;
    }
    return <FileText className={`h-4.5 w-4.5 shrink-0 ${isSelected ? "text-success-green" : "text-text-muted"}`} />;
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file && onLinkFile) {
      onLinkFile(file);
    }
  };

  const isMentionedUnresolved = doc.origin === "mentioned" && !doc.resolved;

  return (
    <div
      onClick={onClick}
      className={`border rounded-lg p-3 cursor-pointer flex flex-col gap-2 transition-all ${
        isMentionedUnresolved
          ? "border-warning-bg bg-warning-bg/10 hover:bg-warning-bg/20"
          : isSelected
            ? "bg-selected-green-bg border-selected-green-border shadow-sm text-success-green animate-fadeIn"
            : "bg-input-bg border-divider hover:bg-section-tint/30 text-text-primary"
      }`}
    >
      <div className="flex items-center justify-between gap-4 min-w-0">
        <div className="flex items-center gap-2.5 min-w-0">
          {getIcon()}
          <div className="min-w-0 leading-tight">
            <span className={`text-xs font-semibold truncate block ${isSelected ? "text-success-green" : "text-text-secondary"}`} title={doc.name}>
              {doc.name}
            </span>
            
            {/* Origin specific indicators */}
            <div className="flex items-center gap-1.5 mt-0.5 text-[9px] text-text-muted">
              {doc.origin === "source" && doc.isPrimary && (
                <span className="text-success-green font-bold bg-selected-green-bg px-1 rounded border border-selected-green-border text-[8px] uppercase">
                  Primary Tender File
                </span>
              )}
              {doc.origin === "generated" && (
                <span className="text-[9px] text-text-muted font-mono">
                  Generated Output ({doc.generator})
                </span>
              )}
              {doc.origin === "linked" && (
                <span className="text-text-muted">
                  Discovered at Page {doc.sourcePage}
                </span>
              )}
              {doc.origin === "mentioned" && (
                <span className={`text-[8px] font-bold px-1.5 py-0.2 rounded border uppercase font-mono ${
                  doc.resolved ? "bg-selected-green-bg border-selected-green-border text-success-green" : "bg-warning-bg border-warning-text/10 text-warning-text"
                }`}>
                  {doc.resolved ? "Resolved" : "Unresolved Mention"}
                </span>
              )}
            </div>
          </div>
        </div>

        {/* Badges/Actions on Right */}
        <div className="flex items-center gap-2 shrink-0">
          <span className={`text-[9px] px-1.5 py-0.5 rounded border font-mono uppercase font-bold shrink-0 ${
            doc.origin === "generated"
              ? "bg-selected-green-bg border-selected-green-border text-success-green"
              : "bg-panel-bg border-divider text-text-muted"
          }`}>
            {doc.kind}
          </span>
          {doc.url && doc.url !== "#" && (
            <a
              href={doc.url}
              target="_blank"
              rel="noopener noreferrer"
              className="p-1 hover:bg-panel-bg rounded text-text-secondary hover:text-text-primary"
              onClick={(e) => e.stopPropagation()}
              title="Open document in new tab"
            >
              <ExternalLink className="h-3.5 w-3.5" />
            </a>
          )}
        </div>
      </div>

      {/* Anchor Text / Mention Snippet if available */}
      {(doc.anchorText || doc.mentionText) && (
        <p className="text-[10px] text-text-muted italic leading-relaxed line-clamp-1 border-t border-divider/20 pt-1.5 mt-0.5 pl-7">
          Context: "{doc.anchorText || doc.mentionText}"
        </p>
      )}

      {/* Link File Action for unresolved mentions */}
      {isMentionedUnresolved && onLinkFile && (
        <div className="flex justify-end pt-1">
          <input
            type="file"
            ref={fileInputRef}
            onChange={handleFileChange}
            className="hidden"
            accept=".pdf,.doc,.docx,.xlsx"
          />
          <button
            onClick={(e) => {
              e.stopPropagation();
              fileInputRef.current?.click();
            }}
            className="px-2.5 py-1 bg-warning-bg hover:bg-warning-bg/85 border border-warning-text/10 text-warning-text font-bold text-[10px] rounded transition-colors flex items-center gap-1.5 shadow-sm animate-pulse-glow"
          >
            <Upload className="h-3 w-3" />
            <span>Link File</span>
          </button>
        </div>
      )}
    </div>
  );
};
export default DocumentRow;
