import { ArrowRight, Building2, ShieldCheck } from "lucide-react";

interface RoleSelectionProps {
  onSelect: (role: "bidder" | "officer") => void;
}

export function RoleSelection({ onSelect }: RoleSelectionProps) {
  return (
    <div className="min-h-screen w-full bg-[#0B0D0C] text-[#D3DAD5] flex items-center justify-center px-6 py-10">
      <div className="w-full max-w-5xl">
        <div className="mb-10">
          <div className="text-[10px] uppercase tracking-[0.22em] text-[#FFAA6E] font-semibold">
            TENDER VOLKS
          </div>

          <h1 className="text-4xl md:text-5xl font-semibold tracking-tight text-[#EEF2EF] mt-3">
            Procurement workspace
          </h1>

          <p className="text-sm md:text-base text-[#7E8983] mt-3 max-w-2xl">
            Choose how you want to enter the platform.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
          <button
            type="button"
            onClick={() => onSelect("bidder")}
            className="group text-left rounded-[22px] border border-[#29312D] bg-[#111513] p-7 hover:border-[#FFAA6E]/35 hover:bg-[#141916] transition-all duration-200"
          >
            <div className="flex items-start justify-between">
              <div className="h-12 w-12 rounded-[14px] bg-[rgba(255,170,110,.08)] border border-[rgba(255,170,110,.14)] flex items-center justify-center">
                <Building2 className="h-5 w-5 text-[#FFAA6E]" />
              </div>

              <ArrowRight className="h-4 w-4 text-[#59645E] group-hover:text-[#FFAA6E] transition-colors" />
            </div>

            <div className="mt-7">
              <div className="text-[10px] uppercase tracking-[0.18em] text-[#78847D] font-semibold">
                Company
              </div>

              <div className="text-2xl font-semibold text-[#EEF2EF] mt-2">
                Bidder Portal
              </div>

              <p className="text-sm text-[#78847D] leading-6 mt-3">
                Browse tenders, review requirements, submit bids and manage
                supporting documents.
              </p>
            </div>

            <div className="mt-7 text-xs text-[#A58A75]">
              Enter as bidder →
            </div>
          </button>

          <button
            type="button"
            onClick={() => onSelect("officer")}
            className="group text-left rounded-[22px] border border-[#29312D] bg-[#111513] p-7 hover:border-[#FFAA6E]/35 hover:bg-[#141916] transition-all duration-200"
          >
            <div className="flex items-start justify-between">
              <div className="h-12 w-12 rounded-[14px] bg-[rgba(255,170,110,.08)] border border-[rgba(255,170,110,.14)] flex items-center justify-center">
                <ShieldCheck className="h-5 w-5 text-[#FFAA6E]" />
              </div>

              <ArrowRight className="h-4 w-4 text-[#59645E] group-hover:text-[#FFAA6E] transition-colors" />
            </div>

            <div className="mt-7">
              <div className="text-[10px] uppercase tracking-[0.18em] text-[#78847D] font-semibold">
                Procurement
              </div>

              <div className="text-2xl font-semibold text-[#EEF2EF] mt-2">
                Officer Portal
              </div>

              <p className="text-sm text-[#78847D] leading-6 mt-3">
                Manage tenders, review bids, verify compliance, inspect risk
                and record procurement decisions.
              </p>
            </div>

            <div className="mt-7 text-xs text-[#A58A75]">
              Enter as officer →
            </div>
          </button>
        </div>

        <div className="mt-8 text-[10px] text-[#59645E]">
          Role-based access will later be backed by real authentication and
          permissions.
        </div>
      </div>
    </div>
  );
}
