import React from "react";
import { SpillMetadata, GisMeasurement } from "../types";
import { Satellite, Maximize2, Layers, Compass, Globe, Hash } from "lucide-react";

interface SpillMetadataCardProps {
  metadata: SpillMetadata;
  measurement: GisMeasurement;
}

export const SpillMetadataCard: React.FC<SpillMetadataCardProps> = ({
  metadata,
  measurement,
}) => {
  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 shadow-xl space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between pb-3 border-b border-slate-800">
        <div className="flex items-center gap-2">
          <Satellite className="w-4 h-4 text-sky-400" />
          <h3 className="font-bold text-slate-100 text-sm">Member 3 GIS Measurements</h3>
        </div>
        <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-sky-950 text-sky-300 border border-sky-800">
          {metadata.crs}
        </span>
      </div>

      {/* Sensor Metadata */}
      <div className="grid grid-cols-2 gap-2 text-xs font-mono">
        <div className="bg-slate-950 p-2 rounded-lg border border-slate-800/80">
          <span className="text-[10px] text-slate-400 block">Sensor Platform</span>
          <span className="font-semibold text-slate-200">{metadata.sensor}</span>
        </div>
        <div className="bg-slate-950 p-2 rounded-lg border border-slate-800/80">
          <span className="text-[10px] text-slate-400 block">SAR Confidence</span>
          <span className="font-semibold text-emerald-400">
            {(metadata.confidence * 100).toFixed(1)}%
          </span>
        </div>
        <div className="bg-slate-950 p-2 rounded-lg border border-slate-800/80">
          <span className="text-[10px] text-slate-400 block">Detection Timestamp</span>
          <span className="font-semibold text-slate-200">
            {metadata.detection_timestamp.replace("T", " ").replace("+00:00", "")} UTC
          </span>
        </div>
        <div className="bg-slate-950 p-2 rounded-lg border border-slate-800/80">
          <span className="text-[10px] text-slate-400 block">Spill ID</span>
          <span className="font-semibold text-slate-200">{metadata.spill_id}</span>
        </div>
      </div>

      {/* Primary Dimensional Metrics */}
      <div className="bg-slate-950 p-3 rounded-lg border border-slate-800">
        <div className="text-[11px] font-semibold text-slate-300 uppercase tracking-wider mb-2 flex items-center gap-1.5">
          <Maximize2 className="w-3.5 h-3.5 text-red-400" />
          Polygon Geometry
        </div>
        <div className="grid grid-cols-3 gap-2 text-center font-mono text-xs">
          <div>
            <div className="text-slate-400 text-[10px]">Area (km²)</div>
            <div className="text-sm font-bold text-red-400">
              {measurement.area.sq_kilometers.toFixed(4)}
            </div>
            <div className="text-[10px] text-slate-500 font-mono">
              {measurement.area.sq_meters.toLocaleString()} m²
            </div>
          </div>
          <div>
            <div className="text-slate-400 text-[10px]">Perimeter</div>
            <div className="text-sm font-bold text-slate-200">
              {measurement.perimeter.kilometers.toFixed(3)} km
            </div>
            <div className="text-[10px] text-slate-500 font-mono">
              {measurement.perimeter.meters.toLocaleString()} m
            </div>
          </div>
          <div>
            <div className="text-slate-400 text-[10px]">Compactness</div>
            <div className="text-sm font-bold text-amber-400">
              {measurement.shape_characteristics.compactness.toFixed(4)}
            </div>
            <div className="text-[10px] text-slate-500 font-mono">
              Ratio: {measurement.shape_characteristics.aspect_ratio.toFixed(2)}
            </div>
          </div>
        </div>

        {/* Centroid Coordinates */}
        <div className="mt-3 pt-2.5 border-t border-slate-800/80 flex items-center justify-between text-[11px] font-mono text-slate-400">
          <span className="flex items-center gap-1">
            <Globe className="w-3 h-3 text-sky-400" /> Centroid:
          </span>
          <span className="text-slate-200 font-semibold">
            {measurement.centroid.latitude.toFixed(6)}°N, {measurement.centroid.longitude.toFixed(6)}°E
          </span>
        </div>
      </div>

      {/* Bounding Box Card */}
      <div className="bg-slate-950 p-2.5 rounded-lg border border-slate-800 text-[11px] font-mono">
        <div className="text-slate-400 text-[10px] uppercase font-semibold mb-1 flex items-center gap-1">
          <Layers className="w-3 h-3 text-purple-400" /> Geospatial Bounding Box
        </div>
        <div className="grid grid-cols-2 gap-1 text-slate-300">
          <div>Lon: [{measurement.bounding_box.min_lon}, {measurement.bounding_box.max_lon}]</div>
          <div>Lat: [{measurement.bounding_box.min_lat}, {measurement.bounding_box.max_lat}]</div>
          {measurement.bounding_box.width_meters && (
            <div className="col-span-2 text-slate-400 text-[10px]">
              Envelope Dimensions: {measurement.bounding_box.width_meters.toFixed(0)}m (W) ×{" "}
              {measurement.bounding_box.height_meters?.toFixed(0)}m (H)
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
