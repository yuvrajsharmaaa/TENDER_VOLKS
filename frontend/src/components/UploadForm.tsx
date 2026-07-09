import { useRef, useState } from "react";

interface Props {
  onSubmit: (tenderName: string, file: File, email: string | null) => void;
  submitting: boolean;
  error: string | null;
}

export default function UploadForm({ onSubmit, submitting, error }: Props) {
  const [tenderName, setTenderName] = useState("");
  const [email, setEmail] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const canSubmit = tenderName.trim().length > 0 && file !== null && !submitting;

  return (
    <div className="upload-card">
      <h2>Process a new tender document</h2>

      <div>
        <label className="field-label" htmlFor="tenderName">
          Tender name
        </label>
        <input
          id="tenderName"
          type="text"
          value={tenderName}
          placeholder="e.g. UPS Infrastructure Supply — GEM/2025/B/6053925"
          onChange={(e) => setTenderName(e.target.value)}
        />
      </div>

      <div>
        <label className="field-label" htmlFor="notifyEmail">
          Notification email <span style={{ opacity: 0.5, fontWeight: 400 }}>(optional — receive CSV by email)</span>
        </label>
        <input
          id="notifyEmail"
          type="email"
          value={email}
          placeholder="e.g. procurement@example.com"
          onChange={(e) => setEmail(e.target.value)}
        />
      </div>

      <div
        className={`dropzone${dragging ? " dragging" : ""}`}
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          const dropped = e.dataTransfer.files?.[0];
          if (dropped) setFile(dropped);
        }}
      >
        <input
          ref={inputRef}
          type="file"
          accept="application/pdf,image/png,image/jpeg"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        />
        {file ? (
          <span>{file.name}</span>
        ) : (
          <span>Click or drag a tender PDF / scanned image here</span>
        )}
      </div>

      {error && <div className="error-banner">{error}</div>}

      <button
        className="btn"
        disabled={!canSubmit}
        onClick={() => file && onSubmit(tenderName.trim(), file, email.trim() || null)}
      >
        {submitting ? "Uploading…" : "Upload & Run OCR"}
      </button>
    </div>
  );
}
