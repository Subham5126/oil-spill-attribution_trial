import React, { useState } from "react";
import { NavPath } from "../components/Sidebar";
import {
  Satellite,
  Waves,
  Ship,
  Upload,
  Play,
  ArrowLeft,
  CheckCircle2,
  Calendar,
  Globe,
} from "lucide-react";

interface NewInvestigationPageProps {
  onNavigate: (path: NavPath) => void;
}

export function NewInvestigationPage({ onNavigate }: NewInvestigationPageProps) {
  const [satelliteScene, setSatelliteScene] = useState("SAR-20250101-IND-0042 (Sentinel-1 C-Band)");
  const [oceanSource, setOceanSource] = useState("Copernicus Marine Global Ocean (CMEMS)");
  const [windSource, setWindSource] = useState("ECMWF ERA5 Atmospheric Reanalysis");
  const [aisSource, setAisSource] = useState("Demo Synthetic AIS (demo/output/demo_synthetic_ais.csv)");

  const handleLaunch = () => {
    onNavigate("analysis-process");
  };

  return (
    <div className="flex flex-col w-full max-w-4xl mx-auto gap-space-lg">
      {/* Header */}
      <div className="flex flex-col gap-space-2xs">
        <button
          type="button"
          onClick={() => onNavigate("investigations")}
          className="hover:text-primary transition-colors cursor-pointer flex items-center gap-1 text-xs text-secondary mb-1"
        >
          <ArrowLeft className="w-4 h-4" />
          <span>Back to Investigations</span>
        </button>
        <h1 className="font-headline-xl text-headline-xl text-on-surface tracking-tight font-bold">
          Initiate Oil Spill Attribution Pipeline
        </h1>
        <p className="font-body-md text-body-md text-on-surface-variant">
          Configure satellite SAR detection inputs, MetOcean hydrodynamic forcing, and historical AIS streams.
        </p>
      </div>

      {/* Form Card */}
      <div className="bg-surface-container-lowest rounded-xl p-space-lg border border-surface-container shadow-sm space-y-6">
        {/* Step 1: Satellite SAR */}
        <div className="space-y-2">
          <label className="font-headline-sm text-sm text-on-surface font-bold flex items-center gap-2">
            <Satellite className="w-4 h-4 text-primary" />
            1. Satellite SAR Imagery Observation
          </label>
          <select
            value={satelliteScene}
            onChange={(e) => setSatelliteScene(e.target.value)}
            className="w-full p-2.5 rounded-lg bg-surface-container-low border border-surface-container text-xs text-on-surface font-mono focus:outline-none focus:ring-1 focus:ring-primary"
          >
            <option value="SAR-20250101-IND-0042 (Sentinel-1 C-Band)">
              SAR-20250101-IND-0042 (Sentinel-1B IW Dual-Pol VV+VH — Arabian Sea Mumbai Corridor)
            </option>
            <option value="SAR-20250102-GOM-0019 (Sentinel-1A)">
              SAR-20250102-GOM-0019 (Sentinel-1A IW — Gulf of Mexico Mississippi Canyon)
            </option>
          </select>
          <p className="text-[11px] text-secondary">
            Calibrated SAR observation polygon will be measured using Member 3 GIS algorithms.
          </p>
        </div>

        {/* Step 2: MetOcean Environmental Datasets */}
        <div className="space-y-3">
          <label className="font-headline-sm text-sm text-on-surface font-bold flex items-center gap-2">
            <Waves className="w-4 h-4 text-sky-500" />
            2. Oceanographic &amp; Meteorological Drift Forcing (Member 4)
          </label>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-space-md">
            <div>
              <span className="text-xs text-secondary block mb-1 font-semibold">Surface Currents:</span>
              <select
                value={oceanSource}
                onChange={(e) => setOceanSource(e.target.value)}
                className="w-full p-2 rounded-lg bg-surface-container-low border border-surface-container text-xs text-on-surface font-mono"
              >
                <option value="Copernicus Marine Global Ocean (CMEMS)">
                  Copernicus Marine CMEMS (0.25° Grid)
                </option>
                <option value="HYCOM Surface Current Analysis">
                  HYCOM Global Ocean Forecast
                </option>
              </select>
            </div>

            <div>
              <span className="text-xs text-secondary block mb-1 font-semibold">Surface Winds (10m):</span>
              <select
                value={windSource}
                onChange={(e) => setWindSource(e.target.value)}
                className="w-full p-2 rounded-lg bg-surface-container-low border border-surface-container text-xs text-on-surface font-mono"
              >
                <option value="ECMWF ERA5 Atmospheric Reanalysis">
                  ECMWF ERA5 Reanalysis (1-hour resolution)
                </option>
                <option value="GFS 0.25 Degree Hourly">
                  NOAA GFS Global Forecast System
                </option>
              </select>
            </div>
          </div>
        </div>

        {/* Step 3: AIS Stream */}
        <div className="space-y-2">
          <label className="font-headline-sm text-sm text-on-surface font-bold flex items-center gap-2">
            <Ship className="w-4 h-4 text-purple-500" />
            3. Historical AIS Trajectory Data (Member 5)
          </label>
          <select
            value={aisSource}
            onChange={(e) => setAisSource(e.target.value)}
            className="w-full p-2.5 rounded-lg bg-surface-container-low border border-surface-container text-xs text-on-surface font-mono focus:outline-none focus:ring-1 focus:ring-primary"
          >
            <option value="Demo Synthetic AIS (demo/output/demo_synthetic_ais.csv)">
              Demo AIS Dataset (demo/output/demo_synthetic_ais.csv — PACIFIC VOYAGER &amp; NORDIC TRADER)
            </option>
            <option value="Local AIS Provider Directory (ASI_data/)">
              Local AIS Provider Directory (ASI_data/)
            </option>
          </select>
          <p className="text-[11px] text-amber-600 font-mono">
            Note: AIS search radius will be automatically derived from the 95% spatial dispersion estimate + 1.0 km buffer.
          </p>
        </div>

        {/* Submit */}
        <div className="pt-4 border-t border-surface-container flex items-center justify-end gap-3">
          <button
            type="button"
            onClick={() => onNavigate("investigations")}
            className="px-4 py-2 rounded-lg bg-surface-container text-on-surface hover:bg-surface-container-high transition-colors font-label-md text-xs cursor-pointer"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleLaunch}
            className="px-5 py-2.5 rounded-lg bg-primary-container text-on-primary hover:bg-primary transition-colors flex items-center gap-2 font-bold text-xs cursor-pointer shadow-md"
          >
            <Play className="w-4 h-4" />
            <span>Execute End-to-End Pipeline</span>
          </button>
        </div>
      </div>
    </div>
  );
}
