import { useState, useEffect } from "react";
import { apiService } from "./services/api";
import type { TenderDetail } from "./types/tender";
import { WorkspaceHeader } from "./components/workspace/WorkspaceHeader";
import type { FiltersState } from "./components/workspace/WorkspaceHeader";
import { TenderCard } from "./components/workspace/TenderCard";
import { TenderCardSkeleton } from "./components/workspace/TenderCardSkeleton";
import { TenderDetailPane } from "./components/workspace/TenderDetailPane";
import { UploadModal } from "./components/workspace/UploadModal";
import { LayoutGrid, Loader2, Sparkles, Calendar, Activity } from "lucide-react";

function App() {
  const [tenders, setTenders] = useState<TenderDetail[]>([]);
  const [selectedTenderId, setSelectedTenderId] = useState<string | null>(null);
  const [searchTerm, setSearchTerm] = useState("");
  
  // Advanced filters state
  const [filters, setFilters] = useState<FiltersState>({
    withinKeywords: "",
    notInKeyword: "",
    city: "",
    valueFrom: "",
    valueTo: "",
    emdFrom: "",
    emdTo: "",
    closingFrom: "",
    closingTo: "",
    state: "",
    sector: "",
    tenderType: "",
    agencyName: ""
  });

  const [loading, setLoading] = useState(true);
  const [isUploadModalOpen, setIsUploadModalOpen] = useState(false);
  const isBackendConnected = true;

  // Poll for background processing updates
  useEffect(() => {
    fetchTenders();

    const interval = setInterval(async () => {
      const data = await apiService.getTenders();
      setTenders(data);
    }, 3000);

    return () => clearInterval(interval);
  }, []);

  const fetchTenders = async () => {
    setLoading(true);
    try {
      const data = await apiService.getTenders();
      setTenders(data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleSelectTender = (tender: TenderDetail) => {
    setSelectedTenderId(tender.id);
  };

  const handleUpdateField = async (fieldId: string, value: string) => {
    if (!selectedTenderId) return;
    try {
      const updated = await apiService.updateTenderField(selectedTenderId, fieldId, value);
      setTenders((prev) => prev.map((t) => (t.id === selectedTenderId ? updated : t)));
    } catch (err) {
      alert("Error updating field value");
    }
  };

  const handleVerifyField = async (fieldId: string) => {
    if (!selectedTenderId) return;
    try {
      const updated = await apiService.verifyField(selectedTenderId, fieldId);
      setTenders((prev) => prev.map((t) => (t.id === selectedTenderId ? updated : t)));
    } catch (err) {
      alert("Error verifying field");
    }
  };

  const handleLinkDocument = async (docId: string, file: File) => {
    if (!selectedTenderId) return;
    try {
      const updated = await apiService.linkDocument(selectedTenderId, docId, file);
      setTenders((prev) => prev.map((t) => (t.id === selectedTenderId ? updated : t)));
    } catch (err) {
      alert("Error linking file");
    }
  };

  const handleUploadTender = async (file: File) => {
    try {
      const pendingTender = await apiService.uploadTender(file);
      setTenders((prev) => [pendingTender, ...prev]);
      
      // Auto trigger asynchronous OCR parsing
      await apiService.triggerProcessing(pendingTender.id);
    } catch (err) {
      alert("Error uploading tender file");
    }
  };

  const handleRetryParse = async () => {
    if (!selectedTenderId) return;
    try {
      const updated = await apiService.triggerProcessing(selectedTenderId);
      setTenders((prev) => prev.map((t) => (t.id === selectedTenderId ? updated : t)));
    } catch (err) {
      alert("Error triggering reparse");
    }
  };

  const handleMarkReviewed = async () => {
    if (!selectedTenderId) return;
    try {
      const updated = await apiService.markReviewed(selectedTenderId, "Yuvraj Sharma");
      setTenders((prev) => prev.map((t) => (t.id === selectedTenderId ? updated : t)));
    } catch (err) {
      alert("Error marking review complete");
    }
  };

  const handleClearFilters = () => {
    setFilters({
      withinKeywords: "",
      notInKeyword: "",
      city: "",
      valueFrom: "",
      valueTo: "",
      emdFrom: "",
      emdTo: "",
      closingFrom: "",
      closingTo: "",
      state: "",
      sector: "",
      tenderType: "",
      agencyName: ""
    });
  };

  const getNumericValue = (valStr: string) => {
    const cleaned = valStr.toLowerCase().replace(/,/g, "").trim();
    if (cleaned.includes("crore") || cleaned.includes("cr")) {
      return parseFloat(cleaned) * 10000000;
    }
    if (cleaned.includes("lakh") || cleaned.includes("l")) {
      return parseFloat(cleaned) * 100000;
    }
    return parseFloat(cleaned) || 0;
  };

  // Advanced filtration query matching logic
  const filteredTenders = tenders.filter((tender) => {
    // 1. Text Search matching title, ID, authority, department
    const query = searchTerm.toLowerCase();
    const matchesSearch =
      !query ||
      tender.title.toLowerCase().includes(query) ||
      tender.id.toLowerCase().includes(query) ||
      tender.authorityName.toLowerCase().includes(query) ||
      (tender.department?.toLowerCase() || "").includes(query);

    if (!matchesSearch) return false;

    // 2. Within Keywords filter
    if (filters.withinKeywords) {
      const k = filters.withinKeywords.toLowerCase();
      const hasKeyword =
        tender.title.toLowerCase().includes(k) ||
        tender.snippet.toLowerCase().includes(k) ||
        (tender.raw_ocr_text || "").toLowerCase().includes(k);
      if (!hasKeyword) return false;
    }

    // 3. Not in Keyword filter
    if (filters.notInKeyword) {
      const k = filters.notInKeyword.toLowerCase();
      const hasExcludedKeyword =
        tender.title.toLowerCase().includes(k) ||
        tender.snippet.toLowerCase().includes(k) ||
        (tender.raw_ocr_text || "").toLowerCase().includes(k);
      if (hasExcludedKeyword) return false;
    }

    // 4. City filter
    if (filters.city && tender.location_city.toLowerCase() !== filters.city.toLowerCase()) {
      return false;
    }

    // 5. State filter
    if (filters.state && tender.location_state.toLowerCase() !== filters.state.toLowerCase()) {
      return false;
    }

    // 6. Sector filter
    if (filters.sector && tender.sector.toLowerCase() !== filters.sector.toLowerCase()) {
      return false;
    }

    // 7. Tender Type filter
    if (filters.tenderType) {
      if (filters.tenderType === "Live" && tender.review_status === "completed") {
        return false;
      }
      if (filters.tenderType === "Completed" && tender.review_status !== "completed") {
        return false;
      }
    }

    // 8. Tender Value Range filter (in INR)
    const valNum = getNumericValue(tender.tenderValue);
    if (filters.valueFrom && valNum < parseFloat(filters.valueFrom)) {
      return false;
    }
    if (filters.valueTo && valNum > parseFloat(filters.valueTo)) {
      return false;
    }

    // 9. EMD Range filter (in INR)
    const emdNum = getNumericValue(tender.emdAmount || "0");
    if (filters.emdFrom && emdNum < parseFloat(filters.emdFrom)) {
      return false;
    }
    if (filters.emdTo && emdNum > parseFloat(filters.emdTo)) {
      return false;
    }

    // 10. Closing Date range filter
    if (filters.closingFrom || filters.closingTo) {
      const deadline = new Date(tender.deadline).getTime();
      if (isNaN(deadline)) return false;
      
      if (filters.closingFrom) {
        const fromDate = new Date(filters.closingFrom).getTime();
        if (deadline < fromDate) return false;
      }
      if (filters.closingTo) {
        const toDate = new Date(filters.closingTo).getTime();
        if (deadline > toDate) return false;
      }
    }

    return true;
  });

  const activeTender = tenders.find((t) => t.id === selectedTenderId);

  // Statistics Calculations
  const statsLive = tenders.filter(t => t.parse_status === "completed" && t.review_status !== "completed").length;
  const statsNew = tenders.filter(t => t.parse_status === "processing" || t.parse_status === "pending").length;
  const statsClosing = tenders.filter(t => {
    const days = Math.ceil((new Date(t.deadline).getTime() - Date.now()) / (1000 * 60 * 60 * 24));
    return days > 0 && days <= 7;
  }).length;
  const statsHighMatch = tenders.filter(t => t.parse_confidence >= 85).length;

  return (
    <div className="h-screen w-screen flex flex-col overflow-hidden bg-app-bg text-text-primary">
      <WorkspaceHeader
        searchTerm={searchTerm}
        onSearchChange={setSearchTerm}
        filters={filters}
        onFiltersChange={setFilters}
        onClearFilters={handleClearFilters}
        onUploadClick={() => setIsUploadModalOpen(true)}
        isBackendConnected={isBackendConnected}
        onRefreshClick={fetchTenders}
      />

      <main className="flex-1 flex overflow-hidden p-6 gap-6 min-h-0">
        {activeTender ? (
          <TenderDetailPane
            tender={activeTender}
            onBack={() => setSelectedTenderId(null)}
            onUpdateField={handleUpdateField}
            onVerifyField={handleVerifyField}
            onMarkReviewed={handleMarkReviewed}
            onRetryParse={handleRetryParse}
            onLinkDocument={handleLinkDocument}
          />
        ) : (
          <div className="flex-1 flex flex-col min-h-0 max-w-[1440px] mx-auto w-full">
            
            {/* Stats KPI Widgets Row */}
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6 shrink-0 select-none">
              
              <div className="bg-card-bg border border-divider/60 rounded-2xl p-5 shadow-[0_1px_3px_rgba(0,0,0,0.02),0_4px_12px_rgba(0,0,0,0.03)] flex items-center justify-between">
                <div className="space-y-1">
                  <span className="text-[10px] text-text-muted font-bold uppercase tracking-wider">Live Tenders</span>
                  <p className="text-2xl font-bold text-text-primary leading-tight font-mono">{statsLive}</p>
                </div>
                <div className="h-10 w-10 bg-selected-green-bg border border-selected-green-border text-success-green flex items-center justify-center rounded-xl">
                  <Activity className="h-5 w-5" />
                </div>
              </div>

              <div className="bg-card-bg border border-divider/60 rounded-2xl p-5 shadow-[0_1px_3px_rgba(0,0,0,0.02),0_4px_12px_rgba(0,0,0,0.03)] flex items-center justify-between">
                <div className="space-y-1">
                  <span className="text-[10px] text-text-muted font-bold uppercase tracking-wider">Ingesting / Processing</span>
                  <p className="text-2xl font-bold text-text-primary leading-tight font-mono">{statsNew}</p>
                </div>
                <div className="h-10 w-10 bg-blue-50 border border-blue-200 text-blue-600 flex items-center justify-center rounded-xl">
                  <Loader2 className="h-5 w-5 animate-spin" />
                </div>
              </div>

              <div className="bg-card-bg border border-divider/60 rounded-2xl p-5 shadow-[0_1px_3px_rgba(0,0,0,0.02),0_4px_12px_rgba(0,0,0,0.03)] flex items-center justify-between">
                <div className="space-y-1">
                  <span className="text-[10px] text-text-muted font-bold uppercase tracking-wider">Closing Soon</span>
                  <p className="text-2xl font-bold text-text-primary leading-tight font-mono">{statsClosing}</p>
                </div>
                <div className="h-10 w-10 bg-warning-bg border border-warning-text/10 text-warning-text flex items-center justify-center rounded-xl">
                  <Calendar className="h-5 w-5" />
                </div>
              </div>

              <div className="bg-card-bg border border-divider/60 rounded-2xl p-5 shadow-[0_1px_3px_rgba(0,0,0,0.02),0_4px_12px_rgba(0,0,0,0.03)] flex items-center justify-between">
                <div className="space-y-1">
                  <span className="text-[10px] text-text-muted font-bold uppercase tracking-wider">High AI Match</span>
                  <p className="text-2xl font-bold text-text-primary leading-tight font-mono">{statsHighMatch}</p>
                </div>
                <div className="h-10 w-10 bg-emerald-50 border border-success-green/20 text-success-green flex items-center justify-center rounded-xl">
                  <Sparkles className="h-5 w-5" />
                </div>
              </div>

            </div>

            {/* Header info bar */}
            <div className="flex items-center justify-between mb-5 shrink-0 select-none">
              <div>
                <h2 className="text-base font-bold text-text-primary font-sans tracking-tight">Tender Results</h2>
                <p className="text-xs text-text-muted mt-1 font-mono">
                  {filteredTenders.length} tenders found
                </p>
              </div>
              <div className="flex items-center gap-1 bg-card-bg border border-divider p-0.5 rounded text-[10px] text-text-muted font-bold font-mono uppercase">
                <LayoutGrid className="h-3.5 w-3.5 text-text-muted" />
                <span className="px-1.5 py-0.5 bg-panel-bg text-text-primary rounded border border-divider shadow-sm">Card View</span>
              </div>
            </div>

            {/* Layout Cards */}
            {loading ? (
              <div className="flex-1 overflow-y-auto grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4 pr-1 align-start content-start pb-6">
                {Array.from({ length: 6 }).map((_, idx) => (
                  <TenderCardSkeleton key={idx} />
                ))}
              </div>
            ) : filteredTenders.length === 0 ? (
              <div className="flex-1 border border-dashed border-divider rounded-2xl flex flex-col items-center justify-center text-text-muted p-8 text-center bg-card-bg/35 select-none">
                <LayoutGrid className="h-12 w-12 text-text-disabled mb-3" />
                <h3 className="text-sm font-semibold text-text-secondary">No live tenders match filters</h3>
                <p className="text-xs text-text-muted max-w-xs mt-1 leading-relaxed">
                  Adjust keywords, location codes, value bounds, or deadline constraints to broaden search results.
                </p>
                <button
                  onClick={handleClearFilters}
                  className="mt-4 px-4 py-2 bg-panel-bg hover:bg-section-tint border border-divider text-xs font-bold text-text-secondary rounded-xl transition-colors shadow-sm cursor-pointer"
                >
                  Clear all filters
                </button>
              </div>
            ) : (
              <div className="flex-1 overflow-y-auto grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4 pr-1 align-start content-start pb-6">
                {filteredTenders.map((tender) => (
                  <TenderCard
                    key={tender.id}
                    tender={tender}
                    onOpen={() => handleSelectTender(tender)}
                  />
                ))}
              </div>
            )}
          </div>
        )}
      </main>

      {/* Upload Modal Ingestion Zone */}
      <UploadModal
        isOpen={isUploadModalOpen}
        onClose={() => setIsUploadModalOpen(false)}
        onUpload={handleUploadTender}
      />
    </div>
  );
}

export default App;
