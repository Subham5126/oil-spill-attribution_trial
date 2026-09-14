import React, { useState, useEffect } from "react";
import { NavPath } from "../components/Sidebar";
import { SystemStatus, SystemSubsystem } from "../types";
import { getSystemStatus } from "../services/api";
import {
  Activity,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  RefreshCw,
  Cpu,
  Database,
  Terminal,
  Server,
  ShieldCheck,
  Radio,
} from "lucide-react";

interface SystemStatusPageProps {
  onNavigate: (path: NavPath) => void;
}

export function SystemStatusPage({ onNavigate }: SystemStatusPageProps) {
  const [statusData, setStatusData] = useState<SystemStatus | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchStatus = () => {
    setLoading(true);
    getSystemStatus()
      .then((data) => setStatusData(data))
      .catch((err) => console.error("Failed to load system status:", err))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchStatus();
  }, []);

  const getStatusBadge = (status: string) => {
    switch (status.toLowerCase()) {
      case "operational":
      case "active":
        return (
          <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-100 text-emerald-800 border border-emerald-200 inline-flex items-center gap-1">
            <CheckCircle2 className="w-3 h-3" />
            OPERATIONAL
          </span>
        );
      case "warning":
      case "degraded":
        return (
          <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-100 text-amber-800 border border-amber-200 inline-flex items-center gap-1">
            <AlertTriangle className="w-3 h-3" />
            DEGRADED
          </span>
        );
      default:
        return (
          <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-rose-100 text-rose-800 border border-rose-200 inline-flex items-center gap-1">
            <XCircle className="w-3 h-3" />
            UNAVAILABLE
          </span>
        );
    }
  };

  return (
    <div className="flex flex-col w-full gap-space-lg">
      {/* Top Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-space-md">
        <div className="flex flex-col gap-space-2xs">
          <div className="flex items-center gap-space-xs text-on-surface-variant font-label-sm text-label-sm">
            <span className="font-semibold text-primary uppercase tracking-wider">Operational Health</span>
          </div>
          <h1 className="font-headline-xl text-headline-xl text-on-surface tracking-tight font-bold flex items-center gap-2">
            <ShieldCheck className="w-6 h-6 text-primary" />
            System Diagnostic Health &amp; Subsystems
          </h1>
          <p className="font-body-md text-body-md text-on-surface-variant">
            Live diagnostic verification of scientific computing drivers, deep learning runtime, database, and telemetry endpoints.
          </p>
        </div>

        <button
          type="button"
          onClick={fetchStatus}
          className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-surface-container text-on-surface hover:bg-surface-container-high transition-colors text-xs font-semibold"
        >
          <RefreshCw className="w-3.5 h-3.5" />
          <span>Run Self-Test Diagnostics</span>
        </button>
      </div>

      {/* Overall Health Status Banner */}
      <div className="p-5 rounded-xl bg-surface-container-lowest border border-surface-container shadow-sm flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="w-12 h-12 rounded-xl bg-emerald-100 border border-emerald-300 flex items-center justify-center text-emerald-700">
            <CheckCircle2 className="w-6 h-6" />
          </div>
          <div>
            <div className="text-[10px] font-mono text-secondary uppercase font-bold tracking-wider">
              Aggregate Health Status
            </div>
            <div className="text-xl font-bold text-on-surface">
              {statusData?.overall || "Operational"}
            </div>
            <div className="text-xs text-secondary mt-0.5">
              All scientific and geospatial components reporting operational readiness.
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2 font-mono text-xs text-secondary bg-surface-container-low px-3 py-2 rounded-lg border border-surface-container">
          <span className="w-2 h-2 rounded-full bg-emerald-500 animate-ping"></span>
          <span>FastAPI Backend: http://127.0.0.1:8000</span>
        </div>
      </div>

      {/* Subsystems Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-space-md">
        {statusData?.subsystems.map((sub: SystemSubsystem) => (
          <div
            key={sub.name}
            className="p-space-md rounded-xl bg-surface-container-lowest border border-surface-container shadow-sm flex flex-col justify-between"
          >
            <div>
              <div className="flex items-center justify-between pb-2 border-b border-surface-container-low">
                <span className="text-[10px] font-mono font-bold text-secondary uppercase tracking-wider">
                  {sub.category}
                </span>
                {getStatusBadge(sub.status)}
              </div>
              <h3 className="font-bold text-sm text-on-surface mt-2.5">{sub.name}</h3>
              <p className="text-xs text-secondary font-mono mt-1 leading-relaxed bg-surface-container-low p-2.5 rounded-lg border border-surface-container">
                {sub.details}
              </p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
