/**
 * SpillReplayController — bottom-of-map canonical investigation timeline.
 */
import React from "react";
import { Pause, Play, RotateCcw, Waves } from "lucide-react";
import type { IncidentReplayModel, InvestigationReplayState, ReplayEventMarker } from "../replay/types";
import { formatInvestigationUtc } from "../replay/time";

const SPEEDS = [0.5, 1, 2, 5, 10, 20] as const;

interface SpillReplayControllerProps {
  model: IncidentReplayModel | null;
  clock: InvestigationReplayState;
  onTogglePlay: () => void;
  onReplay: () => void;
  onSeek: (timeMs: number) => void;
  onSpeedChange: (rate: number) => void;
  onClose: () => void;
  onFitInvestigation: () => void;
}

function markerLeftPct(event: ReplayEventMarker, start: number, end: number): number {
  const span = Math.max(1, end - start);
  return ((event.timestamp - start) / span) * 100;
}

export const SpillReplayController: React.FC<SpillReplayControllerProps> = ({
  model,
  clock,
  onTogglePlay,
  onReplay,
  onSeek,
  onSpeedChange,
  onClose,
  onFitInvestigation,
}) => {
  const { clock: clockLabel, full } = formatInvestigationUtc(clock.currentTime);
  const span = Math.max(1, clock.endTime - clock.startTime);
  const progress = (clock.currentTime - clock.startTime) / span;
  const startLabel = formatInvestigationUtc(clock.startTime).clock;
  const endLabel = formatInvestigationUtc(clock.endTime).clock;
  const events = model?.events ?? [];

  return (
    <div className="absolute inset-x-0 bottom-0 z-30 pointer-events-none px-2 pb-2 sm:px-3 sm:pb-3">
      <div className="pointer-events-auto mx-auto w-full max-w-5xl rounded-xl border border-slate-700/80 bg-slate-950/92 backdrop-blur-md shadow-2xl text-slate-100 px-3 py-2.5 sm:px-4">
        <div className="flex flex-wrap items-center gap-2 sm:gap-3">
          <div className="flex items-center gap-1.5">
            <button
              type="button"
              aria-label={clock.isPlaying ? "Pause investigation replay" : "Play investigation replay"}
              title={clock.isPlaying ? "Pause" : "Play"}
              onClick={onTogglePlay}
              className="p-2 rounded-lg bg-cyan-500 hover:bg-cyan-400 text-slate-950 transition-colors cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-cyan-300"
            >
              {clock.isPlaying ? <Pause className="w-4 h-4 fill-current" /> : <Play className="w-4 h-4 fill-current" />}
            </button>
            <button
              type="button"
              aria-label="Replay from start"
              title="Replay from start"
              onClick={onReplay}
              className="p-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 transition-colors cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-cyan-300"
            >
              <RotateCcw className="w-4 h-4" />
            </button>
          </div>

          <div className="flex items-center gap-1 flex-wrap" role="group" aria-label="Playback speed">
            <span className="text-[10px] uppercase tracking-wider text-slate-400 mr-1">Speed</span>
            {SPEEDS.map((s) => (
              <button
                key={s}
                type="button"
                aria-pressed={clock.playbackRate === s}
                aria-label={`${s} times playback speed`}
                onClick={() => onSpeedChange(s)}
                className={`px-1.5 py-0.5 rounded text-[10px] font-mono cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-cyan-300 ${
                  clock.playbackRate === s
                    ? "bg-cyan-500 text-slate-950 font-bold"
                    : "text-slate-400 hover:text-white hover:bg-slate-800"
                }`}
              >
                {s}×
              </button>
            ))}
          </div>

          <div className="ml-auto flex items-center gap-2 min-w-0">
            <div className="text-right min-w-0">
              <div className="font-mono text-[12px] sm:text-sm font-semibold text-cyan-200 truncate" aria-live="polite">
                {clockLabel}
              </div>
              <div className="font-mono text-[9px] text-slate-400 truncate">{full}</div>
            </div>
            <button
              type="button"
              aria-label="Close incident replay"
              onClick={onClose}
              className="p-1.5 rounded text-slate-400 hover:text-white hover:bg-slate-800 cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-cyan-300"
            >
              Close
            </button>
          </div>
        </div>

        <div className="mt-2.5">
          <label className="sr-only" htmlFor="investigation-timeline">
            Investigation timeline
          </label>
          <input
            id="investigation-timeline"
            type="range"
            min={clock.startTime}
            max={clock.endTime}
            step={1000}
            value={clock.currentTime}
            onChange={(e) => onSeek(Number(e.target.value))}
            className="w-full accent-cyan-400 cursor-pointer h-2"
          />
          <div className="relative h-4 mt-0.5">
            {events.map((ev) => (
              <button
                key={ev.id}
                type="button"
                title={`${ev.label} — seek`}
                aria-label={`Seek to ${ev.label}`}
                onClick={() => onSeek(ev.timestamp)}
                style={{ left: `${markerLeftPct(ev, clock.startTime, clock.endTime)}%` }}
                className={`absolute -translate-x-1/2 top-0 text-[8px] font-mono px-1 rounded cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-cyan-300 ${
                  ev.kind === "spill"
                    ? "text-rose-300"
                    : ev.kind === "forecast"
                      ? "text-amber-300"
                      : ev.kind === "ais"
                        ? "text-sky-300"
                        : "text-slate-400"
                }`}
              >
                {ev.kind === "spill" ? "🛢️" : ev.kind === "forecast" ? "🌊" : "📍"}
              </button>
            ))}
          </div>
          <div className="flex justify-between font-mono text-[10px] text-slate-400">
            <span>{startLabel}</span>
            <span className="text-slate-200">{Math.round(progress * 100)}%</span>
            <span>{endLabel}</span>
          </div>
        </div>

        <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[10px] font-mono text-slate-300">
          <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-cyan-400 inline-block shadow-[0_0_4px_#22d3ee]" /> ORIGIN OIL</span>
          <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-rose-600 inline-block shadow-[0_0_4px_#e11d48]" /> DETECTED SLICK</span>
          <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-amber-400 inline-block shadow-[0_0_4px_#f59e0b]" /> FORECAST OIL</span>
          {model?.availability.forecast === false && <span className="text-amber-300">{model.availability.forecastMessage}</span>}
          {model?.availability.forecastIsApproximation && model.availability.forecast && (
            <span className="text-amber-200/90">Forward-cast is a visualization approximation</span>
          )}
          <button
            type="button"
            onClick={onFitInvestigation}
            className="ml-auto px-2 py-0.5 rounded border border-slate-600 text-slate-300 hover:text-white cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-cyan-300"
          >
            Fit evidence
          </button>
        </div>
      </div>
    </div>
  );
};

export default SpillReplayController;
