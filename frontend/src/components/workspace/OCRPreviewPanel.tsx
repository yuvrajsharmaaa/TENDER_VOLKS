import React, { useState } from "react";
import { Search } from "lucide-react";

interface OCRPreviewPanelProps {
  rawText: string;
}

export const OCRPreviewPanel: React.FC<OCRPreviewPanelProps> = ({ rawText }) => {
  const [searchTerm, setSearchTerm] = useState("");
  
  if (!rawText) {
    return (
      <div className="p-8 text-center text-text-muted bg-card-bg border border-divider rounded-lg font-sans">
        OCR text extraction in progress or text is empty for this document page.
      </div>
    );
  }

  const highlightMatches = (text: string, search: string) => {
    if (!search.trim()) return text;
    
    const escaped = search.replace(/[-\/\\^$*+?.()|[\]{}]/g, "\\$&");
    const regex = new RegExp(`(${escaped})`, "gi");
    
    const parts = text.split(regex);
    return parts.map((part, i) => 
      regex.test(part) ? (
        <mark key={i} className="bg-gold-bg text-gold-text px-0.5 rounded border border-gold-fill/20 font-bold">
          {part}
        </mark>
      ) : (
        part
      )
    );
  };

  return (
    <div className="space-y-4 flex flex-col h-[calc(100vh-220px)]">
      {/* Search tool */}
      <div className="relative shrink-0 select-none">
        <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-text-muted" />
        <input
          type="text"
          placeholder="Find string in raw OCR document text..."
          className="w-full bg-input-bg border border-divider rounded-lg pl-10 pr-4 py-2.5 text-xs text-text-primary placeholder-text-disabled focus:outline-none focus:border-success-green"
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
        />
      </div>

      {/* Raw text container */}
      <div className="flex-1 bg-panel-bg border border-divider rounded-lg p-4 overflow-auto font-mono text-xs text-text-primary leading-relaxed whitespace-pre-wrap select-text">
        {highlightMatches(rawText, searchTerm)}
      </div>
    </div>
  );
};
