import React, { useState, useEffect } from "react";
import { Eye, EyeOff, CheckCircle2, XCircle, AlertCircle, Loader2, ArrowRight, KeyRound } from "lucide-react";
import { verifyResetToken, completePasswordReset, TokenVerificationData } from "../services/api";

interface ResetPasswordPageProps {
  onSuccess?: () => void;
}

export function ResetPasswordPage({ onSuccess }: ResetPasswordPageProps) {
  const [token, setToken] = useState<string | null>(null);
  const [verifying, setVerifying] = useState(true);
  const [verifyError, setVerifyError] = useState<string | null>(null);
  const [employeeInfo, setEmployeeInfo] = useState<TokenVerificationData | null>(null);

  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);

  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [countdown, setCountdown] = useState(3);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const tok = params.get("token");
    if (!tok) {
      setVerifying(false);
      setVerifyError("No password reset token found. Please use the link sent to your official email.");
      return;
    }
    setToken(tok);

    verifyResetToken(tok)
      .then((info) => {
        setEmployeeInfo(info);
        setVerifying(false);
      })
      .catch((err: any) => {
        setVerifyError(err?.message || "This password reset link is invalid or has expired. Please request a new reset link from your administrator.");
        setVerifying(false);
      });
  }, []);

  // Password validation rules
  const hasMinLen = password.length >= 8;
  const hasUpper = /[A-Z]/.test(password);
  const hasLower = /[a-z]/.test(password);
  const hasDigit = /\d/.test(password);
  const hasSpecial = /[^A-Za-z0-9]/.test(password);
  const passwordsMatch = password.length > 0 && password === confirmPassword;

  const isValid = hasMinLen && hasUpper && hasLower && hasDigit && hasSpecial && passwordsMatch;

  const handleReset = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token || !isValid) return;

    setSubmitting(true);
    setSubmitError(null);

    try {
      await completePasswordReset(token, password);
      setSuccess(true);
      let count = 3;
      const interval = setInterval(() => {
        count -= 1;
        setCountdown(count);
        if (count <= 0) {
          clearInterval(interval);
          if (onSuccess) {
            onSuccess();
          } else {
            window.location.href = "/";
          }
        }
      }, 1000);
    } catch (err: any) {
      setSubmitError(err?.message || "Failed to reset password. Please try again.");
    } finally {
      setSubmitting(false);
    }
  };

  const navigateToLogin = () => {
    if (onSuccess) {
      onSuccess();
    } else {
      window.location.href = "/";
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

      <div className="relative w-full max-w-md">
        <div className="bg-slate-900/90 border border-slate-700/60 rounded-2xl p-8 shadow-2xl shadow-black/50 space-y-6 backdrop-blur-sm">
          {/* Header */}
          <div className="flex flex-col items-center text-center space-y-2">
            <div className="w-14 h-14 rounded-2xl bg-cyan-500/10 border border-cyan-500/30 flex items-center justify-center shadow-lg mb-1">
              <span className="material-symbols-outlined text-[32px] text-cyan-400">lock_reset</span>
            </div>
            <h1 className="text-2xl font-bold tracking-tight text-white">OILTRACE</h1>
            <p className="text-[11px] text-slate-400 font-mono tracking-widest uppercase">
              Secure Password Reset
            </p>
            <div className="w-16 h-px bg-slate-700 mt-1" />
            <p className="text-[11px] text-slate-500 font-mono">
              Coast Authority Security Operations
            </p>
          </div>

          {/* Verifying Spinner */}
          {verifying && (
            <div className="flex flex-col items-center justify-center py-10 space-y-3">
              <Loader2 className="w-8 h-8 text-cyan-400 animate-spin" />
              <p className="text-xs font-mono text-slate-400">Verifying reset token...</p>
            </div>
          )}

          {/* Verification Error */}
          {!verifying && verifyError && (
            <div className="space-y-5">
              <div className="flex items-start gap-3 p-4 rounded-xl bg-red-950/40 border border-red-800/50 text-red-200">
                <XCircle className="w-5 h-5 text-red-400 mt-0.5 flex-shrink-0" />
                <div className="text-xs font-mono space-y-1">
                  <p className="font-semibold text-red-300">Reset Link Invalid or Expired</p>
                  <p className="text-slate-400 text-[11px]">{verifyError}</p>
                </div>
              </div>
              <p className="text-xs text-slate-400 font-sans text-center">
                Please contact your Tech Administrator to request a new password reset link.
              </p>
              <button
                type="button"
                onClick={navigateToLogin}
                className="w-full py-2.5 px-4 bg-slate-800 hover:bg-slate-700 border border-slate-700 rounded-lg text-xs font-mono text-slate-300 transition-colors cursor-pointer"
              >
                Return to Sign In
              </button>
            </div>
          )}

          {/* Success Screen */}
          {!verifying && success && (
            <div className="space-y-6 text-center py-4">
              <div className="w-12 h-12 mx-auto rounded-full bg-emerald-500/20 border border-emerald-500/40 flex items-center justify-center text-emerald-400">
                <CheckCircle2 className="w-6 h-6" />
              </div>
              <div className="space-y-2">
                <h2 className="text-lg font-bold text-white">Password Reset Successfully!</h2>
                <p className="text-xs text-slate-300 font-sans">
                  Your password has been updated. You may now log in with your new credentials.
                </p>
                <p className="text-[11px] font-mono text-slate-500">
                  Redirecting to Sign In in {countdown} second{countdown !== 1 ? "s" : ""}...
                </p>
              </div>
              <button
                type="button"
                onClick={navigateToLogin}
                className="w-full py-2.5 px-4 bg-cyan-600 hover:bg-cyan-500 rounded-lg text-xs font-mono text-white flex items-center justify-center gap-2 font-semibold transition-colors cursor-pointer"
              >
                <span>Sign In Now</span>
                <ArrowRight className="w-4 h-4" />
              </button>
            </div>
          )}

          {/* Reset Form */}
          {!verifying && !verifyError && !success && employeeInfo && (
            <form onSubmit={handleReset} className="space-y-5">
              {/* Identity Details Card */}
              <div className="bg-slate-950/60 border border-slate-800 rounded-xl p-3.5 space-y-2 text-xs font-mono">
                <div className="flex items-center justify-between pb-2 border-b border-slate-800/80">
                  <span className="text-[10px] text-slate-500 tracking-wider uppercase font-semibold">
                    Account Identity
                  </span>
                  <span className="px-2 py-0.5 rounded text-[10px] bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">
                    {employeeInfo.role}
                  </span>
                </div>
                <div className="grid grid-cols-2 gap-2 text-[11px]">
                  <div>
                    <span className="text-slate-500 block text-[10px]">EMPLOYEE ID</span>
                    <span className="text-slate-200 font-semibold">{employeeInfo.employee_id}</span>
                  </div>
                  <div>
                    <span className="text-slate-500 block text-[10px]">NAME</span>
                    <span className="text-slate-200 font-semibold">{employeeInfo.full_name}</span>
                  </div>
                  <div className="col-span-2">
                    <span className="text-slate-500 block text-[10px]">OFFICIAL EMAIL</span>
                    <span className="text-slate-200">{employeeInfo.official_email}</span>
                  </div>
                </div>
              </div>

              {submitError && (
                <div className="flex items-start gap-2 p-3 rounded-lg bg-red-950/30 border border-red-800/40 text-red-300 text-xs font-mono">
                  <AlertCircle className="w-4 h-4 mt-0.5 flex-shrink-0" />
                  <span>{submitError}</span>
                </div>
              )}

              {/* Password Fields */}
              <div className="space-y-3">
                <div>
                  <label className="block text-[11px] text-slate-400 font-mono mb-1 tracking-wider uppercase">
                    New Password
                  </label>
                  <div className="relative">
                    <input
                      type={showPassword ? "text" : "password"}
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      required
                      placeholder="••••••••••••"
                      className="w-full px-3 py-2 bg-slate-950/80 border border-slate-700 rounded-lg text-xs font-mono text-slate-100 placeholder-slate-600 focus:outline-none focus:border-cyan-500/70 focus:ring-1 focus:ring-cyan-500/50 pr-10"
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword(!showPassword)}
                      className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300 cursor-pointer"
                    >
                      {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                    </button>
                  </div>
                </div>

                <div>
                  <label className="block text-[11px] text-slate-400 font-mono mb-1 tracking-wider uppercase">
                    Confirm Password
                  </label>
                  <div className="relative">
                    <input
                      type={showConfirmPassword ? "text" : "password"}
                      value={confirmPassword}
                      onChange={(e) => setConfirmPassword(e.target.value)}
                      required
                      placeholder="••••••••••••"
                      className="w-full px-3 py-2 bg-slate-950/80 border border-slate-700 rounded-lg text-xs font-mono text-slate-100 placeholder-slate-600 focus:outline-none focus:border-cyan-500/70 focus:ring-1 focus:ring-cyan-500/50 pr-10"
                    />
                    <button
                      type="button"
                      onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                      className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300 cursor-pointer"
                    >
                      {showConfirmPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                    </button>
                  </div>
                </div>
              </div>

              {/* Password Checklist */}
              <div className="bg-slate-950/40 border border-slate-800/80 rounded-lg p-3 space-y-1.5 text-[11px] font-mono">
                <p className="text-[10px] text-slate-500 uppercase tracking-wider mb-1 font-semibold">
                  Password Requirements
                </p>
                <div className="grid grid-cols-2 gap-1.5">
                  <div className={`flex items-center gap-1.5 ${hasMinLen ? "text-emerald-400" : "text-slate-500"}`}>
                    {hasMinLen ? <CheckCircle2 className="w-3.5 h-3.5" /> : <div className="w-3.5 h-3.5 rounded-full border border-slate-600" />}
                    <span>At least 8 chars</span>
                  </div>
                  <div className={`flex items-center gap-1.5 ${hasUpper ? "text-emerald-400" : "text-slate-500"}`}>
                    {hasUpper ? <CheckCircle2 className="w-3.5 h-3.5" /> : <div className="w-3.5 h-3.5 rounded-full border border-slate-600" />}
                    <span>1 uppercase letter</span>
                  </div>
                  <div className={`flex items-center gap-1.5 ${hasLower ? "text-emerald-400" : "text-slate-500"}`}>
                    {hasLower ? <CheckCircle2 className="w-3.5 h-3.5" /> : <div className="w-3.5 h-3.5 rounded-full border border-slate-600" />}
                    <span>1 lowercase letter</span>
                  </div>
                  <div className={`flex items-center gap-1.5 ${hasDigit ? "text-emerald-400" : "text-slate-500"}`}>
                    {hasDigit ? <CheckCircle2 className="w-3.5 h-3.5" /> : <div className="w-3.5 h-3.5 rounded-full border border-slate-600" />}
                    <span>1 numeric digit</span>
                  </div>
                  <div className={`flex items-center gap-1.5 ${hasSpecial ? "text-emerald-400" : "text-slate-500"}`}>
                    {hasSpecial ? <CheckCircle2 className="w-3.5 h-3.5" /> : <div className="w-3.5 h-3.5 rounded-full border border-slate-600" />}
                    <span>1 special symbol</span>
                  </div>
                  <div className={`flex items-center gap-1.5 ${passwordsMatch ? "text-emerald-400" : "text-slate-500"}`}>
                    {passwordsMatch ? <CheckCircle2 className="w-3.5 h-3.5" /> : <div className="w-3.5 h-3.5 rounded-full border border-slate-600" />}
                    <span>Passwords match</span>
                  </div>
                </div>
              </div>

              {/* Submit */}
              <button
                type="submit"
                disabled={!isValid || submitting}
                className={`w-full py-2.5 px-4 rounded-lg text-xs font-mono font-semibold flex items-center justify-center gap-2 transition-all shadow-lg ${
                  isValid && !submitting
                    ? "bg-cyan-600 hover:bg-cyan-500 text-white shadow-cyan-900/40 cursor-pointer"
                    : "bg-slate-800 text-slate-500 border border-slate-700 cursor-not-allowed"
                }`}
              >
                {submitting ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    <span>Resetting Password...</span>
                  </>
                ) : (
                  <>
                    <KeyRound className="w-4 h-4" />
                    <span>RESET PASSWORD</span>
                  </>
                )}
              </button>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}
