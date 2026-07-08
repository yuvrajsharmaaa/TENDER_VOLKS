import React, { useState, useRef } from "react";
import { Upload, X, FileText, Loader2, Check } from "lucide-react";

interface UploadModalProps {
  isOpen: boolean;
  onClose: () => void;
  onUpload: (file: File) => Promise<void>;
}

export const UploadModal: React.FC<UploadModalProps> = ({ isOpen, onClose, onUpload }) => {
  const [dragActive, setDragActive] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [success, setSuccess] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  if (!isOpen) return null;

  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);

    const droppedFile = e.dataTransfer.files?.[0];
    if (droppedFile && droppedFile.type === "application/pdf") {
      setFile(droppedFile);
    } else {
      alert("Please upload a PDF document.");
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = e.target.files?.[0];
    if (selectedFile) {
      setFile(selectedFile);
    }
  };

  const handleUploadSubmit = async () => {
    if (!file) return;

    setUploading(true);
    setProgress(15);
    
    const interval = setInterval(() => {
      setProgress((prev) => {
        if (prev >= 90) {
          clearInterval(interval);
          return 90;
        }
        return prev + 25;
      });
    }, 300);

    try {
      await onUpload(file);
      clearInterval(interval);
      setProgress(100);
      setSuccess(true);
      setTimeout(() => {
        handleReset();
        onClose();
      }, 1000);
    } catch (err) {
      clearInterval(interval);
      alert("Failed to upload tender document.");
      setUploading(false);
    }
  };

  const handleReset = () => {
    setFile(null);
    setUploading(false);
    setProgress(0);
    setSuccess(false);
  };

  return (
    <div className="fixed inset-0 bg-text-primary/40 backdrop-blur-sm flex items-center justify-center z-50 p-4">
      <div className="bg-panel-bg border border-divider rounded-xl w-full max-w-lg shadow-xl overflow-hidden relative font-sans select-none animate-fadeIn">
        {/* Close Button */}
        <button
          onClick={onClose}
          className="absolute top-4 right-4 text-text-secondary hover:text-text-primary transition-colors"
          disabled={uploading}
        >
          <X className="h-5 w-5" />
        </button>

        {/* Modal Header */}
        <div className="px-6 py-5 border-b border-divider bg-card-bg">
          <h3 className="text-sm font-bold text-text-primary">Upload Tender Document</h3>
          <p className="text-xs text-text-secondary mt-1">
            Upload the primary Tender PDF to trigger the page-aware OCR extraction pipeline.
          </p>
        </div>

        {/* Drag and drop zone */}
        <div className="p-6">
          {!file ? (
            <div
              onDragEnter={handleDrag}
              onDragOver={handleDrag}
              onDragLeave={handleDrag}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
              className={`border-2 border-dashed rounded-lg p-10 flex flex-col items-center justify-center text-center cursor-pointer transition-colors ${
                dragActive
                  ? "border-success-green bg-selected-green-bg text-success-green"
                  : "border-divider hover:border-text-muted bg-input-bg/40 text-text-secondary"
              }`}
            >
              <input
                type="file"
                ref={fileInputRef}
                onChange={handleFileChange}
                className="hidden"
                accept="application/pdf"
              />
              <Upload className="h-10 w-10 text-text-disabled mb-3" />
              <p className="text-sm font-semibold text-text-primary">Drag & Drop Tender PDF here</p>
              <p className="text-xs text-text-secondary mt-1">or click to browse local files</p>
              <span className="text-[10px] text-text-disabled mt-4 font-bold tracking-wider font-mono">
                PDF LIMIT: 50MB
              </span>
            </div>
          ) : (
            <div className="border border-divider bg-input-bg rounded-lg p-5 space-y-4">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-selected-green-bg text-success-green border border-selected-green-border rounded-lg shrink-0">
                  <FileText className="h-5 w-5" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-xs font-bold text-text-primary truncate">{file.name}</p>
                  <p className="text-[10px] text-text-muted mt-0.5 font-mono">
                    {(file.size / (1024 * 1024)).toFixed(2)} MB
                  </p>
                </div>
                {!uploading && (
                  <button
                    onClick={handleReset}
                    className="p-1 hover:bg-section-tint rounded text-text-secondary hover:text-text-primary"
                  >
                    <X className="h-4 w-4" />
                  </button>
                )}
              </div>

              {/* Progress bar */}
              {uploading && (
                <div className="space-y-2">
                  <div className="flex items-center justify-between text-[11px] font-mono text-text-secondary">
                    <span className="flex items-center gap-1.5 font-bold">
                      {success ? (
                        <Check className="h-3 w-3 text-success-green" />
                      ) : (
                        <Loader2 className="h-3 w-3 animate-spin text-success-green" />
                      )}
                      <span>{success ? "Upload Completed!" : "Ingesting PDF..."}</span>
                    </span>
                    <span>{progress}%</span>
                  </div>
                  <div className="h-1.5 w-full bg-section-tint rounded-full overflow-hidden">
                    <div
                      className="bg-success-green h-full rounded-full transition-all duration-300"
                      style={{ width: `${progress}%` }}
                    ></div>
                  </div>
                </div>
              )}

              {/* Upload trigger */}
              {!uploading && (
                <div className="flex gap-3 justify-end pt-2">
                  <button
                    onClick={handleReset}
                    className="px-4 py-2 bg-panel-bg hover:bg-section-tint text-text-secondary hover:text-text-primary border border-divider text-xs font-bold rounded-lg transition-colors"
                  >
                    Clear
                  </button>
                  <button
                    onClick={handleUploadSubmit}
                    className="px-4 py-2 bg-success-green hover:bg-cta-green text-panel-bg text-xs font-bold rounded-lg transition-colors shadow-sm"
                  >
                    Submit File
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
