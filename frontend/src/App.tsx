import { useState } from "react";
import UploadForm from "./components/UploadForm";
import PDFPreviewPane from "./components/PDFPreviewPane";
import TenderDetailPane from "./components/TenderDetailPane";
import {
  createTenderProject,
  getExtractedFields,
  pollDocumentStatus,
  processComplete,
  triggerProcessing,
  uploadDocuments,
} from "./services/api";
import type { ExtractedField, ProcessCompleteResult } from "./types/tender";

type Stage = "idle" | "uploading" | "processing" | "extracting" | "ready" | "error";

interface ResultState {
  tenderProjectId: string;
  documentId: string;
  filename: string;
  pageCount: number;
  fields: ExtractedField[];
  processResult: ProcessCompleteResult | null;
}

const STAGE_LABEL: Record<Stage, string> = {
  idle: "",
  uploading: "Uploading document…",
  processing: "Running OCR & layout analysis on the document (Tesseract)…",
  extracting: "Extracting structured tender fields…",
  ready: "",
  error: "",
};

export default function App() {
  const [stage, setStage] = useState<Stage>("idle");
  const [error, setError] = useState<string | null>(null);
  const [warning, setWarning] = useState<string | null>(null);
  const [result, setResult] = useState<ResultState | null>(null);

  async function handleSubmit(tenderName: string, file: File, email: string | null) {
    setError(null);
    setWarning(null);
    setResult(null);
    try {
      setStage("uploading");
      const tender = await createTenderProject(tenderName);
      const uploadResponse = await uploadDocuments(tender.tender_project_id, [file]);
      if (uploadResponse.failed.length > 0 || uploadResponse.documents.length === 0) {
        throw new Error("Upload failed — the backend rejected this file.");
      }
      const documentId = uploadResponse.documents[0].document_id;

      setStage("processing");
      await triggerProcessing(tender.tender_project_id, documentId);
      const detail = await pollDocumentStatus(tender.tender_project_id, documentId);
      const doc = detail.documents.find((d) => d.document_id === documentId);
      if (!doc || doc.processing_status !== "completed") {
        throw new Error(doc?.error_message || "OCR processing failed.");
      }

      setStage("extracting");
      let processResult: ProcessCompleteResult | null = null;
      const extracted = await getExtractedFields(documentId);
      try {
        processResult = await processComplete(tender.tender_project_id, documentId, email ?? undefined);
      } catch (e) {
        // process-complete persists + exports CSV (and optionally emails it).
        // Its failure is surfaced as a non-blocking warning so OCR results
        // are still shown; the user can retry or download data manually.
        const msg = e instanceof Error ? e.message : String(e);
        setWarning(`Results saved, but the export step encountered an issue: ${msg}`);
      }

      setResult({
        tenderProjectId: tender.tender_project_id,
        documentId,
        filename: doc.original_filename,
        pageCount: extracted.page_count,
        fields: extracted.extracted_fields,
        processResult,
      });
      setStage("ready");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setStage("error");
    }
  }

  const busy = stage === "uploading" || stage === "processing" || stage === "extracting";

  return (
    <div className="app-shell">
      <header className="app-header">
        <span className="logo-badge">TENDER OCR</span>
        <h1>Document Intelligence Pipeline</h1>
        {result && (
          <button
            className="btn btn-secondary"
            style={{ marginLeft: "auto" }}
            onClick={() => {
              setResult(null);
              setStage("idle");
              setError(null);
            }}
          >
            New upload
          </button>
        )}
      </header>

      <main className="app-main">
        {!result && (
          <div className="upload-screen">
            <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem", alignItems: "center" }}>
              <UploadForm onSubmit={handleSubmit} submitting={busy} error={stage === "error" ? error : null} />
              {warning && <div className="warning-banner">{warning}</div>}
              {busy && (
                <div className="status-row">
                  <span className="status-dot processing" />
                  <span>{STAGE_LABEL[stage]}</span>
                </div>
              )}
            </div>
          </div>
        )}

        {result && (
          <div className="workspace">
            <PDFPreviewPane documentId={result.documentId} filename={result.filename} />
            <TenderDetailPane
              filename={result.filename}
              pageCount={result.pageCount}
              fields={result.fields}
              processResult={result.processResult}
            />
          </div>
        )}
      </main>
    </div>
  );
}
