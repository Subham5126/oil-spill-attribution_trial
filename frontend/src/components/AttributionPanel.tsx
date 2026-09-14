import React from "react";
import { CandidateVessel } from "../types";
import {
  Ship,
  FileText,
  Clock,
  Navigation,
  Activity,
  CheckCircle2,
  ChevronRight,
  AlertOctagon,
} from "lucide-react";

interface AttributionPanelProps {
  candidates: CandidateVessel[];
  selectedVessel: CandidateVessel | null;
  onSelectVessel: (vessel: CandidateVessel) => void;
  onOpenDossier: (vessel: CandidateVessel) => void;
}

export const AttributionPanel: React.FC<AttributionPanelProps> = ({
  candidates,
  selectedVessel,
  onSelectVessel,
  onOpenDossier,
}) => {
  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 shadow-xl flex flex-col h-full">
      <div className="flex items-center justify-between pb-3 border-b border-slate-800 mb-3">
        <div>
          <h3 className="font-bold text-slate-100 text-sm flex items-center gap-2">
            <Ship className="w-4 h-4 text-rose-400" />
            Ranked Candidate Vessels
          </h3>
          <p className="text-xs text-slate-400">
            Multi-factor spatial (40%), temporal (35%), trajectory (15%) &amp; behaviour (10%)
          </p>
        </div>
        <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700">
          {candidates.length} Correlated
        </span>
      </div>

      {/* Candidate List */}
      <div className="space-y-3 overflow-y-auto pr-1 flex-1">
        {candidates.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-48 text-center px-4 py-6 border border-dashed border-slate-800 rounded-lg bg-slate-900/50">
            <AlertOctagon className="w-8 h-8 text-amber-500 mb-2" />
            <h4 className="text-sm font-semibold text-slate-200">NO AIS CANDIDATES</h4>
            <p className="text-xs text-slate-400 mt-1">
              No vessels found matching the spatial and temporal window of the detected spill.
            </p>
            <span className="mt-2 text-[11px] font-mono px-2 py-0.5 rounded bg-amber-950/40 text-amber-400 border border-amber-800/50">
              STATUS: NO_DATA_FEED
            </span>
          </div>
        ) : (
          candidates.map((candidate) => {
          const isSelected = selectedVessel?.mmsi === candidate.mmsi;
          const isPrimary = candidate.rank === 1;

          const badgeColor =
            candidate.confidence_category === "High Suspect" || isPrimary
              ? "bg-rose-950/70 text-rose-300 border-rose-800"
              : "bg-amber-950/70 text-amber-300 border-amber-800";

          const progressColor =
            candidate.confidence_category === "High Suspect" || isPrimary
              ? "bg-rose-500"
              : "bg-amber-500";

          return (
            <div
              key={candidate.mmsi}
              onClick={() => onSelectVessel(candidate)}
              className={`p-3 rounded-lg border cursor-pointer transition-all ${
                isSelected
                  ? "bg-slate-800/90 border-sky-500 ring-1 ring-sky-500/40"
                  : isPrimary
                  ? "bg-slate-850/60 border-rose-900/70 hover:border-rose-700/70"
                  : "bg-slate-950/60 border-slate-800 hover:border-slate-700"
              }`}
            >
              {/* Header */}
              <div className="flex items-start justify-between gap-2">
                <div className="flex items-center gap-2">
                  <span
                    className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold ${
                      isPrimary ? "bg-rose-600 text-white" : "bg-slate-800 text-slate-300"
                    }`}
                  >
                    #{candidate.rank}
                  </span>
                  <div>
                    <div className="font-semibold text-sm text-slate-100 flex items-center gap-1.5">
                      {candidate.vessel_name}
                      {isPrimary && (
                        <span className="text-[10px] px-1.5 py-0.2 rounded bg-rose-950 text-rose-300 font-bold border border-rose-800">
                          PRIMARY SUSPECT
                        </span>
                      )}
                    </div>
                    <div className="text-[11px] text-slate-400 font-mono">
                      MMSI: {candidate.mmsi} • IMO: {candidate.imo}
                    </div>
                  </div>
                </div>

                <span className={`text-[10px] font-semibold px-2 py-0.5 rounded border ${badgeColor}`}>
                  {(((candidate.scores?.overall ?? 0)) * 100).toFixed(1)}% Score
                </span>
              </div>

              {/* Progress bar */}
              <div className="mt-2.5 w-full bg-slate-950 rounded-full h-1.5 overflow-hidden border border-slate-800">
                <div
                  className={`h-full ${progressColor}`}
                  style={{ width: `${Math.min(100, (candidate.scores?.overall ?? 0) * 100)}%` }}
                />
              </div>

              {/* Multi-Factor Metrics Breakdown */}
              <div className="mt-3 grid grid-cols-4 gap-1.5 text-center font-mono text-[10px]">
                <div className="bg-slate-950 p-1.5 rounded border border-slate-850">
                  <span className="text-slate-400 block text-[9px]">Spatial (40%)</span>
                  <span className="font-bold text-sky-400">
                    {(((candidate.scores?.spatial ?? 0)) * 100).toFixed(0)}%
                  </span>
                </div>
                <div className="bg-slate-950 p-1.5 rounded border border-slate-855">
                  <span className="text-slate-400 block text-[9px]">Temporal (35%)</span>
                  <span className="font-bold text-emerald-400">
                    {(((candidate.scores?.temporal ?? 0)) * 100).toFixed(0)}%
                  </span>
                </div>
                <div className="bg-slate-950 p-1.5 rounded border border-slate-855">
                  <span className="text-slate-400 block text-[9px]">Track (15%)</span>
                  <span className="font-bold text-amber-400">
                    {(((candidate.scores?.trajectory ?? 0)) * 100).toFixed(0)}%
                  </span>
                </div>
                <div className="bg-slate-950 p-1.5 rounded border border-slate-855">
                  <span className="text-slate-400 block text-[9px]">Behaviour (10%)</span>
                  <span className="font-bold text-purple-400">
                    {(((candidate.scores?.behaviour ?? 0)) * 100).toFixed(0)}%
                  </span>
                </div>
              </div>

              {/* Telemetry Details */}
              <div className="mt-2 flex items-center justify-between text-[11px] text-slate-400 font-mono pt-2 border-t border-slate-800/60">
                <div>
                  Min Dist:{" "}
                  <strong className={isPrimary ? "text-rose-400" : "text-slate-200"}>
                    {(candidate.metrics?.min_distance_km ?? candidate.min_distance_km ?? candidate.distance_to_track_km ?? 0).toFixed(3)} km
                  </strong>
                </div>
                <div>
                  Offset:{" "}
                  <strong className="text-slate-200">
                    {(candidate.metrics?.time_difference_minutes ?? 0).toFixed(0)} min
                  </strong>
                </div>
                <div>
                  Speed:{" "}
                  <strong className="text-slate-200">
                    {(candidate.metrics?.transit_speed_knots ?? 0).toFixed(1)} kn
                  </strong>
                </div>
              </div>

              {/* Action Ribbon */}
              <div className="mt-2.5 flex items-center justify-end gap-2">
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    onOpenDossier(candidate);
                  }}
                  className="px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 text-[11px] font-semibold flex items-center gap-1 transition-colors"
                >
                  <FileText className="w-3.5 h-3.5 text-sky-400" />
                  Legal Dossier
                </button>
              </div>
            </div>
          );
        }))}
      </div>
    </div>
  );
};
