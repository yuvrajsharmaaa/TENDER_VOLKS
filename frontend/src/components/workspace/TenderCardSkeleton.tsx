import React from "react";

export const TenderCardSkeleton: React.FC = () => (
  <div
    aria-busy="true"
    aria-label="Loading tender"
    className="bg-card-bg border border-divider/60 rounded-2xl p-5 flex flex-col gap-3.5
      shadow-[0_1px_3px_rgba(0,0,0,0.02),0_4px_12px_rgba(0,0,0,0.03)]
      animate-pulse select-none"
  >
    {/* Badges row — mirrors TenderCard badges */}
    <div className="flex items-center gap-1.5">
      <div className="h-5 w-14 bg-section-tint rounded" />
      <div className="h-5 w-16 bg-section-tint rounded" />
      <div className="h-5 w-16 bg-section-tint rounded" />
    </div>

    {/* Title + reference */}
    <div className="space-y-1.5">
      <div className="h-4 bg-section-tint rounded w-11/12" />
      <div className="h-4 bg-section-tint rounded w-3/4" />
      <div className="h-3 bg-section-tint rounded w-1/3 mt-1" />
    </div>

    {/* Meta row */}
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 border-b border-divider/30 pb-3">
      <div className="h-3.5 w-28 bg-section-tint rounded" />
      <div className="h-3.5 w-20 bg-section-tint rounded" />
      <div className="h-3.5 w-24 bg-section-tint rounded" />
    </div>

    {/* Financials row */}
    <div className="flex items-center gap-2">
      <div className="h-6 w-24 bg-section-tint rounded-lg" />
      <div className="h-6 w-20 bg-section-tint rounded-lg" />
      <div className="h-3.5 w-12 bg-section-tint rounded ml-auto" />
    </div>

    {/* Footer */}
    <div className="border-t border-divider/40 pt-3 flex items-center justify-between">
      <div className="h-3 w-16 bg-section-tint rounded" />
      <div className="h-3.5 w-20 bg-section-tint rounded" />
    </div>
  </div>
);

export default TenderCardSkeleton;
