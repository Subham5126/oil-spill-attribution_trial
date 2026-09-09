import React, { useState, useEffect } from "react";
import { NavPath } from "../components/Sidebar";
import { MapLibreGIS } from "../map/MapLibreGIS";
import { TimelineController } from "../components/TimelineController";
import { EndToEndResult } from "../types";
import { getActivePipelineResult } from "../services/api";
import { BASELINE_DEMO_RESULT } from "../services/demoDataAdapter";
import {
  Compass,
  Waves,
  Wind,
  ShieldCheck,
  RotateCcw,
  ArrowRight,
  Info,
  Clock,
  Layers,
} from "lucide-react";

interface DriftAnalysisPageProps {
  onNavigate: (path: NavPath) => void;
  onOpenDossier?: () => void;
}

export function DriftAnalysisPage({ onNavigate, onOpenDossier }: DriftAnalysisPageProps) {
  const [pipelineData, setPipelineData] = useState<EndToEndResult>(BASELINE_DEMO_RESULT);
  const [simOffsetHours, setSimOffsetHours] = useState<number>(-4);

  useEffect(() => {
    getActivePipelineResult().then(setPipelineData);
  }, []);

  const { ocean_drift, gis_measurement, spill_metadata } = pipelineData;
  const { probable_origin, uncertainty } = ocean_drift;

  return (
    <div className="flex flex-col w-full gap-space-lg">
      {/* Top Breadcrumb & Actions */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-space-md">
        <div className="flex flex-col gap-space-2xs">
          <div className="flex items-center gap-space-xs text-on-surface-variant font-label-sm text-label-sm">
            <button
              type="button"
              onClick={() => onNavigate("investigations")}
              className="hover:text-primary transition-colors cursor-pointer"
            >
              Investigations
            </button>
            <span className="text-outline-variant">/</span>
            <span className="text-on-surface font-semibold">{spill_metadata.spill_id}</span>
            <span className="text-outline-variant">/</span>
            <span className="text-primary font-bold">Ocean &amp; Drift Hindcast</span>
          </div>
          <h1 className="font-headline-xl text-headline-xl text-on-surface tracking-tight font-bold">
            Lagrangian Drift Hindcasting &amp; Origin Estimation
          </h1>
          <p className="font-body-md text-body-md text-on-surface-variant">
            Eulerian-Lagrangian particle advection model using Copernicus marine currents and ERA5 surface wind fields.
          </p>
        </div>

        {/* Action Button */}
        <div className="flex items-center gap-space-sm flex-wrap">
          <button
            type="button"
            onClick={() => onNavigate("vessel-analysis")}
            className="flex items-center gap-space-xs px-space-lg py-2 rounded-lg bg-primary-container text-on-primary hover:bg-primary transition-colors font-label-md text-label-md font-semibold cursor-pointer shadow-sm"
          >
            <span>Correlate AIS Vessels</span>
            <span className="material-symbols-outlined text-[18px]">arrow_forward</span>
          </button>
        </div>
      </div>

      {/* Timeline Scrubber */}
      <TimelineController
        observationTime={spill_metadata.detection_timestamp}
        onTimeChange={(val) => setSimOffsetHours(val)}
      />

      {/* Main Grid: 8 Cols Map + 4 Cols MetOcean/Origin Stats */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-space-lg items-start">
        {/* Left 8 Cols: MapLibre GIS */}
        <div className="lg:col-span-8 flex flex-col gap-space-md">
          <div className="bg-surface-container-lowest rounded-xl p-space-sm border border-surface-container shadow-sm flex flex-col gap-2">
            <div className="flex items-center justify-between px-2 pt-1">
              <span className="font-headline-sm text-headline-sm text-on-surface font-semibold flex items-center gap-2">
                <Compass className="w-4 h-4 text-emerald-500" />
                Origin Localization &amp; Trajectory Drift Simulation
              </span>
              <span className="font-data-mono-sm text-xs text-emerald-600 font-bold">
                Origin @ {probable_origin.latitude.toFixed(4)}°N, {probable_origin.longitude.toFixed(4)}°E
              </span>
            </div>

            <MapLibreGIS result={pipelineData} height="560px" />
          </div>
        </div>

        {/* Right 4 Cols: Scientifically Correct Ocean/Drift Metrics */}
        <div className="lg:col-span-4 flex flex-col gap-space-md">
          {/* Probable Origin Card */}
          <div className="bg-surface-container-lowest rounded-xl p-space-md border border-surface-container shadow-sm flex flex-col gap-space-sm">
            <h3 className="font-headline-sm text-headline-sm text-on-surface font-semibold pb-2 border-b border-surface-container-low flex items-center gap-2">
              <Compass className="w-4 h-4 text-emerald-500" />
              Probable Spill Origin
            </h3>

            <div className="space-y-2.5 font-mono text-xs">
              <div className="flex justify-between p-2 rounded-lg bg-surface-container-low">
                <span className="text-secondary">Release Latitude:</span>
                <span className="font-bold text-on-surface">
                  {probable_origin.latitude.toFixed(6)}° N
                </span>
              </div>
              <div className="flex justify-between p-2 rounded-lg bg-surface-container-low">
                <span className="text-secondary">Release Longitude:</span>
                <span className="font-bold text-on-surface">
                  {probable_origin.longitude.toFixed(6)}° E
                </span>
              </div>
              <div className="flex justify-between p-2 rounded-lg bg-surface-container-low">
                <span className="text-secondary">Estimated Release Time:</span>
                <span className="font-bold text-on-surface">
                  {probable_origin.timestamp.replace("T", " ").replace("+00:00", "")} UTC
                </span>
              </div>
              <div className="flex justify-between p-2 rounded-lg bg-surface-container-low">
                <span className="text-secondary">Relative Heuristic Score:</span>
                <span className="font-bold text-emerald-600">
                  {probable_origin.relative_heuristic_score.toFixed(4)}
                </span>
              </div>
            </div>

            <div className="mt-1 p-2 rounded bg-surface-container-low/60 border border-surface-container text-[11px] text-secondary">
              <span className="font-bold text-on-surface block mb-0.5">Scientific Convention Notice:</span>
              Origin ranking is represented as a <em>Relative heuristic origin score</em> based on
              backward particle concentration peaks, not an uncalibrated probability.
            </div>
          </div>

          {/* Spatial Dispersion Uncertainty Card */}
          <div className="bg-surface-container-lowest rounded-xl p-space-md border border-surface-container shadow-sm flex flex-col gap-space-sm">
            <h3 className="font-headline-sm text-headline-sm text-on-surface font-semibold pb-2 border-b border-surface-container-low flex items-center gap-2">
              <ShieldCheck className="w-4 h-4 text-sky-500" />
              Empirical Spatial Dispersion
            </h3>

            <div className="space-y-2.5 font-mono text-xs">
              <div className="flex justify-between p-2 rounded-lg bg-surface-container-low">
                <span className="text-secondary">Dispersion Radius:</span>
                <span className="font-bold text-sky-600">
                  {uncertainty.radius_km.toFixed(3)} km
                </span>
              </div>
              <div className="flex justify-between p-2 rounded-lg bg-surface-container-low">
                <span className="text-secondary">Coverage Metric:</span>
                <span className="font-bold text-on-surface">
                  {uncertainty.dispersion_description}
                </span>
              </div>
              <div className="flex justify-between p-2 rounded-lg bg-surface-container-low">
                <span className="text-secondary">Particle Spread:</span>
                <span className="font-bold text-on-surface">
                  {uncertainty.spread_km.toFixed(3)} km
                </span>
              </div>
              <div className="flex justify-between p-2 rounded-lg bg-surface-container-low">
                <span className="text-secondary">Simulated Particles:</span>
                <span className="font-bold text-on-surface">
                  {ocean_drift.particles_simulated} Initialized
                </span>
              </div>
            </div>

            <div className="mt-1 p-2 rounded bg-surface-container-low/60 border border-surface-container text-[11px] text-secondary">
              <span className="font-bold text-on-surface block mb-0.5">Statistical Rigor:</span>
              The envelope is defined as a <strong>"95% empirical spatial dispersion estimate"</strong> derived
              from Lagrangian particle ensemble variance, rather than an assumed parametric distribution.
            </div>
          </div>

          {/* MetOcean Forcing Status */}
          <div className="bg-surface-container-lowest rounded-xl p-space-md border border-surface-container shadow-sm flex flex-col gap-space-xs font-mono text-xs">
            <h4 className="font-headline-sm text-headline-sm text-on-surface font-semibold pb-2 border-b border-surface-container-low">
              Environmental Forcing Status
            </h4>
            <div className="flex justify-between py-1 border-b border-surface-container-low">
              <span className="text-secondary flex items-center gap-1">
                <Waves className="w-3.5 h-3.5 text-sky-400" /> Ocean Currents:
              </span>
              <span className="text-emerald-600 font-bold">Copernicus CMEMS Active</span>
            </div>
            <div className="flex justify-between py-1 border-b border-surface-container-low">
              <span className="text-secondary flex items-center gap-1">
                <Wind className="w-3.5 h-3.5 text-amber-400" /> Surface Wind (10m):
              </span>
              <span className="text-emerald-600 font-bold">ECMWF ERA5 Active</span>
            </div>
            <div className="flex justify-between py-1 text-secondary">
              <span>Simulation Timestep:</span>
              <span className="text-on-surface font-bold">
                {ocean_drift.hindcast.timestep_seconds / 60} min (Forward/Backward Euler)
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
