import React, { useState, useEffect } from "react";
import { NavPath } from "../components/Sidebar";
import { MapLibreGIS } from "../map/MapLibreGIS";
import { Investigation, EndToEndResult, CandidateVessel, GeoJSONFeatureCollection } from "../types";
import { getInvestigations, getActivePipelineResult, getGISLayersGeoJSON } from "../services/api";
import { BASELINE_DEMO_RESULT } from "../services/demoDataAdapter";
import {
  Globe,
  Compass,
  Layers,
  MapPin,
  ArrowRight,
  Maximize2,
  Ship,
  Calendar,
  Radio,
  ExternalLink,
} from "lucide-react";

interface MapExplorerPageProps {
  onNavigate: (path: NavPath) => void;
  activeInvestigationId?: string | null;
  onSelectInvestigation?: (id: string) => void;
  onOpenDossier?: () => void;
}

export function MapExplorerPage({
  onNavigate,
  activeInvestigationId,
  onSelectInvestigation,
  onOpenDossier,
}: MapExplorerPageProps) {
  const [investigations, setInvestigations] = useState<Investigation[]>([]);
  const [selectedId, setSelectedId] = useState<string>(activeInvestigationId || "");
  const [pipelineData, setPipelineData] = useState<EndToEndResult>(BASELINE_DEMO_RESULT);
  const [layersGeoJSON, setLayersGeoJSON] = useState<GeoJSONFeatureCollection | null>(null);
  const [selectedVessel, setSelectedVessel] = useState<CandidateVessel | null>(
    BASELINE_DEMO_RESULT.primary_suspect
  );
  const [loading, setLoading] = useState(true);

  // Fetch all registered investigations
  useEffect(() => {
    getInvestigations().then((list) => {
      setInvestigations(list);
      if (!selectedId && list.length > 0) {
        setSelectedId(list[0].id);
      }
    });
  }, []);

  // When selectedId changes, fetch pipeline data and GeoJSON layers for that incident
  useEffect(() => {
    if (selectedId) {
      setLoading(true);
      Promise.all([
        getActivePipelineResult(selectedId),
        getGISLayersGeoJSON(selectedId),
      ])
        .then(([data, layers]) => {
          setPipelineData(data);
          setLayersGeoJSON(layers);
          if (data.primary_suspect) {
            setSelectedVessel(data.primary_suspect);
          } else if (data.candidate_vessels && data.candidate_vessels.length > 0) {
            setSelectedVessel(data.candidate_vessels[0]);
          } else {
            setSelectedVessel(null);
          }
        })
        .finally(() => setLoading(false));
    }
  }, [selectedId]);

  const handleSelectCase = (id: string) => {
    setSelectedId(id);
    if (onSelectInvestigation) onSelectInvestigation(id);
  };

  const { spill_metadata, gis_measurement, ocean_drift, candidate_vessels } = pipelineData;

  return (
    <div className="flex flex-col w-full h-[calc(100vh-120px)] gap-space-sm">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-space-sm">
        <div className="flex items-center gap-space-sm">
          <div className="w-8 h-8 rounded-lg bg-primary-container text-on-primary flex items-center justify-center">
            <Globe className="w-4 h-4" />
          </div>
          <div>
            <h1 className="font-headline-sm text-headline-sm text-on-surface font-bold">
              Multi-Incident GIS Map Explorer
            </h1>
            <p className="font-body-sm text-xs text-on-surface-variant">
              Spatial command center displaying SAR slick footprints, hydrodynamic drift envelopes, and AIS tracks across all registered cases.
            </p>
          </div>
        </div>

        {/* Telemetry Capsule */}
        <div className="flex items-center gap-2 px-3 py-1.5 bg-surface-container-lowest border border-surface-container rounded-lg shadow-sm font-mono text-xs text-on-surface">
          <span className="w-2 h-2 rounded-full bg-emerald-500 animate-ping"></span>
          <span className="font-bold">ACTIVE SECTOR:</span>
          <span className="text-primary font-bold">{selectedId || "NO SECTOR"}</span>
          <span className="text-secondary">•</span>
          <span className="text-secondary">
            {(gis_measurement?.centroid?.latitude ?? 0).toFixed(4)}°N,{" "}
            {(gis_measurement?.centroid?.longitude ?? 0).toFixed(4)}°E
          </span>
        </div>
      </div>

      {/* Main Grid: Sidebar of Incidents (4 Cols) + GIS Map (8 Cols) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-space-md flex-1 min-h-0">
        {/* Left Side Panel: Registered Incident List */}
        <div className="lg:col-span-4 flex flex-col gap-2 bg-surface-container-lowest p-3 rounded-xl border border-surface-container shadow-sm overflow-hidden h-full">
          <div className="flex items-center justify-between pb-2 border-b border-surface-container-low">
            <div className="flex items-center gap-1.5 text-xs font-bold text-on-surface uppercase tracking-wider">
              <Layers className="w-3.5 h-3.5 text-primary" />
              <span>Incident Sectors ({investigations.length})</span>
            </div>
            <button
              type="button"
              onClick={() => onNavigate("new-investigation")}
              className="text-[11px] text-primary font-semibold hover:underline"
            >
              + New Sector
            </button>
          </div>

          <div className="flex-1 overflow-y-auto flex flex-col gap-2 pr-1">
            {investigations.map((inv) => {
              const isSelected = inv.id === selectedId;
              return (
                <div
                  key={inv.id}
                  onClick={() => handleSelectCase(inv.id)}
                  className={`p-3 rounded-lg border transition-all cursor-pointer flex flex-col gap-1.5 ${
                    isSelected
                      ? "bg-primary/5 border-primary shadow-xs"
                      : "bg-surface-container-low border-surface-container hover:border-outline-variant"
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-xs font-bold text-primary">{inv.id}</span>
                    <span
                      className={`text-[10px] px-1.5 py-0.5 rounded font-bold ${
                        inv.status === "Completed"
                          ? "bg-emerald-100 text-emerald-800"
                          : inv.status === "Active"
                          ? "bg-sky-100 text-sky-800"
                          : "bg-surface-container text-secondary"
                      }`}
                    >
                      {inv.status}
                    </span>
                  </div>

                  <div className="font-semibold text-xs text-on-surface truncate">
                    {inv.title}
                  </div>

                  <div className="flex items-center justify-between text-[11px] text-secondary font-mono">
                    <span className="flex items-center gap-1">
                      <MapPin className="w-3 h-3 text-primary" />
                      {inv.region}
                    </span>
                    <span className="text-rose-600 font-bold">
                      {inv.spill_area_km2 ? `${inv.spill_area_km2.toFixed(2)} km²` : "—"}
                    </span>
                  </div>

                  {inv.suspect_vessel && (
                    <div className="text-[11px] text-secondary truncate flex items-center gap-1">
                      <Ship className="w-3 h-3 text-indigo-500" />
                      <span>Suspect: {inv.suspect_vessel}</span>
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          {/* Quick Details footer for selected incident */}
          <div className="p-2.5 rounded-lg bg-surface-container-low border border-surface-container text-xs flex items-center justify-between">
            <div className="truncate">
              <span className="text-secondary block text-[10px]">SELECTED CASE</span>
              <span className="font-mono font-bold text-on-surface truncate block">
                {spill_metadata?.spill_id || selectedId}
              </span>
            </div>
            <button
              type="button"
              onClick={() => {
                if (onSelectInvestigation) onSelectInvestigation(selectedId);
                onNavigate("dashboard");
              }}
              className="flex items-center gap-1 px-2.5 py-1 rounded bg-primary text-on-primary text-xs font-semibold shadow-xs hover:bg-primary/90"
            >
              <span>Inspect</span>
              <ArrowRight className="w-3 h-3" />
            </button>
          </div>
        </div>

        {/* Right 8 Cols: MapLibre GIS Container */}
        <div className="lg:col-span-8 bg-surface-container-lowest rounded-xl p-2 border border-surface-container shadow-sm flex flex-col h-full overflow-hidden">
          <MapLibreGIS
            investigationId={selectedId}
            result={pipelineData}
            layersGeoJSON={layersGeoJSON}
            selectedVessel={selectedVessel}
            onSelectVessel={(v) => {
              setSelectedVessel(v);
              onNavigate("vessel-analysis");
            }}
            height="100%"
          />
        </div>
      </div>
    </div>
  );
}
