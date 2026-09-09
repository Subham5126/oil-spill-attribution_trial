import React, { useState, useEffect } from "react";
import { NavPath } from "../components/Sidebar";
import { KinematicSpeedChart } from "../charts/KinematicSpeedChart";
import { AttributionRadarChart } from "../charts/AttributionRadarChart";
import { EndToEndResult, CandidateVessel } from "../types";
import { getActivePipelineResult } from "../services/api";
import { BASELINE_DEMO_RESULT } from "../services/demoDataAdapter";
import {
  Ship,
  FileText,
  Clock,
  Navigation,
  Compass,
  Scale,
  ShieldAlert,
  Printer,
  ChevronLeft,
  CheckCircle2,
  AlertTriangle,
} from "lucide-react";

interface VesselDetailPageProps {
  onNavigate: (path: NavPath) => void;
  onOpenDossier?: () => void;
}

export function VesselDetailPage({ onNavigate, onOpenDossier }: VesselDetailPageProps) {
  const [pipelineData, setPipelineData] = useState<EndToEndResult>(BASELINE_DEMO_RESULT);
  const [vessel, setVessel] = useState<CandidateVessel>(BASELINE_DEMO_RESULT.primary_suspect);

  useEffect(() => {
    getActivePipelineResult().then((data) => {
      setPipelineData(data);
      if (data.primary_suspect) {
        setVessel(data.primary_suspect);
      }
    });
  }, []);

  return (
    <div className="flex flex-col w-full gap-space-lg">
      {/* Top Header & Breadcrumbs */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-space-md">
        <div className="flex flex-col gap-space-2xs">
          <div className="flex items-center gap-space-xs text-on-surface-variant font-label-sm text-label-sm">
            <button
              type="button"
              onClick={() => onNavigate("vessel-analysis")}
              className="hover:text-primary transition-colors cursor-pointer flex items-center gap-1"
            >
              <ChevronLeft className="w-4 h-4" />
              <span>Back to Candidate Vessels</span>
            </button>
            <span className="text-outline-variant">/</span>
            <span className="text-primary font-bold">{vessel.vessel_name}</span>
          </div>
          <div className="flex items-center gap-3">
            <h1 className="font-headline-xl text-headline-xl text-on-surface tracking-tight font-bold">
              {vessel.vessel_name}
            </h1>
            <span className="px-2.5 py-1 rounded bg-rose-600 text-white font-bold text-xs shadow-sm">
              Rank #{vessel.rank} Suspect
            </span>
          </div>
          <p className="font-body-md text-body-md text-on-surface-variant font-mono">
            MMSI: {vessel.mmsi} • IMO: {vessel.imo} • Attribution Score:{" "}
            <strong className="text-rose-600">{(vessel.scores.overall * 100).toFixed(1)}%</strong>
          </p>
        </div>

        {/* Action Buttons */}
        <div className="flex items-center gap-space-sm flex-wrap">
          <button
            type="button"
            onClick={() => window.print()}
            className="flex items-center gap-space-xs px-space-md py-2 rounded-lg bg-surface-container text-on-surface hover:bg-surface-container-high transition-colors font-label-md text-label-md cursor-pointer border border-surface-container"
          >
            <Printer className="w-4 h-4" />
            <span>Print Report</span>
          </button>
          <button
            type="button"
            onClick={onOpenDossier}
            className="flex items-center gap-space-xs px-space-lg py-2 rounded-lg bg-primary-container text-on-primary hover:bg-primary transition-colors font-label-md text-label-md font-semibold cursor-pointer shadow-sm"
          >
            <FileText className="w-4 h-4" />
            <span>Legal Prosecution Dossier</span>
          </button>
        </div>
      </div>

      {/* Grid: 4 Metric Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-space-md">
        <div className="p-space-md rounded-xl bg-surface-container-lowest border border-surface-container shadow-sm">
          <span className="font-label-sm text-label-sm text-secondary uppercase font-semibold">
            Closest Point of Approach
          </span>
          <div className="mt-1 font-headline-lg text-headline-lg font-bold text-rose-600 font-mono">
            {vessel.metrics.min_distance_km.toFixed(3)} km
          </div>
          <span className="text-[11px] text-on-surface-variant font-mono">
            Inside 95% dispersion radius (1.885 km)
          </span>
        </div>

        <div className="p-space-md rounded-xl bg-surface-container-lowest border border-surface-container shadow-sm">
          <span className="font-label-sm text-label-sm text-secondary uppercase font-semibold">
            Temporal Coincidence
          </span>
          <div className="mt-1 font-headline-lg text-headline-lg font-bold text-emerald-600 font-mono">
            {vessel.metrics.time_difference_minutes.toFixed(0)} min offset
          </div>
          <span className="text-[11px] text-on-surface-variant font-mono">
            Concurrent with 01:00 UTC release window
          </span>
        </div>

        <div className="p-space-md rounded-xl bg-surface-container-lowest border border-surface-container shadow-sm">
          <span className="font-label-sm text-label-sm text-secondary uppercase font-semibold">
            Transit Speed Profile
          </span>
          <div className="mt-1 font-headline-lg text-headline-lg font-bold text-sky-600 font-mono">
            {vessel.metrics.transit_speed_knots.toFixed(1)} kn
          </div>
          <span className="text-[11px] text-on-surface-variant font-mono">
            Operational en-route transit speed
          </span>
        </div>

        <div className="p-space-md rounded-xl bg-surface-container-lowest border border-surface-container shadow-sm">
          <span className="font-label-sm text-label-sm text-secondary uppercase font-semibold">
            MARPOL Violation Risk
          </span>
          <div className="mt-1 font-headline-lg text-headline-lg font-bold text-rose-600 font-sans">
            CRITICAL HIGH
          </div>
          <span className="text-[11px] text-on-surface-variant font-mono">
            Annex I Reg 15 discharge criteria breached
          </span>
        </div>
      </div>

      {/* Main Charts: Radar & Speed Line */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-space-lg">
        {/* Radar Chart */}
        <div className="bg-surface-container-lowest rounded-xl p-space-md border border-surface-container shadow-sm flex flex-col">
          <h3 className="font-headline-sm text-headline-sm text-on-surface font-semibold pb-2 border-b border-surface-container-low mb-2 flex items-center gap-2">
            <Scale className="w-4 h-4 text-primary" />
            4-Tier Attribution Weight Breakdown
          </h3>
          <AttributionRadarChart
            candidates={pipelineData.candidate_vessels}
            selectedVessel={vessel}
          />
        </div>

        {/* Speed Chart */}
        <div className="bg-surface-container-lowest rounded-xl p-space-md border border-surface-container shadow-sm flex flex-col">
          <h3 className="font-headline-sm text-headline-sm text-on-surface font-semibold pb-2 border-b border-surface-container-low mb-2 flex items-center gap-2">
            <Navigation className="w-4 h-4 text-sky-500" />
            Kinematic Speed Profile &amp; CPA Trajectory
          </h3>
          <KinematicSpeedChart
            vesselName={vessel.vessel_name}
            speedKnots={vessel.metrics.transit_speed_knots}
          />
        </div>
      </div>

      {/* Forensic Timeline Events */}
      <div className="bg-surface-container-lowest rounded-xl p-space-md border border-surface-container shadow-sm flex flex-col">
        <h3 className="font-headline-sm text-headline-sm text-on-surface font-semibold pb-3 border-b border-surface-container-low mb-4 flex items-center gap-2">
          <Clock className="w-4 h-4 text-emerald-500" />
          Forensic Incident Reconstruction Timeline
        </h3>
        <div className="space-y-4 font-sans text-xs">
          <div className="flex items-start gap-3">
            <span className="w-2.5 h-2.5 rounded-full bg-slate-400 mt-1 shrink-0" />
            <div>
              <div className="font-bold text-on-surface font-mono">2025-01-01 00:15 UTC — Entrance to Basin</div>
              <p className="text-secondary mt-0.5">
                Vessel entered AIS observation corridor cruising steady at 12.4 knots. Heading 142°.
              </p>
            </div>
          </div>
          <div className="flex items-start gap-3">
            <span className="w-2.5 h-2.5 rounded-full bg-rose-600 mt-1 shrink-0 animate-ping" />
            <div>
              <div className="font-bold text-rose-600 font-mono">
                2025-01-01 01:00 UTC — Intercept at Probable Origin (CPA)
              </div>
              <p className="text-on-surface mt-0.5 leading-relaxed">
                Vessel position logged at <strong>18.527°N, 72.505°E</strong>, within <strong>0.572 km</strong> of
                the estimated spill release centroid. Concurrent release window established by backward Lagrangian simulation.
              </p>
            </div>
          </div>
          <div className="flex items-start gap-3">
            <span className="w-2.5 h-2.5 rounded-full bg-slate-400 mt-1 shrink-0" />
            <div>
              <div className="font-bold text-on-surface font-mono">2025-01-01 01:45 UTC — Corridor Departure</div>
              <p className="text-secondary mt-0.5">
                Target maintained continuous Class-A transmission departing corridor southward towards Gujarat corridor.
              </p>
            </div>
          </div>
          <div className="flex items-start gap-3">
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-600 mt-1 shrink-0" />
            <div>
              <div className="font-bold text-emerald-600 font-mono">
                2025-01-01 05:00 UTC — Sentinel-1 SAR Detection
              </div>
              <p className="text-secondary mt-0.5">
                Satellite radar pass confirmed 3.9275 km² surface slick displaced westward by 4h ocean advection.
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
