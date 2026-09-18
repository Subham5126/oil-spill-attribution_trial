import React, { useState } from "react";
import { Eye, EyeOff, ArrowRight, AlertCircle, Loader2 } from "lucide-react";
import { useAuth } from "../hooks/useAuth";

interface LoginPageProps {
  onLoginSuccess: () => void;
}

export function LoginPage({ onLoginSuccess }: LoginPageProps) {
  const { login } = useAuth();
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lockoutMessage, setLockoutMessage] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLockoutMessage(null);

    if (!identifier.trim() || !password) {
      setError("Please enter your identifier and password.");
      return;
    }

    setIsLoading(true);
    try {
      await login(identifier.trim(), password);
      onLoginSuccess();
    } catch (err: any) {
      const status = err?.status ?? 0;
      const msg: string = err?.message ?? "An unexpected error occurred.";

      if (status === 429) {
        // Brute-force lockout — extract timing from the message
        setLockoutMessage(msg);
      } else if (status === 401) {
        setError("Invalid credentials. Check your identifier and password.");
      } else if (status === 0 || status >= 500) {
        setError("Unable to reach the authentication server. Please try again.");
      } else {
        setError(msg);
      }
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen w-full bg-[#070f1a] text-slate-100 flex items-center justify-center p-4 font-sans">
      {/* Background grid lines */}
      <div
        className="fixed inset-0 pointer-events-none opacity-[0.03]"
        style={{
          backgroundImage:
            "linear-gradient(0deg, transparent 24%, rgba(100,200,255,1) 25%, rgba(100,200,255,1) 26%, transparent 27%), linear-gradient(90deg, transparent 24%, rgba(100,200,255,1) 25%, rgba(100,200,255,1) 26%, transparent 27%)",
          backgroundSize: "40px 40px",
        }}
      />

      <div className="relative w-full max-w-sm">
        {/* Card */}
        <div className="bg-slate-900/90 border border-slate-700/60 rounded-2xl p-8 shadow-2xl shadow-black/50 space-y-7 backdrop-blur-sm">
          {/* Header */}
          <div className="flex flex-col items-center text-center space-y-2">
            <div className="w-14 h-14 rounded-2xl bg-cyan-500/10 border border-cyan-500/30 flex items-center justify-center shadow-lg mb-1">
              <span className="material-symbols-outlined text-[32px] text-cyan-400">radar</span>
            </div>
            <h1 className="text-2xl font-bold tracking-tight text-white">OILTRACE</h1>
            <p className="text-[11px] text-slate-400 font-mono tracking-widest uppercase">
              Marine Oil Spill Attribution System
            </p>
            <div className="w-16 h-px bg-slate-700 mt-1" />
            <p className="text-[11px] text-slate-500 font-mono">
              Coast Authority Internal Access
            </p>
          </div>

          {/* Error / Lockout banners */}
          {(error || lockoutMessage) && (
            <div
              className={`flex items-start gap-2 px-3 py-2.5 rounded-lg text-xs font-mono ${
                lockoutMessage
                  ? "bg-amber-900/30 border border-amber-700/40 text-amber-300"
                  : "bg-red-900/30 border border-red-700/40 text-red-300"
              }`}
            >
              <AlertCircle className="w-4 h-4 mt-0.5 flex-shrink-0" />
              <span>{lockoutMessage ?? error}</span>
            </div>
          )}

          {/* Form */}
          <form onSubmit={handleSubmit} className="space-y-4">
            {/* Identifier */}
            <div>
              <label className="block text-[11px] text-slate-400 font-mono mb-1.5 tracking-wider uppercase">
                Identifier
              </label>
              <input
                type="text"
                value={identifier}
                onChange={(e) => { setIdentifier(e.target.value); setError(null); setLockoutMessage(null); }}
                placeholder="Official email or Employee ID"
                autoComplete="username"
                autoFocus
                disabled={isLoading}
                className="w-full px-3 py-2.5 rounded-lg bg-slate-950 border border-slate-700 text-slate-200 placeholder-slate-600 text-sm font-mono focus:outline-none focus:ring-1 focus:ring-cyan-500/60 focus:border-cyan-500/60 transition-colors disabled:opacity-50"
              />
            </div>

            {/* Password */}
            <div>
              <label className="block text-[11px] text-slate-400 font-mono mb-1.5 tracking-wider uppercase">
                Password
              </label>
              <div className="relative">
                <input
                  type={showPassword ? "text" : "password"}
                  value={password}
                  onChange={(e) => { setPassword(e.target.value); setError(null); setLockoutMessage(null); }}
                  placeholder="••••••••••••"
                  autoComplete="current-password"
                  disabled={isLoading}
                  className="w-full px-3 py-2.5 pr-10 rounded-lg bg-slate-950 border border-slate-700 text-slate-200 placeholder-slate-600 text-sm font-mono focus:outline-none focus:ring-1 focus:ring-cyan-500/60 focus:border-cyan-500/60 transition-colors disabled:opacity-50"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((v) => !v)}
                  tabIndex={-1}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300 transition-colors"
                  aria-label={showPassword ? "Hide password" : "Show password"}
                >
                  {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
              <p className="text-[10px] text-slate-600 font-mono mt-1.5">
                Use your official org email or Employee ID
              </p>
            </div>

            {/* Submit */}
            <button
              type="submit"
              disabled={isLoading || !identifier.trim() || !password}
              className="w-full py-2.5 rounded-lg bg-cyan-600 hover:bg-cyan-500 disabled:opacity-40 disabled:cursor-not-allowed text-white font-bold text-sm flex items-center justify-center gap-2 transition-colors mt-1 shadow-lg shadow-cyan-900/30"
            >
              {isLoading ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span>Authenticating…</span>
                </>
              ) : (
                <>
                  <span>SIGN IN</span>
                  <ArrowRight className="w-4 h-4" />
                </>
              )}
            </button>
          </form>

          {/* Footer */}
          <div className="text-[10px] text-center text-slate-600 font-mono pt-1 border-t border-slate-800">
            Authorized Coast Guard &amp; Port State Control Personnel Only
            <br />
            Unauthorized access is a criminal offence.
          </div>
        </div>

        {/* Classification badge */}
        <p className="text-center text-[10px] text-slate-700 font-mono mt-4 tracking-widest">
          OFFICIAL — NOT FOR PUBLIC RELEASE
        </p>
      </div>
    </div>
  );
}
