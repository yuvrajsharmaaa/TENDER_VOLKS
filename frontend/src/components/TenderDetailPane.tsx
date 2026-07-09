import type { ExtractedField, ProcessCompleteResult } from "../types/tender";

interface Props {
  filename: string;
  pageCount: number;
  fields: ExtractedField[];
  processResult: ProcessCompleteResult | null;
}

function confidenceClass(confidence: number): string {
  if (confidence >= 0.8) return "conf-high";
  if (confidence >= 0.4) return "conf-med";
  return "conf-low";
}

export default function TenderDetailPane({ filename, pageCount, fields, processResult }: Props) {
  const foundCount = fields.filter((f) => f.value !== "Not Found").length;

  return (
    <div className="detail-pane">
      <div className="detail-pane-header">
        <div>
          <h2>Extracted Fields</h2>
          <div className="summary-strip">
            <span>
              <b>{foundCount}</b>/{fields.length} fields found
            </span>
            <span>
              <b>{pageCount}</b> pages
            </span>
            {processResult && (
              <span>
                <a className="link" href={processResult.csv_url} target="_blank" rel="noreferrer">
                  Download CSV
                </a>
              </span>
            )}
          </div>
        </div>
      </div>

      {processResult && (
        <div className="status-row">
          <span className="status-dot completed" />
          <span>{processResult.message}</span>
        </div>
      )}

      <div className="field-grid">
        {fields.map((field) => {
          const notFound = field.value === "Not Found";
          return (
            <div key={field.field_name} className={`field-card${notFound ? " not-found" : ""}`}>
              <div className="field-card-header">
                <span className="field-card-title">{field.field_name.replace(/_/g, " ")}</span>
                {!notFound && (
                  <span className={`conf-badge ${confidenceClass(field.confidence)}`}>
                    {(field.confidence * 100).toFixed(0)}%
                  </span>
                )}
              </div>
              <div className="field-card-value">{field.value}</div>
              {!notFound && (
                <>
                  <div className="field-card-evidence">{field.evidence}</div>
                  <div className="field-card-page">page {field.source_page}</div>
                </>
              )}
            </div>
          );
        })}
      </div>
      {fields.length === 0 && (
        <p style={{ color: "var(--text-secondary)" }}>No fields extracted from {filename}.</p>
      )}
    </div>
  );
}
