import React, { useEffect, useRef } from "react";
import {
  Search,
  RefreshCw,
  Upload,
  SlidersHorizontal,
} from "lucide-react";

interface CommandHeaderProps {
  searchTerm: string;
  onSearchChange: (value: string) => void;
  onUpload: () => void;
  onRefresh: () => void;
  onFilters: () => void;
  filtersActive: number;
  workspaceName: string;
}

export const CommandHeader: React.FC<CommandHeaderProps> = ({
  searchTerm,
  onSearchChange,
  onUpload,
  onRefresh,
  onFilters,
  filtersActive,
  workspaceName,
}) => {
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if (
        (event.metaKey || event.ctrlKey) &&
        event.key.toLowerCase() === "k"
      ) {
        event.preventDefault();
        inputRef.current?.focus();
      }
    };

    window.addEventListener("keydown", handler);

    return () =>
      window.removeEventListener("keydown", handler);
  }, []);

  return (
    <header className="tv-command-header">

      <div className="tv-command-context">

        <div className="tv-command-eyebrow">
          WORKSPACE
        </div>

        <div className="tv-command-title">
          {workspaceName}
        </div>

      </div>

      <div className="tv-command-search">

        <Search className="tv-command-search-icon" />

        <input
          ref={inputRef}
          type="search"
          value={searchTerm}
          onChange={(event) =>
            onSearchChange(event.target.value)
          }
          placeholder="Search tenders, agencies, locations or IDs..."
        />

        <div className="tv-command-shortcut">
          ⌘ K
        </div>

      </div>

      <div className="tv-command-actions">

        <button
          type="button"
          className="tv-command-icon"
          onClick={onRefresh}
          title="Refresh"
        >
          <RefreshCw />
        </button>

        <button
          type="button"
          className={`tv-command-filter ${
            filtersActive > 0 ? "is-active" : ""
          }`}
          onClick={onFilters}
        >
          <SlidersHorizontal />
          Filters

          {filtersActive > 0 && (
            <span>{filtersActive}</span>
          )}
        </button>

        <button
          type="button"
          className="tv-command-upload"
          onClick={onUpload}
        >
          <Upload />
          Upload
        </button>

      </div>

    </header>
  );
};
