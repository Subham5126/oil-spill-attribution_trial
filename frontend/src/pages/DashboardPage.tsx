import React, { useState, useEffect } from "react";
import { NavPath } from "../components/Sidebar";
import { MapLibreGIS } from "../map/MapLibreGIS";
import { SpillMetadataCard } from "../components/SpillMetadataCard";
import { AttributionPanel } from "../components/AttributionPanel";
import { PipelineSteps } from "../components/PipelineSteps";
import { AttributionRadarChart } from "../charts/AttributionRadarChart";
import { EndToEndResult, CandidateVessel } from "../types";
import { getActivePipelineResult } from "../services/api";
import { BASELINE_DEMO_RESULT } from "../services/demoDataAdapter";
import {
  Satellite,
  Ship,
  Maximize2,
  Compass,
  ArrowRight,
  ShieldCheck,
  AlertTriangle,
  FileText,
  Activity,
} from "lucide-react";

interface DashboardPageProps {
  onNavigate: (path: NavPath) => void;
  onOpenDossier?: () => void;
}

export function DashboardPage({ onNavigate, onOpenDossier }: DashboardPageProps) {
  const [pipelineData, setPipelineData] = useState<EndToEndResult>(BASELINE_DEMO_RESULT);
  const [selectedVessel, setSelectedVessel] = useState<CandidateVessel | null>(
    BASELINE_DEMO_RESULT.primary_suspect
  );

  useEffect(() => {
    getActivePipelineResult().then((data) => {
      setPipelineData(data);
      if (data.primary_suspect) {
        setSelectedVessel(data.primary_suspect);
      }
    });
  }, []);

  const { spill_metadata, gis_measurement, ocean_drift, candidate_vessels } = pipelineData;

  return (
    <div className="flex flex-col w-full gap-space-lg">
      {/* Top Operational Header Bar */}
      <div className="flex flex-col lg:flex-row lg:items-end justify-between gap-space-md">
        <div className="flex flex-col gap-space-2xs">
          <div className="flex items-center gap-space-xs">
            <span className="w-2 h-2 rounded-full bg-emerald-500 animate-ping"></span>
            <span className="font-label-sm text-label-sm text-secondary uppercase tracking-widest font-semibold">
              Operational Command Hub // Arabian Sea Node
            </span>
          </div>
          <h1 className="font-headline-xl text-headline-xl text-on-surface tracking-tight font-bold">
            Maritime Spill Attribution Overview
          </h1>
          <p className="font-body-md text-body-md text-on-surface-variant max-w-3xl">
            Live Sentinel-1 SAR dark slick extraction, hydrodynamic Lagrangian drift hindcasting,
            and AIS vessel trajectory correlation for incident{" "}
            <code className="text-primary font-bold">{spill_metadata.spill_id}</code>.
          </p>
        </div>

        {/* Quick Action Ribbon */}
        <div className="flex items-center gap-space-sm flex-wrap">
          <button
            type="button"
            onClick={() => onNavigate("analysis-process")}
            className="flex items-center gap-space-xs px-space-md py-2 rounded-lg bg-surface-container text-on-surface hover:bg-surface-container-high transition-colors font-label-md text-label-md cursor-pointer border border-surface-container"
          >
            <Activity className="w-4 h-4 text-primary" />
            <span>View Pipeline Stream</span>
          </button>
          <button
            type="button"
            onClick={onOpenDossier}
            className="flex items-center gap-space-xs px-space-md py-2 rounded-lg bg-primary-container text-on-primary hover:bg-primary transition-colors font-label-md text-label-md font-semibold shadow-md cursor-pointer"
          >
            <FileText className="w-4 h-4" />
            <span>Legal Prosecution Dossier</span>
          </button>
        </div>
      </div>

      {/* 8-Stage Pipeline Progress Tracker */}
      <PipelineSteps currentStep={8} />

      {/* 4 Summary Stat Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-space-md">
        {/* Stat 1: Detected Area */}
        <div className="p-space-md rounded-xl bg-surface-container-lowest border border-surface-container shadow-sm flex flex-col justify-between">
          <div className="flex items-center justify-between text-secondary">
            <span className="font-label-sm text-label-sm font-semibold uppercase">
              Measured Spill Area
            </span>
            <Maximize2 className="w-4 h-4 text-rose-500" />
          </div>
          <div className="mt-2">
            <div className="font-headline-lg text-headline-lg font-bold text-on-surface">
              {gis_measurement.area.sq_kilometers.toFixed(4)} km²
            </div>
            <div className="font-data-mono-sm text-[11px] text-on-surface-variant mt-1">
              Perimeter: {gis_measurement.perimeter.kilometers.toFixed(3)} km • Compactness:{" "}
              {gis_measurement.shape_characteristics.compactness.toFixed(3)}
            </div>
          </div>
        </div>

        {/* Stat 2: Origin Localization */}
        <div className="p-space-md rounded-xl bg-surface-container-lowest border border-surface-container shadow-sm flex flex-col justify-between">
          <div className="flex items-center justify-between text-secondary">
            <span className="font-label-sm text-label-sm font-semibold uppercase">
              Probable Spill Origin
            </span>
            <Compass className="w-4 h-4 text-emerald-500" />
          </div>
          <div className="mt-2">
            <div className="font-headline-lg text-headline-lg font-bold text-emerald-600">
              {ocean_drift.probable_origin.latitude.toFixed(4)}°N
            </div>
            <div className="font-data-mono-sm text-[11px] text-on-surface-variant mt-1">
              Release: {ocean_drift.probable_origin.timestamp.replace("T", " ").replace("+00:00", "")} UTC
            </div>
          </div>
        </div>

        {/* Stat 3: Empirical Uncertainty */}
        <div className="p-space-md rounded-xl bg-surface-container-lowest border border-surface-container shadow-sm flex flex-col justify-between">
          <div className="flex items-center justify-between text-secondary">
            <span className="font-label-sm text-label-sm font-semibold uppercase">
              95% Dispersion Radius
            </span>
            <ShieldCheck className="w-4 h-4 text-sky-500" />
          </div>
          <div className="mt-2">
            <div className="font-headline-lg text-headline-lg font-bold text-sky-600">
              {ocean_drift.uncertainty.radius_km.toFixed(3)} km
            </div>
            <div className="font-data-mono-sm text-[11px] text-on-surface-variant mt-1">
              40 particles • 4h backward Euler hindcast
            </div>
          </div>
        </div>

        {/* Stat 4: Top Ranked Suspect */}
        <div className="p-space-md rounded-xl bg-surface-container-lowest border border-surface-container shadow-sm flex flex-col justify-between">
          <div className="flex items-center justify-between text-secondary">
            <span className="font-label-sm text-label-sm font-semibold uppercase">
              Primary Attributed Vessel
            </span>
            <Ship className="w-4 h-4 text-rose-500" />
          </div>
          <div className="mt-2">
            <div className="font-headline-lg text-headline-lg font-bold text-rose-600 truncate">
              {candidate_vessels[0]?.vessel_name || "PACIFIC VOYAGER"}
            </div>
            <div className="font-data-mono-sm text-[11px] text-on-surface-variant mt-1">
              Attribution Score:{" "}
              <strong className="text-rose-600">
                {((candidate_vessels[0]?.scores.overall || 0.954) * 100).toFixed(1)}%
              </strong>{" "}
              (Rank #1)
            </div>
          </div>
        </div>
      </div>

      {/* Main Command View: MapLibre GIS (Left 8 Cols) + Attribution & Metadata (Right 4 Cols) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-space-lg items-start">
        {/* Left Column: Interactive MapLibre GIS */}
        <div className="lg:col-span-8 flex flex-col gap-space-md">
          <div className="bg-surface-container-lowest rounded-xl p-space-sm border border-surface-container shadow-sm flex flex-col gap-2">
            <div className="flex items-center justify-between px-2 pt-1">
              <div className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-primary"></span>
                <h2 className="font-headline-sm text-headline-sm text-on-surface font-semibold">
                  Interactive GIS Evidence Canvas
                </h2>
              </div>
              <button
                type="button"
                onClick={() => onNavigate("live-map")}
                className="text-primary hover:underline text-xs font-semibold flex items-center gap-1 cursor-pointer"
              >
                <span>Full-Screen GIS Command</span>
                <ArrowRight className="w-3 h-3" />
              </button>
            </div>

            {/* MapLibre GL JS Container */}
            <MapLibreGIS
              result={pipelineData}
              selectedVessel={selectedVessel}
              onSelectVessel={(v) => {
                setSelectedVessel(v);
                onNavigate("vessel-analysis");
              }}
              height="520px"
            />
          </div>

          {/* Radar Evidence Comparison Card */}
          <div className="bg-surface-container-lowest rounded-xl p-space-md border border-surface-container shadow-sm flex flex-col">
            <div className="flex items-center justify-between pb-2 border-b border-surface-container-low mb-2">
              <h3 className="font-headline-sm text-headline-sm text-on-surface font-semibold">
                Multi-Criteria Evidence Weighting Breakdown
              </h3>
              <span className="font-data-mono-sm text-xs text-secondary">
                Spatial 40% • Temporal 35% • Trajectory 15% • Behaviour 10%
              </span>
            </div>
            <AttributionRadarChart
              candidates={candidate_vessels}
              selectedVessel={selectedVessel}
            />
          </div>
        </div>

        {/* Right Column: GIS Metadata & Ranked Suspects */}
        <div className="lg:col-span-4 flex flex-col gap-space-md">
          {/* Member 3 GIS Measurement Card */}
          <SpillMetadataCard metadata={spill_metadata} measurement={gis_measurement} />

          {/* Ranked Candidates Panel */}
          <div className="h-[420px]">
            <AttributionPanel
              candidates={candidate_vessels}
              selectedVessel={selectedVessel}
              onSelectVessel={(v) => setSelectedVessel(v)}
              onOpenDossier={(v) => {
                setSelectedVessel(v);
                if (onOpenDossier) onOpenDossier();
              }}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
