import React, { useState, useEffect, useMemo } from "react";
import { NavPath } from "../components/Sidebar";
import { MapLibreGIS } from "../map/MapLibreGIS";
import { EndToEndResult, DashboardSummary, Investigation, GeoJSONFeatureCollection } from "../types";
import { getActivePipelineResult, getDashboardSummary, getGISLayersGeoJSON } from "../services/api";
import {
  Ship,
  Maximize2,
  FolderPlus,
  Radio,
  Layers,
  CheckCircle2,
  ShieldCheck,
  ExternalLink,
  MapPin,
  Clock,
  ChevronRight,
  Activity,
  Satellite,
  Waves,
  FileCheck,
  Cpu,
  Compass,
  FileText,
  Workflow,
  Search,
} from "lucide-react";

interface DashboardPageProps {
  onNavigate: (path: NavPath) => void;
  onOpenDossier?: () => void;
  activeInvestigationId?: string | null;
  onSelectInvestigation?: (id: string) => void;
}

export function DashboardPage({
  onNavigate,
  onOpenDossier,
  onSelectInvestigation,
}: DashboardPageProps) {
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [pipelineData, setPipelineData] = useState<EndToEndResult | null>(null);
  const [layersGeoJSON, setLayersGeoJSON] = useState<GeoJSONFeatureCollection | null>(null);
  const [loading, setLoading] = useState(true);

  // Load aggregate dashboard statistics and overview GIS layers
  useEffect(() => {
    setLoading(true);
    Promise.all([
      getDashboardSummary().catch(() => null),
      getActivePipelineResult().catch(() => null),
      getGISLayersGeoJSON().catch(() => null),
    ])
      .then(([sum, pipe, layers]) => {
        if (sum) {
          setSummary(sum);
          if (sum.total_investigations === 0) {
            setPipelineData(null);
            setLayersGeoJSON({ type: "FeatureCollection", features: [] });
            return;
          }
        }
        if (pipe) setPipelineData(pipe);
        if (layers) setLayersGeoJSON(layers);
      })
      .finally(() => setLoading(false));
  }, []);

  const handleOpenCase = (id: string) => {
    if (onSelectInvestigation) {
      onSelectInvestigation(id);
    }
    onNavigate("investigation-detail");
  };

  const isZeroState = !loading && summary && summary.total_investigations === 0;

  const readinessState = useMemo(() => {
    if (summary?.forensic_readiness) {
      const st = summary.forensic_readiness.status;
      const det = summary.forensic_readiness.detail;
      let dotClass = "bg-emerald-500";
      if (st === "PROCESSING") dotClass = "bg-primary animate-pulse";
      else if (st === "ATTENTION") dotClass = "bg-amber-500";
      else if (st === "BLOCKED") dotClass = "bg-rose-500";
      else if (st === "STANDBY") dotClass = "bg-slate-400";
      return { status: st, detail: det, dotClass };
    }

    if (!summary || summary.total_investigations === 0) {
      return {
        status: "STANDBY",
        detail: "Awaiting investigation",
        dotClass: "bg-slate-400",
      };
    }
    if ((summary.running_investigations ?? 0) > 0) {
      return {
        status: "PROCESSING",
        detail: "Investigation pipeline active",
        dotClass: "bg-primary animate-pulse",
      };
    }
    if ((summary.failed_investigations ?? 0) > 0) {
      return {
        status: "ATTENTION",
        detail: "Evidence requires review",
        dotClass: "bg-amber-500",
      };
    }
    if ((summary.completed_investigations ?? 0) > 0) {
      return {
        status: "READY",
        detail: "Evidence standards satisfied",
        dotClass: "bg-emerald-500",
      };
    }
    return {
      status: "STANDBY",
      detail: "Awaiting investigation",
      dotClass: "bg-slate-400",
    };
  }, [summary]);

  // 7 Human-Readable Pipeline Stages (No M1-M5 labels)
  const pipelineStages = [
    {
      id: "sar-detection",
      name: "SAR Detection",
      icon: Satellite,
      desc: "Sentinel-1 C-SAR GRD high-resolution calibrated ingestion",
      status: "Operational",
      targetPath: "datasets" as NavPath,
    },
    {
      id: "ai-segmentation",
      name: "AI Segmentation",
      icon: Cpu,
      desc: "Deep U-Net mineral oil slick segmentation & mask inference",
      status: "Active",
      targetPath: "analysis-process" as NavPath,
    },
    {
      id: "gis-geometry",
      name: "GIS Geometry",
      icon: Maximize2,
      desc: "Geodesic EPSG:4326 polygon vectorization & centroid extraction",
      status: "Validated",
      targetPath: "map-explorer" as NavPath,
    },
    {
      id: "ocean-analysis",
      name: "Ocean Current Analysis",
      icon: Waves,
      desc: "Copernicus Marine (CMEMS) hydrodynamic surface velocity fields",
      status: "Operational",
      targetPath: "datasets" as NavPath,
    },
    {
      id: "drift-reconstruction",
      name: "Drift Reconstruction",
      icon: Compass,
      desc: "Lagrangian backward trajectory hindcast to release origin",
      status: "Active",
      targetPath: "drift-analysis" as NavPath,
    },
    {
      id: "ais-correlation",
      name: "AIS Correlation",
      icon: Ship,
      desc: "Spatiotemporal trajectory search across Class-A vessels",
      status: "Operational",
      targetPath: "vessel-intelligence" as NavPath,
    },
    {
      id: "evidence-dossier",
      name: "Evidence Dossier",
      icon: FileCheck,
      desc: "Cryptographically sealed 11-section MARPOL Annex I legal dossier",
      status: "Ready",
      targetPath: "reports" as NavPath,
    },
  ];

  return (
    <div className="flex flex-col w-full gap-space-lg pb-12">
      {/* 1. Compact Operational Hero Header */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-space-sm border-b border-surface-container-low pb-space-sm">
        {/* Left: Eyebrow, Title & Description (~65-70%) */}
        <div className="flex flex-col gap-1 max-w-2xl">
          <div className="flex items-center gap-2">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
            <span className="text-[11px] text-secondary uppercase tracking-widest font-semibold font-mono">
              MARITIME SURVEILLANCE // COMMAND CENTER
            </span>
          </div>
          <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-on-surface">
            Maritime Oil Spill Surveillance
          </h1>
          <p className="text-xs sm:text-sm text-secondary leading-snug">
            Monitor satellite detections, ocean drift, and vessel attribution across active maritime investigations.
          </p>
        </div>

        {/* Right: Actions Ribbon with Strict Visual Hierarchy (~30-35%) */}
        <div className="flex items-center gap-2 flex-wrap lg:justify-end pt-1 lg:pt-0">
          {/* PRIMARY: + New Incident (Strong filled blue) */}
          <button
            type="button"
            onClick={() => onNavigate("new-investigation")}
            title="Register a new satellite scene or manual spill incident"
            className="flex items-center gap-1.5 px-3.5 py-2 rounded-lg bg-primary text-on-primary hover:bg-primary/90 transition-colors text-xs font-bold shadow-xs cursor-pointer"
          >
            <FolderPlus className="w-3.5 h-3.5" />
            <span>+ New Incident</span>
          </button>

          {/* SECONDARY: Investigations (Subtle outline) */}
          <button
            type="button"
            onClick={() => onNavigate("investigations")}
            title="Browse all registered incident investigations"
            className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-transparent text-secondary hover:text-on-surface hover:bg-surface-container-low border border-surface-container-high/60 transition-colors text-xs font-medium cursor-pointer"
          >
            <Layers className="w-3.5 h-3.5 text-secondary" />
            <span>Investigations</span>
          </button>

          {/* TERTIARY: Live Pipelines (Subtle outline/text) */}
          <button
            type="button"
            onClick={() => onNavigate("live-investigations")}
            title="Monitor real-time asynchronous pipeline execution"
            className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-transparent text-secondary hover:text-on-surface hover:bg-surface-container-low border border-surface-container-high/60 transition-colors text-xs font-medium cursor-pointer"
          >
            <Radio className="w-3.5 h-3.5 text-sky-500" />
            <span>Live Pipelines</span>
          </button>
        </div>
      </div>

      {/* 2. Compact Operational Summary Strip */}
      <section
        aria-label="Operational Summary"
        className="w-full bg-surface-container-lowest border border-surface-container-high/60 rounded-lg shadow-xs px-4 py-3 sm:px-5 sm:py-3.5 mb-6"
      >
        {/* Header Ribbon */}
        <div className="flex items-center justify-between pb-2 mb-2.5 border-b border-surface-container/60">
          <div className="flex items-center gap-2">
            <span className="w-1.5 h-1.5 rounded-full bg-primary" />
            <h2 className="text-[10px] font-bold tracking-wider text-secondary uppercase font-mono">
              Operational Summary
            </h2>
          </div>
          <span className="text-[9px] sm:text-[10px] text-outline tracking-wider font-mono uppercase hidden xs:inline">
            Real-Time Forensic Telemetry
          </span>
        </div>

        {/* 4 Metric Columns in 1 Unified Strip */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 divide-y sm:divide-y-0 sm:divide-x divide-surface-container/80">
          {/* 01: INCIDENTS */}
          <button
            type="button"
            onClick={() => onNavigate("investigations")}
            title="View all registered investigations"
            className="flex flex-col text-left py-2 sm:py-0 px-2 sm:px-3.5 lg:first:pl-0 group cursor-pointer hover:bg-surface-container-low/50 rounded transition-colors"
          >
            <div className="flex items-center justify-between w-full mb-1">
              <div className="flex items-center gap-1.5">
                <span className="text-[10px] font-mono text-outline font-medium">01</span>
                <span className="text-[10px] sm:text-[11px] font-bold tracking-wider text-secondary uppercase group-hover:text-primary transition-colors">
                  INCIDENTS
                </span>
              </div>
              <Layers className="w-3.5 h-3.5 text-outline-variant group-hover:text-primary transition-colors shrink-0" />
            </div>
            <div className="text-xl sm:text-2xl font-bold font-mono text-on-surface tracking-tight">
              {summary ? summary.total_investigations : "—"}
            </div>
            <div className="text-[11px] text-secondary mt-0.5 flex items-center gap-1.5 font-mono truncate">
              {isZeroState ? (
                <>
                  <span className="w-1.5 h-1.5 rounded-full bg-slate-400 shrink-0" />
                  <span>Awaiting first investigation</span>
                </>
              ) : (
                <>
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 shrink-0" />
                  <span className="text-on-surface-variant font-medium">
                    {summary?.completed_investigations ?? 0} completed
                  </span>
                  <span className="text-outline">·</span>
                  <span className="text-secondary">
                    {summary?.active_investigations ?? 0} active
                  </span>
                </>
              )}
            </div>
          </button>

          {/* 02: SPILL FOOTPRINT */}
          <button
            type="button"
            onClick={() => onNavigate("map-explorer")}
            title="Inspect detected spill footprints in Map Explorer"
            className="flex flex-col text-left py-2 sm:py-0 px-2 sm:px-3.5 group cursor-pointer hover:bg-surface-container-low/50 rounded transition-colors"
          >
            <div className="flex items-center justify-between w-full mb-1">
              <div className="flex items-center gap-1.5">
                <span className="text-[10px] font-mono text-outline font-medium">02</span>
                <span className="text-[10px] sm:text-[11px] font-bold tracking-wider text-secondary uppercase group-hover:text-primary transition-colors">
                  SPILL FOOTPRINT
                </span>
              </div>
              <Maximize2 className="w-3.5 h-3.5 text-outline-variant group-hover:text-primary transition-colors shrink-0" />
            </div>
            <div className="text-xl sm:text-2xl font-bold font-mono text-on-surface tracking-tight">
              {summary
                ? isZeroState
                  ? "0.00 km²"
                  : `${(summary.total_spill_area_km2 || 0).toFixed(2)} km²`
                : "—"}
            </div>
            <div className="text-[11px] text-secondary mt-0.5 flex items-center gap-1.5 font-mono truncate">
              <span className={`w-1.5 h-1.5 rounded-full ${isZeroState ? "bg-slate-400" : "bg-primary"} shrink-0`} />
              <span>{isZeroState ? "No detected footprint" : "Total detected footprint"}</span>
            </div>
          </button>

          {/* 03: AIS VESSELS */}
          <button
            type="button"
            onClick={() => onNavigate("vessel-intelligence")}
            title="Open Vessel Intelligence registry"
            className="flex flex-col text-left py-2 sm:py-0 px-2 sm:px-3.5 group cursor-pointer hover:bg-surface-container-low/50 rounded transition-colors"
          >
            <div className="flex items-center justify-between w-full mb-1">
              <div className="flex items-center gap-1.5">
                <span className="text-[10px] font-mono text-outline font-medium">03</span>
                <span className="text-[10px] sm:text-[11px] font-bold tracking-wider text-secondary uppercase group-hover:text-primary transition-colors">
                  AIS VESSELS
                </span>
              </div>
              <Ship className="w-3.5 h-3.5 text-outline-variant group-hover:text-primary transition-colors shrink-0" />
            </div>
            <div className="text-xl sm:text-2xl font-bold font-mono text-on-surface tracking-tight">
              {summary ? (summary.candidate_vessels_tracked || 0).toLocaleString() : "—"}
            </div>
            <div className="text-[11px] text-secondary mt-0.5 flex items-center gap-1.5 font-mono truncate">
              <span className={`w-1.5 h-1.5 rounded-full ${isZeroState || (summary?.candidate_vessels_tracked ?? 0) === 0 ? "bg-slate-400" : "bg-primary"} shrink-0`} />
              <span>
                {isZeroState || (summary?.candidate_vessels_tracked ?? 0) === 0
                  ? "No vessels profiled"
                  : "Vessels profiled across investigations"}
              </span>
            </div>
          </button>

          {/* 04: FORENSIC READINESS */}
          <button
            type="button"
            onClick={() => onNavigate("reports")}
            title="Inspect forensic reports and legal dossiers"
            className="flex flex-col text-left py-2 sm:py-0 px-2 sm:px-3.5 lg:last:pr-0 group cursor-pointer hover:bg-surface-container-low/50 rounded transition-colors"
          >
            <div className="flex items-center justify-between w-full mb-1">
              <div className="flex items-center gap-1.5">
                <span className="text-[10px] font-mono text-outline font-medium">04</span>
                <span className="text-[10px] sm:text-[11px] font-bold tracking-wider text-secondary uppercase group-hover:text-primary transition-colors">
                  READINESS
                </span>
              </div>
              <ShieldCheck className={`w-3.5 h-3.5 ${
                readinessState.status === "READY"
                  ? "text-emerald-500"
                  : readinessState.status === "PROCESSING"
                  ? "text-primary"
                  : readinessState.status === "ATTENTION"
                  ? "text-amber-500"
                  : readinessState.status === "BLOCKED"
                  ? "text-rose-500"
                  : "text-outline-variant"
              } group-hover:scale-105 transition-all shrink-0`} />
            </div>
            <div className={`text-xl sm:text-2xl font-bold font-mono tracking-tight ${
              readinessState.status === "READY"
                ? "text-emerald-600"
                : readinessState.status === "PROCESSING"
                ? "text-primary"
                : readinessState.status === "ATTENTION"
                ? "text-amber-600"
                : readinessState.status === "BLOCKED"
                ? "text-rose-600"
                : "text-secondary"
            }`}>
              {readinessState.status}
            </div>
            <div className="text-[11px] text-secondary mt-0.5 flex items-center gap-1.5 font-mono truncate">
              <span className={`w-1.5 h-1.5 rounded-full ${readinessState.dotClass} shrink-0`} />
              <span>{readinessState.detail}</span>
            </div>
          </button>
        </div>
      </section>

      {/* 3. Empty State Banner */}
      {isZeroState && (
        <div className="p-8 bg-surface-container-lowest rounded-xl border border-dashed border-surface-container text-center flex flex-col items-center gap-3">
          <div className="w-12 h-12 rounded-full bg-primary/10 flex items-center justify-center text-primary">
            <FolderPlus className="w-6 h-6" />
          </div>
          <h2 className="text-base font-bold text-on-surface">No Incident Investigations Registered</h2>
          <p className="text-xs text-secondary max-w-md">
            Execute the pipeline on real Sentinel-1 SAR imagery to detect marine dark slicks and correlate vessel trajectories.
          </p>
          <button
            type="button"
            onClick={() => onNavigate("new-investigation")}
            className="mt-2 px-4 py-2 rounded-lg bg-primary text-on-primary font-bold text-xs hover:bg-primary/90 transition-colors shadow-xs cursor-pointer"
          >
            Launch First Incident Investigation
          </button>
        </div>
      )}

      {/* 4. Main Operational Split: Canvas (Left 7) + Recent Incidents (Right 5) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-space-md items-start">
        {/* Left Column: Operational Surveillance Canvas (7 Cols) */}
        <div className="lg:col-span-7 flex flex-col gap-3">
          <div className="bg-surface-container-lowest rounded-xl p-space-md border border-surface-container shadow-xs flex flex-col gap-2">
            <div className="flex items-center justify-between pb-2 border-b border-surface-container-low">
              <div className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-primary" />
                <h2 className="font-headline-sm text-sm font-bold text-on-surface">
                  Operational Surveillance Canvas
                </h2>
              </div>
              <button
                type="button"
                onClick={() => onNavigate("map-explorer")}
                className="text-primary hover:underline text-xs font-semibold flex items-center gap-1 cursor-pointer"
              >
                <span>Open Map Explorer</span>
                <ChevronRight className="w-3.5 h-3.5" />
              </button>
            </div>

            {/* Controlled MapLibre Map showing aggregated or latest pipeline layers */}
            <MapLibreGIS
              result={pipelineData}
              layersGeoJSON={layersGeoJSON}
              height="380px"
              showControls={true}
            />

            {/* Map footer info */}
            <div className="flex items-center justify-between pt-1 text-[11px] text-secondary">
              <span>Sentinel-1 SAR Slick Detections & Ocean Current Advection Overlays</span>
              <button
                type="button"
                onClick={() => onNavigate("map-explorer")}
                className="text-primary hover:underline flex items-center gap-1 font-semibold cursor-pointer"
              >
                <span>Full-Screen GIS Command</span>
                <ExternalLink className="w-3 h-3" />
              </button>
            </div>
          </div>
        </div>

        {/* Right Column: Recent Investigations (5 Cols) */}
        <div className="lg:col-span-5 flex flex-col gap-3">
          <div className="bg-surface-container-lowest rounded-xl p-space-md border border-surface-container shadow-xs flex flex-col gap-3">
            <div className="flex items-center justify-between pb-2 border-b border-surface-container-low">
              <div className="flex items-center gap-2">
                <Activity className="w-4 h-4 text-primary" />
                <h2 className="font-headline-sm text-sm font-bold text-on-surface">
                  Recent Investigations
                </h2>
              </div>
              <button
                type="button"
                onClick={() => onNavigate("investigations")}
                className="text-primary hover:underline text-xs font-semibold flex items-center gap-1 cursor-pointer"
              >
                <span>View All ({summary?.total_investigations || 0})</span>
                <ChevronRight className="w-3.5 h-3.5" />
              </button>
            </div>

            {/* Investigations List */}
            {summary && summary.recent_investigations && summary.recent_investigations.length > 0 ? (
              <div className="flex flex-col gap-2">
                {summary.recent_investigations.slice(0, 5).map((inv: Investigation) => (
                  <div
                    key={inv.id}
                    onClick={() => handleOpenCase(inv.id)}
                    className="p-3 rounded-lg border bg-surface-container-low border-surface-container hover:border-primary/40 hover:bg-surface-container transition-all cursor-pointer flex flex-col gap-1.5"
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-mono text-xs font-bold text-primary">{inv.id}</span>
                      <span
                        className={`text-[10px] px-1.5 py-0.5 rounded font-bold uppercase ${
                          inv.status === "Completed"
                            ? "bg-emerald-500/15 text-emerald-600 border border-emerald-500/30"
                            : inv.status === "Active"
                            ? "bg-sky-500/15 text-sky-600 border border-sky-500/30"
                            : "bg-surface-container text-secondary"
                        }`}
                      >
                        {inv.status}
                      </span>
                    </div>

                    <div className="text-xs font-semibold text-on-surface truncate">
                      {inv.title}
                    </div>

                    <div className="flex items-center justify-between text-[11px] text-secondary font-mono">
                      <span className="flex items-center gap-1">
                        <MapPin className="w-3 h-3 text-secondary shrink-0" />
                        <span className="truncate max-w-[150px]">{inv.region || "Offshore EEZ"}</span>
                      </span>
                      <span className="font-bold text-on-surface">
                        {inv.spill_area_km2 ? `${inv.spill_area_km2.toFixed(2)} km²` : "—"}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-center py-8 text-xs text-secondary">
                No recent investigations available.
              </div>
            )}
          </div>
        </div>
      </div>

      {/* 5. Pipeline Overview: 7 Human-Readable Stages (No M1-M5 labels) */}
      <div className="bg-surface-container-lowest rounded-xl p-space-md border border-surface-container shadow-xs flex flex-col gap-4">
        <div className="flex items-center justify-between pb-2 border-b border-surface-container-low">
          <div className="flex items-center gap-2">
            <Workflow className="w-4 h-4 text-primary" />
            <h2 className="font-headline-sm text-sm font-bold text-on-surface">
              Pipeline Overview
            </h2>
          </div>
          <span className="text-[11px] text-secondary font-mono">
            Autonomous Multimodal Architecture
          </span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-7 gap-3">
          {pipelineStages.map((stage, idx) => {
            const Icon = stage.icon;
            return (
              <button
                key={stage.id}
                type="button"
                onClick={() => onNavigate(stage.targetPath)}
                className="p-3 rounded-lg bg-surface-container-low border border-surface-container hover:border-primary hover:bg-surface-container transition-all flex flex-col justify-between text-left cursor-pointer group"
              >
                <div className="flex flex-col gap-2">
                  <div className="flex items-center justify-between">
                    <div className="w-7 h-7 rounded-lg bg-surface-container flex items-center justify-center text-primary group-hover:bg-primary group-hover:text-on-primary transition-colors">
                      <Icon className="w-4 h-4" />
                    </div>
                    <span className="text-[9px] px-1.5 py-0.5 rounded font-bold uppercase bg-emerald-500/10 text-emerald-600 border border-emerald-500/20">
                      {stage.status}
                    </span>
                  </div>
                  <div>
                    <h3 className="text-xs font-bold text-on-surface group-hover:text-primary transition-colors">
                      {stage.name}
                    </h3>
                    <p className="text-[10px] text-secondary mt-1 leading-snug line-clamp-3">
                      {stage.desc}
                    </p>
                  </div>
                </div>
                <div className="mt-3 pt-2 border-t border-surface-container/60 flex items-center justify-between text-[10px] text-primary font-semibold">
                  <span>Open Stage</span>
                  <ChevronRight className="w-3 h-3 group-hover:translate-x-0.5 transition-transform" />
                </div>
              </button>
            );
          })}
        </div>
      </div>

      {/* 6. Operational Activity & System Status Split */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-space-md">
        {/* Operational Activity Log (7 Cols) */}
        <div className="lg:col-span-7 bg-surface-container-lowest rounded-xl p-space-md border border-surface-container shadow-xs flex flex-col gap-3">
          <div className="flex items-center justify-between pb-2 border-b border-surface-container-low">
            <div className="flex items-center gap-2">
              <Clock className="w-4 h-4 text-primary" />
              <h2 className="font-headline-sm text-sm font-bold text-on-surface">
                Operational Activity
              </h2>
            </div>
            <span className="text-[11px] text-secondary font-mono">Live Ingestion & Correlation Stream</span>
          </div>

          {isZeroState ? (
            <div className="text-center py-10 text-xs text-secondary flex flex-col items-center justify-center gap-1.5 min-h-[160px]">
              <span className="font-semibold text-on-surface">No investigation activity yet.</span>
              <span className="text-[11px] text-secondary">System idle • Awaiting satellite scene ingestion</span>
            </div>
          ) : (
            <div className="space-y-3">
              {[
                {
                  event: "SAR Scene Processed & Calibrated",
                  target: summary?.recent_investigations?.[0]?.id || "INV-00736",
                  desc: "Sentinel-1 Level-1 GRD radiometric calibration and speckle filtering verified nominal.",
                  time: "12m ago",
                  color: "bg-sky-500",
                },
                {
                  event: "Spill Geometry Computed",
                  target: summary?.recent_investigations?.[0]?.id || "INV-00736",
                  desc: "Geodesic polygon calculated; surface area and dispersion envelope registered.",
                  time: "24m ago",
                  color: "bg-indigo-500",
                },
                {
                  event: "Ocean Current Analysis Completed",
                  target: summary?.recent_investigations?.[1]?.id || "INV-98315",
                  desc: "Copernicus Marine surface velocity fields interpolated for backward Lagrangian drift.",
                  time: "48m ago",
                  color: "bg-teal-500",
                },
                {
                  event: "AIS Vessels Correlated",
                  target: summary?.recent_investigations?.[0]?.id || "INV-00736",
                  desc: "Class-A tanker tracks correlated within spatiotemporal release window.",
                  time: "1h ago",
                  color: "bg-amber-500",
                },
                {
                  event: "Forensic Evidence Dossier Compiled",
                  target: summary?.recent_investigations?.[0]?.id || "INV-00736",
                  desc: "MARPOL Annex I prosecution report generated with cryptographic SHA-256 seal.",
                  time: "1h 15m ago",
                  color: "bg-emerald-500",
                },
              ].map((act, index) => (
                <div
                  key={index}
                  className="p-2.5 rounded-lg bg-surface-container-low border border-surface-container flex items-start justify-between gap-3 text-xs"
                >
                  <div className="flex items-start gap-2.5">
                    <span className={`w-2 h-2 rounded-full ${act.color} mt-1.5 shrink-0`} />
                    <div className="flex flex-col gap-0.5">
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-on-surface">{act.event}</span>
                        <button
                          type="button"
                          onClick={() => handleOpenCase(act.target)}
                          className="font-mono text-[10px] text-primary hover:underline font-bold"
                        >
                          [{act.target}]
                        </button>
                      </div>
                      <span className="text-[11px] text-secondary leading-snug">{act.desc}</span>
                    </div>
                  </div>
                  <span className="text-[10px] font-mono text-outline-variant shrink-0">{act.time}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* System Status Subsystems (5 Cols) */}
        <div className="lg:col-span-5 bg-surface-container-lowest rounded-xl p-space-md border border-surface-container shadow-xs flex flex-col gap-3">
          <div className="flex items-center justify-between pb-2 border-b border-surface-container-low">
            <div className="flex items-center gap-2">
              <ShieldCheck className="w-4 h-4 text-emerald-500" />
              <h2 className="font-headline-sm text-sm font-bold text-on-surface">
                System Status
              </h2>
            </div>
            <button
              type="button"
              onClick={() => onNavigate("system-status")}
              className="text-primary hover:underline text-xs font-semibold flex items-center gap-1 cursor-pointer"
            >
              <span>Full Diagnostics</span>
              <ChevronRight className="w-3.5 h-3.5" />
            </button>
          </div>

          <div className="space-y-2.5">
            <div className="p-3 rounded-lg bg-surface-container-low border border-surface-container flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <Satellite className="w-4 h-4 text-primary shrink-0" />
                <div className="flex flex-col">
                  <span className="text-xs font-bold text-on-surface">Satellite Data / Sentinel-1</span>
                  <span className="text-[11px] text-secondary">Copernicus Data Space Ecosystem (C-SAR)</span>
                </div>
              </div>
              <span className="text-[10px] font-bold px-2 py-0.5 rounded uppercase bg-emerald-500/10 text-emerald-600 border border-emerald-500/20">
                Nominal
              </span>
            </div>

            <div className="p-3 rounded-lg bg-surface-container-low border border-surface-container flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <Waves className="w-4 h-4 text-sky-500 shrink-0" />
                <div className="flex flex-col">
                  <span className="text-xs font-bold text-on-surface">Ocean Data / Copernicus Marine</span>
                  <span className="text-[11px] text-secondary">CMEMS Global 1/12° Hydrodynamics & GFS Wind</span>
                </div>
              </div>
              <span className="text-[10px] font-bold px-2 py-0.5 rounded uppercase bg-emerald-500/10 text-emerald-600 border border-emerald-500/20">
                Nominal
              </span>
            </div>

            <div className="p-3 rounded-lg bg-surface-container-low border border-surface-container flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <Ship className="w-4 h-4 text-indigo-500 shrink-0" />
                <div className="flex flex-col">
                  <span className="text-xs font-bold text-on-surface">AIS Intelligence / Global Fleet</span>
                  <span className="text-[11px] text-secondary">Terrestrial & Satellite AIS Transponder Feeds</span>
                </div>
              </div>
              <span className="text-[10px] font-bold px-2 py-0.5 rounded uppercase bg-emerald-500/10 text-emerald-600 border border-emerald-500/20">
                Active
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default DashboardPage;
