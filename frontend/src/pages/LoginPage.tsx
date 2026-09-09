import React, { useState } from "react";
import { Shield, Key, ArrowRight } from "lucide-react";

interface LoginPageProps {
  onLoginSuccess: () => void;
}

export function LoginPage({ onLoginSuccess }: LoginPageProps) {
  const [username, setUsername] = useState("analyst@maritime-gov.in");
  const [password, setPassword] = useState("••••••••••••");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onLoginSuccess();
  };

  return (
    <div className="min-h-screen w-full bg-[#0b1c30] text-slate-100 flex items-center justify-center p-4 font-sans">
      <div className="w-full max-w-md bg-slate-900 border border-slate-800 rounded-2xl p-8 shadow-2xl space-y-6">
        <div className="flex flex-col items-center text-center space-y-2">
          <div className="w-12 h-12 rounded-2xl bg-primary-container text-on-primary flex items-center justify-center shadow-lg shadow-primary-container/30 mb-2">
            <span className="material-symbols-outlined text-[28px]">radar</span>
          </div>
          <h1 className="text-2xl font-bold tracking-tight">OILTRACE GIS</h1>
          <p className="text-xs text-slate-400 font-mono">
            Operational Marine Oil Spill Attribution &amp; Enforcement Node
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4 text-xs font-mono">
          <div>
            <label className="block text-slate-300 mb-1">Analyst Identifier / Email</label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full p-2.5 rounded-lg bg-slate-950 border border-slate-800 text-slate-200 focus:outline-none focus:ring-1 focus:ring-primary"
            />
          </div>

          <div>
            <label className="block text-slate-300 mb-1">Passkey / Token</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full p-2.5 rounded-lg bg-slate-950 border border-slate-800 text-slate-200 focus:outline-none focus:ring-1 focus:ring-primary"
            />
          </div>

          <button
            type="submit"
            className="w-full py-3 rounded-lg bg-primary-container text-on-primary hover:bg-primary transition-colors font-bold text-xs flex items-center justify-center gap-2 shadow-md cursor-pointer mt-2"
          >
            <span>Authenticate Session</span>
            <ArrowRight className="w-4 h-4" />
          </button>
        </form>

        <div className="text-[11px] text-center text-slate-500 font-mono pt-2 border-t border-slate-800">
          Authorized Coast Guard &amp; Port State Control Personnel Only
        </div>
      </div>
    </div>
  );
}
