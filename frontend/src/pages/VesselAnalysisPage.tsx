import React, { useState, useEffect } from "react";
import { NavPath } from "../components/Sidebar";
import { MapLibreGIS } from "../map/MapLibreGIS";
import { AttributionRadarChart } from "../charts/AttributionRadarChart";
import { KinematicSpeedChart } from "../charts/KinematicSpeedChart";
import { EndToEndResult, CandidateVessel } from "../types";
import { getActivePipelineResult } from "../services/api";
import { BASELINE_DEMO_RESULT } from "../services/demoDataAdapter";
import {
  Ship,
  FileText,
  Clock,
  Compass,
  Scale,
  Activity,
  AlertTriangle,
  CheckCircle2,
  ChevronRight,
  ShieldAlert,
} from "lucide-react";

interface VesselAnalysisPageProps {
  onNavigate: (path: NavPath) => void;
  onOpenDossier?: () => void;
}

export function VesselAnalysisPage({ onNavigate, onOpenDossier }: VesselAnalysisPageProps) {
  const [pipelineData, setPipelineData] = useState<EndToEndResult>(BASELINE_DEMO_RESULT);
  const [selectedVessel, setSelectedVessel] = useState<CandidateVessel | null>(
    BASELINE_DEMO_RESULT.primary_suspect
  );
  const [searchQuery, setSearchQuery] = useState("");

  useEffect(() => {
    getActivePipelineResult().then((data) => {
      setPipelineData(data);
      if (data.primary_suspect) {
        setSelectedVessel(data.primary_suspect);
      }
    });
  }, []);

  const candidates = pipelineData.candidate_vessels || [];

  const filteredCandidates = candidates.filter(
    (c) =>
      c.vessel_name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      c.mmsi.toString().includes(searchQuery) ||
      c.imo.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div className="flex flex-col w-full gap-space-lg">
      {/* Top Header & Actions */}
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
            <span className="text-on-surface font-semibold">{pipelineData.spill_metadata.spill_id}</span>
            <span className="text-outline-variant">/</span>
            <span className="text-primary font-bold">Vessel Attribution Ranking</span>
          </div>
          <h1 className="font-headline-xl text-headline-xl text-on-surface tracking-tight font-bold">
            AIS Trajectory Correlation &amp; Attribution
          </h1>
          <p className="font-body-md text-body-md text-on-surface-variant">
            4-tier multi-criteria scoring model (Spatial 40%, Temporal 35%, Trajectory 15%, Behaviour 10%)
            ranking correlated maritime traffic against the estimated discharge origin.
          </p>
        </div>

        {/* Action Buttons */}
        <div className="flex items-center gap-space-sm flex-wrap">
          <button
            type="button"
            onClick={onOpenDossier}
            className="flex items-center gap-space-xs px-space-md py-2 rounded-lg bg-surface-container text-on-surface hover:bg-surface-container-high transition-colors font-label-md text-label-md cursor-pointer border border-surface-container"
          >
            <ShieldAlert className="w-4 h-4 text-rose-500" />
            <span>Port State Control Notice</span>
          </button>

          <button
            type="button"
            onClick={onOpenDossier}
            className="flex items-center gap-space-xs px-space-lg py-2 rounded-lg bg-primary-container text-on-primary hover:bg-primary transition-colors font-label-md text-label-md font-semibold cursor-pointer shadow-sm"
          >
            <FileText className="w-4 h-4" />
            <span>Generate Full Dossier</span>
          </button>
        </div>
      </div>

      {/* Main Grid: 8 Cols Left (Table + Kinematics), 4 Cols Right (Suspect Details & Map) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-space-lg items-start">
        {/* Left 8 Cols: Ranked Candidates Table & Kinematics */}
        <div className="lg:col-span-8 flex flex-col gap-space-md">
          {/* Candidates Table Card */}
          <div className="bg-surface-container-lowest rounded-xl p-space-md border border-surface-container shadow-sm flex flex-col">
            <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-space-sm pb-3 border-b border-surface-container-low mb-3">
              <div className="flex items-center gap-2">
                <Ship className="w-5 h-5 text-rose-500" />
                <h3 className="font-headline-sm text-headline-sm text-on-surface font-semibold">
                  Ranked Maritime Candidates
                </h3>
                <span className="font-data-mono-sm text-xs px-2 py-0.5 rounded-full bg-surface-container text-secondary font-bold">
                  {candidates.length} Survived Spatial/Temporal Filters
                </span>
              </div>

              <input
                type="text"
                placeholder="Search MMSI or name..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="px-3 py-1.5 rounded-lg bg-surface-container-low border border-surface-container text-xs text-on-surface w-full sm:w-56 focus:outline-none focus:ring-1 focus:ring-primary font-mono"
              />
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left font-mono text-xs text-on-surface">
                <thead>
                  <tr className="border-b border-surface-container-low text-secondary text-[11px] uppercase">
                    <th className="py-2.5 px-2">Rank</th>
                    <th className="py-2.5 px-2">Vessel Details</th>
                    <th className="py-2.5 px-2 text-center">Overall Score</th>
                    <th className="py-2.5 px-2 text-center">Min Distance</th>
                    <th className="py-2.5 px-2 text-center">Time Offset</th>
                    <th className="py-2.5 px-2 text-center">Speed</th>
                    <th className="py-2.5 px-2 text-right">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-surface-container-low">
                  {filteredCandidates.map((c) => {
                    const isSelected = selectedVessel?.mmsi === c.mmsi;
                    const isPrimary = c.rank === 1;

                    return (
                      <tr
                        key={c.mmsi}
                        onClick={() => setSelectedVessel(c)}
                        className={`cursor-pointer transition-colors ${
                          isSelected
                            ? "bg-primary-fixed/20 font-bold"
                            : isPrimary
                            ? "bg-rose-50/50 hover:bg-rose-50"
                            : "hover:bg-surface-container-low"
                        }`}
                      >
                        <td className="py-3 px-2">
                          <span
                            className={`w-6 h-6 rounded-full inline-flex items-center justify-center font-bold text-xs ${
                              isPrimary ? "bg-rose-600 text-white" : "bg-slate-700 text-white"
                            }`}
                          >
                            #{c.rank}
                          </span>
                        </td>
                        <td className="py-3 px-2">
                          <div className="font-bold text-sm text-on-surface font-sans flex items-center gap-1.5">
                            {c.vessel_name}
                            {isPrimary && (
                              <span className="text-[10px] px-1.5 py-0.2 rounded bg-rose-100 text-rose-800 font-bold border border-rose-300">
                                PRIMARY
                              </span>
                            )}
                          </div>
                          <div className="text-[11px] text-secondary">
                            MMSI: {c.mmsi} • IMO: {c.imo}
                          </div>
                        </td>
                        <td className="py-3 px-2 text-center">
                          <span
                            className={`px-2 py-0.5 rounded font-bold ${
                              isPrimary
                                ? "bg-rose-600 text-white"
                                : "bg-surface-container text-on-surface"
                            }`}
                          >
                            {(c.scores.overall * 100).toFixed(1)}%
                          </span>
                        </td>
                        <td className="py-3 px-2 text-center font-semibold text-on-surface">
                          {c.metrics.min_distance_km.toFixed(3)} km
                        </td>
                        <td className="py-3 px-2 text-center text-secondary">
                          {c.metrics.time_difference_minutes.toFixed(0)} min
                        </td>
                        <td className="py-3 px-2 text-center text-secondary">
                          {c.metrics.transit_speed_knots.toFixed(1)} kn
                        </td>
                        <td className="py-3 px-2 text-right">
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              setSelectedVessel(c);
                              onNavigate("vessel-detail");
                            }}
                            className="text-primary hover:underline font-sans font-semibold text-xs inline-flex items-center"
                          >
                            Details <ChevronRight className="w-3.5 h-3.5" />
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>

          {/* Kinematic Speed & Distance Profile (Apache ECharts) */}
          <div className="bg-surface-container-lowest rounded-xl p-space-md border border-surface-container shadow-sm flex flex-col">
            <div className="flex items-center justify-between pb-2 border-b border-surface-container-low mb-2">
              <h3 className="font-headline-sm text-headline-sm text-on-surface font-semibold flex items-center gap-2">
                <Activity className="w-4 h-4 text-sky-500" />
                Kinematic Speed &amp; Closest Point of Approach (CPA) Profile
              </h3>
              <span className="font-data-mono-sm text-xs text-secondary">
                Target: {selectedVessel?.vessel_name || "PACIFIC VOYAGER"}
              </span>
            </div>
            <KinematicSpeedChart
              vesselName={selectedVessel?.vessel_name}
              speedKnots={selectedVessel?.metrics.transit_speed_knots}
            />
          </div>
        </div>

        {/* Right 4 Cols: Radar Evidence & Candidate Profile */}
        <div className="lg:col-span-4 flex flex-col gap-space-md">
          {/* Radar Weighting Comparison */}
          <div className="bg-surface-container-lowest rounded-xl p-space-md border border-surface-container shadow-sm flex flex-col">
            <h3 className="font-headline-sm text-headline-sm text-on-surface font-semibold pb-2 border-b border-surface-container-low flex items-center gap-2">
              <Scale className="w-4 h-4 text-purple-500" />
              Evidence Matrix Comparison
            </h3>
            <div className="text-[11px] text-secondary font-mono mt-1 mb-2">
              Spatial (40%) • Temporal (35%) • Trajectory (15%) • Behaviour (10%)
            </div>
            <AttributionRadarChart
              candidates={candidates}
              selectedVessel={selectedVessel}
            />
          </div>

          {/* Selected Vessel Inspector Card */}
          {selectedVessel && (
            <div className="bg-surface-container-lowest rounded-xl p-space-md border border-surface-container shadow-sm flex flex-col gap-space-sm">
              <div className="flex items-center justify-between pb-2 border-b border-surface-container-low">
                <div>
                  <h4 className="font-bold text-sm text-on-surface">
                    {selectedVessel.vessel_name}
                  </h4>
                  <p className="text-[11px] text-secondary font-mono">
                    MMSI: {selectedVessel.mmsi} • IMO: {selectedVessel.imo}
                  </p>
                </div>
                <span className="text-xs px-2.5 py-1 rounded bg-rose-100 text-rose-800 font-bold border border-rose-300">
                  Rank #{selectedVessel.rank}
                </span>
              </div>

              {/* 4 Score Bars */}
              <div className="space-y-2 text-xs font-mono">
                <div>
                  <div className="flex justify-between text-[11px] mb-0.5">
                    <span className="text-secondary">Spatial Proximity (40%)</span>
                    <span className="font-bold text-sky-600">
                      {(selectedVessel.scores.spatial * 100).toFixed(1)}%
                    </span>
                  </div>
                  <div className="w-full bg-surface-container rounded-full h-1.5">
                    <div
                      className="bg-sky-500 h-1.5 rounded-full"
                      style={{ width: `${selectedVessel.scores.spatial * 100}%` }}
                    />
                  </div>
                </div>

                <div>
                  <div className="flex justify-between text-[11px] mb-0.5">
                    <span className="text-secondary">Temporal Coincidence (35%)</span>
                    <span className="font-bold text-emerald-600">
                      {(selectedVessel.scores.temporal * 100).toFixed(1)}%
                    </span>
                  </div>
                  <div className="w-full bg-surface-container rounded-full h-1.5">
                    <div
                      className="bg-emerald-500 h-1.5 rounded-full"
                      style={{ width: `${selectedVessel.scores.temporal * 100}%` }}
                    />
                  </div>
                </div>

                <div>
                  <div className="flex justify-between text-[11px] mb-0.5">
                    <span className="text-secondary">Trajectory Alignment (15%)</span>
                    <span className="font-bold text-amber-600">
                      {(selectedVessel.scores.trajectory * 100).toFixed(1)}%
                    </span>
                  </div>
                  <div className="w-full bg-surface-container rounded-full h-1.5">
                    <div
                      className="bg-amber-500 h-1.5 rounded-full"
                      style={{ width: `${selectedVessel.scores.trajectory * 100}%` }}
                    />
                  </div>
                </div>

                <div>
                  <div className="flex justify-between text-[11px] mb-0.5">
                    <span className="text-secondary">Kinematic Behaviour (10%)</span>
                    <span className="font-bold text-purple-600">
                      {(selectedVessel.scores.behaviour * 100).toFixed(1)}%
                    </span>
                  </div>
                  <div className="w-full bg-surface-container rounded-full h-1.5">
                    <div
                      className="bg-purple-500 h-1.5 rounded-full"
                      style={{ width: `${selectedVessel.scores.behaviour * 100}%` }}
                    />
                  </div>
                </div>
              </div>

              {/* Automated Explanation Narrative */}
              <div className="mt-2 p-3 rounded-lg bg-surface-container-low border border-surface-container text-xs text-on-surface font-sans">
                <span className="font-bold text-on-surface block mb-1">Attribution Finding:</span>
                <ul className="space-y-1 list-disc list-inside text-secondary text-[11px]">
                  {selectedVessel.explanation?.map((exp, i) => (
                    <li key={i}>{exp}</li>
                  )) || (
                    <>
                      <li>Transit trajectory directly intersects the 95% spatial dispersion envelope.</li>
                      <li>Closest point of approach occurs concurrently with the estimated release time.</li>
                    </>
                  )}
                </ul>
              </div>

              <button
                type="button"
                onClick={onOpenDossier}
                className="mt-1 w-full py-2 rounded-lg bg-primary-container text-on-primary font-semibold text-xs hover:bg-primary transition-colors cursor-pointer shadow-sm"
              >
                Inspect Full Evidence Dossier
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
