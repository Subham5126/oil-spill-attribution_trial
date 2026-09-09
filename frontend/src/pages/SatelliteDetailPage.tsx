import React, { useState, useEffect } from "react";
import { NavPath } from "../components/Sidebar";
import { EndToEndResult } from "../types";
import { getActivePipelineResult } from "../services/api";
import { BASELINE_DEMO_RESULT } from "../services/demoDataAdapter";
import { Satellite, Radio, CheckCircle2, ChevronLeft, Layers, Eye } from "lucide-react";

interface SatelliteDetailPageProps {
  onNavigate: (path: NavPath) => void;
}

export function SatelliteDetailPage({ onNavigate }: SatelliteDetailPageProps) {
  const [pipelineData, setPipelineData] = useState<EndToEndResult>(BASELINE_DEMO_RESULT);

  useEffect(() => {
    getActivePipelineResult().then(setPipelineData);
  }, []);

  const meta = pipelineData.spill_metadata;

  return (
    <div className="flex flex-col w-full gap-space-lg">
      <div className="flex flex-col gap-space-2xs">
        <button
          type="button"
          onClick={() => onNavigate("spill-analysis")}
          className="hover:text-primary transition-colors cursor-pointer flex items-center gap-1 text-xs text-secondary mb-1"
        >
          <ChevronLeft className="w-4 h-4" />
          <span>Back to Spill Geometry</span>
        </button>
        <h1 className="font-headline-xl text-headline-xl text-on-surface tracking-tight font-bold">
          Sentinel-1 SAR C-Band Acquisition Metadata
        </h1>
        <p className="font-body-md text-body-md text-on-surface-variant">
          Calibrated Level-1 GRD SAR backscatter characteristics and polarimetric properties.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-space-md">
        {/* Sensor Specs */}
        <div className="bg-surface-container-lowest rounded-xl p-space-md border border-surface-container shadow-sm flex flex-col gap-3">
          <h3 className="font-headline-sm text-headline-sm text-on-surface font-semibold pb-2 border-b border-surface-container-low flex items-center gap-2">
            <Satellite className="w-4 h-4 text-primary" />
            Sensor Parameters
          </h3>
          <div className="space-y-2.5 font-mono text-xs">
            <div className="flex justify-between p-2 rounded-lg bg-surface-container-low">
              <span className="text-secondary">Mission:</span>
              <span className="font-bold text-on-surface">{meta.properties?.mission || "Sentinel-1B"}</span>
            </div>
            <div className="flex justify-between p-2 rounded-lg bg-surface-container-low">
              <span className="text-secondary">Instrument:</span>
              <span className="font-bold text-on-surface">{meta.sensor}</span>
            </div>
            <div className="flex justify-between p-2 rounded-lg bg-surface-container-low">
              <span className="text-secondary">Polarization Channels:</span>
              <span className="font-bold text-on-surface">{meta.properties?.polarization || "VV+VH"}</span>
            </div>
            <div className="flex justify-between p-2 rounded-lg bg-surface-container-low">
              <span className="text-secondary">Spatial Resolution:</span>
              <span className="font-bold text-on-surface">{meta.properties?.resolution_meters || 10.0}m GRD</span>
            </div>
            <div className="flex justify-between p-2 rounded-lg bg-surface-container-low">
              <span className="text-secondary">Detection Confidence:</span>
              <span className="font-bold text-emerald-600">{(meta.confidence * 100).toFixed(1)}%</span>
            </div>
          </div>
        </div>

        {/* Analyst Notes */}
        <div className="bg-surface-container-lowest rounded-xl p-space-md border border-surface-container shadow-sm flex flex-col gap-3">
          <h3 className="font-headline-sm text-headline-sm text-on-surface font-semibold pb-2 border-b border-surface-container-low flex items-center gap-2">
            <Radio className="w-4 h-4 text-sky-500" />
            Remote Sensing Analyst Assessment
          </h3>
          <p className="text-xs text-secondary leading-relaxed font-sans">
            {meta.properties?.analyst_notes || "Continuous linear sheen with heavy core patch offshore Mumbai shipping corridor."}
          </p>
          <div className="p-3 rounded-lg bg-surface-container-low border border-surface-container font-mono text-xs text-secondary">
            <div>Detection Timestamp: <strong className="text-on-surface">{meta.detection_timestamp}</strong></div>
            <div className="mt-1">Coordinate Reference: <strong className="text-primary">{meta.crs}</strong></div>
          </div>
        </div>
      </div>
    </div>
  );
}
