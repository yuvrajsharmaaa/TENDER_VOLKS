import React from "react";
import type { TenderDocuments, DocumentOrigin } from "../../types/tender";
import { DocumentRow } from "./document-groups/DocumentRow";

interface DocumentsPanelProps {
  documents: TenderDocuments;
  onLinkDocument: (docId: string, file: File) => void;
  selectedDocId: string;
  onSelectDocument: (docId: string, origin: DocumentOrigin) => void;
}

export const DocumentsPanel: React.FC<DocumentsPanelProps> = ({
  documents,
  onLinkDocument,
  selectedDocId,
  onSelectDocument
}) => {
  return (
    <div className="space-y-6 max-h-[calc(100vh-220px)] overflow-y-auto pr-2 select-none">
      
      {/* A. Source Documents */}
      <div className="space-y-2.5">
        <div className="border-b border-divider pb-1 flex justify-between items-center select-none">
          <span className="text-[10px] text-text-muted font-bold uppercase tracking-widest">
            A. Source Documents ({documents.sourceDocuments.length})
          </span>
        </div>
        <div className="space-y-2">
          {documents.sourceDocuments.map((doc) => (
            <DocumentRow
              key={doc.id}
              doc={doc}
              isSelected={doc.id === selectedDocId}
              onClick={() => onSelectDocument(doc.id, "source")}
            />
          ))}
        </div>
      </div>

      {/* B. Generated Outputs */}
      <div className="space-y-2.5">
        <div className="border-b border-divider pb-1 flex justify-between items-center select-none">
          <span className="text-[10px] text-text-muted font-bold uppercase tracking-widest">
            B. Generated Outputs ({documents.generatedOutputs.length})
          </span>
        </div>
        <div className="space-y-2">
          {documents.generatedOutputs.map((doc) => (
            <DocumentRow
              key={doc.id}
              doc={doc}
              isSelected={doc.id === selectedDocId}
              onClick={() => onSelectDocument(doc.id, "generated")}
            />
          ))}
        </div>
      </div>

      {/* C. Extracted Linked PDFs */}
      <div className="space-y-2.5">
        <div className="border-b border-divider pb-1 flex justify-between items-center select-none">
          <span className="text-[10px] text-text-muted font-bold uppercase tracking-widest">
            C. Extracted Linked PDFs ({documents.extractedLinkedPdfs.length})
          </span>
        </div>
        {documents.extractedLinkedPdfs.length === 0 ? (
          <p className="text-[11px] text-text-muted italic px-2">No hyperlinked sub-documents detected in main PDF.</p>
        ) : (
          <div className="space-y-2">
            {documents.extractedLinkedPdfs.map((doc) => (
              <DocumentRow
                key={doc.id}
                doc={doc}
                isSelected={doc.id === selectedDocId}
                onClick={() => onSelectDocument(doc.id, "linked")}
              />
            ))}
          </div>
        )}
      </div>

      {/* D. Mentioned Attachments */}
      <div className="space-y-2.5">
        <div className="border-b border-divider pb-1 flex justify-between items-center select-none">
          <span className="text-[10px] text-text-muted font-bold uppercase tracking-widest">
            D. Mentioned Attachments ({documents.mentionedAttachments.length})
          </span>
        </div>
        {documents.mentionedAttachments.length === 0 ? (
          <p className="text-[11px] text-text-muted italic px-2">No unlinked document mentions parsed from text.</p>
        ) : (
          <div className="space-y-2">
            {documents.mentionedAttachments.map((doc) => (
              <DocumentRow
                key={doc.id}
                doc={doc}
                isSelected={doc.id === selectedDocId}
                onClick={() => onSelectDocument(doc.id, "mentioned")}
                onLinkFile={(file) => onLinkDocument(doc.id, file)}
              />
            ))}
          </div>
        )}
      </div>

    </div>
  );
};
export default DocumentsPanel;
