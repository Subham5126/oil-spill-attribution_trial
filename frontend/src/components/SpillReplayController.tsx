/**
 * SpillReplayController: Forensic Incident Replay UI & Timeline Controls.
 *
 * Provides a professional maritime forensic reconstruction controller for
 * step-by-step or continuous animated playback of:
 * AIS Vessel Motion -> Possible Release -> Oil Dispersion -> Current Drift -> Detected Slick.
 */

import React, { useState, useEffect } from "react";
import {
  Play,
  Pause,
  RotateCcw,
  FastForward,
  Info,
  Compass,
  Ship,
  Wind,
  Layers,
  Crosshair,
  AlertTriangle,
  CheckCircle2,
  X,
  Minimize2,
  Maximize2,
} from "lucide-react";
import { ForensicReconstruction } from "../types";

interface SpillReplayControllerProps {
  reconstruction: ForensicReconstruction | null;
  isPlaying: boolean;
  progress: number; // 0.0 to 1.0
  playbackSpeed: number; // 0.5, 1, 2, 4
  currentStage: number; // 1 to 5
  onTogglePlay: () => void;
  onRestart: () => void;
  onSeek: (newProgress: number) => void;
  onSpeedChange: (newSpeed: number) => void;
  onClose: () => void;
  onFitInvestigation: () => void;
}

export const SpillReplayController: React.FC<SpillReplayControllerProps> = ({
  reconstruction,
  isPlaying,
  progress,
  playbackSpeed,
  currentStage,
  onTogglePlay,
  onRestart,
  onSeek,
  onSpeedChange,
  onClose,
  onFitInvestigation,
}) => {
  const [isMinimized, setIsMinimized] = useState<boolean>(false);

  // Check for reduced motion preference
  const prefersReducedMotion =
    typeof window !== "undefined" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // Format relative time (e.g. T+00:00 to T+72h)
  const formatRelativeTime = (p: number) => {
    const totalHours = reconstruction?.drift_trajectory?.total_distance_km
      ? Math.round((reconstruction.drift_trajectory.total_distance_km / 1.5) * 10) / 10
      : 72;
    const currentHours = Math.round(p * totalHours * 10) / 10;
    const hrs = Math.floor(currentHours);
    const mins = Math.round((currentHours - hrs) * 60);
    return `T+${hrs.toString().padStart(2, "0")}h ${mins.toString().padStart(2, "0")}m`;
  };

  // Interpolate real UTC timestamp from forensic timeline
  const formatUtcTime = (p: number) => {
    let startMs: number | null = null;
    let endMs: number | null = null;

    if (reconstruction?.ais_track?.waypoints?.[0]?.timestamp) {
      startMs = new Date(reconstruction.ais_track.waypoints[0].timestamp).getTime();
    } else if (reconstruction?.release_window?.start_time) {
      startMs = new Date(reconstruction.release_window.start_time).getTime();
    } else if (reconstruction?.probable_origin?.estimated_time) {
      startMs = new Date(reconstruction.probable_origin.estimated_time).getTime();
    }

    if (reconstruction?.spill_geometry?.detection_time) {
      endMs = new Date(reconstruction.spill_geometry.detection_time).getTime();
    }

    if (startMs && endMs && !isNaN(startMs) && !isNaN(endMs) && endMs > startMs) {
      const curDate = new Date(startMs + p * (endMs - startMs));
      return curDate.toISOString().replace("T", " ").substring(0, 19) + " UTC";
    }

    if (reconstruction?.probable_origin?.estimated_time) {
      return reconstruction.probable_origin.estimated_time.replace("T", " ").substring(0, 19) + " UTC";
    }

    return null;
  };

  const currentStageInfo = reconstruction?.timeline?.find((s) => s.stage === currentStage) || {
    stage: currentStage,
    name: "Forensic Analysis",
    description: "Reconstructing event sequence",
    timestamp: "N/A",
  };

  const status = reconstruction?.reconstruction_status || "FULL_RECONSTRUCTION";
  const vessel = reconstruction?.vessel;
  const current = reconstruction?.ocean_current;
  const spill = reconstruction?.spill_geometry;

  const speeds = [0.5, 1, 2, 4];
  const currentUtc = formatUtcTime(progress);

  if (isMinimized) {
    return (
      <div className="absolute top-3 left-3 z-30 flex items-center gap-2.5 bg-slate-950/95 backdrop-blur-md border border-slate-700/80 rounded-xl px-3 py-1.5 shadow-2xl text-slate-100 pointer-events-auto">
        <button
          type="button"
          onClick={onTogglePlay}
          title={isPlaying ? "Pause" : "Play"}
          className="p-1 rounded bg-cyan-500 hover:bg-cyan-400 text-slate-950 font-bold transition-colors cursor-pointer"
        >
          {isPlaying ? <Pause className="w-3.5 h-3.5 fill-current" /> : <Play className="w-3.5 h-3.5 fill-current" />}
        </button>

        <button
          type="button"
          onClick={onRestart}
          title="Restart Replay"
          className="p-1 rounded text-slate-400 hover:text-white transition-colors cursor-pointer"
        >
          <RotateCcw className="w-3 h-3" />
        </button>

        <div className="flex items-center gap-1.5 border-l border-slate-800 pl-2">
          <span className="text-[9px] uppercase font-mono px-1 py-0.5 rounded bg-cyan-950 text-cyan-300 border border-cyan-800">
            S{currentStage}
          </span>
          <span className="text-[11px] font-semibold text-slate-200 hidden sm:inline">
            {currentStageInfo.name}
          </span>
        </div>

        <input
          type="range"
          min={0}
          max={1}
          step={0.002}
          value={progress}
          onChange={(e) => onSeek(parseFloat(e.target.value))}
          className="w-24 sm:w-36 h-1 bg-slate-800 rounded appearance-none cursor-pointer accent-cyan-400"
        />

        <div className="flex flex-col items-end pl-1">
          <span className="text-[10px] font-mono font-bold text-sky-400">
            {formatRelativeTime(progress)}
          </span>
          {currentUtc && (
            <span className="text-[9px] font-mono text-slate-400 hidden md:inline">
              {currentUtc.substring(11, 19)} UTC
            </span>
          )}
        </div>

        <div className="flex items-center gap-1 border-l border-slate-800 pl-2">
          <button
            type="button"
            onClick={() => setIsMinimized(false)}
            title="Expand Forensic Panel"
            className="p-1 rounded hover:bg-slate-800 text-slate-400 hover:text-white transition-colors cursor-pointer"
          >
            <Maximize2 className="w-3.5 h-3.5" />
          </button>
          <button
            type="button"
            onClick={onClose}
            title="Close Replay Mode"
            className="p-1 rounded hover:bg-rose-950/60 text-slate-400 hover:text-rose-300 transition-colors cursor-pointer"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="absolute top-2.5 left-2.5 right-2.5 sm:right-auto sm:w-[325px] z-30 flex flex-col gap-1.5 pointer-events-auto">
      {/* Main Glassmorphism Forensic Panel */}
      <div className="bg-slate-950/92 backdrop-blur-md border border-slate-700/80 rounded-lg shadow-xl p-2 text-slate-100 flex flex-col gap-1.5">
        {/* Top Header Bar */}
        <div className="flex items-center justify-between border-b border-slate-800 pb-1">
          <div className="flex items-center gap-1.5">
            <div className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse" />
            <span className="text-[9.5px] font-mono uppercase tracking-wider text-cyan-400 font-semibold">
              Incident Replay
            </span>
          </div>

          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={onFitInvestigation}
              title="Fit View to Full Investigation"
              className="p-1 rounded hover:bg-slate-800 text-slate-300 hover:text-white transition-colors cursor-pointer"
            >
              <Crosshair className="w-3 h-3" />
            </button>
            <button
              type="button"
              onClick={() => setIsMinimized(true)}
              title="Minimize to Compact Bar"
              className="p-1 rounded hover:bg-slate-800 text-slate-400 hover:text-white transition-colors cursor-pointer"
            >
              <Minimize2 className="w-3 h-3" />
            </button>
            <button
              type="button"
              onClick={onClose}
              title="Close Replay Mode"
              className="p-1 rounded hover:bg-rose-950/60 text-slate-400 hover:text-rose-300 transition-colors cursor-pointer"
            >
              <X className="w-3 h-3" />
            </button>
          </div>
        </div>

        {/* Current Stage Indicator */}
        <div className="flex items-center justify-between bg-slate-900/80 border border-slate-800 rounded-md p-1.5">
          <div className="flex flex-col gap-0.5 min-w-0 pr-1">
            <div className="flex items-center gap-1.5">
              <span className="text-[8.5px] uppercase font-mono px-1 py-0.2 rounded bg-cyan-950 text-cyan-300 border border-cyan-800 shrink-0">
                S{currentStage}/5
              </span>
              <span className="text-[11px] font-bold text-slate-100 tracking-tight truncate">
                {currentStageInfo.name.toUpperCase()}
              </span>
            </div>
            <p className="text-[9.5px] text-slate-300 mt-0.5 leading-tight line-clamp-1">
              {currentStageInfo.description}
            </p>
          </div>
          <div className="flex flex-col items-end shrink-0 pl-1">
            <span className="text-[10px] font-mono font-bold text-sky-400 whitespace-nowrap">
              {formatRelativeTime(progress)}
            </span>
            {currentUtc && (
              <span className="text-[8.5px] font-mono text-slate-400 whitespace-nowrap">
                {currentUtc.substring(11, 19)} UTC
              </span>
            )}
          </div>
        </div>

        {/* Missing Data Warning Banners if applicable */}
        {(status === "VESSEL_UNAVAILABLE" || !vessel) && (
          <div className="flex items-start gap-1.5 bg-amber-950/30 border border-amber-800/60 rounded-md px-2 py-1 text-[9.5px] text-amber-200">
            <AlertTriangle className="w-3 h-3 text-amber-400 shrink-0 mt-0.5" />
            <span>
              <strong>No Candidate Track:</strong> Demonstrating drift to detected slick.
            </span>
          </div>
        )}

        {status === "VESSEL_TRACK_UNAVAILABLE" && (
          <div className="flex items-start gap-1.5 bg-amber-950/30 border border-amber-800/60 rounded-md px-2 py-1 text-[9.5px] text-amber-200">
            <AlertTriangle className="w-3 h-3 text-amber-400 shrink-0 mt-0.5" />
            <span>
              <strong>Vessel Track Unavailable:</strong> Demonstrating recorded position & drift.
            </span>
          </div>
        )}

        {status === "OCEAN_UNAVAILABLE" && (
          <div className="flex items-start gap-1.5 bg-amber-950/30 border border-amber-800/60 rounded-md px-2 py-1 text-[9.5px] text-amber-200">
            <AlertTriangle className="w-3 h-3 text-amber-400 shrink-0 mt-0.5" />
            <span>
              <strong>Currents Unavailable:</strong> Demonstrating recorded AIS & slick.
            </span>
          </div>
        )}

        {/* Timeline Scrubber & Stage Marks */}
        <div className="flex flex-col gap-1 pt-0.5">
          <div className="flex items-center justify-between text-[8.5px] font-mono text-slate-400">
            <span>{reconstruction?.ais_track?.waypoints?.[0]?.timestamp ? reconstruction.ais_track.waypoints[0].timestamp.substring(11, 16) + "Z" : "Start"}</span>
            <span className="text-cyan-400 font-bold">{Math.round(progress * 100)}%</span>
            <span>{reconstruction?.spill_geometry?.detection_time ? reconstruction.spill_geometry.detection_time.substring(11, 16) + "Z" : "SAR"}</span>
          </div>

          <input
            type="range"
            min={0}
            max={1}
            step={0.002}
            value={progress}
            onChange={(e) => onSeek(parseFloat(e.target.value))}
            className="w-full h-1 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-cyan-400 hover:accent-cyan-300"
          />

          {/* Stage Progression Bar Marks */}
          <div className="grid grid-cols-5 gap-0.5 text-[8px] font-mono text-center text-slate-400">
            <button
              type="button"
              onClick={() => onSeek(0.05)}
              className={`py-0.5 px-0.5 rounded hover:bg-slate-800 transition-colors cursor-pointer truncate ${
                currentStage === 1 ? "text-cyan-300 font-bold bg-cyan-950/70 border border-cyan-800" : ""
              }`}
            >
              1. AIS
            </button>
            <button
              type="button"
              onClick={() => onSeek(0.30)}
              className={`py-0.5 px-0.5 rounded hover:bg-slate-800 transition-colors cursor-pointer truncate ${
                currentStage === 2 ? "text-cyan-300 font-bold bg-cyan-950/70 border border-cyan-800" : ""
              }`}
            >
              2. Release
            </button>
            <button
              type="button"
              onClick={() => onSeek(0.50)}
              className={`py-0.5 px-0.5 rounded hover:bg-slate-800 transition-colors cursor-pointer truncate ${
                currentStage === 3 ? "text-cyan-300 font-bold bg-cyan-950/70 border border-cyan-800" : ""
              }`}
            >
              3. Wake
            </button>
            <button
              type="button"
              onClick={() => onSeek(0.72)}
              className={`py-0.5 px-0.5 rounded hover:bg-slate-800 transition-colors cursor-pointer truncate ${
                currentStage === 4 ? "text-cyan-300 font-bold bg-cyan-950/70 border border-cyan-800" : ""
              }`}
            >
              4. Drift
            </button>
            <button
              type="button"
              onClick={() => onSeek(0.95)}
              className={`py-0.5 px-0.5 rounded hover:bg-slate-800 transition-colors cursor-pointer truncate ${
                currentStage === 5 ? "text-emerald-300 font-bold bg-emerald-950/70 border border-emerald-800" : ""
              }`}
            >
              5. Slick
            </button>
          </div>
        </div>

        {/* Transport Controls & Speed Selector */}
        <div className="flex items-center justify-between pt-0.5 border-t border-slate-800/80">
          <div className="flex items-center gap-1.5">
            <button
              type="button"
              onClick={onRestart}
              title="Restart Replay"
              className="p-1 rounded bg-slate-900 hover:bg-slate-800 text-slate-300 border border-slate-700 transition-colors cursor-pointer"
            >
              <RotateCcw className="w-3 h-3" />
            </button>

            <button
              type="button"
              onClick={onTogglePlay}
              title={isPlaying ? "Pause Replay" : "Play Replay"}
              className={`px-3 py-1 rounded font-bold text-[11px] flex items-center gap-1 transition-all cursor-pointer shadow-sm ${
                isPlaying
                  ? "bg-amber-500 hover:bg-amber-600 text-slate-950 font-bold"
                  : "bg-cyan-500 hover:bg-cyan-400 text-slate-950 font-bold"
              }`}
            >
              {isPlaying ? (
                <>
                  <Pause className="w-3 h-3 fill-current" />
                  <span>Pause</span>
                </>
              ) : progress >= 0.99 ? (
                <>
                  <RotateCcw className="w-3 h-3" />
                  <span>Replay</span>
                </>
              ) : (
                <>
                  <Play className="w-3 h-3 fill-current" />
                  <span>{progress === 0 ? "Play" : "Resume"}</span>
                </>
              )}
            </button>
          </div>

          {/* Speed Selector */}
          <div className="flex items-center gap-0.5 bg-slate-900 border border-slate-800 p-0.5 rounded">
            {speeds.map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => onSpeedChange(s)}
                className={`px-1.5 py-0.2 rounded text-[9px] font-mono font-semibold transition-colors cursor-pointer ${
                  playbackSpeed === s
                    ? "bg-cyan-500 text-slate-950 font-bold shadow-xs"
                    : "text-slate-400 hover:text-slate-200"
                }`}
              >
                {s}×
              </button>
            ))}
          </div>
        </div>

        {/* Telemetry Metrics Grid */}
        <div className="grid grid-cols-3 gap-1 bg-slate-900/50 border border-slate-800/60 p-1 rounded-md text-[9px]">
          <div className="flex flex-col min-w-0">
            <span className="text-slate-400 flex items-center gap-0.5 font-mono uppercase text-[8px]">
              <Ship className="w-2.5 h-2.5 text-cyan-400 shrink-0" />
              Candidate
            </span>
            <span className="font-bold text-slate-100 font-mono truncate text-[9px] mt-0.5">
              {vessel?.vessel_name || (status === "VESSEL_UNAVAILABLE" ? "None" : "Unknown")}
            </span>
          </div>

          <div className="flex flex-col min-w-0">
            <span className="text-slate-400 flex items-center gap-0.5 font-mono uppercase text-[8px]">
              <Wind className="w-2.5 h-2.5 text-sky-400 shrink-0" />
              Current
            </span>
            <span className="font-bold text-slate-100 font-mono text-[9px] mt-0.5">
              {current?.speed_m_s ? `${current.speed_m_s.toFixed(2)}m/s` : "N/A"}
            </span>
          </div>

          <div className="flex flex-col min-w-0">
            <span className="text-slate-400 flex items-center gap-0.5 font-mono uppercase text-[8px]">
              <Layers className="w-2.5 h-2.5 text-rose-400 shrink-0" />
              Slick
            </span>
            <span className="font-bold text-rose-400 font-mono text-[9px] mt-0.5">
              {spill?.area_sq_km ? `${spill.area_sq_km.toFixed(2)}km²` : "N/A"}
            </span>
          </div>
        </div>

        {/* Visual Map Legend */}
        <div className="flex flex-wrap items-center justify-between gap-1 px-1 py-0.5 border-t border-slate-800/70 text-[8px] font-mono text-slate-300">
          <div className="flex items-center gap-1">
            <span className="w-2 h-0.5 bg-[#38bdf8] rounded"></span>
            <span>Traversed</span>
          </div>
          <div className="flex items-center gap-1">
            <span className="w-2 h-0.5 border-t border-dashed border-[#0284c7]"></span>
            <span>Upcoming</span>
          </div>
          <div className="flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-[#f59e0b]"></span>
            <span>Release</span>
          </div>
          <div className="flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-[#3b2d1d] border border-[#a16207]"></span>
            <span>Trail</span>
          </div>
          <div className="flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-xs bg-[#e11d48]"></span>
            <span>Slick</span>
          </div>
        </div>

        {/* Forensic Evidentiary Disclaimer */}
        <div className="text-[7.5px] text-slate-400 border-t border-slate-900 pt-0.5 leading-tight flex items-start gap-1">
          <Info className="w-2.5 h-2.5 text-slate-500 shrink-0 mt-0.2" />
          <span>
            <strong>FORENSIC REPLAY:</strong> Illustrative reconstruction based on AIS & drift model. Not definitive proof.
          </span>
        </div>
      </div>
    </div>
  );
};

export default SpillReplayController;
