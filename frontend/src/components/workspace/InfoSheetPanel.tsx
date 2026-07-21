import React, { useState } from "react";
import type { InfoSheetSection, InfoSheetField } from "../../types/tender";
import { AlertTriangle, Check, Edit2, RotateCcw, ShieldAlert, CheckCircle } from "lucide-react";

interface InfoSheetPanelProps {
  sections: InfoSheetSection[];
  onUpdateField: (fieldId: string, value: string) => void;
  onVerifyField: (fieldId: string) => void;
}

export const InfoSheetPanel: React.FC<InfoSheetPanelProps> = ({
  sections,
  onUpdateField,
  onVerifyField
}) => {
  const [editingFieldId, setEditingFieldId] = useState<string | null>(null);
  const [editValue, setEditValue] = useState("");

  const handleStartEdit = (field: InfoSheetField) => {
    setEditingFieldId(field.id);
    setEditValue(typeof field.value === "object" ? JSON.stringify(field.value) : (field.value || ""));
  };

  const handleSaveEdit = (fieldId: string) => {
    onUpdateField(fieldId, editValue);
    setEditingFieldId(null);
  };

  const getFieldStatusBorder = (field: InfoSheetField) => {
    if (field.status === "missing") return "border-alert-text/20 bg-alert-bg/30 text-alert-text";
    if (field.confidence && field.confidence < 70 && field.status === "extracted") return "border-warning-text/20 bg-warning-bg/30 text-warning-text";
    if (field.status === "edited") return "border-blue-200 bg-blue-50/50";
    if (field.status === "verified") return "border-selected-green-border bg-selected-green-bg/20";
    return "border-divider bg-card-bg/60";
  };

  return (
    <div className="space-y-6 max-h-[calc(100vh-220px)] overflow-y-auto pr-2 select-none">
      {sections.length === 0 ? (
        <div className="p-8 text-center text-text-muted bg-card-bg border border-divider rounded-lg font-sans">
          No structured metadata fields extracted yet. Trigger parser extraction.
        </div>
      ) : (
        sections.map((section) => (
          <div key={section.id} className="space-y-3">
            <h3 className="text-[10px] font-bold text-text-muted uppercase tracking-widest border-b border-divider pb-2">
              {section.title}
            </h3>
            
            <div className="grid grid-cols-1 gap-3">
              {section.fields.map((field) => {
                const isEditing = editingFieldId === field.id;
                const isLowConfidence = field.confidence && field.confidence < 70 && field.status === "extracted";

                return (
                  <div
                    key={field.id}
                    className={`border rounded-lg p-3.5 transition-colors flex flex-col md:flex-row md:items-center justify-between gap-3 ${getFieldStatusBorder(
                      field
                    )}`}
                  >
                    <div className="flex-1 space-y-1 min-w-0">
                      {/* Label & Badges */}
                      <div className="flex items-center gap-2 flex-wrap font-sans">
                        <span className="text-xs font-semibold text-text-secondary">
                          {field.label}
                        </span>
                        {field.critical && (
                          <span className="text-[9px] bg-alert-bg text-alert-text font-bold px-1.5 py-0.5 rounded border border-alert-text/10">
                            CRITICAL
                          </span>
                        )}
                        {field.status === "edited" && (
                          <span className="text-[9px] bg-blue-50 text-blue-600 px-1.5 py-0.5 rounded border border-blue-200">
                            EDITED
                          </span>
                        )}
                        {field.status === "verified" && (
                          <span className="text-[9px] bg-selected-green-bg text-success-green px-1.5 py-0.5 rounded border border-selected-green-border flex items-center gap-0.5 font-bold">
                            <Check className="h-2 w-2" />
                            VERIFIED
                          </span>
                        )}
                        {isLowConfidence && (
                          <span className="text-[9px] bg-warning-bg text-warning-text px-1.5 py-0.5 rounded border border-warning-text/10 flex items-center gap-0.5 font-bold animate-pulse">
                            <AlertTriangle className="h-2.5 w-2.5" />
                            LOW CONFIDENCE ({field.confidence}%)
                          </span>
                        )}
                      </div>

                      {/* Value Input or Text */}
                      {isEditing ? (
                        <div className="flex items-center gap-2 mt-1">
                          <input
                            type="text"
                            className="bg-input-bg border border-success-green rounded px-2.5 py-1 text-xs text-text-primary focus:outline-none flex-1 font-mono"
                            value={editValue}
                            onChange={(e) => setEditValue(e.target.value)}
                            autoFocus
                            onKeyDown={(e) => {
                              if (e.key === "Enter") handleSaveEdit(field.id);
                              if (e.key === "Escape") setEditingFieldId(null);
                            }}
                          />
                          <button
                            onClick={() => handleSaveEdit(field.id)}
                            className="bg-success-green hover:bg-cta-green p-1.5 rounded text-panel-bg"
                            title="Save Changes"
                          >
                            <Check className="h-3.5 w-3.5" />
                          </button>
                          <button
                            onClick={() => setEditingFieldId(null)}
                            className="bg-input-bg border border-divider hover:bg-section-tint p-1.5 rounded text-text-secondary"
                            title="Cancel"
                          >
                            <RotateCcw className="h-3.5 w-3.5" />
                          </button>
                        </div>
                      ) : field.status === "missing" ? (
                        <div className="flex items-center gap-2 mt-1.5 font-sans">
                          <ShieldAlert className="h-4 w-4 text-alert-text shrink-0" />
                          <span
                            onClick={() => handleStartEdit(field)}
                            className="text-xs text-alert-text hover:underline font-mono italic cursor-pointer"
                          >
                            [Missing Value - Click to fill manually]
                          </span>
                        </div>
                      ) : (
                        <div className="text-xs font-mono text-text-primary mt-1 select-all break-all whitespace-pre-wrap">
                          {typeof field.value === "object" ? JSON.stringify(field.value, null, 2) : field.value}
                        </div>
                      )}

                      {/* Source Text Cite */}
                      {!isEditing && field.sourceSnippet && (
                        <div className="text-[10px] text-text-muted italic mt-1 line-clamp-1">
                          Cite: Page {field.sourcePage} — "{field.sourceSnippet}"
                        </div>
                      )}
                    </div>

                    {/* Edit/Verify Actions */}
                    {!isEditing && (
                      <div className="flex items-center gap-1.5 shrink-0 self-end md:self-center select-none">
                        <button
                          onClick={() => handleStartEdit(field)}
                          className="p-1.5 bg-input-bg border border-divider hover:bg-section-tint text-text-secondary hover:text-text-primary rounded transition-colors text-xs"
                          title="Edit Field"
                        >
                          <Edit2 className="h-3.5 w-3.5" />
                        </button>
                        {field.status !== "verified" && field.status !== "missing" && (
                          <button
                            onClick={() => onVerifyField(field.id)}
                            className="p-1.5 bg-input-bg border border-divider hover:bg-selected-green-bg hover:border-selected-green-border text-text-secondary hover:text-success-green rounded transition-colors text-xs"
                            title="Verify Field"
                          >
                            <CheckCircle className="h-3.5 w-3.5" />
                          </button>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        ))
      )}
    </div>
  );
};
export default InfoSheetPanel;
