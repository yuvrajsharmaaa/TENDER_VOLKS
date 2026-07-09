import { originalDocumentUrl } from "../services/api";

interface Props {
  documentId: string;
  filename: string;
}

/**
 * Renders the real uploaded PDF (served straight from the backend's
 * /storage mount) — no placeholder or mocked preview.
 */
export default function PDFPreviewPane({ documentId, filename }: Props) {
  const url = originalDocumentUrl(documentId);
  return (
    <div className="pdf-pane">
      <div className="pdf-pane-header">
        <strong title={filename} style={{ fontSize: "0.85rem" }}>
          {filename}
        </strong>
        <a className="link" href={url} target="_blank" rel="noreferrer">
          Open in new tab
        </a>
      </div>
      <iframe title="Tender document preview" src={url} />
    </div>
  );
}
