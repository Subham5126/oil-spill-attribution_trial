import React, { useState, useEffect } from "react";
import { Play, Pause, RotateCcw, Clock, FastForward } from "lucide-react";

interface TimelineControllerProps {
  observationTime?: string;
  onTimeChange?: (offsetHours: number) => void;
}

export const TimelineController: React.FC<TimelineControllerProps> = ({
  observationTime = "2025-01-01T05:00:00 UTC",
  onTimeChange,
}) => {
  // -4h = Origin release, 0h = Observation, +2h = Forecast
  const [timeOffset, setTimeOffset] = useState<number>(-4);
  const [isPlaying, setIsPlaying] = useState<boolean>(false);

  useEffect(() => {
    let interval: NodeJS.Timeout;
    if (isPlaying) {
      interval = setInterval(() => {
        setTimeOffset((curr) => {
          if (curr >= 2) {
            setIsPlaying(false);
            return 2;
          }
          const next = Math.round((curr + 0.5) * 10) / 10;
          if (onTimeChange) onTimeChange(next);
          return next;
        });
      }, 900);
    }
    return () => clearInterval(interval);
  }, [isPlaying, onTimeChange]);

  const handleSliderChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = parseFloat(e.target.value);
    setTimeOffset(val);
    if (onTimeChange) onTimeChange(val);
  };

  const getPhaseLabel = (offset: number) => {
    if (offset < 0) return `Backward Hindcast (${Math.abs(offset)}h before observation)`;
    if (offset === 0) return "Sentinel-1 SAR Observation Time (T0)";
    return `Forward Forecast (+${offset}h spread)`;
  };

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-3.5 shadow-xl flex flex-col md:flex-row items-center justify-between gap-3 text-xs">
      {/* Control Buttons */}
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={() => setIsPlaying(!isPlaying)}
          className="p-2 rounded-lg bg-primary-container text-on-primary hover:bg-primary transition-colors shadow-sm cursor-pointer"
          title={isPlaying ? "Pause Simulation" : "Play Lagrangian Drift"}
        >
          {isPlaying ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4" />}
        </button>

        <button
          type="button"
          onClick={() => {
            setIsPlaying(false);
            setTimeOffset(-4);
            if (onTimeChange) onTimeChange(-4);
          }}
          className="p-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 transition-colors cursor-pointer"
          title="Reset to Probable Origin (T-4h)"
        >
          <RotateCcw className="w-4 h-4" />
        </button>
      </div>

      {/* Slider and Phase display */}
      <div className="flex-1 w-full max-w-xl flex flex-col gap-1">
        <div className="flex items-center justify-between font-mono text-[11px] text-slate-400">
          <span className="text-emerald-400 font-bold">T-4h (Origin Release)</span>
          <span className="text-slate-200 font-bold">{getPhaseLabel(timeOffset)}</span>
          <span className="text-amber-400 font-bold">T+2h (Forecast)</span>
        </div>

        <input
          type="range"
          min="-4"
          max="2"
          step="0.5"
          value={timeOffset}
          onChange={handleSliderChange}
          className="w-full accent-primary cursor-pointer"
        />
      </div>

      {/* Time Badge */}
      <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-slate-950 border border-slate-800 font-mono text-slate-300 shrink-0">
        <Clock className="w-3.5 h-3.5 text-sky-400" />
        <span>Offset: {timeOffset >= 0 ? `+${timeOffset}h` : `${timeOffset}h`}</span>
      </div>
    </div>
  );
};
