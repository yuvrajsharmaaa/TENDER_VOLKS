import { useState } from "react";
import type { FormEvent } from "react";
import {
  ArrowRight,
  Building2,
  Eye,
  EyeOff,
  LockKeyhole,
  Mail,
  UserRound,
} from "lucide-react";
import { login, register } from "../../services/auth";
import type { AuthUser } from "../../services/auth";

interface AuthScreenProps {
  onAuthenticated: (user: AuthUser) => void;
}

type Mode = "login" | "register";

const inputClass =
  "w-full rounded-lg border border-divider bg-input-bg px-3 py-2.5 text-sm " +
  "text-text-primary placeholder:text-text-disabled font-sans " +
  "focus:outline-none focus:border-success-green " +
  "focus:ring-1 focus:ring-success-green/30 transition-colors";

export default function AuthScreen({
  onAuthenticated,
}: AuthScreenProps) {
  const [mode, setMode] = useState<Mode>("login");

  const [fullName, setFullName] = useState("");
  const [companyName, setCompanyName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const isRegister = mode === "register";

  const switchMode = (nextMode: Mode) => {
    setMode(nextMode);
    setError("");
  };

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setLoading(true);

    try {
      const response = isRegister
        ? await register({
            full_name: fullName.trim(),
            company_name: companyName.trim(),
            email: email.trim(),
            password,
          })
        : await login({
            email: email.trim(),
            password,
          });

      onAuthenticated(response.user);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Unable to complete the request."
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-app-bg text-text-primary font-sans">
      <div className="min-h-screen flex items-center justify-center px-4 py-8 sm:px-6">
        <div className="w-full max-w-[1080px]">
          {/* Brand */}
          <div className="mb-6 flex items-center justify-center">
            <div className="flex items-center gap-2">
              <img
                src="/src/assets/logovolks.png"
                alt="Tender Volks"
                className="h-8 w-auto object-contain"
              />
              <span className="text-base font-semibold tracking-tight text-text-primary">
                Tender OCR
              </span>
            </div>
          </div>

          {/* Main card */}
          <div className="overflow-hidden rounded-2xl border border-divider bg-card-bg shadow-sm">
            <div className="grid lg:grid-cols-[1fr_460px]">
              {/* Product introduction */}
              <div className="hidden border-r border-divider bg-section-tint p-10 lg:flex lg:flex-col lg:justify-between">
                <div>
                  <div className="inline-flex items-center rounded-full border border-selected-green-border bg-selected-green-bg px-3 py-1.5 text-[10px] font-bold uppercase tracking-[0.12em] text-cta-green">
                    Tender intelligence platform
                  </div>

                  <h1 className="mt-6 max-w-xl text-4xl font-semibold leading-tight tracking-tight text-text-primary">
                    From tender discovery to verified bid compliance.
                  </h1>

                  <p className="mt-5 max-w-lg text-sm leading-6 text-text-secondary">
                    Manage tenders, bidder submissions, document extraction,
                    compliance verification and procurement review from one
                    workspace.
                  </p>
                </div>

                <div className="grid grid-cols-3 gap-3">
                  <InfoCard
                    title="OCR"
                    description="Document extraction"
                  />
                  <InfoCard
                    title="AI"
                    description="Evidence analysis"
                  />
                  <InfoCard
                    title="Audit"
                    description="Decision trail"
                  />
                </div>
              </div>

              {/* Auth panel */}
              <div className="p-6 sm:p-8 lg:p-10">
                <div className="mb-7">
                  <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-text-muted">
                    Secure workspace
                  </p>

                  <h2 className="mt-2 text-2xl font-semibold tracking-tight text-text-primary">
                    {isRegister
                      ? "Create company account"
                      : "Welcome back"}
                  </h2>

                  <p className="mt-1.5 text-xs leading-5 text-text-secondary">
                    {isRegister
                      ? "Register your company to participate in tenders."
                      : "Sign in to continue to your Tender Volks workspace."}
                  </p>
                </div>

                {/* Mode switch */}
                <div className="mb-6 grid grid-cols-2 rounded-lg border border-divider bg-section-tint p-1">
                  <button
                    type="button"
                    onClick={() => switchMode("login")}
                    className={`rounded-md px-3 py-2 text-xs font-semibold transition-colors ${
                      !isRegister
                        ? "bg-white text-text-primary shadow-sm border border-divider"
                        : "text-text-secondary hover:text-text-primary"
                    }`}
                  >
                    Sign in
                  </button>

                  <button
                    type="button"
                    onClick={() => switchMode("register")}
                    className={`rounded-md px-3 py-2 text-xs font-semibold transition-colors ${
                      isRegister
                        ? "bg-white text-text-primary shadow-sm border border-divider"
                        : "text-text-secondary hover:text-text-primary"
                    }`}
                  >
                    Create account
                  </button>
                </div>

                <form onSubmit={handleSubmit} className="space-y-4">
                  {isRegister && (
                    <>
                      <Field
                        label="Full name"
                        icon={<UserRound className="h-4 w-4" />}
                        value={fullName}
                        onChange={setFullName}
                        placeholder="Company administrator"
                      />

                      <Field
                        label="Company name"
                        icon={<Building2 className="h-4 w-4" />}
                        value={companyName}
                        onChange={setCompanyName}
                        placeholder="Registered company name"
                      />
                    </>
                  )}

                  <Field
                    label="Email"
                    icon={<Mail className="h-4 w-4" />}
                    value={email}
                    onChange={setEmail}
                    placeholder="you@company.com"
                    type="email"
                  />

                  <div>
                    <label className="mb-1.5 block text-xs font-semibold text-text-secondary">
                      Password
                    </label>

                    <div className="relative">
                      <LockKeyhole className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-text-muted" />

                      <input
                        type={showPassword ? "text" : "password"}
                        value={password}
                        onChange={(event) =>
                          setPassword(event.target.value)
                        }
                        required
                        minLength={8}
                        placeholder="Enter your password"
                        className={`${inputClass} pl-10 pr-10`}
                      />

                      <button
                        type="button"
                        onClick={() =>
                          setShowPassword((visible) => !visible)
                        }
                        className="absolute right-3 top-1/2 -translate-y-1/2 text-text-muted transition-colors hover:text-text-secondary"
                        aria-label={
                          showPassword
                            ? "Hide password"
                            : "Show password"
                        }
                      >
                        {showPassword ? (
                          <EyeOff className="h-4 w-4" />
                        ) : (
                          <Eye className="h-4 w-4" />
                        )}
                      </button>
                    </div>
                  </div>

                  {error && (
                    <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2.5 text-xs text-red-700">
                      {error}
                    </div>
                  )}

                  <button
                    type="submit"
                    disabled={loading}
                    className="flex w-full items-center justify-center gap-2 rounded-lg bg-cta-green px-4 py-2.5 text-xs font-bold text-white shadow-sm transition-colors hover:bg-success-green disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {loading
                      ? "Please wait..."
                      : isRegister
                        ? "Create account"
                        : "Sign in"}

                    {!loading && (
                      <ArrowRight className="h-3.5 w-3.5" />
                    )}
                  </button>
                </form>

                <div className="mt-6 border-t border-divider pt-4">
                  <p className="text-center text-[10px] leading-5 text-text-muted">
                    {isRegister
                      ? "Company users can self-register. Procurement officer accounts are provisioned by the administration."
                      : "Your account role and permissions are determined by the authenticated backend session."}
                  </p>
                </div>
              </div>
            </div>
          </div>

          <p className="mt-5 text-center text-[10px] text-text-muted">
            Tender Volks · Secure procurement workspace
          </p>
        </div>
      </div>
    </div>
  );
}

function Field({
  label,
  icon,
  value,
  onChange,
  placeholder,
  type = "text",
}: {
  label: string;
  icon: React.ReactNode;
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
  type?: string;
}) {
  return (
    <div>
      <label className="mb-1.5 block text-xs font-semibold text-text-secondary">
        {label}
      </label>

      <div className="relative">
        <div className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-text-muted">
          {icon}
        </div>

        <input
          type={type}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          required
          className={`${inputClass} pl-10`}
          placeholder={placeholder}
        />
      </div>
    </div>
  );
}

function InfoCard({
  title,
  description,
}: {
  title: string;
  description: string;
}) {
  return (
    <div className="rounded-xl border border-divider bg-white p-4 shadow-sm">
      <div className="text-sm font-semibold text-text-primary">
        {title}
      </div>
      <div className="mt-1 text-[10px] leading-4 text-text-muted">
        {description}
      </div>
    </div>
  );
}
