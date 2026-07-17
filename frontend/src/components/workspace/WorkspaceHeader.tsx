import React, { useId, useState } from "react";
import { Search, Plus, RefreshCw, SlidersHorizontal, ChevronDown, ChevronUp } from "lucide-react";
import volksLogo from "../../assets/logovolks.png";

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
  onRefreshClick,
}) => {
  const [isFiltersOpen, setIsFiltersOpen] = useState(false);
  const [activeTab, setActiveTab] = useState<"keywords" | "pinned">("keywords");
  const uid = useId();

  const f = (key: keyof FiltersState, val: string) =>
    onFiltersChange({ ...filters, [key]: val });

  const activeFiltersCount = Object.keys(filters).reduce((acc, key) => {
    if (key === "tenderType") return acc;
    return acc + (filters[key as keyof FiltersState] ? 1 : 0);
  }, 0);

  /* shared input class */
  const inputCls =
    "w-full bg-input-bg border border-divider rounded-lg px-3 py-2 text-xs text-text-primary " +
    "focus:outline-none focus:border-success-green focus:ring-1 focus:ring-success-green/30 " +
    "transition-colors font-mono placeholder-text-disabled";

  return (
    <div className="bg-panel-bg border-b border-divider flex flex-col shrink-0 z-20 select-none">

      {/* ── Brand bar ────────────────────────────────────── */}
      <header className="px-6 py-3 border-b border-divider flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <img src={volksLogo} alt="Volks" className="h-8 w-auto object-contain" />
            <span className="font-semibold text-base text-text-primary tracking-tight">Tender OCR</span>
          </div>
          <div className="h-4 w-px bg-divider hidden sm:block" />

          <nav className="hidden lg:flex items-center gap-4 text-xs font-semibold text-text-secondary" aria-label="Workspace navigation">
            <span className="text-success-green cursor-pointer">Live Tenders</span>
            <span className="hover:text-text-primary cursor-pointer transition-colors">Workspace Logs</span>
            <span className="hover:text-text-primary cursor-pointer transition-colors">Rule Auditing</span>
          </nav>
        </div>

        <div className="flex items-center gap-3">
          {/* Pipeline status */}
          <div className="flex items-center gap-1.5 text-xs text-text-secondary">
            <span
              className={`h-2 w-2 rounded-full ${
                isBackendConnected
                  ? "bg-brand-orange shadow-[0_0_0_2px_rgba(232,89,12,0.2)]"
                  : "bg-alert-text"
              }`}
            />
            <span className="hidden sm:inline">{isBackendConnected ? "Pipeline Active" : "Offline"}</span>
          </div>

          <button
            type="button"
            onClick={onRefreshClick}
            aria-label="Refresh workspace"
            className="p-1.5 bg-input-bg border border-divider hover:bg-section-tint text-text-secondary
              hover:text-text-primary rounded-lg transition-colors
              focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-success-green/40"
          >
            <RefreshCw className="h-3.5 w-3.5" aria-hidden />
          </button>

          <button
            type="button"
            onClick={onUploadClick}
            aria-label="Upload tender document"
            className="bg-brand-orange hover:bg-brand-orange-hover text-panel-bg font-bold text-xs px-3.5 py-2
              rounded-lg flex items-center gap-1.5 shadow-sm transition-colors
              focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-success-green/50 focus-visible:ring-offset-2"
          >
            <Plus className="h-3.5 w-3.5 stroke-[2.5]" aria-hidden />
            Upload Tender
          </button>
        </div>
      </header>

      {/* ── Sub-nav tabs ─────────────────────────────────── */}
      <div className="px-6 py-2 bg-card-bg border-b border-divider flex items-center gap-2" role="tablist" aria-label="View mode">
        {(["keywords", "pinned"] as const).map((tab) => (
          <button
            key={tab}
            type="button"
            role="tab"
            aria-selected={activeTab === tab}
            onClick={() => setActiveTab(tab)}
            className={`px-3 py-1 rounded text-xs font-bold transition-all capitalize
              focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-success-green/40 ${
              activeTab === tab
                ? "bg-section-tint text-text-primary"
                : "text-text-muted hover:text-text-secondary"
            }`}
          >
            {tab === "keywords" ? "Keywords" : "Pinned Checks"}
          </button>
        ))}
      </div>

      {/* ── Search + filters area ─────────────────────────── */}
      <div className="px-6 py-4 max-w-[1440px] w-full mx-auto space-y-3">

        {/* Search row */}
        <div className="flex flex-col md:flex-row gap-3">
          <div className="relative flex-1">
            <label htmlFor={`${uid}-search`} className="sr-only">Search tenders</label>
            <Search className="absolute left-4 top-1/2 -translate-y-1/2 h-4 w-4 text-text-muted pointer-events-none" aria-hidden />
            <input
              id={`${uid}-search`}
              type="search"
              placeholder="Search by title, department, location, tender ID..."
              className="w-full bg-input-bg border border-divider rounded-xl pl-11 pr-16 py-3 text-sm
                text-text-primary placeholder-text-disabled
                focus:outline-none focus:border-success-green focus:ring-2 focus:ring-success-green/20
                transition-all font-sans shadow-[0_1px_2px_rgba(0,0,0,0.02)]"
              value={searchTerm}
              onChange={(e) => onSearchChange(e.target.value)}
              autoComplete="off"
            />
            <div
              aria-hidden
              className="absolute right-4 top-1/2 -translate-y-1/2 hidden sm:flex items-center
                text-[10px] bg-section-tint text-text-muted px-2 py-0.5 rounded border border-divider
                font-mono font-bold pointer-events-none"
            >
              ⌘K
            </div>
          </div>

          <div className="flex gap-2 shrink-0">
            <button
              type="button"
              onClick={() => setIsFiltersOpen(!isFiltersOpen)}
              aria-expanded={isFiltersOpen}
              aria-controls={`${uid}-adv-filters`}
              aria-label={`Advanced filters${activeFiltersCount > 0 ? `, ${activeFiltersCount} active` : ""}`}
              className={`px-4 py-3 border rounded-xl text-xs font-bold flex items-center gap-2
                transition-all cursor-pointer shadow-[0_1px_2px_rgba(0,0,0,0.02)]
                focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-success-green/40 ${
                isFiltersOpen || activeFiltersCount > 0
                  ? "bg-selected-green-bg border-selected-green-border text-success-green"
                  : "bg-input-bg border-divider text-text-secondary hover:text-text-primary hover:border-text-muted"
              }`}
            >
              <SlidersHorizontal className="h-4 w-4" aria-hidden />
              Filters
              {activeFiltersCount > 0 && (
                <span className="bg-success-green text-panel-bg text-[9px] px-1.5 py-0.5 rounded-full font-bold leading-none">
                  {activeFiltersCount}
                </span>
              )}
              {isFiltersOpen
                ? <ChevronUp className="h-3.5 w-3.5" aria-hidden />
                : <ChevronDown className="h-3.5 w-3.5" aria-hidden />
              }
            </button>

            <button
              type="button"
              className="bg-success-green hover:bg-cta-green text-panel-bg font-bold text-xs
                px-6 py-3 rounded-xl transition-colors shadow-sm cursor-pointer
                focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-success-green/50 focus-visible:ring-offset-2"
            >
              Search
            </button>
          </div>
        </div>

        {/* Quick-view chips */}
        <div className="flex items-center gap-2 overflow-x-auto pb-0.5" role="group" aria-label="Quick view filters">
          <span className="text-[10px] text-text-muted uppercase font-bold tracking-wider font-sans shrink-0">
            Quick view:
          </span>
          {([
            { label: "All Tenders",      value: "",          active: "bg-text-primary border-text-primary text-panel-bg" },
            { label: "Open Tenders",     value: "Live",      active: "bg-success-green border-success-green text-panel-bg" },
            { label: "Closed / Reviewed",value: "Completed", active: "bg-text-secondary border-text-secondary text-panel-bg" },
          ] as const).map(({ label, value, active }) => (
            <button
              key={value}
              type="button"
              aria-pressed={filters.tenderType === value}
              onClick={() => f("tenderType", value)}
              className={`px-3 py-1 rounded-full text-xs font-bold border transition-all shrink-0
                focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-success-green/40 ${
                filters.tenderType === value
                  ? `${active} shadow-sm`
                  : "bg-card-bg border-divider text-text-secondary hover:text-text-primary"
              }`}
            >
              {label}
            </button>
          ))}
        </div>

        {/* Advanced filter panel */}
        {isFiltersOpen && (
          <div
            id={`${uid}-adv-filters`}
            className="bg-card-bg border border-divider rounded-2xl p-5 space-y-4
              shadow-[0_4px_20px_rgba(0,0,0,0.04)] animate-fadeIn"
          >
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">

              <div className="space-y-1.5">
                <label htmlFor={`${uid}-kw-in`} className="text-[10px] font-bold text-text-muted uppercase tracking-wide block">
                  Within Keywords
                </label>
                <input id={`${uid}-kw-in`} type="text" placeholder="Contains terms…" className={inputCls}
                  value={filters.withinKeywords} onChange={(e) => f("withinKeywords", e.target.value)} />
              </div>

              <div className="space-y-1.5">
                <label htmlFor={`${uid}-kw-ex`} className="text-[10px] font-bold text-text-muted uppercase tracking-wide block">
                  Exclude Keywords
                </label>
                <input id={`${uid}-kw-ex`} type="text" placeholder="Exclude terms…" className={inputCls}
                  value={filters.notInKeyword} onChange={(e) => f("notInKeyword", e.target.value)} />
              </div>

              <div className="space-y-1.5">
                <label htmlFor={`${uid}-city`} className="text-[10px] font-bold text-text-muted uppercase tracking-wide block">
                  City
                </label>
                <input id={`${uid}-city`} type="text" placeholder="e.g. Raipur" className={inputCls}
                  value={filters.city} onChange={(e) => f("city", e.target.value)} />
              </div>

              <fieldset className="space-y-1.5">
                <legend className="text-[10px] font-bold text-text-muted uppercase tracking-wide">
                  Tender Value (INR)
                </legend>
                <div className="flex items-center gap-2">
                  <input type="number" aria-label="Minimum tender value" placeholder="Min" className={inputCls}
                    value={filters.valueFrom} onChange={(e) => f("valueFrom", e.target.value)} />
                  <span className="text-text-muted text-xs shrink-0">—</span>
                  <input type="number" aria-label="Maximum tender value" placeholder="Max" className={inputCls}
                    value={filters.valueTo} onChange={(e) => f("valueTo", e.target.value)} />
                </div>
              </fieldset>

              <fieldset className="space-y-1.5">
                <legend className="text-[10px] font-bold text-text-muted uppercase tracking-wide">
                  EMD Amount (INR)
                </legend>
                <div className="flex items-center gap-2">
                  <input type="number" aria-label="Minimum EMD" placeholder="Min" className={inputCls}
                    value={filters.emdFrom} onChange={(e) => f("emdFrom", e.target.value)} />
                  <span className="text-text-muted text-xs shrink-0">—</span>
                  <input type="number" aria-label="Maximum EMD" placeholder="Max" className={inputCls}
                    value={filters.emdTo} onChange={(e) => f("emdTo", e.target.value)} />
                </div>
              </fieldset>

              <fieldset className="space-y-1.5">
                <legend className="text-[10px] font-bold text-text-muted uppercase tracking-wide">
                  Closing Deadline Range
                </legend>
                <div className="flex items-center gap-2">
                  <input type="date" aria-label="Deadline from" className={inputCls}
                    value={filters.closingFrom} onChange={(e) => f("closingFrom", e.target.value)} />
                  <span className="text-text-muted text-xs shrink-0">—</span>
                  <input type="date" aria-label="Deadline to" className={inputCls}
                    value={filters.closingTo} onChange={(e) => f("closingTo", e.target.value)} />
                </div>
              </fieldset>

              <div className="space-y-1.5">
                <label htmlFor={`${uid}-state`} className="text-[10px] font-bold text-text-muted uppercase tracking-wide block">
                  State
                </label>
                <select id={`${uid}-state`}
                  className={`${inputCls} cursor-pointer`}
                  value={filters.state} onChange={(e) => f("state", e.target.value)}
                >
                  <option value="">All States</option>
                  <option>Chhattisgarh</option>
                  <option>Bihar</option>
                  <option>Maharashtra</option>
                  <option>Uttar Pradesh</option>
                  <option>Delhi</option>
                </select>
              </div>

              <div className="space-y-1.5">
                <label htmlFor={`${uid}-sector`} className="text-[10px] font-bold text-text-muted uppercase tracking-wide block">
                  Sector
                </label>
                <select id={`${uid}-sector`}
                  className={`${inputCls} cursor-pointer`}
                  value={filters.sector} onChange={(e) => f("sector", e.target.value)}
                >
                  <option value="">Any Sector</option>
                  <option>Infrastructure</option>
                  <option>Renewable Energy</option>
                </select>
              </div>

            </div>

            <div className="border-t border-divider/60 pt-3 flex justify-between items-center">
              <span className="text-text-muted font-mono text-[10px]">
                5,00,000+ live tenders · updated hourly
              </span>
              <button
                type="button"
                onClick={onClearFilters}
                className="text-xs text-text-secondary hover:text-success-green font-bold
                  underline decoration-dotted transition-colors cursor-pointer
                  focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-success-green/40 rounded"
              >
                Clear all filters
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default WorkspaceHeader;
