import React from "react";
import type { TenderDetail } from "../../types/tender";
import { AlertCircle, Calendar, ShieldAlert, Award, FileText, CheckCircle2, Loader2, XCircle } from "lucide-react";

interface TenderTableProps {
  tenders: TenderDetail[];
  selectedTenderId: string | null;
  onSelectTender: (tender: TenderDetail) => void;
  loading: boolean;
}

export const TenderTable: React.FC<TenderTableProps> = ({
  tenders,
  selectedTenderId,
  onSelectTender,
  loading
}) => {
  const getStatusBadge = (status: TenderDetail["parse_status"], reviewStatus: TenderDetail["review_status"]) => {
    if (status === "pending") {
      return (
        <span className="inline-flex items-center gap-1 bg-slate-800 text-slate-300 text-xs px-2.5 py-1 rounded-full font-medium">
          <Loader2 className="h-3 w-3 animate-spin" />
          <span>Queued</span>
        </span>
      );
    }
    if (status === "processing") {
      return (
        <span className="inline-flex items-center gap-1 bg-blue-950 text-blue-400 text-xs px-2.5 py-1 rounded-full font-medium border border-blue-900/50">
          <Loader2 className="h-3 w-3 animate-spin" />
          <span>Processing</span>
        </span>
      );
    }
    if (status === "failed") {
      return (
        <span className="inline-flex items-center gap-1 bg-rose-950/40 text-rose-400 text-xs px-2.5 py-1 rounded-full font-medium border border-rose-900/30">
          <XCircle className="h-3 w-3" />
          <span>Failed</span>
        </span>
      );
    }
    if (reviewStatus === "completed") {
      return (
        <span className="inline-flex items-center gap-1 bg-emerald-950 text-emerald-400 text-xs px-2.5 py-1 rounded-full font-medium border border-emerald-900/40">
          <CheckCircle2 className="h-3 w-3" />
          <span>Reviewed</span>
        </span>
      );
    }
    return (
      <span className="inline-flex items-center gap-1 bg-amber-950 text-amber-400 text-xs px-2.5 py-1 rounded-full font-medium border border-amber-900/40">
        <AlertCircle className="h-3 w-3" />
        <span>Ready / Unreviewed</span>
      </span>
    );
  };

  const getConfidenceBadge = (score: number) => {
    if (score === 0) return <span className="text-slate-500 font-mono text-xs">--</span>;
    let color = "text-emerald-400 bg-emerald-950/30 border-emerald-900/50";
    if (score < 70) {
      color = "text-rose-400 bg-rose-950/30 border-rose-900/50";
    } else if (score < 85) {
      color = "text-amber-400 bg-amber-950/30 border-amber-900/50";
    }

    return (
      <span className={`inline-flex items-center gap-1 border px-2 py-0.5 rounded font-mono text-xs font-semibold ${color}`}>
        <Award className="h-3 w-3" />
        <span>{score.toFixed(1)}%</span>
      </span>
    );
  };

  const formatDate = (isoString: string) => {
    if (!isoString) return "Not Set";
    return new Date(isoString).toLocaleDateString("en-IN", {
      day: "2-digit",
      month: "short",
      year: "numeric"
    });
  };

  if (loading) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center text-slate-400">
        <Loader2 className="h-8 w-8 animate-spin text-blue-500 mb-2" />
        <span>Loading procurement workspace...</span>
      </div>
    );
  }

  if (tenders.length === 0) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center p-8 text-center text-slate-400">
        <FileText className="h-12 w-12 text-slate-600 mb-3" />
        <h3 className="text-lg font-semibold text-slate-200 mb-1">No Tenders Found</h3>
        <p className="text-sm text-slate-500 max-w-md">
          There are no tender documents in this workspace. Upload a tender PDF above to trigger visual OCR and field extraction.
        </p>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-auto border border-slate-800/80 rounded-lg bg-slate-900/40">
      <table className="w-full border-collapse text-left">
        <thead>
          <tr className="border-b border-slate-800 bg-slate-900/80 text-slate-400 text-xs font-semibold uppercase tracking-wider sticky top-0 z-[5]">
            <th className="py-3.5 px-4 w-[40%]">Tender Details / Scope</th>
            <th className="py-3.5 px-4">Authority & Dept</th>
            <th className="py-3.5 px-4">Est. Value & EMD</th>
            <th className="py-3.5 px-4">Submission Deadline</th>
            <th className="py-3.5 px-4 text-center">Status</th>
            <th className="py-3.5 px-4 text-center">Confidence</th>
            <th className="py-3.5 px-4 text-center">Alerts</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-800/50">
          {tenders.map((tender) => {
            const isSelected = selectedTenderId === tender.id;
            return (
              <tr
                key={tender.id}
                onClick={() => onSelectTender(tender)}
                className={`cursor-pointer transition-colors group ${
                  isSelected ? "bg-blue-950/20 border-l-2 border-l-blue-500" : "hover:bg-slate-900/60"
                }`}
              >
                {/* Details */}
                <td className="py-4 px-4">
                  <div className="flex flex-col gap-1">
                    <span className="font-semibold text-slate-200 text-sm group-hover:text-blue-400 transition-colors line-clamp-2">
                      {tender.title}
                    </span>
                    <div className="flex items-center gap-2 text-xs text-slate-500">
                      <span className="font-mono bg-slate-800 px-1.5 py-0.5 rounded text-slate-400">{tender.id}</span>
                      <span>Ref: {tender.reference_number || "Pending"}</span>
                    </div>
                  </div>
                </td>

                {/* Authority */}
                <td className="py-4 px-4">
                  <div className="flex flex-col">
                    <span className="text-slate-300 text-xs font-medium">{tender.authorityName}</span>
                    <span className="text-slate-500 text-[11px]">{tender.department}</span>
                  </div>
                </td>

                {/* Pricing */}
                <td className="py-4 px-4">
                  <div className="flex flex-col">
                    <span className="text-slate-300 text-xs font-mono font-semibold">{tender.tenderValue}</span>
                    <span className="text-slate-500 text-[11px]">
                      EMD: {tender.emdAmount || "N/A"}
                    </span>
                  </div>
                </td>

                {/* Timeline */}
                <td className="py-4 px-4 text-xs text-slate-400">
                  <div className="flex items-center gap-1.5">
                    <Calendar className="h-3.5 w-3.5 text-slate-500" />
                    <span>{tender.deadline ? formatDate(tender.deadline) : "Not Extracted"}</span>
                  </div>
                </td>

                {/* Status */}
                <td className="py-4 px-4 text-center">
                  {getStatusBadge(tender.parse_status, tender.review_status)}
                </td>

                {/* Confidence */}
                <td className="py-4 px-4 text-center">
                  {getConfidenceBadge(tender.parse_confidence)}
                </td>

                {/* Issues */}
                <td className="py-4 px-4 text-center">
                  {tender.issues_count > 0 ? (
                    <span className="inline-flex items-center gap-1 bg-red-950/60 text-red-400 text-xs font-bold px-2 py-0.5 rounded border border-red-900/50">
                      <ShieldAlert className="h-3 w-3" />
                      <span>{tender.issues_count}</span>
                    </span>
                  ) : (
                    <span className="text-slate-600 text-xs">-</span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
};
