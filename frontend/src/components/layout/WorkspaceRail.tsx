import React from "react";
import {
  Activity,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  UploadCloud,
} from "lucide-react";

type Tab = "tenders" | "recommendations" | "compliance";

interface WorkspaceRailProps {
  activeTab: Tab;
  onTabChange: (tab: Tab) => void;
  onUpload: () => void;
  onRefresh: () => void;
}

export const WorkspaceRail: React.FC<WorkspaceRailProps> = ({
  activeTab,
  onTabChange,
  onUpload,
  onRefresh,
}) => {
  return (
    <aside className="tv-rail">

      <div className="tv-rail-brand">
        <div className="tv-rail-brand-mark">
          V
        </div>

        <div>
          <div className="tv-rail-brand-title">
            VOLKS
          </div>

          <div className="tv-rail-brand-subtitle">
            Procurement AI
          </div>
        </div>
      </div>

      <div className="tv-rail-label">
        Workspace
      </div>

      <div className="tv-rail-nav">

        <button
          type="button"
          className={`tv-rail-item ${
            activeTab === "tenders" ? "is-active" : ""
          }`}
          onClick={() => onTabChange("tenders")}
        >
          <Activity />
          <span>Tenders</span>
        </button>

        <button
          type="button"
          className={`tv-rail-item ${
            activeTab === "compliance" ? "is-active" : ""
          }`}
          onClick={() => onTabChange("compliance")}
        >
          <ShieldCheck />
          <span>Bid Compliance</span>
        </button>

        <button
          type="button"
          className={`tv-rail-item ${
            activeTab === "recommendations" ? "is-active" : ""
          }`}
          onClick={() => onTabChange("recommendations")}
        >
          <Sparkles />
          <span>PQC Intelligence</span>
        </button>

      </div>

      <div className="tv-rail-label tv-rail-label-spaced">
        Actions
      </div>

      <div className="tv-rail-actions">

        <button
          type="button"
          className="tv-rail-action"
          onClick={onUpload}
        >
          <UploadCloud />
          Upload Tender
        </button>

        <button
          type="button"
          className="tv-rail-action"
          onClick={onRefresh}
        >
          <RefreshCw />
          Refresh
        </button>

      </div>

      <div className="tv-rail-footer">

        <div className="tv-pipeline">
          <div className="tv-pipeline-dot" />

          <div>
            <div className="tv-pipeline-title">
              Pipeline active
            </div>

            <div className="tv-pipeline-meta">
              OCR · AI · Verification
            </div>
          </div>
        </div>

      </div>

    </aside>
  );
};
