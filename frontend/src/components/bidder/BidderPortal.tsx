import { useEffect, useState } from "react";
import {
  ArrowLeft,
  ArrowRight,
  Building2,
  CalendarDays,
  MapPin,
  RefreshCw,
} from "lucide-react";
import { apiService } from "../../services/api";
import type { TenderDetail } from "../../types/tender";

interface BidderPortalProps {
  onExit: () => void;
}

export default function BidderPortal({ onExit }: BidderPortalProps) {
  const [tenders, setTenders] = useState<TenderDetail[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedTender, setSelectedTender] = useState<TenderDetail | null>(
    null
  );

  const fetchTenders = async () => {
    setLoading(true);

    try {
      const data = await apiService.getTenders();
      setTenders(data);
    } catch (error) {
      console.error("Failed to load tenders:", error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTenders();
  }, []);

  return (
    <div className="h-screen w-full overflow-hidden bg-[#0B0D0C] text-[#D3DAD5]">
      <header className="h-[72px] border-b border-[#202723] bg-[#0D100F] flex items-center justify-between px-5 lg:px-8">
        <div className="flex items-center gap-3">
          <div className="h-9 w-9 rounded-[11px] bg-[rgba(255,170,110,.08)] border border-[rgba(255,170,110,.14)] flex items-center justify-center">
            <Building2 className="h-4 w-4 text-[#FFAA6E]" />
          </div>

          <div>
            <div className="text-[9px] uppercase tracking-[0.2em] text-[#FFAA6E] font-semibold">
              TENDER VOLKS
            </div>
            <div className="text-sm font-semibold text-[#E7ECE8]">
              Bidder Portal
            </div>
          </div>
        </div>

        <button
          type="button"
          onClick={onExit}
          className="flex items-center gap-2 rounded-[9px] border border-[#303934] bg-[#141916] px-3 py-2 text-[10px] font-semibold text-[#A1AAA5] hover:text-[#EEF2EF]"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          Switch portal
        </button>
      </header>

      <main className="h-[calc(100vh-72px)] overflow-y-auto px-5 py-7 lg:px-8">
        <div className="max-w-[1380px] mx-auto">
          {!selectedTender ? (
            <>
              <div className="flex items-end justify-between gap-5">
                <div>
                  <div className="text-[10px] uppercase tracking-[0.2em] text-[#FFAA6E] font-semibold">
                    Company workspace
                  </div>

                  <h1 className="text-3xl md:text-4xl font-semibold text-[#EEF2EF] mt-2">
                    Find opportunities
                  </h1>

                  <p className="text-sm text-[#78847D] mt-3 max-w-2xl">
                    Review procurement opportunities and prepare your bid
                    submission.
                  </p>
                </div>

                <button
                  type="button"
                  onClick={fetchTenders}
                  disabled={loading}
                  className="hidden sm:flex items-center gap-2 rounded-[9px] border border-[#303934] bg-[#141916] px-3 py-2 text-[10px] font-semibold text-[#A1AAA5]"
                >
                  <RefreshCw
                    className={`h-3.5 w-3.5 ${
                      loading ? "animate-spin" : ""
                    }`}
                  />
                  Refresh
                </button>
              </div>

              {loading ? (
                <div className="mt-8 text-sm text-[#68746D]">
                  Loading opportunities…
                </div>
              ) : tenders.length === 0 ? (
                <div className="mt-8 rounded-[18px] border border-dashed border-[#303934] bg-[#111513] p-12 text-center">
                  <div className="text-sm font-semibold text-[#D3DAD5]">
                    No opportunities available
                  </div>
                </div>
              ) : (
                <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-4 mt-8">
                  {tenders.map((tender) => (
                    <div
                      key={tender.id}
                      className="rounded-[18px] border border-[#29312D] bg-[#111513] p-5 hover:border-[#FFAA6E]/25 transition-colors"
                    >
                      <div className="text-[9px] uppercase tracking-[0.16em] text-[#78847D]">
                        {tender.review_status === "completed"
                          ? "Reviewed"
                          : "Open"}
                      </div>

                      <div className="text-base font-semibold text-[#E7ECE8] mt-2 leading-6">
                        {tender.title}
                      </div>

                      <div className="text-xs text-[#78847D] mt-2">
                        {tender.authorityName || "Procurement authority"}
                      </div>

                      <div className="grid grid-cols-2 gap-3 mt-5">
                        <div>
                          <div className="text-[9px] uppercase tracking-[0.12em] text-[#59645E]">
                            Value
                          </div>
                          <div className="text-xs text-[#C7CEC9] mt-1">
                            {tender.tenderValue || "—"}
                          </div>
                        </div>

                        <div>
                          <div className="text-[9px] uppercase tracking-[0.12em] text-[#59645E]">
                            Deadline
                          </div>
                          <div className="text-xs text-[#C7CEC9] mt-1">
                            {tender.deadline
                              ? new Date(
                                  tender.deadline
                                ).toLocaleDateString()
                              : "—"}
                          </div>
                        </div>
                      </div>

                      <div className="flex items-center gap-2 mt-4 text-[10px] text-[#68746D]">
                        <MapPin className="h-3 w-3" />
                        {tender.location || "Location not specified"}
                      </div>

                      <button
                        type="button"
                        onClick={() => setSelectedTender(tender)}
                        className="w-full mt-5 flex items-center justify-center gap-2 rounded-[9px] bg-[#FFAA6E] px-3 py-2.5 text-[10px] font-bold text-[#1A120D]"
                      >
                        View tender
                        <ArrowRight className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </>
          ) : (
            <div className="max-w-4xl">
              <button
                type="button"
                onClick={() => setSelectedTender(null)}
                className="flex items-center gap-2 text-[10px] font-semibold text-[#78847D] hover:text-[#EEF2EF]"
              >
                <ArrowLeft className="h-3.5 w-3.5" />
                Back to opportunities
              </button>

              <div className="mt-6 rounded-[22px] border border-[#29312D] bg-[#111513] p-6 lg:p-8">
                <div className="text-[9px] uppercase tracking-[0.18em] text-[#FFAA6E] font-semibold">
                  Tender details
                </div>

                <h1 className="text-2xl md:text-3xl font-semibold text-[#EEF2EF] mt-3">
                  {selectedTender.title}
                </h1>

                <div className="text-sm text-[#78847D] mt-2">
                  {selectedTender.authorityName || "Procurement authority"}
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-7">
                  <div className="rounded-[14px] border border-[#252D28] bg-[#0D100F] p-4">
                    <div className="text-[9px] uppercase tracking-[0.12em] text-[#59645E]">
                      Tender value
                    </div>
                    <div className="text-sm font-semibold text-[#D3DAD5] mt-2">
                      {selectedTender.tenderValue || "—"}
                    </div>
                  </div>

                  <div className="rounded-[14px] border border-[#252D28] bg-[#0D100F] p-4">
                    <div className="text-[9px] uppercase tracking-[0.12em] text-[#59645E]">
                      Location
                    </div>
                    <div className="flex items-center gap-2 text-sm font-semibold text-[#D3DAD5] mt-2">
                      <MapPin className="h-3.5 w-3.5 text-[#FFAA6E]" />
                      {selectedTender.location || "—"}
                    </div>
                  </div>

                  <div className="rounded-[14px] border border-[#252D28] bg-[#0D100F] p-4">
                    <div className="text-[9px] uppercase tracking-[0.12em] text-[#59645E]">
                      Deadline
                    </div>
                    <div className="flex items-center gap-2 text-sm font-semibold text-[#D3DAD5] mt-2">
                      <CalendarDays className="h-3.5 w-3.5 text-[#FFAA6E]" />
                      {selectedTender.deadline
                        ? new Date(
                            selectedTender.deadline
                          ).toLocaleDateString()
                        : "Not specified"}
                    </div>
                  </div>
                </div>

                <div className="mt-8 rounded-[16px] border border-[rgba(255,170,110,.12)] bg-[rgba(255,170,110,.035)] p-5">
                  <div className="text-sm font-semibold text-[#E7ECE8]">
                    Bid submission
                  </div>

                  <p className="text-xs text-[#78847D] mt-2 leading-5">
                    The bid submission workflow will be connected here next.
                    This will include company details, tender requirements,
                    document uploads, OCR processing and final submission.
                  </p>

                  <button
                    type="button"
                    disabled
                    className="mt-5 rounded-[9px] border border-[#38423C] bg-[#171D19] px-4 py-2.5 text-[10px] font-semibold text-[#68746D] cursor-not-allowed"
                  >
                    Start bid — coming next
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
