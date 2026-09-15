import React, { useState, useEffect } from "react";
import { NavPath } from "../components/Sidebar";
import { Sliders, Save, ShieldCheck, RefreshCw, AlertTriangle, CheckCircle2, RotateCcw } from "lucide-react";
import { getAttributionCalibration, updateAttributionCalibration } from "../services/api";
import { AttributionCalibration } from "../types";

interface SettingsPageProps {
  onNavigate: (path: NavPath) => void;
}

export function SettingsPage({ onNavigate }: SettingsPageProps) {
  const [calibration, setCalibration] = useState<AttributionCalibration | null>(null);
  const [spatialWeight, setSpatialWeight] = useState(35);
  const [temporalWeight, setTemporalWeight] = useState(25);
  const [trajectoryWeight, setTrajectoryWeight] = useState(15);
  const [behaviourWeight, setBehaviourWeight] = useState(10);
  const [vesselTypeWeight, setVesselTypeWeight] = useState(8);
  const [aisQualityWeight, setAisQualityWeight] = useState(7);

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saveStatus, setSaveStatus] = useState<"idle" | "success" | "error">("idle");
  const [statusMessage, setStatusMessage] = useState<string>("");

  const totalSum = spatialWeight + temporalWeight + trajectoryWeight + behaviourWeight + vesselTypeWeight + aisQualityWeight;
  const isSumValid = Math.abs(totalSum - 100) < 0.5;

  const loadSettings = () => {
    setLoading(true);
    getAttributionCalibration()
      .then((data) => {
        setCalibration(data);
        setSpatialWeight(Math.round(data.percentages.spatial_proximity));
        setTemporalWeight(Math.round(data.percentages.temporal_overlap));
        setTrajectoryWeight(Math.round(data.percentages.drift_consistency));
        setBehaviourWeight(Math.round(data.percentages.track_consistency));
        setVesselTypeWeight(Math.round(data.percentages.vessel_type_relevance || 8));
        setAisQualityWeight(Math.round(data.percentages.ais_quality || 7));
      })
      .catch((err) => {
        setStatusMessage("Failed to load settings from backend: " + err.message);
        setSaveStatus("error");
      })
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadSettings();
  }, []);

  const handleSave = async () => {
    if (!isSumValid) {
      setSaveStatus("error");
      setStatusMessage(`Attribution weights must sum exactly to 100% (currently ${totalSum}%).`);
      return;
    }

    setSaving(true);
    setSaveStatus("idle");
    setStatusMessage("");

    try {
      const updated = await updateAttributionCalibration({
        spatial_proximity: spatialWeight,
        temporal_overlap: temporalWeight,
        drift_consistency: trajectoryWeight,
        track_consistency: behaviourWeight,
        vessel_type_relevance: vesselTypeWeight,
        ais_quality: aisQualityWeight,
        notes: `Operational calibration saved from Web Console (${totalSum}%)`,
      });
      setCalibration(updated);
      setSaveStatus("success");
      setStatusMessage(`Calibration saved successfully as version: ${updated.version}`);
      setTimeout(() => setSaveStatus("idle"), 4000);
    } catch (err: any) {
      setSaveStatus("error");
      setStatusMessage(err.message || "Failed to persist calibration");
    } finally {
      setSaving(false);
    }
  };

  const handleResetDefaults = () => {
    setSpatialWeight(35);
    setTemporalWeight(25);
    setTrajectoryWeight(15);
    setBehaviourWeight(10);
    setVesselTypeWeight(8);
    setAisQualityWeight(7);
    setSaveStatus("idle");
    setStatusMessage("Weights reset to scientific baseline standards. Click 'Save Calibration' to persist.");
  };

  return (
    <div className="flex flex-col w-full max-w-4xl mx-auto gap-space-lg">
      <div className="flex flex-col gap-space-2xs">
        <div className="flex items-center gap-space-xs text-on-surface-variant font-label-sm text-label-sm">
          <span className="font-semibold text-primary uppercase tracking-wider">Calibration Engine</span>
        </div>
        <h1 className="font-headline-xl text-headline-xl text-on-surface tracking-tight font-bold flex items-center gap-2">
          <Sliders className="w-6 h-6 text-primary" />
          Attribution Scoring Configuration &amp; Calibration
        </h1>
        <p className="font-body-md text-body-md text-on-surface-variant">
          Adjust multi-criteria forensic attribution weights. Persisted calibrations are stamped with version provenance and consumed directly by the M5 attribution engine.
        </p>
      </div>

      {/* Active Version Provenance Strip */}
      <div className="bg-surface-container-lowest rounded-xl p-4 border border-surface-container shadow-xs flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <ShieldCheck className="w-5 h-5 text-emerald-600" />
          <div>
            <div className="text-[10px] font-mono uppercase tracking-wider text-secondary">
              Active Calibration Version
            </div>
            <div className="text-sm font-mono font-bold text-on-surface">
              {calibration?.version || "CALIB-v1-DEFAULT"}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={loadSettings}
            disabled={loading}
            className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-surface-container text-xs font-semibold text-on-surface hover:bg-surface-container-high transition-colors"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
            <span>Reload</span>
          </button>
          <button
            type="button"
            onClick={handleResetDefaults}
            className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-surface-container text-xs font-semibold text-on-surface hover:bg-surface-container-high transition-colors"
          >
            <RotateCcw className="w-3.5 h-3.5" />
            <span>Baseline Defaults</span>
          </button>
        </div>
      </div>

      {/* Status Notice */}
      {statusMessage && (
        <div
          className={`p-3.5 rounded-xl border flex items-center gap-2.5 text-xs font-mono ${
            saveStatus === "success"
              ? "bg-emerald-50 border-emerald-300 text-emerald-800"
              : saveStatus === "error"
              ? "bg-rose-50 border-rose-300 text-rose-800"
              : "bg-surface-container-low border-surface-container text-secondary"
          }`}
        >
          {saveStatus === "success" && <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />}
          {saveStatus === "error" && <AlertTriangle className="w-4 h-4 text-rose-600 shrink-0" />}
          <span>{statusMessage}</span>
        </div>
      )}

      {/* Attribution Weights Settings Card */}
      <div className="bg-surface-container-lowest rounded-xl p-space-lg border border-surface-container shadow-sm space-y-5">
        <div className="flex items-center justify-between pb-3 border-b border-surface-container-low">
          <h3 className="font-headline-sm text-headline-sm text-on-surface font-semibold flex items-center gap-2">
            <Sliders className="w-4 h-4 text-primary" />
            Multi-Criteria Attribution Weights
          </h3>
          <span
            className={`font-mono font-bold text-xs px-2.5 py-1 rounded-full border ${
              isSumValid
                ? "bg-emerald-100 text-emerald-800 border-emerald-300"
                : "bg-rose-100 text-rose-800 border-rose-300"
            }`}
          >
            Sum: {totalSum}% {isSumValid ? "✓ Valid" : "✗ Must equal 100%"}
          </span>
        </div>

        <div className="space-y-4 font-mono text-xs">
          <div>
            <div className="flex justify-between mb-1">
              <span>Spatial Proximity (Distance to Slick Centroid):</span>
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
              <span>Temporal Coincidence (AIS Query Temporal Window):</span>
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
              <span>Trajectory Alignment (Backward Drift Corridor Proximity):</span>
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
              <span>Kinematic Behaviour (Speed Consistency / Loitering):</span>
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

          <div>
            <div className="flex justify-between mb-1">
              <span>Vessel Type Correlation (Tanker / Cargo / Tug Discharge Risk):</span>
              <strong className="text-primary">{vesselTypeWeight}%</strong>
            </div>
            <input
              type="range"
              min="0"
              max="100"
              value={vesselTypeWeight}
              onChange={(e) => setVesselTypeWeight(Number(e.target.value))}
              className="w-full accent-primary cursor-pointer"
            />
          </div>

          <div>
            <div className="flex justify-between mb-1">
              <span>AIS Data Quality &amp; Transponder Continuity:</span>
              <strong className="text-primary">{aisQualityWeight}%</strong>
            </div>
            <input
              type="range"
              min="0"
              max="100"
              value={aisQualityWeight}
              onChange={(e) => setAisQualityWeight(Number(e.target.value))}
              className="w-full accent-primary cursor-pointer"
            />
          </div>
        </div>

        <div className="pt-4 border-t border-surface-container flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <span className="text-[11px] text-secondary font-mono">
            Scientific baseline: 35% Spatial, 25% Temporal, 15% Drift, 10% Kinematics, 8% Type, 7% Quality.
          </span>
          <button
            type="button"
            onClick={handleSave}
            disabled={saving || !isSumValid}
            className={`px-4 py-2 rounded-lg transition-colors flex items-center gap-1.5 text-xs font-bold shadow-sm ${
              !isSumValid
                ? "bg-surface-container text-secondary cursor-not-allowed"
                : "bg-primary text-on-primary hover:bg-primary/90 cursor-pointer"
            }`}
          >
            <Save className="w-4 h-4" />
            <span>{saving ? "Saving..." : "Save Calibration"}</span>
          </button>
        </div>
      </div>
    </div>
  );
}

