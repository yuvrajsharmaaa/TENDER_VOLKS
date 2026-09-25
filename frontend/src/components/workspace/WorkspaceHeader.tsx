import React, { useState } from "react";
import { CommandHeader } from "../layout/CommandHeader";

export interface FiltersState {
  withinKeywords: string;
  notInKeyword: string;
  city: string;
  valueFrom: string;
  valueTo: string;
  emdFrom: string;
  emdTo: string;
  closingFrom: string;
  closingTo: string;
  state: string;
  sector: string;
  tenderType: string;
  agencyName: string;
}

interface WorkspaceHeaderProps {
  searchTerm: string;
  onSearchChange: (val: string) => void;
  filters: FiltersState;
  onFiltersChange: (newFilters: FiltersState) => void;
  onClearFilters: () => void;
  onUploadClick: () => void;
  isBackendConnected: boolean;
  onRefreshClick: () => void;
  activeNavTab?: "tenders" | "recommendations" | "compliance";
  onNavTabChange?: (
    tab: "tenders" | "recommendations" | "compliance"
  ) => void;
}

export const WorkspaceHeader: React.FC<WorkspaceHeaderProps> = ({
  searchTerm,
  onSearchChange,
  filters,
  onFiltersChange,
  onClearFilters,
  onUploadClick,
  onRefreshClick,
  activeNavTab = "tenders",
}) => {
  const [filterOpen, setFilterOpen] = useState(false);

  const activeFilters = Object.entries(filters).filter(
    ([key, value]) =>
      key !== "tenderType" && Boolean(value)
  ).length;

  const f = (
    key: keyof FiltersState,
    value: string
  ) => {
    onFiltersChange({
      ...filters,
      [key]: value,
    });
  };

  const workspaceName =
    activeNavTab === "compliance"
      ? "Bid Compliance"
      : activeNavTab === "recommendations"
        ? "PQC Intelligence"
        : "Live Tenders";

  return (
    <>
      <CommandHeader
        searchTerm={searchTerm}
        onSearchChange={onSearchChange}
        onUpload={onUploadClick}
        onRefresh={onRefreshClick}
        onFilters={() => setFilterOpen((v) => !v)}
        filtersActive={activeFilters}
        workspaceName={workspaceName}
      />

      {filterOpen && (
        <div className="tv-filter-drawer">

          <div className="tv-filter-head">
            <div>
              <div className="tv-filter-title">
                Advanced filters
              </div>

              <div className="tv-filter-subtitle">
                Refine the opportunity queue.
              </div>
            </div>

            <button
              type="button"
              onClick={onClearFilters}
              className="tv-filter-clear"
            >
              Clear all
            </button>
          </div>

          <div className="tv-filter-grid">

            {[
              ["withinKeywords", "Contains"],
              ["notInKeyword", "Exclude"],
              ["city", "City"],
              ["state", "State"],
              ["sector", "Sector"],
              ["agencyName", "Agency"],
              ["valueFrom", "Minimum value"],
              ["valueTo", "Maximum value"],
              ["closingFrom", "Closing from"],
              ["closingTo", "Closing to"],
            ].map(([key, label]) => (
              <label key={key}>
                <span>{label}</span>

                <input
                  value={filters[key as keyof FiltersState]}
                  onChange={(event) =>
                    f(
                      key as keyof FiltersState,
                      event.target.value
                    )
                  }
                />
              </label>
            ))}

          </div>

          <div className="tv-filter-presets">

            {[
              ["", "All"],
              ["Live", "Open"],
              ["Completed", "Reviewed"],
            ].map(([value, label]) => (
              <button
                type="button"
                key={value}
                onClick={() =>
                  f("tenderType", value)
                }
                className={
                  filters.tenderType === value
                    ? "is-selected"
                    : ""
                }
              >
                {label}
              </button>
            ))}

          </div>

        </div>
      )}
    </>
  );
};
