import React, { useState } from "react";
import { Search, Plus, RefreshCw, SlidersHorizontal, ChevronDown, ChevronUp } from "lucide-react";

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
}

export const WorkspaceHeader: React.FC<WorkspaceHeaderProps> = ({
  searchTerm,
  onSearchChange,
  filters,
  onFiltersChange,
  onClearFilters,
  onUploadClick,
  isBackendConnected,
  onRefreshClick
}) => {
  const [isFiltersOpen, setIsFiltersOpen] = useState(false);
  const [activeTab, setActiveTab] = useState<"keywords" | "pinned">("keywords");

  const handleFilterChange = (key: keyof FiltersState, val: string) => {
    onFiltersChange({
      ...filters,
      [key]: val
    });
  };

  const activeFiltersCount = Object.keys(filters).reduce((acc, key) => {
    if (key === "tenderType") return acc; // Exclude tab chip filter
    return acc + (filters[key as keyof FiltersState] ? 1 : 0);
  }, 0);

  return (
    <div className="bg-panel-bg border-b border-divider flex flex-col shrink-0 z-20 select-none">
      {/* Top Brand Header Bar */}
      <header className="px-6 py-3 border-b border-divider flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <div className="bg-success-green px-3 py-1 rounded text-panel-bg font-bold text-xs tracking-wider uppercase">
              Volks
            </div>
            <span className="font-semibold text-base text-text-primary tracking-tight">Tender OCR</span>
          </div>
          <div className="h-4 w-px bg-divider hidden sm:block"></div>
          
          <nav className="hidden lg:flex items-center gap-4 text-xs font-semibold text-text-secondary">
            <span className="text-success-green cursor-pointer">Live Tenders</span>
            <span className="hover:text-text-primary cursor-pointer transition-colors">Workspace Logs</span>
            <span className="hover:text-text-primary cursor-pointer transition-colors">Rule Auditing</span>
          </nav>
        </div>

        {/* Right action control */}
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-1.5 text-xs text-text-secondary">
            <span className={`h-2 w-2 rounded-full ${isBackendConnected ? "bg-success-green shadow-sm shadow-success-green/50" : "bg-alert-text"}`}></span>
            <span className="hidden sm:inline">{isBackendConnected ? "Pipeline Active" : "Offline"}</span>
          </div>

          <button
            onClick={onRefreshClick}
            className="p-1.5 bg-input-bg border border-divider hover:bg-section-tint text-text-secondary hover:text-text-primary rounded transition-colors"
            title="Reload Workspace"
          >
            <RefreshCw className="h-3.5 w-3.5" />
          </button>

          <button
            onClick={onUploadClick}
            className="bg-success-green hover:bg-cta-green text-panel-bg font-bold text-xs px-3.5 py-1.8 rounded flex items-center gap-1.5 shadow-sm transition-colors cursor-pointer"
          >
            <Plus className="h-3.5 w-3.5 stroke-[2.5]" />
            <span>Upload Tender</span>
          </button>
        </div>
      </header>

      {/* Workspace Menu Bar */}
      <div className="px-6 py-2 bg-card-bg border-b border-divider flex items-center gap-2">
        <button
          onClick={() => setActiveTab("keywords")}
          className={`px-3 py-1 rounded text-xs font-bold transition-all ${
            activeTab === "keywords" ? "bg-section-tint text-text-primary" : "text-text-muted hover:text-text-secondary"
          }`}
        >
          Keywords
        </button>
        <button
          onClick={() => setActiveTab("pinned")}
          className={`px-3 py-1 rounded text-xs font-bold transition-all ${
            activeTab === "pinned" ? "bg-section-tint text-text-primary" : "text-text-muted hover:text-text-secondary"
          }`}
        >
          Pinned Checks
        </button>
      </div>

      {/* Premium Search & Filters Area */}
      <div className="px-6 py-5 max-w-[1440px] w-full mx-auto space-y-4">
        {/* Search Input and Buttons */}
        <div className="flex flex-col md:flex-row gap-3">
          <div className="relative flex-1">
            <Search className="absolute left-4 top-1/2 -translate-y-1/2 h-4 w-4 text-text-muted" />
            <input
              type="text"
              placeholder="Try searching tender names, departments, location codes..."
              className="w-full bg-input-bg border border-divider rounded-xl pl-11 pr-16 py-3 text-sm text-text-primary placeholder-text-disabled focus:outline-none focus:border-success-green focus:ring-1 focus:ring-success-green transition-all font-mono shadow-[0_1px_2px_rgba(0,0,0,0.02)]"
              value={searchTerm}
              onChange={(e) => onSearchChange(e.target.value)}
            />
            {/* Keyboard shortcut Badge */}
            <div className="absolute right-4 top-1/2 -translate-y-1/2 hidden sm:flex items-center text-[10px] bg-section-tint text-text-muted px-2 py-0.5 rounded border border-divider font-mono select-none font-bold">
              ⌘K
            </div>
          </div>

          <div className="flex gap-2">
            <button
              onClick={() => setIsFiltersOpen(!isFiltersOpen)}
              className={`px-4 py-3 border rounded-xl text-xs font-bold flex items-center gap-2 transition-all shrink-0 cursor-pointer shadow-[0_1px_2px_rgba(0,0,0,0.02)] ${
                isFiltersOpen || activeFiltersCount > 0
                  ? "bg-selected-green-bg border-selected-green-border text-success-green"
                  : "bg-input-bg border-divider text-text-secondary hover:text-text-primary hover:border-text-muted"
              }`}
            >
              <SlidersHorizontal className="h-4 w-4" />
              <span>Filters</span>
              {activeFiltersCount > 0 && (
                <span className="bg-success-green text-panel-bg text-[9px] px-1.5 py-0.2 rounded-full font-bold">
                  {activeFiltersCount}
                </span>
              )}
              {isFiltersOpen ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
            </button>

            <button className="bg-success-green hover:bg-cta-green text-panel-bg font-bold text-xs px-6 py-3 rounded-xl shrink-0 transition-colors shadow-sm cursor-pointer">
              Search
            </button>
          </div>
        </div>

        {/* Horizontal Chips filter bar */}
        <div className="flex items-center gap-2 overflow-x-auto pb-1 select-none">
          <span className="text-[10px] text-text-muted uppercase font-bold tracking-wider mr-2 font-sans">Quick Views:</span>
          
          <button
            onClick={() => handleFilterChange("tenderType", "")}
            className={`px-3 py-1 rounded-full text-xs font-bold border transition-all ${
              filters.tenderType === ""
                ? "bg-text-primary border-text-primary text-panel-bg shadow-sm"
                : "bg-card-bg border-divider text-text-secondary hover:text-text-primary"
            }`}
          >
            All Tenders
          </button>
          
          <button
            onClick={() => handleFilterChange("tenderType", "Live")}
            className={`px-3 py-1 rounded-full text-xs font-bold border transition-all ${
              filters.tenderType === "Live"
                ? "bg-success-green border-success-green text-panel-bg shadow-sm"
                : "bg-card-bg border-divider text-text-secondary hover:text-text-primary"
            }`}
          >
            Open Tenders
          </button>
          
          <button
            onClick={() => handleFilterChange("tenderType", "Completed")}
            className={`px-3 py-1 rounded-full text-xs font-bold border transition-all ${
              filters.tenderType === "Completed"
                ? "bg-text-secondary border-text-secondary text-panel-bg shadow-sm"
                : "bg-card-bg border-divider text-text-secondary hover:text-text-primary"
            }`}
          >
            Closed / Reviewed
          </button>
        </div>

        {/* Collapsible advanced filters panel */}
        {isFiltersOpen && (
          <div className="bg-card-bg border border-divider rounded-2xl p-6 space-y-4 shadow-[0_4px_20px_rgba(0,0,0,0.03)] animate-fadeIn">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              
              <div className="space-y-1">
                <label className="text-[10px] font-bold text-text-muted uppercase tracking-wide">Within Keywords</label>
                <input
                  type="text"
                  placeholder="Contains terms..."
                  className="w-full bg-input-bg border border-divider rounded-lg px-3 py-2 text-xs text-text-primary focus:outline-none focus:border-success-green font-mono"
                  value={filters.withinKeywords}
                  onChange={(e) => handleFilterChange("withinKeywords", e.target.value)}
                />
              </div>

              <div className="space-y-1">
                <label className="text-[10px] font-bold text-text-muted uppercase tracking-wide">Not In Keyword</label>
                <input
                  type="text"
                  placeholder="Excludes terms..."
                  className="w-full bg-input-bg border border-divider rounded-lg px-3 py-2 text-xs text-text-primary focus:outline-none focus:border-success-green font-mono"
                  value={filters.notInKeyword}
                  onChange={(e) => handleFilterChange("notInKeyword", e.target.value)}
                />
              </div>

              <div className="space-y-1">
                <label className="text-[10px] font-bold text-text-muted uppercase tracking-wide">City</label>
                <input
                  type="text"
                  placeholder="e.g. Supaul"
                  className="w-full bg-input-bg border border-divider rounded-lg px-3 py-2 text-xs text-text-primary focus:outline-none focus:border-success-green font-mono"
                  value={filters.city}
                  onChange={(e) => handleFilterChange("city", e.target.value)}
                />
              </div>

              <div className="space-y-1">
                <label className="text-[10px] font-bold text-text-muted uppercase tracking-wide">Tender Value (INR)</label>
                <div className="flex items-center gap-2">
                  <input
                    type="number"
                    placeholder="Min"
                    className="w-full bg-input-bg border border-divider rounded-lg px-3 py-2 text-xs text-text-primary focus:outline-none focus:border-success-green font-mono"
                    value={filters.valueFrom}
                    onChange={(e) => handleFilterChange("valueFrom", e.target.value)}
                  />
                  <span className="text-text-muted text-xs">—</span>
                  <input
                    type="number"
                    placeholder="Max"
                    className="w-full bg-input-bg border border-divider rounded-lg px-3 py-2 text-xs text-text-primary focus:outline-none focus:border-success-green font-mono"
                    value={filters.valueTo}
                    onChange={(e) => handleFilterChange("valueTo", e.target.value)}
                  />
                </div>
              </div>

              <div className="space-y-1">
                <label className="text-[10px] font-bold text-text-muted uppercase tracking-wide">EMD Amount (INR)</label>
                <div className="flex items-center gap-2">
                  <input
                    type="number"
                    placeholder="Min"
                    className="w-full bg-input-bg border border-divider rounded-lg px-3 py-2 text-xs text-text-primary focus:outline-none focus:border-success-green font-mono"
                    value={filters.emdFrom}
                    onChange={(e) => handleFilterChange("emdFrom", e.target.value)}
                  />
                  <span className="text-text-muted text-xs">—</span>
                  <input
                    type="number"
                    placeholder="Max"
                    className="w-full bg-input-bg border border-divider rounded-lg px-3 py-2 text-xs text-text-primary focus:outline-none focus:border-success-green font-mono"
                    value={filters.emdTo}
                    onChange={(e) => handleFilterChange("emdTo", e.target.value)}
                  />
                </div>
              </div>

              <div className="space-y-1">
                <label className="text-[10px] font-bold text-text-muted uppercase tracking-wide">Closing Deadline Range</label>
                <div className="flex items-center gap-2">
                  <input
                    type="date"
                    className="w-full bg-input-bg border border-divider rounded-lg px-3 py-2 text-xs text-text-primary focus:outline-none focus:border-success-green font-mono"
                    value={filters.closingFrom}
                    onChange={(e) => handleFilterChange("closingFrom", e.target.value)}
                  />
                  <span className="text-text-muted text-xs">—</span>
                  <input
                    type="date"
                    className="w-full bg-input-bg border border-divider rounded-lg px-3 py-2 text-xs text-text-primary focus:outline-none focus:border-success-green font-mono"
                    value={filters.closingTo}
                    onChange={(e) => handleFilterChange("closingTo", e.target.value)}
                  />
                </div>
              </div>

              <div className="space-y-1">
                <label className="text-[10px] font-bold text-text-muted uppercase tracking-wide">State</label>
                <select
                  value={filters.state}
                  onChange={(e) => handleFilterChange("state", e.target.value)}
                  className="w-full bg-input-bg border border-divider rounded-lg px-3 py-2 text-xs text-text-secondary focus:outline-none focus:border-success-green cursor-pointer font-sans"
                >
                  <option value="">All States</option>
                  <option value="Chhattisgarh">Chhattisgarh</option>
                  <option value="Bihar">Bihar</option>
                  <option value="Maharashtra">Maharashtra</option>
                  <option value="Uttar Pradesh">Uttar Pradesh</option>
                  <option value="Delhi">Delhi</option>
                </select>
              </div>

              <div className="space-y-1">
                <label className="text-[10px] font-bold text-text-muted uppercase tracking-wide">Sector</label>
                <select
                  value={filters.sector}
                  onChange={(e) => handleFilterChange("sector", e.target.value)}
                  className="w-full bg-input-bg border border-divider rounded-lg px-3 py-2 text-xs text-text-secondary focus:outline-none focus:border-success-green cursor-pointer font-sans"
                >
                  <option value="">Any Sector</option>
                  <option value="Infrastructure">Infrastructure</option>
                  <option value="Renewable Energy">Renewable Energy</option>
                </select>
              </div>

            </div>

            <div className="border-t border-divider/60 pt-3 flex justify-between items-center text-xs select-none">
              <span className="text-text-muted font-mono text-[10px]">
                Search scope: 5,00,000+ live tenders | updated hourly
              </span>
              <button
                onClick={onClearFilters}
                className="text-text-secondary hover:text-success-green font-bold underline decoration-dotted transition-colors cursor-pointer"
              >
                Clear all advanced filters
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
export default WorkspaceHeader;
