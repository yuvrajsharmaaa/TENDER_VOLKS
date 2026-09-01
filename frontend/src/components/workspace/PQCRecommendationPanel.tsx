import React, { useState, useEffect } from "react";
import {
  Sparkles,
  ShieldCheck,
  TrendingUp,
  BrainCircuit,
  Bot,
  RefreshCw,
  ChevronDown,
  ChevronUp,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  ExternalLink,
  Award,
  Database,
  Building2,
  IndianRupee,
  Layers
} from "lucide-react";
import { apiService } from "../../services/api";
import type { ScoredTender, PQCRecommendationResponse } from "../../types/tender";

interface PQCRecommendationPanelProps {
  onSelectTender?: (tenderNo: string) => void;
}

export const PQCRecommendationPanel: React.FC<PQCRecommendationPanelProps> = ({
  onSelectTender
}) => {
  const [data, setData] = useState<PQCRecommendationResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedTenderNo, setExpandedTenderNo] = useState<string | null>(null);
  const [topK, setTopK] = useState<number>(20);
  const [source, setSource] = useState<"db" | "dataset">("dataset");
  const [includeGroq, setIncludeGroq] = useState<boolean>(true);

  const fetchRecommendations = async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await apiService.recommendPQC(topK, includeGroq, source);
      setData(resp);
      if (resp.recommendations.length > 0 && !expandedTenderNo) {
        setExpandedTenderNo(resp.recommendations[0].tender_no);
      }
    } catch (err: any) {
      console.error("[PQCPanel] Failed to fetch recommendations:", err);
      setError(err?.message || "Failed to load PQC recommendations");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchRecommendations();
  }, [topK, source, includeGroq]);

  const formatCurrency = (val: number) => {
    if (!val || val <= 0) return "Not Specified";
    if (val >= 10000000) {
      return `₹${(val / 10000000).toFixed(2)} Cr`;
    }
    if (val >= 100000) {
      return `₹${(val / 100000).toFixed(2)} Lakh`;
    }
    return `₹${val.toLocaleString("en-IN")}`;
  };

  const getComplianceBadge = (status: string) => {
    switch (status) {
      case "QUALIFIED":
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
            <CheckCircle2 className="h-3 w-3 text-emerald-600" />
            QUALIFIED
          </span>
        );
      case "NEEDS_REVIEW":
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-50 text-amber-700 border border-amber-200">
            <AlertTriangle className="h-3 w-3 text-amber-600" />
            NEEDS REVIEW
          </span>
        );
      case "DISQUALIFIED":
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-rose-50 text-rose-700 border border-rose-200">
            <XCircle className="h-3 w-3 text-rose-600" />
            DISQUALIFIED
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-700">
            {status}
          </span>
        );
    }
  };

  return (
    <div className="flex-1 flex flex-col h-full bg-[#FAFAFA] overflow-y-auto p-4 sm:p-6 select-none font-sans">
      {/* ── KPI & Control Header ──────────────────────────────────────── */}
      <div className="bg-white border border-[#E5E7EB] rounded-2xl p-5 shadow-xs mb-6">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <div className="h-8 w-8 rounded-lg bg-blue-50 text-blue-600 flex items-center justify-center">
                <Sparkles className="h-4 w-4" />
              </div>
              <h1 className="text-lg font-bold text-gray-900 tracking-tight">
                PQC Recommendation & Multi-Signal Bid Ranking
              </h1>
            </div>
            <p className="text-xs text-gray-500 max-w-2xl">
              Deterministic Hard Compliance (<span className="font-semibold text-gray-700">35%</span>) + Qdrant
              Historical Similarity (<span className="font-semibold text-gray-700">35%</span>) + LightGBM Predictive Win
              Probability (<span className="font-semibold text-gray-700">15%</span>) + Groq LLM Qualitative Fit (
              <span className="font-semibold text-gray-700">15%</span>).
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            {/* Source Switcher */}
            <div className="flex items-center bg-gray-100 p-1 rounded-xl border border-gray-200 text-xs font-medium">
              <button
                type="button"
                onClick={() => setSource("dataset")}
                className={`px-3 py-1.5 rounded-lg transition-all ${
                  source === "dataset"
                    ? "bg-white text-gray-900 shadow-xs font-semibold"
                    : "text-gray-600 hover:text-gray-900"
                }`}
              >
                657 Gold Standard Dataset
              </button>
              <button
                type="button"
                onClick={() => setSource("db")}
                className={`px-3 py-1.5 rounded-lg transition-all ${
                  source === "db"
                    ? "bg-white text-gray-900 shadow-xs font-semibold"
                    : "text-gray-600 hover:text-gray-900"
                }`}
              >
                Active Database
              </button>
            </div>

            {/* Top-K Selector */}
            <select
              value={topK}
              onChange={(e) => setTopK(Number(e.target.value))}
              className="bg-white border border-gray-200 text-xs font-medium text-gray-700 rounded-xl px-3 py-2 shadow-xs focus:outline-none focus:ring-2 focus:ring-blue-500/20"
            >
              <option value={10}>Top 10</option>
              <option value={20}>Top 20</option>
              <option value={50}>Top 50</option>
            </select>

            {/* Groq AI Enrichment Toggle */}
            <button
              type="button"
              onClick={() => setIncludeGroq(!includeGroq)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl border text-xs font-semibold transition-all shadow-xs ${
                includeGroq
                  ? "bg-purple-50 text-purple-700 border-purple-200"
                  : "bg-gray-100 text-gray-500 border-gray-200"
              }`}
            >
              <Bot className="h-3.5 w-3.5" />
              Groq AI {includeGroq ? "On" : "Off"}
            </button>

            {/* Refresh Button */}
            <button
              type="button"
              onClick={fetchRecommendations}
              disabled={loading}
              className="flex items-center gap-1.5 px-3.5 py-2 bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold rounded-xl shadow-xs transition-colors disabled:opacity-50 cursor-pointer"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
              Re-score & Rank
            </button>
          </div>
        </div>

        {/* Metric Badges */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-5 pt-4 border-t border-gray-100">
          <div className="bg-gray-50/80 rounded-xl p-3 border border-gray-100">
            <span className="text-[11px] font-medium text-gray-500 flex items-center gap-1">
              <ShieldCheck className="h-3.5 w-3.5 text-emerald-600" /> Hard Compliance
            </span>
            <p className="text-base font-bold text-gray-900 mt-1 font-mono">35% Weight</p>
            <p className="text-[10px] text-gray-400">8 Invariant Statutory Rules</p>
          </div>

          <div className="bg-gray-50/80 rounded-xl p-3 border border-gray-100">
            <span className="text-[11px] font-medium text-gray-500 flex items-center gap-1">
              <Layers className="h-3.5 w-3.5 text-blue-600" /> Historical Similarity
            </span>
            <p className="text-base font-bold text-gray-900 mt-1 font-mono">35% Weight</p>
            <p className="text-[10px] text-gray-400">Qdrant Top-5 Precedent Win Rate</p>
          </div>

          <div className="bg-gray-50/80 rounded-xl p-3 border border-gray-100">
            <span className="text-[11px] font-medium text-gray-500 flex items-center gap-1">
              <BrainCircuit className="h-3.5 w-3.5 text-purple-600" /> LightGBM Classifier
            </span>
            <p className="text-base font-bold text-gray-900 mt-1 font-mono">15% Weight</p>
            <p className="text-[10px] text-gray-400">16-Feature ML Win Probability</p>
          </div>

          <div className="bg-gray-50/80 rounded-xl p-3 border border-gray-100">
            <span className="text-[11px] font-medium text-gray-500 flex items-center gap-1">
              <Bot className="h-3.5 w-3.5 text-amber-600" /> Groq AI Fit
            </span>
            <p className="text-base font-bold text-gray-900 mt-1 font-mono">15% Weight</p>
            <p className="text-[10px] text-gray-400">llama-3.1-8b Strategic Synthesis</p>
          </div>
        </div>
      </div>

      {/* ── Recommendation Table ─────────────────────────────────────── */}
      {loading ? (
        <div className="flex-1 flex flex-col items-center justify-center p-12 bg-white rounded-2xl border border-gray-200">
          <RefreshCw className="h-8 w-8 text-blue-600 animate-spin mb-3" />
          <p className="text-sm font-semibold text-gray-900">Evaluating multi-signal fit across tenders...</p>
          <p className="text-xs text-gray-500 mt-1">Executing hard compliance filters and vector similarity scoring</p>
        </div>
      ) : error ? (
        <div className="p-6 bg-rose-50 border border-rose-200 rounded-2xl text-center">
          <AlertTriangle className="h-8 w-8 text-rose-500 mx-auto mb-2" />
          <p className="text-sm font-bold text-rose-900">Error Loading Recommendations</p>
          <p className="text-xs text-rose-700 mt-1">{error}</p>
        </div>
      ) : !data || data.recommendations.length === 0 ? (
        <div className="p-12 text-center bg-white rounded-2xl border border-gray-200">
          <p className="text-sm font-semibold text-gray-700">No recommended tenders available</p>
        </div>
      ) : (
        <div className="space-y-3">
          {data.recommendations.map((t: ScoredTender) => {
            const isExpanded = expandedTenderNo === t.tender_no;
            const decomp = t.score_decomposition;

            return (
              <div
                key={t.tender_no}
                className={`bg-white border rounded-2xl transition-all duration-200 overflow-hidden shadow-xs ${
                  isExpanded ? "border-blue-400 ring-2 ring-blue-100" : "border-gray-200 hover:border-gray-300"
                }`}
              >
                {/* ── Row Summary Bar ───────────────────────────────── */}
                <div
                  onClick={() => setExpandedTenderNo(isExpanded ? null : t.tender_no)}
                  className="p-4 sm:p-5 flex flex-col lg:flex-row lg:items-center justify-between gap-4 cursor-pointer"
                >
                  <div className="flex items-start gap-3.5 min-w-0">
                    {/* Rank Badge */}
                    <div
                      className={`h-9 w-9 shrink-0 rounded-xl font-mono font-bold text-xs flex items-center justify-center shadow-xs ${
                        t.rank === 1
                          ? "bg-amber-100 text-amber-800 border border-amber-300"
                          : t.rank === 2
                          ? "bg-slate-200 text-slate-800 border border-slate-300"
                          : t.rank === 3
                          ? "bg-amber-50 text-amber-700 border border-amber-200"
                          : "bg-gray-100 text-gray-700 border border-gray-200"
                      }`}
                    >
                      #{t.rank}
                    </div>

                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2 mb-1">
                        <span className="font-mono text-xs font-semibold text-gray-900 bg-gray-100 px-2 py-0.5 rounded-md">
                          {t.tender_no}
                        </span>
                        {getComplianceBadge(decomp.compliance_status)}
                        {t.rank <= 3 && (
                          <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-amber-700 bg-amber-50 border border-amber-200 px-2 py-0.5 rounded-full">
                            <Award className="h-3 w-3" /> High Win Fit
                          </span>
                        )}
                      </div>

                      <h3 className="text-sm font-bold text-gray-900 truncate tracking-tight">{t.tender_name}</h3>

                      <div className="flex flex-wrap items-center gap-4 text-xs text-gray-500 mt-1">
                        <span className="flex items-center gap-1">
                          <Building2 className="h-3.5 w-3.5 text-gray-400" />
                          <span className="font-medium text-gray-700">{t.organization}</span>
                        </span>
                        <span className="flex items-center gap-1 font-mono">
                          <IndianRupee className="h-3.5 w-3.5 text-gray-400" />
                          <span className="font-semibold text-gray-900">{formatCurrency(t.tender_value)}</span>
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* Score Decomposition Columns */}
                  <div className="flex items-center gap-5 shrink-0 self-end lg:self-center">
                    {/* Micro Scores */}
                    <div className="hidden sm:grid grid-cols-4 gap-3 text-center border-r border-gray-100 pr-5">
                      <div>
                        <span className="text-[10px] uppercase font-semibold text-gray-400">Comp</span>
                        <p className="text-xs font-bold text-emerald-700 font-mono">
                          {(decomp.compliance_score * 100).toFixed(0)}%
                        </p>
                      </div>
                      <div>
                        <span className="text-[10px] uppercase font-semibold text-gray-400">Sim</span>
                        <p className="text-xs font-bold text-blue-700 font-mono">
                          {(decomp.similarity_score * 100).toFixed(0)}%
                        </p>
                      </div>
                      <div>
                        <span className="text-[10px] uppercase font-semibold text-gray-400">ML Win</span>
                        <p className="text-xs font-bold text-purple-700 font-mono">
                          {(decomp.ml_win_prob * 100).toFixed(0)}%
                        </p>
                      </div>
                      <div>
                        <span className="text-[10px] uppercase font-semibold text-gray-400">AI Fit</span>
                        <p className="text-xs font-bold text-amber-700 font-mono">
                          {(decomp.groq_fit_score * 100).toFixed(0)}%
                        </p>
                      </div>
                    </div>

                    {/* Composite Score Circle / Bar */}
                    <div className="text-right min-w-[90px]">
                      <span className="text-[11px] font-semibold text-gray-500">Composite Fit</span>
                      <p className="text-lg font-extrabold text-blue-600 font-mono leading-none mt-0.5">
                        {(t.composite_score * 100).toFixed(1)}%
                      </p>
                      <div className="w-20 bg-gray-100 h-1.5 rounded-full mt-1.5 overflow-hidden ml-auto">
                        <div
                          className="bg-blue-600 h-full rounded-full transition-all duration-300"
                          style={{ width: `${Math.min(t.composite_score * 100, 100)}%` }}
                        />
                      </div>
                    </div>

                    <div className="text-gray-400 hover:text-gray-600 p-1">
                      {isExpanded ? <ChevronUp className="h-5 w-5" /> : <ChevronDown className="h-5 w-5" />}
                    </div>
                  </div>
                </div>

                {/* ── Expanded Detail Drawer ────────────────────────── */}
                {isExpanded && (
                  <div className="border-t border-gray-100 bg-[#F9FAFB] p-5 space-y-4 text-xs">
                    {/* Strategic Rationale & Key Drivers */}
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div className="bg-white p-4 rounded-xl border border-gray-200">
                        <h4 className="text-xs font-bold text-gray-900 mb-2 flex items-center gap-1.5">
                          <Bot className="h-4 w-4 text-blue-600" /> Strategic Fit & Rationale
                        </h4>
                        <p className="text-gray-700 leading-relaxed">
                          {t.strategic_rationale ||
                            "Strong statutory and historical commercial fit with verified buyer precedent."}
                        </p>
                      </div>

                      <div className="bg-white p-4 rounded-xl border border-gray-200">
                        <h4 className="text-xs font-bold text-gray-900 mb-2 flex items-center gap-1.5">
                          <TrendingUp className="h-4 w-4 text-purple-600" /> LightGBM Predictive Drivers
                        </h4>
                        <ul className="space-y-1 text-gray-700">
                          {t.key_drivers && t.key_drivers.length > 0 ? (
                            t.key_drivers.map((d, i) => (
                              <li key={i} className="flex items-center gap-1.5">
                                <span className="h-1.5 w-1.5 rounded-full bg-purple-500 shrink-0" />
                                {d}
                              </li>
                            ))
                          ) : (
                            <li className="text-gray-400 italic">No specific anomaly drivers identified.</li>
                          )}
                        </ul>
                      </div>
                    </div>

                    {/* Nearest Neighbor Precedents Table */}
                    {t.similar_tenders && t.similar_tenders.length > 0 && (
                      <div className="bg-white p-4 rounded-xl border border-gray-200">
                        <h4 className="text-xs font-bold text-gray-900 mb-2 flex items-center gap-1.5">
                          <Database className="h-4 w-4 text-blue-600" /> Historical Qdrant Nearest Neighbors
                        </h4>
                        <div className="overflow-x-auto">
                          <table className="w-full text-left border-collapse">
                            <thead>
                              <tr className="border-b border-gray-100 text-[11px] font-semibold text-gray-400 uppercase">
                                <th className="py-2">Tender Ref</th>
                                <th className="py-2">Authority</th>
                                <th className="py-2">Similarity</th>
                                <th className="py-2">Historical Outcome</th>
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-gray-100 text-xs">
                              {t.similar_tenders.map((sim, i) => (
                                <tr key={i} className="hover:bg-gray-50/60">
                                  <td className="py-2 font-mono font-medium text-gray-900">{sim.tender_no}</td>
                                  <td className="py-2 text-gray-600">{sim.organization}</td>
                                  <td className="py-2 font-mono text-gray-700">
                                    {(sim.similarity * 100).toFixed(1)}%
                                  </td>
                                  <td className="py-2">
                                    <span
                                      className={`inline-flex px-2 py-0.5 rounded text-[10px] font-bold ${
                                        sim.outcome.toLowerCase() === "won"
                                          ? "bg-emerald-100 text-emerald-800"
                                          : "bg-gray-100 text-gray-700"
                                      }`}
                                    >
                                      {sim.outcome}
                                    </span>
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    )}

                    {onSelectTender && (
                      <div className="flex justify-end pt-2">
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            onSelectTender(t.tender_no);
                          }}
                          className="flex items-center gap-1.5 px-3 py-1.5 bg-white hover:bg-gray-50 border border-gray-200 text-gray-700 text-xs font-semibold rounded-xl transition-colors shadow-xs cursor-pointer"
                        >
                          <ExternalLink className="h-3.5 w-3.5 text-gray-500" />
                          Open in Live Workspace
                        </button>
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
