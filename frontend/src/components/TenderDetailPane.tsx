import type { ExtractedField, ProcessCompleteResult, ProductItem } from "../types/tender";

interface Props {
  filename: string;
  pageCount: number;
  fields: ExtractedField[];
  products: ProductItem[];
  processResult: ProcessCompleteResult | null;
}

function confidenceClass(confidence: number): string {
  if (confidence >= 0.8) return "conf-high";
  if (confidence >= 0.4) return "conf-med";
  return "conf-low";
}

export default function TenderDetailPane({ filename, pageCount, fields, products, processResult }: Props) {
  const foundCount = fields.filter((f) => f.value !== "Not Found").length;

  // Build a lightweight info-sheet summary from the extracted fields.
  const get = (name: string) => fields.find((f) => f.field_name === name)?.value || null;
  const nit = get("NIT No") || get("bid_number");
  const authority = get("Organisation") || get("organisation_name") || get("ministry_name");
  const department = get("department_name");
  const tenderValue = get("Tender Value") || get("tender_value");
  const emd = get("EMD") || get("emd_amount");
  const fee = get("Tender Fee") || get("tender_fee");
  const submissionEnd = get("Bid Submission End Date") || get("bid_end_datetime");
  const opening = get("Bid Opening Date") || get("bid_open_datetime");
  const preBid = get("Pre-Bid Meeting Date");
  const contractPeriod = get("Period of Work") || get("contract_period");
  const turnover = get("minimum_average_annual_turnover");
  const experience = get("years_of_past_experience");

  const hasSummary = nit || authority || tenderValue || submissionEnd;

  return (
    <div className="detail-pane">
      <div className="detail-pane-header">
        <div>
          <h2>Tender Intelligence</h2>
          <div className="summary-strip">
            <span>
              <b>{foundCount}</b>/{fields.length} fields found
            </span>
            <span>
              <b>{pageCount}</b> pages
            </span>
            {products.length > 0 && (
              <span>
                <b>{products.length}</b> products detected
              </span>
            )}
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

      {/* Info Sheet Summary */}
      {hasSummary && (
        <div className="info-sheet-card">
          <h3 className="info-sheet-title">Info Sheet</h3>
          <div className="info-sheet-grid">
            {nit && (
              <div className="info-sheet-row">
                <span className="info-sheet-label">Tender / NIT No</span>
                <span className="info-sheet-value">{nit}</span>
              </div>
            )}
            {authority && (
              <div className="info-sheet-row">
                <span className="info-sheet-label">Authority</span>
                <span className="info-sheet-value">{authority}</span>
              </div>
            )}
            {department && (
              <div className="info-sheet-row">
                <span className="info-sheet-label">Department</span>
                <span className="info-sheet-value">{department}</span>
              </div>
            )}
            {tenderValue && (
              <div className="info-sheet-row">
                <span className="info-sheet-label">Estimated Value</span>
                <span className="info-sheet-value">{tenderValue}</span>
              </div>
            )}
            {emd && (
              <div className="info-sheet-row">
                <span className="info-sheet-label">EMD</span>
                <span className="info-sheet-value">{emd}</span>
              </div>
            )}
            {fee && (
              <div className="info-sheet-row">
                <span className="info-sheet-label">Tender Fee</span>
                <span className="info-sheet-value">{fee}</span>
              </div>
            )}
            {submissionEnd && (
              <div className="info-sheet-row">
                <span className="info-sheet-label">Submission Deadline</span>
                <span className="info-sheet-value">{submissionEnd}</span>
              </div>
            )}
            {opening && (
              <div className="info-sheet-row">
                <span className="info-sheet-label">Opening Date</span>
                <span className="info-sheet-value">{opening}</span>
              </div>
            )}
            {preBid && (
              <div className="info-sheet-row">
                <span className="info-sheet-label">Pre-Bid Meeting</span>
                <span className="info-sheet-value">{preBid}</span>
              </div>
            )}
            {contractPeriod && (
              <div className="info-sheet-row">
                <span className="info-sheet-label">Contract Period</span>
                <span className="info-sheet-value">{contractPeriod}</span>
              </div>
            )}
            {turnover && (
              <div className="info-sheet-row">
                <span className="info-sheet-label">Min. Turnover</span>
                <span className="info-sheet-value">{turnover}</span>
              </div>
            )}
            {experience && (
              <div className="info-sheet-row">
                <span className="info-sheet-label">Experience Required</span>
                <span className="info-sheet-value">{experience}</span>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Products / Items Section */}
      {products.length > 0 && (
        <div className="info-sheet-card">
          <h3 className="info-sheet-title">Detected Products / Scope</h3>
          <ul className="product-list">
            {products.map((p, idx) => (
              <li key={idx} className="product-item">
                <div className="product-header">
                  <span className="product-name">{p.product_name}</span>
                  <span className={`conf-badge ${confidenceClass(p.confidence)}`}>
                    {(p.confidence * 100).toFixed(0)}%
                  </span>
                </div>
                <div className="product-meta">
                  {p.quantity && (
                    <span>
                      Qty: <b>{p.quantity}</b> {p.unit}
                    </span>
                  )}
                  <span>page {p.page_number}</span>
                </div>
                <div className="product-evidence">{p.evidence_text}</div>
              </li>
            ))}
          </ul>
        </div>
      )}

      <h3 className="section-title">All Extracted Fields</h3>

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
