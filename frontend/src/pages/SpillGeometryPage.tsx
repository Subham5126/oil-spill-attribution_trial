import React, { useState, useEffect } from "react";
import { NavPath } from "../components/Sidebar";
import { MapLibreGIS } from "../map/MapLibreGIS";
import { EndToEndResult } from "../types";
import { getActivePipelineResult } from "../services/api";
import { BASELINE_DEMO_RESULT } from "../services/demoDataAdapter";
import {
  Maximize2,
  Download,
  Share2,
  Globe,
  Layers,
  CheckCircle2,
  FileCode,
  Crosshair,
} from "lucide-react";

interface SpillGeometryPageProps {
  onNavigate: (path: NavPath) => void;
  onOpenDossier?: () => void;
}

export function SpillGeometryPage({ onNavigate, onOpenDossier }: SpillGeometryPageProps) {
  const [pipelineData, setPipelineData] = useState<EndToEndResult>(BASELINE_DEMO_RESULT);

  useEffect(() => {
    getActivePipelineResult().then(setPipelineData);
  }, []);

  const { spill_metadata, gis_measurement } = pipelineData;

  const handleExportGeoJSON = () => {
    window.open("/data/end_to_end_layers.geojson", "_blank");
  };

  return (
    <div className="flex flex-col w-full gap-space-lg">
      {/* Top Breadcrumb & Action Ribbon */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-space-md">
        <div className="flex flex-col gap-space-2xs">
          <div className="flex items-center gap-space-xs text-on-surface-variant font-label-sm text-label-sm">
            <button
              type="button"
              onClick={() => onNavigate("investigations")}
              className="hover:text-primary transition-colors cursor-pointer"
            >
              Investigations
            </button>
            <span className="text-outline-variant">/</span>
            <span className="text-on-surface font-semibold">{spill_metadata.spill_id}</span>
            <span className="text-outline-variant">/</span>
            <span className="text-primary font-bold">Member 3 GIS Measurements</span>
          </div>
          <h1 className="font-headline-xl text-headline-xl text-on-surface tracking-tight font-bold">
            Spill Geometry &amp; Morphological Extraction
          </h1>
          <p className="font-body-md text-body-md text-on-surface-variant">
            Exact spatial morphology and perimeter delineation extracted from calibrated Sentinel-1 C-Band SAR.
          </p>
        </div>

        {/* Action Controls */}
        <div className="flex items-center gap-space-sm flex-wrap">
          <button
            type="button"
            onClick={handleExportGeoJSON}
            className="flex items-center gap-space-xs px-space-md py-2 rounded-lg bg-surface-container text-on-surface hover:bg-surface-container-high transition-colors font-label-md text-label-md cursor-pointer border border-surface-container"
          >
            <Download className="w-4 h-4 text-primary" />
            <span>Export Spill GeoJSON</span>
          </button>

          <button
            type="button"
            onClick={() => onNavigate("drift-analysis")}
            className="flex items-center gap-space-xs px-space-md py-2 rounded-lg bg-primary-container text-on-primary hover:bg-primary transition-colors font-label-md text-label-md font-semibold cursor-pointer shadow-sm"
          >
            <span>Run Drift Hindcast</span>
            <span className="material-symbols-outlined text-[18px]">arrow_forward</span>
          </button>
        </div>
      </div>

      {/* Main Content Grid: 8 Cols Map + 4 Cols Measurements */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-space-lg items-start">
        {/* Left 8 Cols: MapLibre GIS Focus */}
        <div className="lg:col-span-8 flex flex-col gap-space-md">
          <div className="bg-surface-container-lowest rounded-xl p-space-sm border border-surface-container shadow-sm flex flex-col gap-2">
            <div className="flex items-center justify-between px-2 pt-1">
              <span className="font-headline-sm text-headline-sm text-on-surface font-semibold flex items-center gap-2">
                <Maximize2 className="w-4 h-4 text-rose-500" />
                Delineated Slick Polygon Vector
              </span>
              <span className="font-data-mono-sm text-xs text-secondary">
                Coordinate Reference System: {gis_measurement.crs}
              </span>
            </div>

            <MapLibreGIS result={pipelineData} height="560px" />
          </div>

          {/* Polygon Vertex Coordinate Stream */}
          <div className="bg-surface-container-lowest rounded-xl p-space-md border border-surface-container shadow-sm flex flex-col">
            <h3 className="font-headline-sm text-headline-sm text-on-surface font-semibold mb-3 flex items-center gap-2">
              <FileCode className="w-4 h-4 text-primary" />
              Geometric Vertex Boundary Table
            </h3>
            <div className="overflow-x-auto">
              <table className="w-full text-left font-mono text-xs text-on-surface">
                <thead>
                  <tr className="border-b border-surface-container-low text-secondary text-[11px] uppercase">
                    <th className="py-2">Vertex #</th>
                    <th className="py-2">Longitude</th>
                    <th className="py-2">Latitude</th>
                    <th className="py-2">Segment Classification</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-surface-container-low text-[11px]">
                  <tr>
                    <td className="py-2 font-bold text-primary">V-01 (Apex)</td>
                    <td className="py-2">72.465000° E</td>
                    <td className="py-2">18.512000° N</td>
                    <td className="py-2 text-rose-600 font-semibold">Heavy Slick Edge</td>
                  </tr>
                  <tr>
                    <td className="py-2 font-bold text-primary">V-02</td>
                    <td className="py-2">72.478000° E</td>
                    <td className="py-2">18.515000° N</td>
                    <td className="py-2 text-rose-600 font-semibold">Continuous Slick Core</td>
                  </tr>
                  <tr>
                    <td className="py-2 font-bold text-primary">V-03</td>
                    <td className="py-2">72.492000° E</td>
                    <td className="py-2">18.525000° N</td>
                    <td className="py-2 text-amber-600 font-semibold">Emulsified Zone</td>
                  </tr>
                  <tr>
                    <td className="py-2 font-bold text-primary">V-04 (Apex)</td>
                    <td className="py-2">72.501000° E</td>
                    <td className="py-2">18.532000° N</td>
                    <td className="py-2 text-amber-600 font-semibold">Feathering Boundary</td>
                  </tr>
                  <tr>
                    <td className="py-2 font-bold text-primary">Centroid</td>
                    <td className="py-2 text-sky-600 font-bold">
                      {gis_measurement.centroid.longitude.toFixed(6)}° E
                    </td>
                    <td className="py-2 text-sky-600 font-bold">
                      {gis_measurement.centroid.latitude.toFixed(6)}° N
                    </td>
                    <td className="py-2 text-sky-600 font-bold">Center of Mass</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>

        {/* Right 4 Cols: Comprehensive GIS Statistics */}
        <div className="lg:col-span-4 flex flex-col gap-space-md">
          {/* Exact Metrics Box */}
          <div className="bg-surface-container-lowest rounded-xl p-space-md border border-surface-container shadow-sm flex flex-col gap-space-sm">
            <h3 className="font-headline-sm text-headline-sm text-on-surface font-semibold pb-2 border-b border-surface-container-low">
              Spatial Measurement Parameters
            </h3>

            <div className="space-y-3 font-mono text-xs">
              <div className="flex items-center justify-between p-2 rounded-lg bg-surface-container-low">
                <span className="text-secondary">Measured Area</span>
                <span className="font-bold text-on-surface">
                  {gis_measurement.area.sq_kilometers.toFixed(4)} km²
                </span>
              </div>
              <div className="flex items-center justify-between p-2 rounded-lg bg-surface-container-low">
                <span className="text-secondary">Area in Sq. Meters</span>
                <span className="font-bold text-on-surface">
                  {gis_measurement.area.sq_meters.toLocaleString()} m²
                </span>
              </div>
              <div className="flex items-center justify-between p-2 rounded-lg bg-surface-container-low">
                <span className="text-secondary">Total Perimeter</span>
                <span className="font-bold text-on-surface">
                  {gis_measurement.perimeter.kilometers.toFixed(3)} km
                </span>
              </div>
              <div className="flex items-center justify-between p-2 rounded-lg bg-surface-container-low">
                <span className="text-secondary">Perimeter in Meters</span>
                <span className="font-bold text-on-surface">
                  {gis_measurement.perimeter.meters.toLocaleString()} m
                </span>
              </div>
              <div className="flex items-center justify-between p-2 rounded-lg bg-surface-container-low">
                <span className="text-secondary">Compactness (Polsby-Popper)</span>
                <span className="font-bold text-on-surface">
                  {gis_measurement.shape_characteristics.compactness.toFixed(4)}
                </span>
              </div>
              <div className="flex items-center justify-between p-2 rounded-lg bg-surface-container-low">
                <span className="text-secondary">Aspect Ratio (Elongation)</span>
                <span className="font-bold text-on-surface">
                  {gis_measurement.shape_characteristics.aspect_ratio.toFixed(2)}
                </span>
              </div>
              <div className="flex items-center justify-between p-2 rounded-lg bg-surface-container-low">
                <span className="text-secondary">Coordinate System</span>
                <span className="font-bold text-primary">
                  {gis_measurement.crs} (WGS 84)
                </span>
              </div>
            </div>
          </div>

          {/* Bounding Envelope Box */}
          <div className="bg-surface-container-lowest rounded-xl p-space-md border border-surface-container shadow-sm flex flex-col gap-space-xs">
            <h3 className="font-headline-sm text-headline-sm text-on-surface font-semibold pb-2 border-b border-surface-container-low">
              Geospatial Bounding Envelope
            </h3>
            <div className="font-mono text-xs space-y-2 mt-1">
              <div className="flex justify-between text-secondary">
                <span>Min Longitude:</span>
                <span className="font-semibold text-on-surface">
                  {gis_measurement.bounding_box.min_lon}° E
                </span>
              </div>
              <div className="flex justify-between text-secondary">
                <span>Max Longitude:</span>
                <span className="font-semibold text-on-surface">
                  {gis_measurement.bounding_box.max_lon}° E
                </span>
              </div>
              <div className="flex justify-between text-secondary">
                <span>Min Latitude:</span>
                <span className="font-semibold text-on-surface">
                  {gis_measurement.bounding_box.min_lat}° N
                </span>
              </div>
              <div className="flex justify-between text-secondary">
                <span>Max Latitude:</span>
                <span className="font-semibold text-on-surface">
                  {gis_measurement.bounding_box.max_lat}° N
                </span>
              </div>
              {gis_measurement.bounding_box.width_meters && (
                <div className="pt-2 border-t border-surface-container-low flex justify-between text-primary font-bold">
                  <span>Envelope Span:</span>
                  <span>
                    {gis_measurement.bounding_box.width_meters.toFixed(0)}m ×{" "}
                    {gis_measurement.bounding_box.height_meters?.toFixed(0)}m
                  </span>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
