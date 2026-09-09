import React, { useState } from "react";
import { NavPath } from "../components/Sidebar";
import { Sliders, Save, ShieldCheck, Database, Key, Globe } from "lucide-react";

interface SettingsPageProps {
  onNavigate: (path: NavPath) => void;
}

export function SettingsPage({ onNavigate }: SettingsPageProps) {
  const [spatialWeight, setSpatialWeight] = useState(40);
  const [temporalWeight, setTemporalWeight] = useState(35);
  const [trajectoryWeight, setTrajectoryWeight] = useState(15);
  const [behaviourWeight, setBehaviourWeight] = useState(10);
  const [saved, setSaved] = useState(false);

  const handleSave = () => {
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  return (
    <div className="flex flex-col w-full max-w-4xl mx-auto gap-space-lg">
      <div className="flex flex-col gap-space-2xs">
        <h1 className="font-headline-xl text-headline-xl text-on-surface tracking-tight font-bold">
          System Configuration &amp; Scoring Calibration
        </h1>
        <p className="font-body-md text-body-md text-on-surface-variant">
          Adjust multi-criteria forensic attribution weights, external API integrations, and MapLibre tile services.
        </p>
      </div>

      {/* Attribution Weights Settings */}
      <div className="bg-surface-container-lowest rounded-xl p-space-lg border border-surface-container shadow-sm space-y-4">
        <h3 className="font-headline-sm text-headline-sm text-on-surface font-semibold pb-2 border-b border-surface-container-low flex items-center gap-2">
          <Sliders className="w-4 h-4 text-primary" />
          Multi-Criteria Attribution Weights (Sum: {spatialWeight + temporalWeight + trajectoryWeight + behaviourWeight}%)
        </h3>

        <div className="space-y-4 font-mono text-xs">
          <div>
            <div className="flex justify-between mb-1">
              <span>Spatial Proximity Weight:</span>
              <strong className="text-primary">{spatialWeight}%</strong>
            </div>
            <input
              type="range"
              min="0"
              max="100"
              value={spatialWeight}
              onChange={(e) => setSpatialWeight(Number(e.target.value))}
              className="w-full accent-primary cursor-pointer"
            />
          </div>

          <div>
            <div className="flex justify-between mb-1">
              <span>Temporal Coincidence Weight:</span>
              <strong className="text-primary">{temporalWeight}%</strong>
            </div>
            <input
              type="range"
              min="0"
              max="100"
              value={temporalWeight}
              onChange={(e) => setTemporalWeight(Number(e.target.value))}
              className="w-full accent-primary cursor-pointer"
            />
          </div>

          <div>
            <div className="flex justify-between mb-1">
              <span>Trajectory Alignment Weight:</span>
              <strong className="text-primary">{trajectoryWeight}%</strong>
            </div>
            <input
              type="range"
              min="0"
              max="100"
              value={trajectoryWeight}
              onChange={(e) => setTrajectoryWeight(Number(e.target.value))}
              className="w-full accent-primary cursor-pointer"
            />
          </div>

          <div>
            <div className="flex justify-between mb-1">
              <span>Kinematic Behaviour Weight:</span>
              <strong className="text-primary">{behaviourWeight}%</strong>
            </div>
            <input
              type="range"
              min="0"
              max="100"
              value={behaviourWeight}
              onChange={(e) => setBehaviourWeight(Number(e.target.value))}
              className="w-full accent-primary cursor-pointer"
            />
          </div>
        </div>

        <div className="pt-3 border-t border-surface-container flex items-center justify-between">
          <span className="text-[11px] text-secondary font-mono">
            Default baseline weights: 40% Spatial, 35% Temporal, 15% Trajectory, 10% Behaviour.
          </span>
          <button
            type="button"
            onClick={handleSave}
            className="px-4 py-2 rounded-lg bg-primary-container text-on-primary hover:bg-primary transition-colors flex items-center gap-1.5 text-xs font-bold shadow-sm cursor-pointer"
          >
            <Save className="w-4 h-4" />
            <span>{saved ? "Weights Saved!" : "Save Calibration"}</span>
          </button>
        </div>
      </div>
    </div>
  );
}
