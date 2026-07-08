import React from "react";

export const TenderCardSkeleton: React.FC = () => {
  return (
    <div className="bg-card-bg border border-divider/60 rounded-2xl p-6 shadow-[0_1px_3px_rgba(0,0,0,0.02),0_4px_12px_rgba(0,0,0,0.03)] flex flex-col gap-4 animate-pulse select-none">
      
      {/* Top Badges Row */}
      <div className="flex items-center gap-2">
        <div className="h-5 w-16 bg-section-tint rounded-full"></div>
        <div className="h-5 w-20 bg-section-tint rounded-full"></div>
        <div className="h-5 w-24 bg-section-tint rounded-full"></div>
      </div>

      {/* Main Title & Reference Code */}
      <div className="space-y-2">
        <div className="h-5 bg-section-tint rounded-md w-11/12"></div>
        <div className="h-5 bg-section-tint rounded-md w-3/4"></div>
        <div className="h-3 bg-section-tint rounded w-1/3 mt-2"></div>
      </div>

      {/* Meta Icons Row */}
      <div className="flex flex-wrap items-center gap-y-2 gap-x-4 border-b border-divider/30 pb-3">
        <div className="h-4 w-28 bg-section-tint rounded"></div>
        <div className="h-4 w-20 bg-section-tint rounded"></div>
        <div className="h-4 w-24 bg-section-tint rounded"></div>
      </div>

      {/* Financials & Documents row */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div className="h-6 w-20 bg-section-tint rounded-lg"></div>
          <div className="h-6 w-20 bg-section-tint rounded-lg"></div>
          <div className="h-4 w-12 bg-section-tint rounded"></div>
        </div>
      </div>

      {/* Footer updated & View link */}
      <div className="border-t border-divider/40 pt-3.5 flex items-center justify-between mt-auto">
        <div className="h-3 w-20 bg-section-tint rounded"></div>
        <div className="h-4 w-16 bg-section-tint rounded"></div>
      </div>

    </div>
  );
};
export default TenderCardSkeleton;
