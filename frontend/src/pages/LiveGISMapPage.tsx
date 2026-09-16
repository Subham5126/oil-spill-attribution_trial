import React, { useState, useEffect } from "react";
import { NavPath } from "../components/Sidebar";
import { MapLibreGIS } from "../map/MapLibreGIS";
import { EndToEndResult, CandidateVessel } from "../types";
import { getActivePipelineResult } from "../services/api";
import { BASELINE_DEMO_RESULT } from "../services/demoDataAdapter";
import { Globe, Layers, Ship, Compass, Maximize2, ShieldCheck } from "lucide-react";

interface LiveGISMapPageProps {
  onNavigate: (path: NavPath) => void;
  onOpenDossier?: () => void;
  activeInvestigationId?: string | null;
}

export function LiveGISMapPage({ onNavigate, onOpenDossier, activeInvestigationId }: LiveGISMapPageProps) {
  const [pipelineData, setPipelineData] = useState<EndToEndResult>(BASELINE_DEMO_RESULT);
  const [selectedVessel, setSelectedVessel] = useState<CandidateVessel | null>(
    BASELINE_DEMO_RESULT.primary_suspect
  );

  useEffect(() => {
    getActivePipelineResult(activeInvestigationId || undefined).then((data) => {
      setPipelineData(data);
      if (data.primary_suspect) {
        setSelectedVessel(data.primary_suspect);
      } else if (data.candidate_vessels && data.candidate_vessels.length > 0) {
        setSelectedVessel(data.candidate_vessels[0]);
      } else {
        setSelectedVessel(null);
      }
    });
  }, [activeInvestigationId]);

  return (
    <div className="flex flex-col w-full h-[calc(100vh-130px)] gap-space-sm">
      {/* Top Header & Ticker */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-space-sm">
        <div className="flex items-center gap-space-sm">
          <div className="w-8 h-8 rounded-lg bg-primary-container text-on-primary flex items-center justify-center">
            <Globe className="w-4 h-4" />
          </div>
          <div>
            <h1 className="font-headline-sm text-headline-sm text-on-surface font-bold">
              Global Operational GIS Command Center
            </h1>
            <p className="font-body-sm text-body-sm text-on-surface-variant">
              MapLibre GL JS hardware-accelerated rendering of vector spill polygons, Lagrangian drift, and AIS paths.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-space-sm">
          <div className="flex items-center gap-2 px-3 py-1.5 bg-surface-container-lowest border border-surface-container rounded-lg shadow-sm font-mono text-xs text-on-surface">
            <span className="w-2 h-2 rounded-full bg-emerald-500 animate-ping"></span>
            <span className="font-bold">LIVE TELEMETRY</span>
            <span className="text-secondary">•</span>
            <span className="text-secondary">
              Centroid: {pipelineData.gis_measurement.centroid.latitude.toFixed(4)}°N,{" "}
              {pipelineData.gis_measurement.centroid.longitude.toFixed(4)}°E
            </span>
          </div>
        </div>
      </div>

      {/* Full Bleed Map */}
      <div className="relative flex-1 w-full rounded-xl overflow-hidden border border-slate-800 shadow-md">
        <MapLibreGIS
          result={pipelineData}
          selectedVessel={selectedVessel}
          onSelectVessel={(v) => setSelectedVessel(v)}
          height="100%"
          showControls={true}
        />
      </div>
    </div>
  );
}
