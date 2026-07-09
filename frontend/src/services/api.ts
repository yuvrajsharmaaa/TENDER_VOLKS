// Thin fetch wrapper around the real FastAPI backend. All paths are relative
// so they work through the Vite dev proxy (see vite.config.ts) in development
// and through a single origin in production — no hardcoded hosts/ports here.
import type {
  ExtractedFieldsResult,
  ProcessCompleteResult,
  TenderProject,
  TenderProjectDetail,
} from "../types/tender";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init);
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? JSON.stringify(body);
    } catch {
      // response wasn't JSON; keep statusText
    }
    throw new Error(`${res.status} ${detail}`);
  }
  return res.json() as Promise<T>;
}

export async function createTenderProject(tenderName: string): Promise<TenderProject> {
  return request<TenderProject>("/tenders", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      project_id: crypto.randomUUID(),
      tender_name: tenderName,
      source_label: "web-upload",
    }),
  });
}

export async function uploadDocuments(
  tenderProjectId: string,
  files: File[],
): Promise<{ tender_project_id: string; documents: { document_id: string; original_filename: string }[]; failed: unknown[] }> {
  const form = new FormData();
  files.forEach((f) => form.append("files", f));
  return request(`/tenders/${tenderProjectId}/documents`, {
    method: "POST",
    body: form,
  });
}

export async function triggerProcessing(
  tenderProjectId: string,
  documentId: string,
): Promise<{ document_id: string; processing_status: string; message: string }> {
  return request(`/tenders/${tenderProjectId}/documents/${documentId}/process`, {
    method: "POST",
  });
}

export async function getTenderDetail(tenderProjectId: string): Promise<TenderProjectDetail> {
  return request<TenderProjectDetail>(`/tenders/${tenderProjectId}`);
}

export async function getExtractedFields(documentId: string): Promise<ExtractedFieldsResult> {
  return request<ExtractedFieldsResult>(`/job/${documentId}/extracted-fields`);
}

export async function processComplete(
  tenderId: string,
  fileId: string,
  email?: string,
): Promise<ProcessCompleteResult> {
  return request<ProcessCompleteResult>("/tenders/process-complete", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ tender_id: tenderId, file_id: fileId, email: email || null }),
  });
}

/** Polls tender detail until the given document reaches a terminal processing_status. */
export async function pollDocumentStatus(
  tenderProjectId: string,
  documentId: string,
  { intervalMs = 2500, timeoutMs = 5 * 60 * 1000 } = {},
): Promise<TenderProjectDetail> {
  const start = Date.now();
  while (true) {
    const detail = await getTenderDetail(tenderProjectId);
    const doc = detail.documents.find((d) => d.document_id === documentId);
    if (doc && (doc.processing_status === "completed" || doc.processing_status === "failed")) {
      return detail;
    }
    if (Date.now() - start > timeoutMs) {
      throw new Error("Timed out waiting for document processing to finish.");
    }
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
}

export function originalDocumentUrl(documentId: string): string {
  // Backend serves STORAGE_ROOT under /storage; PDF uploads are saved as
  // storage/jobs/<document_id>/original.pdf by the OCR pipeline.
  return `/storage/jobs/${documentId}/original.pdf`;
}
