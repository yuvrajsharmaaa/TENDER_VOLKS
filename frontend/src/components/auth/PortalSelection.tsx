import logo from "../../assets/logovolks.png";

export type PortalType = "BIDDER" | "OFFICER";

interface PortalSelectionProps {
  onSelect: (portal: PortalType) => void;
}

export default function PortalSelection({
  onSelect,
}: PortalSelectionProps) {
  return (
    <div className="min-h-screen bg-app-bg text-text-primary flex items-center justify-center px-4 py-8">
      <div className="w-full max-w-2xl">

        {/* Brand */}
        <div className="flex flex-col items-center mb-8">
          <img
            src={logo}
            alt="TENDER VOLKS"
            className="h-12 w-auto object-contain"
          />

          <p className="mt-3 text-sm text-text-secondary">
            AI-powered tender compliance intelligence
          </p>
        </div>

        {/* Card */}
        <div className="bg-card-bg border border-divider rounded-2xl shadow-sm p-6 sm:p-8">

          <div className="text-center mb-7">
            <h1 className="text-xl font-semibold text-text-primary">
              Choose your portal
            </h1>

            <p className="mt-2 text-sm text-text-secondary">
              Select the workspace you want to access.
            </p>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">

            {/* Bidder */}
            <button
              type="button"
              onClick={() => onSelect("BIDDER")}
              className="
                group
                text-left
                rounded-xl
                border
                border-divider
                bg-section-tint
                p-5
                transition-all
                hover:border-selected-green-border
                hover:bg-selected-green-bg
              "
            >
              <div className="flex items-start justify-between">
                <div>
                  <div className="text-sm font-semibold text-text-primary">
                    Bidder Portal
                  </div>

                  <div className="mt-1 text-xs text-text-muted">
                    For suppliers and bidding companies
                  </div>
                </div>

                <div className="
                  flex
                  h-9
                  w-9
                  items-center
                  justify-center
                  rounded-lg
                  bg-selected-green-bg
                  border
                  border-selected-green-border
                  text-success-green
                ">
                  →
                </div>
              </div>

              <div className="mt-5 space-y-2">
                <div className="text-xs text-text-secondary">
                  • Discover procurement opportunities
                </div>

                <div className="text-xs text-text-secondary">
                  • Submit bid documents
                </div>

                <div className="text-xs text-text-secondary">
                  • Track compliance and verification
                </div>
              </div>

              <div className="
                mt-5
                text-xs
                font-medium
                text-success-green
                group-hover:underline
              ">
                Continue as Bidder →
              </div>
            </button>

            {/* Officer */}
            <button
              type="button"
              onClick={() => onSelect("OFFICER")}
              className="
                group
                text-left
                rounded-xl
                border
                border-divider
                bg-section-tint
                p-5
                transition-all
                hover:border-selected-green-border
                hover:bg-selected-green-bg
              "
            >
              <div className="flex items-start justify-between">
                <div>
                  <div className="text-sm font-semibold text-text-primary">
                    Officer Portal
                  </div>

                  <div className="mt-1 text-xs text-text-muted">
                    For procurement officers
                  </div>
                </div>

                <div className="
                  flex
                  h-9
                  w-9
                  items-center
                  justify-center
                  rounded-lg
                  bg-selected-green-bg
                  border
                  border-selected-green-border
                  text-success-green
                ">
                  →
                </div>
              </div>

              <div className="mt-5 space-y-2">
                <div className="text-xs text-text-secondary">
                  • Review bidder submissions
                </div>

                <div className="text-xs text-text-secondary">
                  • Verify compliance and risk
                </div>

                <div className="text-xs text-text-secondary">
                  • Make procurement decisions
                </div>
              </div>

              <div className="
                mt-5
                text-xs
                font-medium
                text-success-green
                group-hover:underline
              ">
                Continue as Officer →
              </div>
            </button>

          </div>

          <div className="mt-6 border-t border-divider pt-5 text-center">
            <p className="text-xs text-text-muted">
              Your account permissions determine which portal you can access.
            </p>
          </div>

        </div>

        <div className="mt-5 text-center">
          <p className="text-xs text-text-muted">
            TENDER VOLKS • Secure procurement intelligence
          </p>
        </div>

      </div>
    </div>
  );
}
