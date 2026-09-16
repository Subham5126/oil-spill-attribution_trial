import React, { useState, useEffect, useRef } from "react";
import { NavPath } from "../components/Sidebar";
import { Investigation } from "../types";
import { getInvestigations } from "../services/api";
import {
  Radio,
  Clock,
  Play,
  CheckCircle2,
  AlertTriangle,
  ArrowRight,
  RefreshCw,
  Cpu,
  Layers,
  Activity,
  Plus,
} from "lucide-react";

interface LiveInvestigationsPageProps {
  onNavigate: (path: NavPath) => void;
  onSelectInvestigation?: (id: string) => void;
}

export function LiveInvestigationsPage({ onNavigate, onSelectInvestigation }: LiveInvestigationsPageProps) {
  const [activeList, setActiveList] = useState<Investigation[]>([]);
  const [recentCompleted, setRecentCompleted] = useState<Investigation[]>([]);
  const [loading, setLoading] = useState(true);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [lastRefreshed, setLastRefreshed] = useState<Date>(new Date());
  const intervalRef = useRef<any>(null);

  const fetchPipelines = async () => {
    try {
      const all = await getInvestigations();
      const active = all.filter((inv) => inv.status === "Active" || inv.status === "Running");
      const completed = all.filter((inv) => inv.status === "Completed").slice(0, 5);
      setActiveList(active);
      setRecentCompleted(completed);
      setLastRefreshed(new Date());
    } catch (err) {
      console.error("Failed to refresh live investigations:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchPipelines();
    if (autoRefresh) {
      intervalRef.current = setInterval(fetchPipelines, 4000);
    }
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [autoRefresh]);

  const pipelineStages = [
    { key: "m1", label: "SAR Ingestion & Calibration", desc: "Sentinel-1 GRD radiometric calibration & speckle filtering" },
    { key: "m2", label: "Deep Learning Segmentation", desc: "U-Net ResNet34 dark-slick probability inference" },
    { key: "m3", label: "GIS Geometry & Slick Vectors", desc: "Polygonization, geodesic area, perimeter, and centroid" },
    { key: "m4", label: "CMEMS Drift Hindcasting", desc: "Lagrangian hydrodynamic reverse particle simulation" },
    { key: "m5", label: "AIS Vessel Attribution", desc: "Spatiotemporal correlation & multi-criteria candidate ranking" },
    { key: "m6", label: "Forensic Report Synthesis", desc: "Evidence packaging and legal prosecution dossier" },
  ];

  return (
    <div className="flex flex-col w-full gap-space-lg">
      {/* Header Bar */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-space-md">
        <div className="flex flex-col gap-space-2xs">
          <div className="flex items-center gap-space-xs">
            <span className="w-2.5 h-2.5 rounded-full bg-sky-500 animate-pulse"></span>
            <span className="font-semibold text-sky-600 font-mono text-xs uppercase tracking-wider">
              Real-Time Execution Monitor
            </span>
          </div>
          <h1 className="font-headline-xl text-headline-xl text-on-surface tracking-tight font-bold flex items-center gap-2">
            <Radio className="w-6 h-6 text-primary" />
            Live Pipeline Executions
          </h1>
          <p className="font-body-md text-body-md text-on-surface-variant">
            In-flight monitoring of satellite ingest, segmentation, hydrodynamic drift, and AIS attribution stages.
          </p>
        </div>

        {/* Controls */}
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-1.5 text-xs text-secondary cursor-pointer bg-surface-container-lowest px-3 py-2 rounded-lg border border-surface-container">
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
              className="accent-primary rounded"
            />
            <span>Auto-Poll (4s)</span>
          </label>
          <button
            type="button"
            onClick={fetchPipelines}
            className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-surface-container text-on-surface hover:bg-surface-container-high transition-colors text-xs font-semibold"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            <span>Refresh</span>
          </button>
          <button
            type="button"
            onClick={() => onNavigate("new-investigation")}
            className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-primary-container text-on-primary hover:bg-primary transition-colors text-xs font-semibold shadow-xs"
          >
            <Plus className="w-3.5 h-3.5" />
            <span>Launch New Run</span>
          </button>
        </div>
      </div>

      {/* Active Pipelines Section */}
      <div className="flex flex-col gap-4">
        <div className="flex items-center justify-between">
          <h2 className="font-headline-sm text-sm font-bold text-on-surface uppercase tracking-wider flex items-center gap-2">
            <Activity className="w-4 h-4 text-sky-500" />
            Active In-Flight Pipelines ({activeList.length})
          </h2>
          <span className="text-[11px] font-mono text-secondary">
            Last update: {lastRefreshed.toLocaleTimeString()}
          </span>
        </div>

        {activeList.length > 0 ? (
          <div className="grid grid-cols-1 gap-4">
            {activeList.map((inv) => (
              <div
                key={inv.id}
                className="bg-surface-container-lowest p- space-md p-5 rounded-xl border border-sky-300 shadow-sm flex flex-col gap-4"
              >
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pb-3 border-b border-surface-container-low">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-xs font-bold text-primary">{inv.id}</span>
                      <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-sky-100 text-sky-800 border border-sky-200 animate-pulse">
                        IN PROGRESS
                      </span>
                    </div>
                    <h3 className="font-bold text-sm text-on-surface mt-1">{inv.title}</h3>
                    <p className="text-xs text-secondary font-mono mt-0.5">
                      Region: {inv.region} • Initiated:{" "}
                      {inv.created_at ? new Date(inv.created_at).toLocaleTimeString() : "Just now"}
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => {
                      if (onSelectInvestigation) onSelectInvestigation(inv.id);
                      onNavigate("analysis-process");
                    }}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-primary text-on-primary hover:bg-primary/90 text-xs font-semibold shadow-xs"
                  >
                    <span>View Stream Output</span>
                    <ArrowRight className="w-3.5 h-3.5" />
                  </button>
                </div>

                {/* Stages progress bar */}
                <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-2">
                  {pipelineStages.map((stage, idx) => (
                    <div
                      key={stage.key}
                      className="bg-surface-container-low p-2.5 rounded-lg border border-surface-container flex flex-col justify-between"
                    >
                      <div>
                        <div className="flex items-center justify-between text-[10px] font-mono text-secondary mb-1">
                          <span>STAGE 0{idx + 1}</span>
                          <span className="text-sky-600 font-bold">RUNNING</span>
                        </div>
                        <div className="font-semibold text-xs text-on-surface leading-tight">
                          {stage.label}
                        </div>
                      </div>
                      <div className="w-full bg-surface-container h-1.5 rounded-full overflow-hidden mt-3">
                        <div className="bg-sky-500 h-full w-2/3 animate-pulse rounded-full"></div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="p-8 text-center bg-surface-container-lowest rounded-xl border border-dashed border-surface-container flex flex-col items-center gap-2">
            <Radio className="w-10 h-10 text-secondary opacity-30" />
            <h3 className="font-bold text-sm text-on-surface">No Active Pipelines In Flight</h3>
            <p className="text-xs text-secondary max-w-sm">
              All investigation pipelines are currently idle. Start a new investigation to ingest and process a Sentinel-1 SAR scene.
            </p>
            <button
              type="button"
              onClick={() => onNavigate("new-investigation")}
              className="mt-2 px-4 py-2 rounded-lg bg-primary text-on-primary font-bold text-xs hover:bg-primary/90 transition-colors shadow-xs"
            >
              Start Investigation
            </button>
          </div>
        )}
      </div>

      {/* Recently Completed Pipelines */}
      <div className="flex flex-col gap-3 mt-4">
        <h2 className="font-headline-sm text-sm font-bold text-on-surface uppercase tracking-wider flex items-center gap-2">
          <CheckCircle2 className="w-4 h-4 text-emerald-500" />
          Recently Concluded Pipelines
        </h2>

        <div className="bg-surface-container-lowest rounded-xl border border-surface-container shadow-sm overflow-hidden">
          <table className="w-full text-left text-xs">
            <thead className="bg-surface-container-low border-b border-surface-container text-secondary font-mono text-[10px] uppercase">
              <tr>
                <th className="px-4 py-2.5">Investigation ID</th>
                <th className="px-4 py-2.5">Title</th>
                <th className="px-4 py-2.5">Spill Footprint</th>
                <th className="px-4 py-2.5">Primary Suspect</th>
                <th className="px-4 py-2.5">Execution Result</th>
                <th className="px-4 py-2.5 text-right">Inspect</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-surface-container-low">
              {recentCompleted.map((inv) => (
                <tr key={inv.id} className="hover:bg-surface-container-low/50">
                  <td className="px-4 py-3 font-mono font-bold text-primary">{inv.id}</td>
                  <td className="px-4 py-3 font-semibold text-on-surface">{inv.title}</td>
                  <td className="px-4 py-3 font-mono text-rose-600 font-bold">
                    {inv.spill_area_km2 ? `${inv.spill_area_km2.toFixed(3)} km²` : "—"}
                  </td>
                  <td className="px-4 py-3 font-mono">{inv.suspect_vessel || "—"}</td>
                  <td className="px-4 py-3">
                    <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-100 text-emerald-800 border border-emerald-200">
                      SUCCESSFUL
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <button
                      type="button"
                      onClick={() => {
                        if (onSelectInvestigation) onSelectInvestigation(inv.id);
                        onNavigate("dashboard");
                      }}
                      className="px-2.5 py-1 rounded bg-surface-container hover:bg-surface-container-high text-xs font-semibold cursor-pointer"
                    >
                      Open Case
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
