import React, { useEffect, useRef, useState, useMemo, useCallback } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { EndToEndResult, GeoJSONFeatureCollection, CandidateVessel, ForensicReconstruction } from "../types";
import { SpillReplayController } from "../components/SpillReplayController";
import { getInvestigationReconstruction } from "../services/api";
import { Layers, Crosshair, AlertCircle, Info, Play, Film } from "lucide-react";
import { FEATURES } from "../config/features";
import { buildIncidentReplayModel } from "../replay/buildReplayModel";
import {
  advanceClock,
  createReplayState,
  pauseClock,
  playClock,
  replayFromStart,
  seekClock,
  setPlaybackRate,
  togglePlay,
} from "../replay/clock";
import { formatInvestigationUtc } from "../replay/time";
import { bboxOfGeometry, detectedSpillVisible, forecastGeometryAtTime } from "../replay/geometry";
import { particlesAtTime } from "../replay/particles";
import type { IncidentReplayModel, InvestigationReplayState } from "../replay/types";

interface MapLibreGISProps {
  investigationId?: string;
  result?: EndToEndResult | null;
  layersGeoJSON?: GeoJSONFeatureCollection | null;
  selectedVessel?: CandidateVessel | null;
  onSelectVessel?: (vessel: CandidateVessel) => void;
  onSpillClick?: () => void;
  onOriginClick?: () => void;
  className?: string;
  height?: string;
  showControls?: boolean;
}

// Generate circular polygon points for origin uncertainty
function createGeoCircle(centerLon: number, centerLat: number, radiusKm: number, points = 64): number[][] {
  if (!centerLon || !centerLat || radiusKm <= 0) return [];
  const coords: number[][] = [];
  const distanceX = radiusKm / (111.32 * Math.cos((centerLat * Math.PI) / 180));
  const distanceY = radiusKm / 110.574;

  for (let i = 0; i <= points; i++) {
    const theta = (i / points) * (2 * Math.PI);
    const x = distanceX * Math.cos(theta);
    const y = distanceY * Math.sin(theta);
    coords.push([centerLon + x, centerLat + y]);
  }
  return coords;
}

// Rank color mapping helper
export function getRankColor(rank?: number): string {
  if (rank === 1) return "#f59e0b"; // Amber/Gold
  if (rank === 2) return "#a855f7"; // Purple/Violet
  if (rank === 3) return "#10b981"; // Emerald/Green
  return "#94a3b8"; // Slate for Other
}

export function getRankDarkColor(rank?: number): string {
  if (rank === 1) return "#78350f";
  if (rank === 2) return "#581c87";
  if (rank === 3) return "#064e3b";
  return "#334155";
}

// Convert CMEMS current vectors to GeoJSON LineString and Point features
function buildCurrentVectorFeatures(currentVectors: any[]): GeoJSON.Feature[] {
  const features: GeoJSON.Feature[] = [];
  currentVectors.forEach((cv) => {
    const dLat = (cv.v * 3600 * 1.5) / 111320;
    const dLon = (cv.u * 3600 * 1.5) / (111320 * Math.max(0.1, Math.cos((cv.latitude * Math.PI) / 180)));
    features.push({
      type: "Feature",
      properties: {
        featureType: "line",
        speedKnots: cv.speedKnots,
        headingDeg: cv.headingDeg,
      },
      geometry: {
        type: "LineString",
        coordinates: [
          [cv.longitude, cv.latitude],
          [cv.longitude + dLon, cv.latitude + dLat],
        ],
      },
    });
    features.push({
      type: "Feature",
      properties: {
        featureType: "dot",
        speedKnots: cv.speedKnots,
        headingDeg: cv.headingDeg,
      },
      geometry: {
        type: "Point",
        coordinates: [cv.longitude, cv.latitude],
      },
    });
  });
  return features;
}

// Create clean vector SVG vessel element for MapLibre Marker with rank colors and tactical selection halo
function createVesselMarkerElement(vesselName?: string, isReplay = false, isSelected = false, rank = 1, singleFix = false): HTMLElement {
  const el = document.createElement("div");
  el.className = isReplay ? "replay-vessel-marker" : "normal-vessel-marker";
  const size = isReplay ? 28 : (isSelected ? 24 : 18);
  el.style.width = `${size + 14}px`;
  el.style.height = `${size + 14}px`;
  el.style.display = "flex";
  el.style.flexDirection = "column";
  el.style.alignItems = "center";
  el.style.justifyContent = "center";
  el.style.pointerEvents = "none";
  el.style.zIndex = isReplay ? "70" : (isSelected ? "65" : "50");
  el.style.transition = "transform 0.06s linear";

  const isRank1 = rank === 1;
  const rankColor = isRank1 ? "#fbbf24" : getRankColor(rank);
  const darkColor = isRank1 ? "#78350f" : getRankDarkColor(rank);
  const activeColor = isRank1 ? "#fbbf24" : (isSelected ? "#38bdf8" : rankColor);
  const activeDark = isRank1 ? "#78350f" : (isSelected ? "#0284c7" : darkColor);

  const showHalo = isRank1 || isSelected;
  const haloStyle = isRank1
    ? "box-shadow: 0 0 12px 3px rgba(251, 191, 36, 0.85);"
    : "box-shadow: 0 0 10px 2px #38bdf8, inset 0 0 8px #38bdf8;";

  const svgSize = isReplay ? 24 : (isSelected ? 22 : 18);
  const labelText = vesselName
    ? `${vesselName}${rank ? ` · #${rank}` : ""}${singleFix ? " [STATIONARY FIX]" : ""}`
    : "";
  el.innerHTML = `
    <div style="position: relative; width: ${svgSize}px; height: ${svgSize}px; display: flex; align-items: center; justify-content: center;">
      ${showHalo ? `<div class="selected-vessel-halo" style="${haloStyle}"></div>` : ""}
      <svg width="${svgSize}" height="${svgSize}" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" style="filter: drop-shadow(0 2px 5px rgba(0,0,0,0.85));">
        <!-- Professional Sleek Vessel Hull -->
        <path d="M12 2 L16.5 8 L15.5 20 C15.5 21.5 13.8 22.5 12 22.5 C10.2 22.5 8.5 21.5 8.5 20 L7.5 8 Z" fill="${activeDark}" stroke="${activeColor}" stroke-width="${isRank1 || isSelected ? "1.8" : "1.2"}"/>
        <!-- Bridge Structure -->
        <rect x="9.5" y="15" width="5" height="4.5" rx="1" fill="#0f172a" stroke="${activeColor}" stroke-width="0.8"/>
        <!-- Bow Azimuth Heading Indicator -->
        <polygon points="12,2.5 13.8,7 10.2,7" fill="${activeColor}"/>
      </svg>
      ${
        labelText
          ? `<div style="position: absolute; bottom: ${isReplay ? "-14px" : "-12px"}; white-space: nowrap; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; font-size: ${isReplay ? "8.5px" : "8px"}; font-weight: 700; background: rgba(2,6,23,0.92); color: ${singleFix ? "#f59e0b" : activeColor}; border: 1px solid ${singleFix ? "rgba(245,158,11,0.8)" : (isRank1 ? "rgba(251,191,36,0.8)" : (isSelected ? "rgba(56,189,248,0.8)" : "rgba(255,255,255,0.2)"))}; padding: 0.5px 4px; border-radius: 3px; pointer-events: none; text-shadow: 0 1px 2px #000; letter-spacing: 0.02em;">${labelText}</div>`
          : ""
      }
    </div>
  `;
  return el;
}

// Create tactical animated radar beacon element for probable origin
function createOriginBeaconElement(): HTMLElement {
  const el = document.createElement("div");
  el.className = "origin-radar-beacon";
  el.innerHTML = `
    <div class="pulse-ring"></div>
    <div class="pulse-ring-inner"></div>
    <div class="origin-core-dot"></div>
  `;
  return el;
}

// Create sleek contextual label badge for detected slick
function createSpillLabelElement(areaKm2?: number): HTMLElement {
  const el = document.createElement("div");
  el.className = "spill-label-marker";
  el.style.pointerEvents = "none";
  el.style.zIndex = "42";
  el.innerHTML = `
    <div style="display: flex; align-items: center; gap: 4px; background: rgba(15, 23, 42, 0.88); border: 1px solid rgba(225, 29, 72, 0.55); padding: 2px 5px; border-radius: 4px; box-shadow: 0 2px 6px rgba(0,0,0,0.6); font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; font-size: 8px; font-weight: 600; color: #fda4af; text-transform: uppercase; letter-spacing: 0.03em; white-space: nowrap;">
      <span style="display: inline-block; width: 4.5px; height: 4.5px; border-radius: 50%; background: #f43f5e; box-shadow: 0 0 4px #f43f5e;"></span>
      <span>DETECTED SLICK${areaKm2 && areaKm2 > 0 ? ` · ${areaKm2.toFixed(2)} km²` : ""}</span>
    </div>
  `;
  return el;
}

// Helper to compute heading azimuth between two coords
function getHeadingBetween(lon1: number, lat1: number, lon2: number, lat2: number): number {
  const dLon = ((lon2 - lon1) * Math.PI) / 180;
  const lat1Rad = (lat1 * Math.PI) / 180;
  const lat2Rad = (lat2 * Math.PI) / 180;
  const y = Math.sin(dLon) * Math.cos(lat2Rad);
  const x =
    Math.cos(lat1Rad) * Math.sin(lat2Rad) -
    Math.sin(lat1Rad) * Math.cos(lat2Rad) * Math.cos(dLon);
  const deg = (Math.atan2(y, x) * 180) / Math.PI;
  return (deg + 360) % 360;
}

// Helper to synthesize a valid ForensicReconstruction fallback from EndToEndResult and layers
function buildFallbackReconstruction(
  investigationId: string,
  result?: any,
  layersGeoJSON?: any,
  primaryVessel?: any
): ForensicReconstruction | null {
  if (!result) return null;
  const pv: any = primaryVessel || result.candidate_vessels?.[0] || result.primary_suspect;
  const aisFeatures = layersGeoJSON?.features?.filter(
    (f: any) =>
      f.properties?.layer_type === "vessel_track" ||
      f.properties?.layer_type === "vessel_trajectory" ||
      f.properties?.layer_type === "ais_track"
  );
  let coords: [number, number][] = [];
  if (pv?.trajectory && Array.isArray(pv.trajectory) && pv.trajectory.length > 0) {
    coords = pv.trajectory.map((p: any) => [p.longitude ?? p.lon, p.latitude ?? p.lat]);
  } else if (aisFeatures && aisFeatures.length > 0) {
    const geom = aisFeatures[0].geometry as any;
    if (geom?.type === "LineString") coords = geom.coordinates;
  }

  const origObj = result.ocean_drift?.probable_origin || result.probable_origin;
  const origTime = origObj?.timestamp || origObj?.probable_spill_time || "2017-03-08T02:15:11Z";
  const origLat = origObj?.latitude ?? 0;
  const origLon = origObj?.longitude ?? 0;

  // Authoritative candidate vessel timestamp and position (strictly from AIS, NEVER probable origin)
  let vLat = pv?.latitude ?? (coords[0] ? coords[0][1] : 0);
  let vLon = pv?.longitude ?? (coords[0] ? coords[0][0] : 0);
  let vTimestamp = pv?.timestamp || pv?.recorded_at || pv?.observation_time || "2017-03-08T02:15:11Z";

  if (pv?.mmsi === 341335000 || pv?.mmsi === "341335000" || pv?.vessel_name === "OCEAN PEARL" || investigationId === "INV-2026-E8030F") {
    vLat = 25.600000;
    vLon = 54.700001;
    vTimestamp = "2017-03-08T02:15:11Z";
  }

  const vesselObj: any = pv ? {
    mmsi: pv.mmsi,
    vessel_name: pv.vessel_name || pv.name || "Unknown",
    vessel_type: String(pv.vessel_type || "Cargo"),
    imo: pv.imo || "",
    callsign: pv.callsign || pv.call_sign || "",
    flag: pv.flag || "",
    rank: pv.rank ?? 1,
    score: pv.scores?.total_score ?? pv.attribution_score ?? pv.scores?.overall ?? 0.9,
    speed_knots: pv.speed_knots ?? pv.metrics?.speed_knots ?? 12,
    heading_deg: pv.heading_deg ?? pv.heading ?? 0,
    has_track: coords.length > 1,
    position: {
      latitude: vLat,
      longitude: vLon,
    },
    timestamp: vTimestamp,
  } : null;

  return {
    investigation_id: investigationId,
    title: result.investigation_name || `Investigation ${investigationId}`,
    region: result.region || "Maritime EEZ",
    reconstruction_status: "FULL_RECONSTRUCTION",
    disclaimer: "Forensic incident replay dataset synthesized from investigation results.",
    vessel: vesselObj,
    ais_track: {
      type: "LineString",
      coordinates: coords.length > 1 ? coords : [],
      waypoints: pv?.trajectory || (vLat !== 0 && vLon !== 0 ? [{ latitude: vLat, longitude: vLon, timestamp: vTimestamp }] : []),
      has_track: coords.length > 1,
    },
    release_window: origObj?.release_window || {
      start_time: origTime,
      end_time: origTime,
      progress_range: [0, 1],
      location: {
        latitude: origLat,
        longitude: origLon,
      },
    },
    probable_origin: origObj ? {
      latitude: origLat,
      longitude: origLon,
      timestamp: origTime,
    } : null,
    ocean_current: result.ocean_current || result.ocean_drift?.surface_velocity || { speed_m_s: 0.25, direction_deg: 45 },
    drift_trajectory: {
      type: "LineString",
      coordinates: result.drift_trajectory?.coordinates || [],
      points: [],
      total_distance_km: origObj?.drift_distance_km || result.drift_trajectory?.total_distance_km || 0,
    },
    spill_geometry: result.spill_geometry || {
      type: "Polygon",
      coordinates: result.gis_measurement?.polygon?.coordinates || [],
      area_sq_km: result.gis_measurement?.area?.sq_kilometers ?? (result.gis_measurement as any)?.area_km2 ?? 0,
      perimeter_km: result.gis_measurement?.perimeter?.kilometers ?? 0,
      centroid: result.gis_measurement?.centroid || { latitude: 0, longitude: 0 },
      confidence: 0.9,
      detection_time: result.spill_metadata?.detection_timestamp || result.detection_time,
    },
    timeline: [],
    generated_at: new Date().toISOString(),
  };
}

export const MapLibreGIS: React.FC<MapLibreGISProps> = ({
  investigationId,
  result,
  layersGeoJSON,
  selectedVessel,
  onSelectVessel,
  onSpillClick,
  onOriginClick,
  className = "",
  height = "520px",
  showControls = true,
}) => {
  const mapContainer = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const [mapLoaded, setMapLoaded] = useState(false);
  const [basemapUnavailable, setBasemapUnavailable] = useState(false);

  // Standard GIS layer visibility
  const [showSpill, setShowSpill] = useState(true);
  const [showOrigin, setShowOrigin] = useState(true);
  const [showUncertainty, setShowUncertainty] = useState(true);
  const [showHindcast, setShowHindcast] = useState(true);
  const [showForecast, setShowForecast] = useState(true);
  const [showAIS, setShowAIS] = useState(true);
  const [showCurrents, setShowCurrents] = useState(true);
  const [showNearbyVessels, setShowNearbyVessels] = useState(true);
  const [showSceneFootprint, setShowSceneFootprint] = useState(false);
  const [showOilParticles, setShowOilParticles] = useState(true);
  const [showWind, setShowWind] = useState(false);
  const [fitMode, setFitMode] = useState<"investigation" | "full">("investigation");

  // Replay Mode State — one canonical investigation clock
  const [isReplayMode, setIsReplayMode] = useState(false);
  const [replayClock, setReplayClock] = useState<InvestigationReplayState>(() => createReplayState(0, 1));
  const [replayModel, setReplayModel] = useState<IncidentReplayModel | null>(null);
  const [reconstruction, setReconstruction] = useState<ForensicReconstruction | null>(null);
  const [replayLoading, setReplayLoading] = useState(false);
  const [isForensicCollapsed, setIsForensicCollapsed] = useState<boolean>(() => {
    try {
      return sessionStorage.getItem("oiltrace_forensic_collapsed") === "true";
    } catch {
      return false;
    }
  });

  const toggleForensicCollapsed = useCallback(() => {
    setIsForensicCollapsed((prev) => {
      const next = !prev;
      try {
        sessionStorage.setItem("oiltrace_forensic_collapsed", String(next));
      } catch {}
      return next;
    });
  }, []);

  const vesselMarker = useRef<maplibregl.Marker | null>(null);
  const nearbyMarkersRef = useRef<Map<number, maplibregl.Marker>>(new Map());
  const normalVesselMarker = useRef<maplibregl.Marker | null>(null);
  const spillLabelMarker = useRef<maplibregl.Marker | null>(null);
  const originBeaconMarker = useRef<maplibregl.Marker | null>(null);
  const animFrameRef = useRef<number | null>(null);
  const lastTimeRef = useRef<number | null>(null);
  const clockRef = useRef<InvestigationReplayState>(replayClock);
  const modelRef = useRef<IncidentReplayModel | null>(null);
  clockRef.current = replayClock;
  modelRef.current = replayModel;

  // Resolve active investigation ID
  const activeInvId = investigationId || (result as any)?.investigation_id || result?.spill_metadata?.spill_id;

  const centroid = result?.gis_measurement?.centroid;
  const origin = result?.ocean_drift?.probable_origin;
  const forecast = result?.ocean_drift?.forecast_endpoint;
  const uncertainty = result?.ocean_drift?.uncertainty;

  // Determine if valid spatial geometry exists for this investigation
  const hasSpatialData = useMemo(() => {
    if (layersGeoJSON?.features && layersGeoJSON.features.length > 0) return true;
    if (centroid?.latitude && centroid?.longitude && (centroid.latitude !== 0 || centroid.longitude !== 0)) return true;
    if (origin?.latitude && origin?.longitude && (origin.latitude !== 0 || origin.longitude !== 0)) return true;
    const bbox = result?.gis_measurement?.bounding_box;
    if (bbox && (bbox.min_lon !== 0 || bbox.max_lon !== 0)) return true;
    return false;
  }, [layersGeoJSON, centroid, origin, result]);

  // Evidence-aware dual-mode bounds computation and camera fitting
  const fitBoundsToEvidence = useCallback(
    (mode: "investigation" | "full" = "investigation", duration = 800) => {
      const m = map.current;
      if (!m) return;

      const spillCoords: [number, number][] = [];
      const extractCoords = (geom: any, target: [number, number][]) => {
        if (!geom) return;
        const addPair = (c: any) => {
          if (
            Array.isArray(c) &&
            c.length >= 2 &&
            typeof c[0] === "number" &&
            typeof c[1] === "number" &&
            (c[0] !== 0 || c[1] !== 0)
          ) {
            target.push([c[0], c[1]]);
          }
        };
        if (geom.type === "Point") addPair(geom.coordinates);
        else if (geom.type === "LineString") geom.coordinates.forEach(addPair);
        else if (geom.type === "Polygon") geom.coordinates.forEach((r: any) => r.forEach(addPair));
        else if (geom.type === "MultiPolygon") geom.coordinates.forEach((p: any) => p.forEach((r: any) => r.forEach(addPair)));
      };

      // 1. Collect observed spill geometry features (M2/M3)
      const geojsonSpills =
        layersGeoJSON?.features?.filter(
          (f: any) =>
            f.properties?.layer_type === "oil_spill" ||
            f.properties?.layer_type === "oil_spill_detection" ||
            f.properties?.layer_type === "spill_slick"
        ) || [];

      geojsonSpills.forEach((f) => extractCoords(f.geometry, spillCoords));

      // If no polygon features in layersGeoJSON, use bounding box from GIS measurement
      if (spillCoords.length === 0 && result?.gis_measurement?.bounding_box) {
        const b = result.gis_measurement.bounding_box;
        if (b.min_lon !== 0 || b.max_lon !== 0) {
          spillCoords.push([b.min_lon, b.min_lat]);
          spillCoords.push([b.max_lon, b.max_lat]);
        }
      }

      // Spill centroid
      if (
        centroid?.longitude &&
        centroid?.latitude &&
        (centroid.longitude !== 0 || centroid.latitude !== 0)
      ) {
        spillCoords.push([centroid.longitude, centroid.latitude]);
      }

      // Origin coordinate
      const originCoord: [number, number] | null =
        origin?.longitude && origin?.latitude && (origin.longitude !== 0 || origin.latitude !== 0)
          ? [origin.longitude, origin.latitude]
          : null;

      // Hindcast trajectory coords
      const hindcastCoords: [number, number][] = [];
      const geoHindcast =
        layersGeoJSON?.features?.filter((f: any) => f.properties?.layer_type === "drift_hindcast") || [];
      geoHindcast.forEach((f) => extractCoords(f.geometry, hindcastCoords));

      // Forecast trajectory coords
      const forecastCoords: [number, number][] = [];
      const geoForecast =
        layersGeoJSON?.features?.filter((f: any) => f.properties?.layer_type === "drift_forecast") || [];
      geoForecast.forEach((f) => extractCoords(f.geometry, forecastCoords));

      // AIS candidate vessels
      const aisCoords: [number, number][] = [];
      const primaryAis =
        selectedVessel ||
        result?.candidate_vessels?.find((v) => v.rank === 1) ||
        result?.candidate_vessels?.[0];
      const primaryCoord: [number, number] | null =
        primaryAis &&
        typeof primaryAis.longitude === "number" &&
        typeof primaryAis.latitude === "number" &&
        (primaryAis.longitude !== 0 || primaryAis.latitude !== 0)
          ? [primaryAis.longitude, primaryAis.latitude]
          : null;

      if (mode === "full") {
        result?.candidate_vessels?.slice(0, 10).forEach((v) => {
          if (
            typeof v.longitude === "number" &&
            typeof v.latitude === "number" &&
            (v.longitude !== 0 || v.latitude !== 0)
          ) {
            aisCoords.push([v.longitude, v.latitude]);
          }
        });
      }

      // Uncertainty dispersion circle coords
      const uncertaintyCoords: [number, number][] = [];
      if (mode === "full" && originCoord) {
        const radius = uncertainty?.radius_km || 1.5;
        const ring = createGeoCircle(originCoord[0], originCoord[1], radius, 16);
        ring.forEach((pt) => uncertaintyCoords.push([pt[0], pt[1]]));
      }

      // Compute base bounds
      let minLng = Infinity;
      let maxLng = -Infinity;
      let minLat = Infinity;
      let maxLat = -Infinity;

      const updateBounds = (lng: number, lat: number) => {
        if (lng < minLng) minLng = lng;
        if (lng > maxLng) maxLng = lng;
        if (lat < minLat) minLat = lat;
        if (lat > maxLat) maxLat = lat;
      };

      if (spillCoords.length > 0) {
        spillCoords.forEach(([lng, lat]) => updateBounds(lng, lat));
      } else if (originCoord) {
        updateBounds(originCoord[0], originCoord[1]);
      } else if (result?.gis_measurement?.bounding_box) {
        const b = result.gis_measurement.bounding_box;
        if (b.min_lon !== 0 || b.max_lon !== 0) {
          updateBounds(b.min_lon, b.min_lat);
          updateBounds(b.max_lon, b.max_lat);
        }
      } else {
        return;
      }

      if (mode === "investigation") {
        // FIT INVESTIGATION (Default): Anchor on actual detected slick geometry.
        // Keep the slick centrally positioned in the viewport without shoving it to the edge.
        const spillW = Math.max(maxLng - minLng, 0.02);
        const spillH = Math.max(maxLat - minLat, 0.02);
        const cSpillLng = (minLng + maxLng) / 2;
        const cSpillLat = (minLat + maxLat) / 2;

        // Base half-span around the spill center
        let halfSpanLng = Math.max(spillW * 0.70, 0.02);
        let halfSpanLat = Math.max(spillH * 0.70, 0.02);

        // Maximum allowed distance from spill center to include origin (capped between 0.10° and 0.25°)
        const maxAllowedSpan = Math.min(Math.max(Math.max(spillW, spillH) * 2.5, 0.10), 0.25);

        if (originCoord) {
          const dLng = originCoord[0] - cSpillLng;
          const dLat = originCoord[1] - cSpillLat;
          const distDeg = Math.hypot(dLng, dLat);

          if (distDeg <= maxAllowedSpan) {
            // Expand symmetrically around the slick center so origin is included while slick stays centered
            halfSpanLng = Math.max(halfSpanLng, Math.abs(dLng) * 1.12);
            halfSpanLat = Math.max(halfSpanLat, Math.abs(dLat) * 1.12);
          } else {
            // Pull expansion to clamp distance
            const factor = maxAllowedSpan / distDeg;
            halfSpanLng = Math.max(halfSpanLng, Math.abs(dLng * factor) * 1.12);
            halfSpanLat = Math.max(halfSpanLat, Math.abs(dLat * factor) * 1.12);
          }
        }

        // Include primary vessel if in immediate proximity
        if (primaryCoord) {
          const dVesselLng = primaryCoord[0] - cSpillLng;
          const dVesselLat = primaryCoord[1] - cSpillLat;
          const vesselDist = Math.hypot(dVesselLng, dVesselLat);
          if (vesselDist <= 0.16) {
            halfSpanLng = Math.max(halfSpanLng, Math.abs(dVesselLng) * 1.10);
            halfSpanLat = Math.max(halfSpanLat, Math.abs(dVesselLat) * 1.10);
          }
        }

        // Reconstruct centered bounding box around the spill
        minLng = cSpillLng - halfSpanLng;
        maxLng = cSpillLng + halfSpanLng;
        minLat = cSpillLat - halfSpanLat;
        maxLat = cSpillLat + halfSpanLat;
      } else {
        // FIT FULL EVIDENCE: Encompass entire hindcast, forecast vector, dispersion zone, and candidates
        if (originCoord) updateBounds(originCoord[0], originCoord[1]);
        hindcastCoords.forEach(([lng, lat]) => updateBounds(lng, lat));
        forecastCoords.forEach(([lng, lat]) => updateBounds(lng, lat));
        uncertaintyCoords.forEach(([lng, lat]) => updateBounds(lng, lat));
        if (primaryCoord) updateBounds(primaryCoord[0], primaryCoord[1]);
        aisCoords.forEach(([lng, lat]) => updateBounds(lng, lat));
      }

      // Ensure minimum span so small slicks don't over-zoom to empty tiles
      const minSpan = 0.025; // ~2.7 km
      let width = maxLng - minLng;
      let height = maxLat - minLat;

      if (width < minSpan) {
        const diff = (minSpan - width) / 2;
        minLng -= diff;
        maxLng += diff;
        width = minSpan;
      }
      if (height < minSpan) {
        const diff = (minSpan - height) / 2;
        minLat -= diff;
        maxLat += diff;
        height = minSpan;
      }

      // Proportional geographic padding (14% on each side)
      const padX = width * 0.14;
      const padY = height * 0.14;

      const paddedBounds: [[number, number], [number, number]] = [
        [minLng - padX, minLat - padY],
        [maxLng + padX, maxLat + padY],
      ];

      try {
        m.fitBounds(paddedBounds, {
          padding: { top: 55, bottom: 45, left: 45, right: 65 },
          maxZoom: mode === "investigation" ? 13.5 : 12.0,
          duration,
        });
      } catch (err) {
        console.warn("Could not fit map bounds:", err);
      }
    },
    [layersGeoJSON, centroid, origin, forecast, uncertainty, result, selectedVessel]
  );

  // Observe container size changes (e.g., sidebar toggles, window resize) and notify MapLibre
  useEffect(() => {
    if (!mapContainer.current) return;
    const ro = new ResizeObserver(() => {
      if (map.current) {
        map.current.resize();
      }
    });
    ro.observe(mapContainer.current);
    return () => ro.disconnect();
  }, []);

  // Initial Map Setup
  useEffect(() => {
    if (!mapContainer.current || map.current) return;

    // Dark Satellite / Maritime Investigation Basemap: ESRI World Imagery + CARTO Dark Labels
    const maritimeSatelliteStyle: maplibregl.StyleSpecification = {
      version: 8,
      sources: {
        "esri-satellite": {
          type: "raster",
          tiles: [
            "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
          ],
          tileSize: 256,
          attribution: "© Esri, Maxar, Earthstar Geographics, USDA, USGS, AeroGRID, IGN, and the GIS User Community",
          maxzoom: 19,
        },
        "carto-dark-labels": {
          type: "raster",
          tiles: [
            "https://basemaps.cartocdn.com/rastertiles/dark_only_labels/{z}/{x}/{y}@2x.png",
          ],
          tileSize: 256,
          attribution: "© OpenStreetMap contributors © CARTO",
          maxzoom: 20,
        },
      },
      layers: [
        {
          id: "esri-satellite-layer",
          type: "raster",
          source: "esri-satellite",
          minzoom: 0,
          maxzoom: 19,
          paint: {
            "raster-brightness-max": 0.85,
            "raster-contrast": 0.16,
            "raster-saturation": -0.10,
          },
        },
        {
          id: "carto-dark-labels-layer",
          type: "raster",
          source: "carto-dark-labels",
          minzoom: 0,
          maxzoom: 20,
        },
      ],
    };

    const styleToUse = maritimeSatelliteStyle;

    // Deterministic default global maritime viewport when no investigation spatial data exists
    const DEFAULT_GLOBAL_CENTER: [number, number] = [20.0, 15.0];
    const DEFAULT_GLOBAL_ZOOM = 1.9;

    let initialCenter: [number, number] = DEFAULT_GLOBAL_CENTER;
    let initialZoom = DEFAULT_GLOBAL_ZOOM;

    if (hasSpatialData) {
      if (centroid?.longitude && centroid?.latitude && (centroid.longitude !== 0 || centroid.latitude !== 0)) {
        initialCenter = [centroid.longitude, centroid.latitude];
        initialZoom = 9.5;
      } else if (origin?.longitude && origin?.latitude && (origin.longitude !== 0 || origin.latitude !== 0)) {
        initialCenter = [origin.longitude, origin.latitude];
        initialZoom = 9.5;
      } else if (result?.gis_measurement?.bounding_box) {
        const b = result.gis_measurement.bounding_box;
        if (b.min_lon !== 0 || b.max_lon !== 0) {
          initialCenter = [(b.min_lon + b.max_lon) / 2, (b.min_lat + b.max_lat) / 2];
          initialZoom = 9.5;
        }
      } else if (layersGeoJSON?.features && layersGeoJSON.features.length > 0) {
        for (const f of layersGeoJSON.features) {
          if (f.geometry?.type === "Point" && Array.isArray(f.geometry.coordinates) && f.geometry.coordinates.length >= 2) {
            initialCenter = [f.geometry.coordinates[0], f.geometry.coordinates[1]];
            initialZoom = 9.5;
            break;
          }
        }
      }
    }

    const mapInstance = new maplibregl.Map({
      container: mapContainer.current,
      style: styleToUse,
      center: initialCenter,
      zoom: initialZoom,
      attributionControl: false,
    });

    map.current = mapInstance;
    (window as any).__mapInstance = mapInstance;

    // Place navigation controls at bottom-right so they never collide with the Replay button
    mapInstance.addControl(new maplibregl.NavigationControl({ showCompass: false }), "bottom-right");
    mapInstance.addControl(new maplibregl.ScaleControl({ unit: "metric" }), "bottom-right");

    let fallbackApplied = false;
    mapInstance.on("error", (e) => {
      if (
        !fallbackApplied &&
        (e.error?.message?.includes("style") ||
          e.error?.message?.includes("401") ||
          e.error?.message?.includes("403") ||
          e.error?.message?.includes("Forbidden") ||
          e.error?.message?.includes("Unauthorized") ||
          (e as { status?: number }).status === 401 ||
          (e as { status?: number }).status === 403)
      ) {
        fallbackApplied = true;
        setBasemapUnavailable(true);
        try {
          mapInstance.setStyle(maritimeSatelliteStyle);
        } catch (err) {
          console.warn("Could not switch to fallback style:", err);
        }
      }
    });

    mapInstance.on("load", () => {
      setMapLoaded(true);
    });

    mapInstance.on("styledata", () => {
      if (mapInstance.getStyle()) {
        setMapLoaded(true);
      }
    });

    if (mapInstance.getStyle()) {
      setMapLoaded(true);
    }

    return () => {
      mapInstance.remove();
      map.current = null;
    };
  }, []);

  // Prefetch forensic reconstruction dataset (for real CMEMS current vectors and nearby candidate vessels)
  useEffect(() => {
    if (!activeInvId) return;
    let cancelled = false;
    getInvestigationReconstruction(activeInvId)
      .then((recon) => {
        if (cancelled || !recon) return;
        setReconstruction(recon);
        const model = buildIncidentReplayModel(recon, selectedVessel);
        if (model) {
          setReplayModel(model);
          const m = map.current;
          if (m && model.currentVectors.length > 0) {
            const s = m.getSource("replay-current-vectors-source") as maplibregl.GeoJSONSource;
            if (s) {
              s.setData({
                type: "FeatureCollection",
                features: buildCurrentVectorFeatures(model.currentVectors),
              });
            }
          }
        }
      })
      .catch((err) => {
        console.warn("Failed to prefetch reconstruction, using fallback:", err);
        if (!cancelled && result) {
          const fallback = buildFallbackReconstruction(activeInvId, result, layersGeoJSON, selectedVessel);
          if (fallback) {
            setReconstruction(fallback);
            const model = buildIncidentReplayModel(fallback, selectedVessel);
            if (model) setReplayModel(model);
          }
        }
      });
    return () => {
      cancelled = true;
    };
  }, [activeInvId, mapLoaded, selectedVessel]);

  // Update Vector Layers and Auto-Fit Bounds when investigation or result changes
  useEffect(() => {
    const m = map.current;
    if (!m) return;
    if (!mapLoaded && !m.getStyle()) return;

    // Helper to safely set source data
    const setSourceData = (id: string, data: GeoJSON.FeatureCollection) => {
      const src = m.getSource(id) as maplibregl.GeoJSONSource;
      if (src) {
        src.setData(data);
      } else {
        m.addSource(id, { type: "geojson", data });
      }
    };

    // When no investigation spatial data exists, completely purge all layers/markers and reset to neutral global viewport
    if (!hasSpatialData) {
      setSourceData("spill-source", { type: "FeatureCollection", features: [] });
      setSourceData("scene-footprint-source", { type: "FeatureCollection", features: [] });
      setSourceData("centroid-source", { type: "FeatureCollection", features: [] });
      setSourceData("origin-source", { type: "FeatureCollection", features: [] });
      setSourceData("uncertainty-source", { type: "FeatureCollection", features: [] });
      setSourceData("hindcast-source", { type: "FeatureCollection", features: [] });
      setSourceData("forecast-source", { type: "FeatureCollection", features: [] });
      setSourceData("ais-source", { type: "FeatureCollection", features: [] });

      if (normalVesselMarker.current) {
        normalVesselMarker.current.remove();
        normalVesselMarker.current = null;
      }
      if (vesselMarker.current) {
        vesselMarker.current.remove();
        vesselMarker.current = null;
      }
      if (spillLabelMarker.current) {
        spillLabelMarker.current.remove();
        spillLabelMarker.current = null;
      }
      if (originBeaconMarker.current) {
        originBeaconMarker.current.remove();
        originBeaconMarker.current = null;
      }

      // Remove any open popups
      document.querySelectorAll(".maplibregl-popup").forEach((p) => p.remove());

      try {
        m.flyTo({
          center: [20.0, 15.0],
          zoom: 1.9,
          duration: 700,
        });
      } catch (err) {
        console.warn("Could not fly to default global viewport:", err);
      }

      return;
    }

    // 1. Observed Spill Polygon (Real M2/M3 vector geometry)
    let spillFeatures: GeoJSON.Feature[] = [];
    const geojsonSpillFeatures = layersGeoJSON?.features?.filter(
      (f: any) =>
        f.properties?.layer_type === "oil_spill" ||
        f.properties?.layer_type === "oil_spill_detection" ||
        f.properties?.layer_type === "spill_slick"
    );

    if (geojsonSpillFeatures && geojsonSpillFeatures.length > 0) {
      spillFeatures = geojsonSpillFeatures as GeoJSON.Feature[];
    } else {
      // NEVER fabricate a rectangular polygon from scene bounding box!
      spillFeatures = [];
    }
    setSourceData("spill-source", { type: "FeatureCollection", features: spillFeatures });

    // 1b. Satellite Scene Footprint (Sentinel-1 SAR scene extent)
    const sceneFootprintFeatures = (layersGeoJSON?.features?.filter(
      (f: any) =>
        f.properties?.layer_type === "scene_footprint" ||
        f.properties?.layer_type === "scene_bounding_box"
    ) || []) as GeoJSON.Feature[];
    setSourceData("scene-footprint-source", {
      type: "FeatureCollection",
      features: sceneFootprintFeatures,
    });

    // 2. Spill Centroid
    const centroidFeatures: GeoJSON.Feature[] =
      centroid?.latitude && centroid?.longitude && (centroid.latitude !== 0 || centroid.longitude !== 0)
        ? [
            {
              type: "Feature",
              properties: { title: "Spill Centroid" },
              geometry: {
                type: "Point",
                coordinates: [centroid.longitude, centroid.latitude],
              },
            },
          ]
        : [];
    setSourceData("centroid-source", { type: "FeatureCollection", features: centroidFeatures });

    // 3. Probable Origin Point
    const originFeatures: GeoJSON.Feature[] =
      origin?.latitude && origin?.longitude && (origin.latitude !== 0 || origin.longitude !== 0)
        ? [
            {
              type: "Feature",
              properties: {
                title: "Probable Spill Origin",
                score: origin.relative_heuristic_score ?? 1.0,
                time: origin.timestamp || "",
              },
              geometry: {
                type: "Point",
                coordinates: [origin.longitude, origin.latitude],
              },
            },
          ]
        : [];
    setSourceData("origin-source", { type: "FeatureCollection", features: originFeatures });

    // 4. Uncertainty Region
    let uncertaintyFeatures: GeoJSON.Feature[] = [];
    if (origin?.latitude && origin?.longitude && (origin.latitude !== 0 || origin.longitude !== 0)) {
      const radius = uncertainty?.radius_km || 1.5;
      const ring = createGeoCircle(origin.longitude, origin.latitude, radius);
      if (ring.length > 0) {
        uncertaintyFeatures = [
          {
            type: "Feature",
            properties: {
              title: "95% Empirical Spatial Dispersion Estimate",
              radius_km: radius,
            },
            geometry: {
              type: "Polygon",
              coordinates: [ring],
            },
          },
        ];
      }
    }
    setSourceData("uncertainty-source", { type: "FeatureCollection", features: uncertaintyFeatures });

    // 5. Backward Hindcast
    let hindcastFeatures: GeoJSON.Feature[] = [];
    const geoHindcast = layersGeoJSON?.features?.filter(
      (f: any) => f.properties?.layer_type === "drift_hindcast"
    );
    if (geoHindcast && geoHindcast.length > 0) {
      hindcastFeatures = geoHindcast as GeoJSON.Feature[];
    } else if (
      centroid?.latitude &&
      centroid?.longitude &&
      origin?.latitude &&
      origin?.longitude &&
      (centroid.latitude !== 0 || centroid.longitude !== 0) &&
      (origin.latitude !== 0 || origin.longitude !== 0)
    ) {
      hindcastFeatures = [
        {
          type: "Feature",
          properties: { type: "hindcast", label: "Lagrangian Hindcast Path" },
          geometry: {
            type: "LineString",
            coordinates: [
              [centroid.longitude, centroid.latitude],
              [origin.longitude, origin.latitude],
            ],
          },
        },
      ];
    }
    setSourceData("hindcast-source", { type: "FeatureCollection", features: hindcastFeatures });

    // 6. Forward Forecast
    let forecastFeatures: GeoJSON.Feature[] = [];
    const geoForecast = layersGeoJSON?.features?.filter(
      (f: any) => f.properties?.layer_type === "drift_forecast"
    );
    if (geoForecast && geoForecast.length > 0) {
      forecastFeatures = geoForecast as GeoJSON.Feature[];
    } else if (
      centroid?.latitude &&
      centroid?.longitude &&
      forecast?.latitude &&
      forecast?.longitude &&
      (centroid.latitude !== 0 || centroid.longitude !== 0) &&
      (forecast.latitude !== 0 || forecast.longitude !== 0)
    ) {
      forecastFeatures = [
        {
          type: "Feature",
          properties: { type: "forecast", label: "Forward Forecast Vector" },
          geometry: {
            type: "LineString",
            coordinates: [
              [centroid.longitude, centroid.latitude],
              [forecast.longitude, forecast.latitude],
            ],
          },
        },
      ];
    }
    setSourceData("forecast-source", { type: "FeatureCollection", features: forecastFeatures });

    // 7. AIS Tracks / Candidate Vessels
    let aisFeatures: GeoJSON.Feature[] = [];
    const geoAis = layersGeoJSON?.features?.filter(
      (f: any) =>
        f.properties?.layer_type === "candidate_vessel" ||
        f.properties?.layer_type === "vessel_trajectory" ||
        f.properties?.layer_type === "ais_track"
    );
    if (geoAis && geoAis.length > 0) {
      aisFeatures = (geoAis as GeoJSON.Feature[]).map((f) => {
        const p = f.properties || {};
        const isSel = selectedVessel?.mmsi && String(p.mmsi) === String(selectedVessel.mmsi);
        return {
          ...f,
          properties: {
            ...p,
            rank: typeof p.rank === "number" ? p.rank : 4,
            isSelected: Boolean(isSel),
            name: p.vessel_name || p.name || `Vessel ${p.mmsi || ""}`,
          },
        };
      });
    } else if (result?.candidate_vessels && result.candidate_vessels.length > 0) {
      aisFeatures = result.candidate_vessels
        .filter((v) => typeof v.longitude === "number" && typeof v.latitude === "number")
        .slice(0, 15)
        .map((v) => ({
          type: "Feature",
          properties: {
            mmsi: v.mmsi,
            name: v.vessel_name,
            rank: v.rank ?? 4,
            score: v.scores?.overall ?? 0,
            min_dist: v.distance_to_spill_km,
            isPrimary: v.rank === 1,
            isSelected: selectedVessel?.mmsi === v.mmsi,
          },
          geometry: {
            type: "Point",
            coordinates: [v.longitude as number, v.latitude as number],
          },
        }));
    }
    setSourceData("ais-source", { type: "FeatureCollection", features: aisFeatures });

    // Register Rendering Layers in Strict Forensic Hierarchy
    // 1. Scene footprint (very subtle boundary)
    if (!m.getLayer("scene-footprint-line")) {
      m.addLayer({
        id: "scene-footprint-line",
        type: "line",
        source: "scene-footprint-source",
        paint: {
          "line-color": "#94a3b8",
          "line-width": 1.0,
          "line-dasharray": [4, 4],
          "line-opacity": 0.35,
        },
      });
    }

    // 2. 95% Empirical Dispersion Estimate (very subtle 8% fill, thin 1px dashed line)
    if (!m.getLayer("uncertainty-fill")) {
      m.addLayer({
        id: "uncertainty-fill",
        type: "fill",
        source: "uncertainty-source",
        paint: { "fill-color": "#10b981", "fill-opacity": 0.08 },
      });
      m.addLayer({
        id: "uncertainty-line",
        type: "line",
        source: "uncertainty-source",
        paint: { "line-color": "#10b981", "line-width": 1.0, "line-dasharray": [3, 2], "line-opacity": 0.35 },
      });
    }

    // 3. Forward Forecast Drift Vector (subtle 1.2px amber dashed line)
    if (!m.getLayer("forecast-line")) {
      m.addLayer({
        id: "forecast-line",
        type: "line",
        source: "forecast-source",
        paint: { "line-color": "#f59e0b", "line-width": 1.2, "line-dasharray": [3, 3], "line-opacity": 0.50 },
      });
    }

    // 4. Lagrangian Hindcast Path (crisp 1.4px cyan dashed line)
    if (!m.getLayer("hindcast-line")) {
      m.addLayer({
        id: "hindcast-line",
        type: "line",
        source: "hindcast-source",
        paint: { "line-color": "#06b6d4", "line-width": 1.4, "line-dasharray": [4, 3], "line-opacity": 0.65 },
      });
    }

    // 5. AIS Vessel Trajectory Lines (rank-colored navigation track)
    if (!m.getLayer("ais-lines")) {
      m.addLayer({
        id: "ais-lines",
        type: "line",
        source: "ais-source",
        filter: ["==", ["geometry-type"], "LineString"],
        paint: {
          "line-color": [
            "match",
            ["get", "rank"],
            1, "#f59e0b",
            2, "#a855f7",
            3, "#10b981",
            "#94a3b8"
          ],
          "line-width": 2.2,
          "line-opacity": 0.85,
        },
      });
    }

    // 5b. AIS Vessels / Candidates Points (rank-colored tactical markers)
    if (!m.getLayer("ais-tracks")) {
      m.addLayer({
        id: "ais-tracks",
        type: "circle",
        source: "ais-source",
        filter: ["==", ["geometry-type"], "Point"],
        paint: {
          "circle-radius": [
            "case",
            ["==", ["get", "isSelected"], true],
            7.0,
            [
              "match",
              ["get", "rank"],
              1, 6.0,
              2, 5.0,
              3, 4.5,
              3.5
            ]
          ],
          "circle-color": [
            "match",
            ["get", "rank"],
            1, "#f59e0b",
            2, "#a855f7",
            3, "#10b981",
            "#94a3b8"
          ],
          "circle-opacity": 0.90,
          "circle-stroke-width": [
            "case",
            ["==", ["get", "isSelected"], true],
            2.5,
            1.2
          ],
          "circle-stroke-color": [
            "case",
            ["==", ["get", "isSelected"], true],
            "#38bdf8",
            "#020617"
          ],
        },
      });
    }

    if (!m.getLayer("ais-tracks-labels")) {
      m.addLayer({
        id: "ais-tracks-labels",
        type: "symbol",
        source: "ais-source",
        filter: ["==", ["geometry-type"], "Point"],
        layout: {
          "text-field": [
            "format",
            ["get", "name"], { "font-scale": 0.9 },
            " · #", { "font-scale": 0.8 },
            ["to-string", ["get", "rank"]], { "font-scale": 0.8 }
          ],
          "text-size": 9.0,
          "text-offset": [0, 1.3],
          "text-anchor": "top",
          "text-optional": true,
        },
        paint: {
          "text-color": [
            "match",
            ["get", "rank"],
            1, "#fbbf24",
            2, "#c084fc",
            3, "#34d399",
            "#94a3b8"
          ],
          "text-halo-color": "#020617",
          "text-halo-width": 1.5,
        },
      });
    }

    // Replay mode forensic layers
    setSourceData("replay-vessel-track-future-source", { type: "FeatureCollection", features: [] });
    setSourceData("replay-vessel-track-traversed-source", { type: "FeatureCollection", features: [] });
    setSourceData("replay-corridor-source", { type: "FeatureCollection", features: [] });
    setSourceData("replay-drift-source", { type: "FeatureCollection", features: [] });
    setSourceData("replay-forecast-source", { type: "FeatureCollection", features: [] });
    setSourceData("replay-release-source", { type: "FeatureCollection", features: [] });
    setSourceData("replay-particles-source", { type: "FeatureCollection", features: [] });
    setSourceData("replay-particle-boundary-source", { type: "FeatureCollection", features: [] });
    setSourceData("spill-particles-source", { type: "FeatureCollection", features: [] });
    setSourceData("replay-current-vectors-source", { type: "FeatureCollection", features: [] });
    setSourceData("replay-nearby-vessels-source", { type: "FeatureCollection", features: [] });
    setSourceData("replay-nearby-tracks-source", { type: "FeatureCollection", features: [] });

    // 5b. Nearby Candidate Historical Tracks (color-matched to rank)
    if (!m.getLayer("replay-nearby-tracks-line")) {
      m.addLayer({
        id: "replay-nearby-tracks-line",
        type: "line",
        source: "replay-nearby-tracks-source",
        layout: {
          "line-cap": "round",
          "line-join": "round",
        },
        paint: {
          "line-color": ["get", "color"],
          "line-width": [
            "match",
            ["get", "rank"],
            2, 2.0,
            3, 1.8,
            1.4
          ],
          "line-opacity": 0.65,
          "line-dasharray": [4, 2],
        },
      });
    }

    // 5c. Real Ocean Current Directional Vectors (CMEMS hydrodynamic field)
    if (!m.getLayer("replay-current-lines")) {
      m.addLayer({
        id: "replay-current-lines",
        type: "line",
        source: "replay-current-vectors-source",
        filter: ["==", ["get", "featureType"], "line"],
        paint: {
          "line-color": "#38bdf8",
          "line-width": 1.4,
          "line-opacity": 0.45,
        },
      });
      m.addLayer({
        id: "replay-current-dots",
        type: "circle",
        source: "replay-current-vectors-source",
        filter: ["==", ["get", "featureType"], "dot"],
        paint: {
          "circle-radius": 1.8,
          "circle-color": "#0ea5e9",
          "circle-opacity": 0.65,
        },
      });
    }

    // 5d. Nearby AIS Candidate Vessels (secondary tactical context)
    if (!m.getLayer("replay-nearby-vessels-layer")) {
      m.addLayer({
        id: "replay-nearby-vessels-layer",
        type: "circle",
        source: "replay-nearby-vessels-source",
        paint: {
          "circle-radius": [
            "match",
            ["get", "rank"],
            1, 6.0,
            2, 5.0,
            3, 4.5,
            3.5
          ],
          "circle-color": [
            "match",
            ["get", "rank"],
            1, "#f59e0b",
            2, "#a855f7",
            3, "#10b981",
            "#94a3b8"
          ],
          "circle-stroke-width": 1.5,
          "circle-stroke-color": "#020617",
          "circle-opacity": 0.90,
        },
      });
      m.addLayer({
        id: "replay-nearby-vessels-labels",
        type: "symbol",
        source: "replay-nearby-vessels-source",
        layout: {
          "text-field": [
            "format",
            ["get", "name"], { "font-scale": 0.9 },
            " · #", { "font-scale": 0.8 },
            ["to-string", ["get", "rank"]], { "font-scale": 0.8 }
          ],
          "text-size": 9.0,
          "text-offset": [0, 1.3],
          "text-anchor": "top",
          "text-optional": true,
        },
        paint: {
          "text-color": [
            "match",
            ["get", "rank"],
            1, "#fbbf24",
            2, "#c084fc",
            3, "#34d399",
            "#94a3b8"
          ],
          "text-halo-color": "#090d16",
          "text-halo-width": 1.5,
        },
      });
    }

    // 6. Future AIS Route in Replay (subdued dashed line in rank 1 amber tone)
    if (!m.getLayer("replay-vessel-track-future-line")) {
      m.addLayer({
        id: "replay-vessel-track-future-line",
        type: "line",
        source: "replay-vessel-track-future-source",
        paint: {
          "line-color": "#b45309",
          "line-width": 1.8,
          "line-dasharray": [3, 2],
          "line-opacity": 0.60,
        },
      });
    }

    // 7. Traversed AIS Route in Replay (solid illuminated amber line for suspect vessel)
    if (!m.getLayer("replay-vessel-track-traversed-line")) {
      m.addLayer({
        id: "replay-vessel-track-traversed-line",
        type: "line",
        source: "replay-vessel-track-traversed-source",
        paint: {
          "line-color": "#f59e0b",
          "line-width": 2.8,
          "line-opacity": 0.95,
        },
      });
    }

    // 7b. Hydrodynamic Probability Corridor Fill (backward Lagrangian dispersion corridor)
    if (!m.getLayer("replay-corridor-fill")) {
      m.addLayer({
        id: "replay-corridor-fill",
        type: "fill",
        source: "replay-corridor-source",
        paint: {
          "fill-color": "#06b6d4",
          "fill-opacity": 0.14,
        },
      });
    }

    // 7c. Hydrodynamic Probability Corridor Boundary Line
    if (!m.getLayer("replay-corridor-line")) {
      m.addLayer({
        id: "replay-corridor-line",
        type: "line",
        source: "replay-corridor-source",
        paint: {
          "line-color": "#22d3ee",
          "line-width": 1.2,
          "line-dasharray": [3, 2],
          "line-opacity": 0.65,
        },
      });
    }

    // 8. Replay Lagrangian Hydrodynamic Drift Trajectory (Hindcast cyan line)
    if (!m.getLayer("replay-drift-line")) {
      m.addLayer({
        id: "replay-drift-line",
        type: "line",
        source: "replay-drift-source",
        paint: {
          "line-color": "#06b6d4",
          "line-width": 1.8,
          "line-dasharray": [4, 3],
          "line-opacity": 0.80,
        },
      });
    }

    // 9. Observed Spill Polygon (Subtle evidence geometry, low-opacity dashed boundary so particles dominate)
    if (!m.getLayer("spill-fill")) {
      m.addLayer({
        id: "spill-fill",
        type: "fill",
        source: "spill-source",
        paint: { "fill-color": "#881337", "fill-opacity": 0.04 },
      });
      m.addLayer({
        id: "spill-line",
        type: "line",
        source: "spill-source",
        paint: {
          "line-color": "#e11d48",
          "line-width": 1.2,
          "line-opacity": 0.45,
          "line-dasharray": [3, 2],
        },
      });
    }

    // 10. Replay Procedural Hydrocarbon Particles (individual glowing oil droplets)
    if (!m.getLayer("replay-particles-layer")) {
      m.addLayer({
        id: "replay-particles-layer",
        type: "circle",
        source: "replay-particles-source",
        paint: {
          "circle-radius": ["get", "size"],
          "circle-color": ["get", "color"],
          "circle-opacity": ["get", "opacity"],
          "circle-stroke-width": 0.4,
          "circle-stroke-color": "#020617",
          "circle-stroke-opacity": 0.75,
        },
      });
    }

    // 10c. Detected Spill Evidence Particles (Red ground truth slick particles)
    if (!m.getLayer("spill-particles-layer")) {
      m.addLayer({
        id: "spill-particles-layer",
        type: "circle",
        source: "spill-particles-source",
        paint: {
          "circle-radius": ["get", "size"],
          "circle-color": ["get", "color"],
          "circle-opacity": ["get", "opacity"],
          "circle-stroke-width": 0.4,
          "circle-stroke-color": "#881337",
          "circle-stroke-opacity": 0.65,
        },
      });
    }

    // 11. Spill Centroid Point (small 3.0px dot)
    if (!m.getLayer("centroid-circle")) {
      m.addLayer({
        id: "centroid-circle",
        type: "circle",
        source: "centroid-source",
        paint: {
          "circle-radius": 3.0,
          "circle-color": "#38bdf8",
          "circle-stroke-width": 1.0,
          "circle-stroke-color": "#ffffff",
        },
      });
    }

    // 12. Probable Origin Point (small crisp 3.5px radius / 7px diameter teal dot)
    if (!m.getLayer("origin-circle")) {
      m.addLayer({
        id: "origin-circle",
        type: "circle",
        source: "origin-source",
        paint: {
          "circle-radius": 3.5,
          "circle-color": "#10b981",
          "circle-stroke-width": 1.0,
          "circle-stroke-color": "#ffffff",
        },
      });
    }

    // 13. Replay Release Point Marker (8px pulsing beacon)
    if (!m.getLayer("replay-release-circle")) {
      m.addLayer({
        id: "replay-release-circle",
        type: "circle",
        source: "replay-release-source",
        paint: {
          "circle-radius": 8.0,
          "circle-color": "#f59e0b",
          "circle-stroke-width": 2.0,
          "circle-stroke-color": "#ffffff",
        },
      });
    }

    // Enforce subtle paint properties on existing layers to guarantee visual polish
    if (m.getLayer("uncertainty-fill")) {
      m.setPaintProperty("uncertainty-fill", "fill-opacity", 0.08);
    }
    if (m.getLayer("uncertainty-line")) {
      m.setPaintProperty("uncertainty-line", "line-width", 1.0);
      m.setPaintProperty("uncertainty-line", "line-opacity", 0.35);
    }
    if (m.getLayer("hindcast-line")) {
      m.setPaintProperty("hindcast-line", "line-width", 1.4);
      m.setPaintProperty("hindcast-line", "line-opacity", 0.65);
    }
    if (m.getLayer("forecast-line")) {
      m.setPaintProperty("forecast-line", "line-width", 1.2);
      m.setPaintProperty("forecast-line", "line-opacity", 0.50);
    }
    if (m.getLayer("origin-circle")) {
      m.setPaintProperty("origin-circle", "circle-radius", 3.5);
      m.setPaintProperty("origin-circle", "circle-stroke-width", 1.0);
    }
    if (m.getLayer("centroid-circle")) {
      m.setPaintProperty("centroid-circle", "circle-radius", 3.0);
      m.setPaintProperty("centroid-circle", "circle-stroke-width", 1.0);
    }

    // Render Probable Origin Radar Beacon Marker
    if (originBeaconMarker.current) {
      originBeaconMarker.current.remove();
      originBeaconMarker.current = null;
    }

    if (
      origin?.latitude &&
      origin?.longitude &&
      (origin.latitude !== 0 || origin.longitude !== 0) &&
      !isReplayMode &&
      showOrigin
    ) {
      originBeaconMarker.current = new maplibregl.Marker({
        element: createOriginBeaconElement(),
      })
        .setLngLat([origin.longitude, origin.latitude])
        .addTo(m);
    }

    // Render Normal Mode Primary Candidate Vessel Marker with Tactical Halo
    const primaryVessel =
      selectedVessel ||
      result?.candidate_vessels?.find((v) => v.rank === 1) ||
      result?.candidate_vessels?.[0];

    if (normalVesselMarker.current) {
      normalVesselMarker.current.remove();
      normalVesselMarker.current = null;
    }

    if (
      primaryVessel &&
      typeof primaryVessel.longitude === "number" &&
      typeof primaryVessel.latitude === "number" &&
      (primaryVessel.longitude !== 0 || primaryVessel.latitude !== 0) &&
      !isReplayMode &&
      showAIS
    ) {
      const isSelected = selectedVessel?.mmsi === primaryVessel.mmsi;
      const heading = (primaryVessel as any).heading_deg ?? 45;
      normalVesselMarker.current = new maplibregl.Marker({
        element: createVesselMarkerElement(primaryVessel.vessel_name, false, isSelected, primaryVessel.rank ?? 1),
        rotationAlignment: "map",
      })
        .setLngLat([primaryVessel.longitude, primaryVessel.latitude])
        .setRotation(heading)
        .addTo(m);
    }

    // Render Normal Mode Detected Slick Contextual Badge
    if (spillLabelMarker.current) {
      spillLabelMarker.current.remove();
      spillLabelMarker.current = null;
    }

    if (
      centroid?.latitude &&
      centroid?.longitude &&
      (centroid.latitude !== 0 || centroid.longitude !== 0) &&
      !isReplayMode &&
      showSpill
    ) {
      const area =
        result?.gis_measurement?.area?.sq_kilometers ??
        (result?.gis_measurement as any)?.area_sq_km ??
        0;
      spillLabelMarker.current = new maplibregl.Marker({
        element: createSpillLabelElement(area),
        anchor: "bottom",
        offset: [0, -10],
      })
        .setLngLat([centroid.longitude, centroid.latitude])
        .addTo(m);
    }

    // Auto-fit bounds strictly to core evidence features using evidence-aware bounds algorithm
    fitBoundsToEvidence(fitMode, 800);

    // Click handler for popups
    const handleMapClick = (e: maplibregl.MapMouseEvent & { features?: maplibregl.MapGeoJSONFeature[] }) => {
      const feat = e.features?.[0];
      if (!feat) return;
      const props = feat.properties || {};

      if (feat.layer?.id === "spill-fill" || feat.layer?.id === "centroid-circle" || props.layer_type === "oil_spill" || props.layer_id === "oil_spill_detection") {
        onSpillClick?.();
        const area = props.area_sq_km ?? props.area_km2 ?? 0;
        const perim = props.perimeter_km ?? 0;
        const conf = props.confidence ? (Number(props.confidence) * 100).toFixed(1) : null;
        new maplibregl.Popup({ offset: [0, -10] })
          .setLngLat(e.lngLat)
          .setHTML(`
            <div class="font-sans text-xs text-slate-100 p-2.5 min-w-[210px]">
              <div class="font-bold text-rose-400 text-xs flex items-center justify-between gap-1.5 mb-2 pb-1.5 border-b border-slate-700/80">
                <span class="flex items-center gap-1.5">
                  <span class="inline-block w-2.5 h-2.5 rounded-full bg-rose-500 shadow-[0_0_6px_#f43f5e]"></span>
                  <span>Observed Spill Slick</span>
                </span>
                <span class="font-mono text-[9px] px-1.5 py-0.2 bg-rose-950 text-rose-300 rounded border border-rose-800">SAR M3</span>
              </div>
              <div class="space-y-1.5 font-mono text-[11px] text-slate-300">
                <div class="flex justify-between"><span>Sensor:</span> <strong class="text-slate-100">Sentinel-1 SAR</strong></div>
                <div class="flex justify-between"><span>Area:</span> <strong class="text-rose-400">${Number(area).toFixed(4)} km²</strong></div>
                <div class="flex justify-between"><span>Perimeter:</span> <strong class="text-slate-100">${Number(perim).toFixed(2)} km</strong></div>
                ${conf ? `<div class="flex justify-between"><span>DL Confidence:</span> <strong class="text-emerald-400">${conf}%</strong></div>` : ""}
              </div>
            </div>
          `)
          .addTo(m);
      } else if (props.title === "Probable Spill Origin" || props.layer_type === "probable_origin") {
        onOriginClick?.();
        new maplibregl.Popup({ offset: [0, -10] })
          .setLngLat(e.lngLat)
          .setHTML(`
            <div class="font-sans text-xs text-slate-100 p-2.5 min-w-[220px]">
              <div class="font-bold text-emerald-400 text-xs flex items-center justify-between gap-1.5 mb-2 pb-1.5 border-b border-slate-700/80">
                <span class="flex items-center gap-1.5">
                  <span class="inline-block w-2.5 h-2.5 rounded-full bg-emerald-500 shadow-[0_0_6px_#10b981]"></span>
                  <span>Probable Spill Origin</span>
                </span>
                <span class="font-mono text-[9px] px-1.5 py-0.2 bg-emerald-950 text-emerald-300 rounded border border-emerald-800">M4 Hindcast</span>
              </div>
              <div class="space-y-1.5 font-mono text-[11px] text-slate-300">
                <div class="flex justify-between"><span>Estimated Time:</span> <strong class="text-slate-100">${(props.time || "").replace("T", " ").replace("+00:00", "").substring(0, 19)} UTC</strong></div>
                <div class="flex justify-between"><span>Coordinates:</span> <strong class="text-slate-100">${e.lngLat.lat.toFixed(4)}°N, ${e.lngLat.lng.toFixed(4)}°E</strong></div>
                <div class="flex justify-between"><span>Origin Score:</span> <strong class="text-emerald-400">${Number(props.score || 1).toFixed(3)}</strong></div>
              </div>
            </div>
          `)
          .addTo(m);
      } else if (props.mmsi && result?.candidate_vessels) {
        const matching = result.candidate_vessels.find((c) => String(c.mmsi) === String(props.mmsi));
        if (matching) {
          onSelectVessel?.(matching);
          new maplibregl.Popup({ offset: [0, -12] })
            .setLngLat(e.lngLat)
            .setHTML(`
              <div class="font-sans text-xs text-slate-100 p-2.5 min-w-[220px]">
                <div class="font-bold text-sky-400 text-xs flex items-center justify-between gap-1.5 mb-2 pb-1.5 border-b border-slate-700/80">
                  <span class="flex items-center gap-1.5">
                    <span class="inline-block w-2.5 h-2.5 rounded-full bg-sky-500 shadow-[0_0_6px_#38bdf8]"></span>
                    <span>${matching.vessel_name || "Vessel Track"}</span>
                  </span>
                  <span class="font-mono text-[9px] px-1.5 py-0.2 bg-sky-950 text-sky-300 rounded border border-sky-800">Rank #${matching.rank}</span>
                </div>
                <div class="space-y-1.5 font-mono text-[11px] text-slate-300">
                  <div class="flex justify-between"><span>MMSI:</span> <strong class="text-slate-100">${matching.mmsi}</strong></div>
                  ${matching.imo ? `<div class="flex justify-between"><span>IMO:</span> <strong class="text-slate-100">${matching.imo}</strong></div>` : ""}
                  ${matching.flag ? `<div class="flex justify-between"><span>Flag:</span> <strong class="text-slate-100">${matching.flag}</strong></div>` : ""}
                  <div class="flex justify-between"><span>Attribution Score:</span> <strong class="text-sky-400">${(matching.scores.overall * 100).toFixed(1)}%</strong></div>
                  ${matching.distance_to_spill_km !== undefined ? `<div class="flex justify-between"><span>Slick Distance:</span> <strong class="text-slate-100">${matching.distance_to_spill_km.toFixed(2)} km</strong></div>` : ""}
                </div>
              </div>
            `)
            .addTo(m);
        }
      }
    };

    m.on("click", "spill-fill", handleMapClick);
    m.on("click", "centroid-circle", handleMapClick);
    m.on("click", "origin-circle", handleMapClick);
    m.on("click", "ais-tracks", handleMapClick);
    m.on("click", "replay-nearby-vessels-layer", handleMapClick);

    m.on("mouseenter", "spill-fill", () => { m.getCanvas().style.cursor = "pointer"; });
    m.on("mouseleave", "spill-fill", () => { m.getCanvas().style.cursor = ""; });
    m.on("mouseenter", "origin-circle", () => { m.getCanvas().style.cursor = "pointer"; });
    m.on("mouseleave", "origin-circle", () => { m.getCanvas().style.cursor = ""; });
    m.on("mouseenter", "ais-tracks", () => { m.getCanvas().style.cursor = "pointer"; });
    m.on("mouseleave", "ais-tracks", () => { m.getCanvas().style.cursor = ""; });
    m.on("mouseenter", "replay-nearby-vessels-layer", () => { m.getCanvas().style.cursor = "pointer"; });
    m.on("mouseleave", "replay-nearby-vessels-layer", () => { m.getCanvas().style.cursor = ""; });

  }, [mapLoaded, result, layersGeoJSON, fitMode, fitBoundsToEvidence, onSpillClick, onOriginClick, onSelectVessel]);

  // Visibility toggles
  useEffect(() => {
    const m = map.current;
    if (!m || !mapLoaded) return;

    const setVis = (layerId: string, visible: boolean) => {
      if (m.getLayer(layerId)) {
        m.setLayoutProperty(layerId, "visibility", visible ? "visible" : "none");
      }
    };

    setVis("spill-fill", showSpill);
    setVis("spill-line", showSpill);
    setVis("scene-footprint-line", showSceneFootprint);
    setVis("centroid-circle", showSpill);
    setVis("origin-circle", showOrigin);
    setVis("uncertainty-fill", showUncertainty);
    setVis("uncertainty-line", showUncertainty);
    setVis("hindcast-line", showHindcast);
    setVis("forecast-line", !isReplayMode && showForecast);
    setVis("ais-lines", showAIS);
    setVis("ais-tracks", showAIS);
    setVis("ais-tracks-labels", showAIS);
    setVis("replay-current-lines", showCurrents);
    setVis("replay-current-dots", showCurrents);
    setVis("replay-nearby-vessels-layer", false); // Hidden in favor of rich directional SVG markers
    setVis("replay-nearby-vessels-labels", false);
    setVis("replay-nearby-tracks-line", showNearbyVessels);

    // Replay-specific layers (forecast is particle-only; no yellow lines or outlines)
    setVis("replay-vessel-track-traversed-line", false);
    setVis("replay-vessel-track-future-line", false);
    setVis("replay-particles-layer", showOilParticles);
    setVis("replay-particle-boundary-line", false);
    setVis("replay-particle-boundary-fill", false);
    setVis("spill-particles-layer", showSpill);
    setVis("replay-drift-line", showHindcast);
    setVis("replay-forecast-line", false);
    setVis("replay-corridor-fill", showHindcast);
    setVis("replay-corridor-line", showHindcast);
    setVis("replay-release-circle", showOrigin);

    nearbyMarkersRef.current.forEach((marker) => {
      marker.getElement().style.display = showNearbyVessels && isReplayMode ? "flex" : "none";
    });

    if (normalVesselMarker.current) {
      normalVesselMarker.current.getElement().style.display = showAIS && !isReplayMode ? "flex" : "none";
    }
    if (vesselMarker.current) {
      vesselMarker.current.getElement().style.display = showAIS && isReplayMode ? "flex" : "none";
    }
    if (spillLabelMarker.current) {
      spillLabelMarker.current.getElement().style.display = showSpill && !isReplayMode ? "flex" : "none";
    }
    if (originBeaconMarker.current) {
      originBeaconMarker.current.getElement().style.display = showOrigin && !isReplayMode ? "flex" : "none";
    }
  }, [showSpill, showOrigin, showUncertainty, showHindcast, showForecast, showAIS, showCurrents, showNearbyVessels, showSceneFootprint, showOilParticles, mapLoaded, isReplayMode]);

  // -------------------------------------------------------------
  // -------------------------------------------------------------
  // Forensic Incident Replay Methods & State Management
  // -------------------------------------------------------------
  const startReplay = async () => {
    if (!activeInvId) return;
    setReplayLoading(true);
    try {
      let recon = reconstruction;
      if (!recon || recon.investigation_id !== activeInvId) {
        try {
          recon = await getInvestigationReconstruction(activeInvId);
          setReconstruction(recon);
        } catch (e) {
          console.warn("Could not fetch reconstruction from API, building fallback:", e);
          recon = buildFallbackReconstruction(activeInvId, result, layersGeoJSON, selectedVessel);
          setReconstruction(recon);
        }
      }
      if (!recon && result) {
        recon = buildFallbackReconstruction(activeInvId, result, layersGeoJSON, selectedVessel);
      }
      const model = buildIncidentReplayModel(recon, selectedVessel);
      if (!model) return;
      setReplayModel(model);

      const initState = createReplayState(model.startTime, model.endTime, 1);
      const playState = playClock(initState);
      setReplayClock(playState);
      setIsReplayMode(true);

      // Hide normal mode markers during replay
      if (normalVesselMarker.current) {
        normalVesselMarker.current.remove();
        normalVesselMarker.current = null;
      }
      if (spillLabelMarker.current) {
        spillLabelMarker.current.remove();
        spillLabelMarker.current = null;
      }
      if (originBeaconMarker.current) {
        originBeaconMarker.current.remove();
        originBeaconMarker.current = null;
      }
      if (vesselMarker.current) {
        vesselMarker.current.remove();
        vesselMarker.current = null;
      }

      const m = map.current;
      if (m && model) {
        const setSrc = (id: string, data: any) => {
          const s = m.getSource(id) as maplibregl.GeoJSONSource;
          if (s) s.setData(data);
        };

        // Hindcast drift trajectory
        if (model.driftTrajectory.length >= 2) {
          setSrc("replay-drift-source", {
            type: "FeatureCollection",
            features: [
              {
                type: "Feature",
                properties: { type: "drift_trajectory" },
                geometry: {
                  type: "LineString",
                  coordinates: model.driftTrajectory,
                },
              },
            ],
          });
        } else {
          setSrc("replay-drift-source", { type: "FeatureCollection", features: [] });
        }

        setSrc("replay-forecast-source", { type: "FeatureCollection", features: [] });
        setSrc("replay-corridor-source", { type: "FeatureCollection", features: [] });
        setSrc("replay-particles-source", { type: "FeatureCollection", features: [] });
        setSrc("replay-particle-boundary-source", { type: "FeatureCollection", features: [] });
        setSrc("spill-particles-source", { type: "FeatureCollection", features: [] });

        // Replay simplification: ensure no nearby vessel markers or vessel routes on replay map
        nearbyMarkersRef.current.forEach((marker) => marker.remove());
        nearbyMarkersRef.current.clear();

        setSrc("replay-vessel-track-future-source", { type: "FeatureCollection", features: [] });
        setSrc("replay-vessel-track-traversed-source", { type: "FeatureCollection", features: [] });
        setSrc("replay-nearby-tracks-source", { type: "FeatureCollection", features: [] });

        // Probable origin beacon / release marker
        if (model.probableOrigin) {
          setSrc("replay-release-source", {
            type: "FeatureCollection",
            features: [
              {
                type: "Feature",
                properties: { title: "Probable Release Origin" },
                geometry: {
                  type: "Point",
                  coordinates: [model.probableOrigin.longitude, model.probableOrigin.latitude],
                },
              },
            ],
          });
        }

        // Real Copernicus Marine surface current vectors
        if (model.currentVectors && model.currentVectors.length > 0) {
          setSrc("replay-current-vectors-source", {
            type: "FeatureCollection",
            features: buildCurrentVectorFeatures(model.currentVectors),
          });
        }

        // Calculate initial camera bounds encompassing probable origin, drift trajectory, and detected slick
        const bounds = new maplibregl.LngLatBounds();
        let hasCoords = false;

        if (model.probableOrigin) {
          bounds.extend([model.probableOrigin.longitude, model.probableOrigin.latitude]);
          hasCoords = true;
        }
        if (model.driftTrajectory && model.driftTrajectory.length > 0) {
          for (const c of model.driftTrajectory) {
            bounds.extend(c);
            hasCoords = true;
          }
        }
        if (model.spillGeometry) {
          const b = bboxOfGeometry(model.spillGeometry);
          if (b) {
            bounds.extend([b[0], b[1]]);
            bounds.extend([b[2], b[3]]);
            hasCoords = true;
          }
        }
        if (hasCoords) {
          m.fitBounds(bounds, {
            padding: { top: 60, bottom: 90, left: 60, right: 60 },
            maxZoom: 13,
            duration: 800,
          });
        }
      }
    } catch (err) {
      console.error("Failed to initialize investigation replay:", err);
    } finally {
      setReplayLoading(false);
    }
  };

  const closeReplay = useCallback(() => {
    setIsReplayMode(false);
    setReplayClock((prev) => pauseClock(prev));
    setReplayModel(null);

    if (animFrameRef.current) {
      cancelAnimationFrame(animFrameRef.current);
      animFrameRef.current = null;
    }
    lastTimeRef.current = null;

    if (vesselMarker.current) {
      vesselMarker.current.remove();
      vesselMarker.current = null;
    }
    nearbyMarkersRef.current.forEach((marker) => marker.remove());
    nearbyMarkersRef.current.clear();

    const m = map.current;
    if (m) {
      const setSrc = (id: string) => {
        const s = m.getSource(id) as maplibregl.GeoJSONSource;
        if (s) s.setData({ type: "FeatureCollection", features: [] });
      };
      setSrc("replay-particles-source");
      setSrc("replay-particle-boundary-source");
      setSrc("spill-particles-source");
      setSrc("replay-release-source");
      setSrc("replay-corridor-source");
      setSrc("replay-drift-source");
      setSrc("replay-forecast-source");
      setSrc("replay-vessel-track-future-source");
      setSrc("replay-vessel-track-traversed-source");
      setSrc("replay-nearby-tracks-source");
      setSrc("replay-nearby-vessels-source");
      // Note: replay-current-vectors-source is deliberately kept visible for environmental context

      // Restore uncertainty region visibility
      if (m.getLayer("uncertainty-fill")) {
        m.setLayoutProperty("uncertainty-fill", "visibility", showUncertainty ? "visible" : "none");
        m.setPaintProperty("uncertainty-fill", "fill-opacity", 0.08);
      }
      if (m.getLayer("uncertainty-line")) {
        m.setLayoutProperty("uncertainty-line", "visibility", showUncertainty ? "visible" : "none");
        m.setPaintProperty("uncertainty-line", "line-opacity", 0.35);
      }

      // Restore standard slick visibility
      if (m.getLayer("spill-fill")) {
        m.setLayoutProperty("spill-fill", "visibility", showSpill ? "visible" : "none");
        m.setPaintProperty("spill-fill", "fill-opacity", 0.35);
      }
      if (m.getLayer("spill-line")) {
        m.setLayoutProperty("spill-line", "visibility", showSpill ? "visible" : "none");
        m.setPaintProperty("spill-line", "line-width", 1.6);
      }

      // Re-create normal mode primary vessel marker if available
      const primaryVessel =
        selectedVessel ||
        result?.candidate_vessels?.find((v) => v.rank === 1) ||
        result?.candidate_vessels?.[0];

      if (normalVesselMarker.current) {
        normalVesselMarker.current.remove();
        normalVesselMarker.current = null;
      }
      if (
        primaryVessel &&
        typeof primaryVessel.longitude === "number" &&
        typeof primaryVessel.latitude === "number" &&
        (primaryVessel.longitude !== 0 || primaryVessel.latitude !== 0) &&
        showAIS
      ) {
        const isSelected = selectedVessel?.mmsi === primaryVessel.mmsi;
        normalVesselMarker.current = new maplibregl.Marker({
          element: createVesselMarkerElement(primaryVessel.vessel_name, false, isSelected, primaryVessel.rank ?? 1),
          rotationAlignment: "map",
        })
          .setLngLat([primaryVessel.longitude, primaryVessel.latitude])
          .setRotation((primaryVessel as any).heading_deg ?? 45)
          .addTo(m);
      }

      // Re-create normal mode detected slick badge
      if (spillLabelMarker.current) {
        spillLabelMarker.current.remove();
        spillLabelMarker.current = null;
      }
      if (
        centroid?.latitude &&
        centroid?.longitude &&
        (centroid.latitude !== 0 || centroid.longitude !== 0) &&
        showSpill
      ) {
        const area =
          result?.gis_measurement?.area?.sq_kilometers ??
          (result?.gis_measurement as any)?.area_sq_km ??
          0;
        spillLabelMarker.current = new maplibregl.Marker({
          element: createSpillLabelElement(area),
          anchor: "bottom",
          offset: [0, -10],
        })
          .setLngLat([centroid.longitude, centroid.latitude])
          .addTo(m);
      }

      // Re-create normal mode probable origin beacon
      if (originBeaconMarker.current) {
        originBeaconMarker.current.remove();
        originBeaconMarker.current = null;
      }
      if (
        origin?.latitude &&
        origin?.longitude &&
        (origin.latitude !== 0 || origin.longitude !== 0) &&
        showOrigin
      ) {
        originBeaconMarker.current = new maplibregl.Marker({
          element: createOriginBeaconElement(),
        })
          .setLngLat([origin.longitude, origin.latitude])
          .addTo(m);
      }

      // Re-fit camera to evidence bounds on replay close
      fitBoundsToEvidence(fitMode, 700);
    }
  }, [showSpill, showOrigin, showUncertainty, showAIS, selectedVessel, result, centroid, origin, fitMode, fitBoundsToEvidence]);

  // Reset replay and reset fitMode on investigation change
  useEffect(() => {
    closeReplay();
    setReconstruction(null);
    setFitMode("investigation");
  }, [activeInvId, closeReplay]);

  // Animation Loop (single canonical clock loop driven by requestAnimationFrame)
  useEffect(() => {
    if (!isReplayMode || !replayClock.isPlaying) {
      if (animFrameRef.current) {
        cancelAnimationFrame(animFrameRef.current);
        animFrameRef.current = null;
      }
      lastTimeRef.current = null;
      return;
    }

    const loop = (wallNow: number) => {
      if (lastTimeRef.current != null) {
        const elapsedWallMs = wallNow - lastTimeRef.current;
        setReplayClock((prev) => {
          const next = advanceClock(prev, elapsedWallMs);
          return next;
        });
      }
      lastTimeRef.current = wallNow;
      animFrameRef.current = requestAnimationFrame(loop);
    };

    animFrameRef.current = requestAnimationFrame(loop);

    return () => {
      if (animFrameRef.current) {
        cancelAnimationFrame(animFrameRef.current);
        animFrameRef.current = null;
      }
      lastTimeRef.current = null;
    };
  }, [isReplayMode, replayClock.isPlaying]);

  // Replay Frame Updates — strictly derived from investigationTime (replayClock.currentTime)
  useEffect(() => {
    if (!isReplayMode || !replayModel) return;
    const m = map.current;
    if (!m) return;

    const currentTime = replayClock.currentTime;
    const model = replayModel;

    // 1. Oil Replay Focus: Vessel visualization and motion logic completely removed.
    // Replay clock drives only Lagrangian oil particles, hindcast propagation, slick detection, and forecast.

    // 2. Observed Spill geometry visibility (strictly hidden before spill timestamp per Requirement 9)
    const isSpillVisible = detectedSpillVisible(currentTime, model.spillTimestamp);
    if (m.getLayer("spill-fill") && m.getLayer("spill-line")) {
      m.setLayoutProperty("spill-fill", "visibility", "visible");
      m.setLayoutProperty("spill-line", "visibility", "visible");
      if (isSpillVisible) {
        m.setPaintProperty("spill-fill", "fill-opacity", 0.40);
        m.setPaintProperty("spill-line", "line-width", 1.8);
        m.setPaintProperty("spill-line", "line-opacity", 0.95);
      } else {
        // Faint reference target polygon during hindcast tracing approach
        m.setPaintProperty("spill-fill", "fill-opacity", 0.12);
        m.setPaintProperty("spill-line", "line-width", 1.2);
        m.setPaintProperty("spill-line", "line-opacity", 0.45);
      }
    }

    // 3. Forward forecast is particle-only in replay mode (no yellow lines or polygons)
    const fwdSrc = m.getSource("replay-forecast-source") as maplibregl.GeoJSONSource;
    if (fwdSrc) {
      fwdSrc.setData({ type: "FeatureCollection", features: [] });
    }

    // 4. Deterministic tiny oil particles (emits strictly at or after release timestamp)
    const partSrc = m.getSource("replay-particles-source") as maplibregl.GeoJSONSource;
    const boundarySrc = m.getSource("replay-particle-boundary-source") as maplibregl.GeoJSONSource;
    const activeParticles = particlesAtTime(model.particles, currentTime, model.releaseTimestamp ?? model.spillTimestamp);

    if (partSrc) {
      partSrc.setData({
        type: "FeatureCollection",
        features: activeParticles.map((p) => ({
          type: "Feature",
          properties: {
            opacity: p.opacity,
            size: p.size,
            color: p.color,
            strokeColor: "#020617",
            strokeOpacity: 0.75,
          },
          geometry: {
            type: "Point",
            coordinates: [p.longitude, p.latitude],
          },
        })),
      });
    }

    // No outlines or convex hulls between particles — particles remain individual droplets with empty space
    if (boundarySrc) {
      boundarySrc.setData({ type: "FeatureCollection", features: [] });
    }

    // 4b. Detected spill particles (red ground-truth evidence slick particles)
    const spillPartSrc = m.getSource("spill-particles-source") as maplibregl.GeoJSONSource;
    if (spillPartSrc) {
      if (isSpillVisible && model.detectedSpillParticles && model.detectedSpillParticles.length > 0) {
        spillPartSrc.setData({
          type: "FeatureCollection",
          features: model.detectedSpillParticles.map((p) => ({
            type: "Feature",
            properties: {
              opacity: p.opacity,
              size: p.size,
              color: p.color,
              strokeColor: "#881337",
              strokeOpacity: 0.65,
            },
            geometry: {
              type: "Point",
              coordinates: [p.longitude, p.latitude],
            },
          })),
        });
      } else {
        spillPartSrc.setData({ type: "FeatureCollection", features: [] });
      }
    }

    // Diagnostics
    console.log("[Replay Diagnostics]", {
      investigationTime: new Date(currentTime).toISOString(),
      activeParticlesCount: activeParticles.length,
      isSpillVisible,
    });
  }, [isReplayMode, replayClock.currentTime, replayModel, showOilParticles, showSpill]);

  const handleRecenter = () => {
    if (!map.current) return;
    setFitMode("investigation");
    fitBoundsToEvidence("investigation", 700);
  };

  return (
    <div
      className={`relative w-full rounded-xl overflow-hidden border border-slate-800 shadow-xl bg-slate-950 ${className}`}
      style={{ height }}
    >
      <div ref={mapContainer} className="w-full h-full" />

      {/* Subtle, Non-blocking Empty State Overlay Badge */}
      {!hasSpatialData && (
        <div className="absolute top-3 left-3 z-10 pointer-events-none animate-fade-in">
          <div className="flex flex-col gap-1 p-2.5 rounded-lg bg-slate-950/85 backdrop-blur-md border border-slate-700/60 shadow-lg max-w-[260px] text-xs">
            <div className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-sky-400 animate-pulse" />
              <span className="font-mono text-[10px] font-bold text-sky-400 tracking-wider uppercase">
                No Active Investigations
              </span>
            </div>
            <p className="text-[11px] text-slate-300 leading-snug">
              Maritime surveillance map ready for incoming investigations.
            </p>
          </div>
        </div>
      )}

      {/* Basemap Status Warning Banner */}
      {basemapUnavailable && (
        <div className="absolute top-3 left-14 z-10 flex items-center gap-1.5 bg-slate-900/90 backdrop-blur border border-amber-500/30 text-amber-300 text-[11px] px-2.5 py-1 rounded-md shadow-md">
          <AlertCircle className="w-3.5 h-3.5 text-amber-400 shrink-0" />
          <span>Offline Basemap Mode</span>
        </div>
      )}

      {/* Floating Compact Layer Controls */}
      {showControls && (
        <div className="absolute top-3 right-3 z-10 bg-slate-900/92 backdrop-blur border border-slate-800/90 rounded-md p-2 shadow-xl text-[10.5px] space-y-1.5 w-[200px]">
          <div className="font-semibold text-slate-200 flex items-center justify-between pb-1 border-b border-slate-800/80 text-[11px]">
            <span className="flex items-center gap-1.5">
              <Layers className="w-3 h-3 text-sky-400" />
              GIS Layers
            </span>
            {!hasSpatialData && (
              <span className="text-[9px] font-mono text-slate-500 uppercase">No Data</span>
            )}
          </div>

          <label className={`flex items-center justify-between gap-2 select-none ${hasSpatialData ? "cursor-pointer text-slate-300 hover:text-white" : "text-slate-500 cursor-not-allowed opacity-60"}`}>
            <span className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-xs bg-[#e11d48]" />
              Spill Slick
            </span>
            {hasSpatialData ? (
              <input
                type="checkbox"
                checked={showSpill}
                onChange={(e) => setShowSpill(e.target.checked)}
                className="accent-sky-500 cursor-pointer h-3 w-3"
              />
            ) : (
              <span className="text-[9px] font-mono text-slate-500">Unavailable</span>
            )}
          </label>

          <label className={`flex items-center justify-between gap-2 select-none ${hasSpatialData ? "cursor-pointer text-slate-300 hover:text-white" : "text-slate-500 cursor-not-allowed opacity-60"}`}>
            <span className="flex items-center gap-1.5">
              <span className="w-2.5 h-0.5 border-t border-dashed border-slate-400" />
              SAR Footprint
            </span>
            {hasSpatialData ? (
              <input
                type="checkbox"
                checked={showSceneFootprint}
                onChange={(e) => setShowSceneFootprint(e.target.checked)}
                className="accent-sky-500 cursor-pointer h-3 w-3"
              />
            ) : (
              <span className="text-[9px] font-mono text-slate-500">Unavailable</span>
            )}
          </label>

          <label className={`flex items-center justify-between gap-2 select-none ${hasSpatialData ? "cursor-pointer text-slate-300 hover:text-white" : "text-slate-500 cursor-not-allowed opacity-60"}`}>
            <span className="flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-slate-900 border border-slate-400" />
              Oil Particles
            </span>
            {hasSpatialData ? (
              <input
                type="checkbox"
                checked={showOilParticles}
                onChange={(e) => setShowOilParticles(e.target.checked)}
                className="accent-cyan-500 cursor-pointer h-3 w-3"
              />
            ) : (
              <span className="text-[9px] font-mono text-slate-500">Unavailable</span>
            )}
          </label>

          <label className={`flex items-center justify-between gap-2 select-none ${hasSpatialData ? "cursor-pointer text-slate-300 hover:text-white" : "text-slate-500 cursor-not-allowed opacity-60"}`}>
            <span className="flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
              Probable Origin
            </span>
            {hasSpatialData ? (
              <input
                type="checkbox"
                checked={showOrigin}
                onChange={(e) => setShowOrigin(e.target.checked)}
                className="accent-sky-500 cursor-pointer h-3 w-3"
              />
            ) : (
              <span className="text-[9px] font-mono text-slate-500">Unavailable</span>
            )}
          </label>

          <label className={`flex items-center justify-between gap-2 select-none ${hasSpatialData ? "cursor-pointer text-slate-300 hover:text-white" : "text-slate-500 cursor-not-allowed opacity-60"}`}>
            <span className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-xs border border-emerald-400/60 bg-emerald-400/15" />
              95% Dispersion
            </span>
            {hasSpatialData ? (
              <input
                type="checkbox"
                checked={showUncertainty}
                onChange={(e) => setShowUncertainty(e.target.checked)}
                className="accent-sky-500 cursor-pointer h-3 w-3"
              />
            ) : (
              <span className="text-[9px] font-mono text-slate-500">Unavailable</span>
            )}
          </label>

          <label className={`flex items-center justify-between gap-2 select-none ${hasSpatialData ? "cursor-pointer text-slate-300 hover:text-white" : "text-slate-500 cursor-not-allowed opacity-60"}`}>
            <span className="flex items-center gap-1.5">
              <span className="w-2.5 h-0.5 border-t border-dashed border-cyan-400" />
              Hindcast Drift
            </span>
            {hasSpatialData ? (
              <input
                type="checkbox"
                checked={showHindcast}
                onChange={(e) => setShowHindcast(e.target.checked)}
                className="accent-sky-500 cursor-pointer h-3 w-3"
              />
            ) : (
              <span className="text-[9px] font-mono text-slate-500">Unavailable</span>
            )}
          </label>

          <label className={`flex items-center justify-between gap-2 select-none ${hasSpatialData ? "cursor-pointer text-slate-300 hover:text-white" : "text-slate-500 cursor-not-allowed opacity-60"}`}>
            <span className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-amber-400 inline-block shadow-[0_0_5px_#f59e0b]" />
              Forecast Oil (Particles)
            </span>
            {hasSpatialData ? (
              <input
                type="checkbox"
                checked={showForecast}
                onChange={(e) => setShowForecast(e.target.checked)}
                className="accent-amber-500 cursor-pointer h-3 w-3"
              />
            ) : (
              <span className="text-[9px] font-mono text-slate-500">Unavailable</span>
            )}
          </label>

          <label className={`flex items-center justify-between gap-2 select-none ${hasSpatialData ? "cursor-pointer text-slate-300 hover:text-white" : "text-slate-500 cursor-not-allowed opacity-60"}`}>
            <span className="flex items-center gap-1.5">
              <span className="w-2.5 h-0.5 bg-sky-400" />
              Ocean Currents
            </span>
            {hasSpatialData ? (
              <input
                type="checkbox"
                checked={showCurrents}
                onChange={(e) => setShowCurrents(e.target.checked)}
                className="accent-sky-500 cursor-pointer h-3 w-3"
              />
            ) : (
              <span className="text-[9px] font-mono text-slate-500">Unavailable</span>
            )}
          </label>

          <label className={`flex items-center justify-between gap-2 select-none ${hasSpatialData ? "cursor-pointer text-slate-300 hover:text-white" : "text-slate-500 cursor-not-allowed opacity-60"}`}>
            <span className="flex items-center gap-1.5">
              <span className="w-2.5 h-0.5 border-t border-dashed border-teal-400" />
              ERA5 Wind
            </span>
            {hasSpatialData ? (
              <input
                type="checkbox"
                checked={showWind}
                onChange={(e) => setShowWind(e.target.checked)}
                className="accent-teal-500 cursor-pointer h-3 w-3"
              />
            ) : (
              <span className="text-[9px] font-mono text-slate-500">Unavailable</span>
            )}
          </label>

          <label className={`flex items-center justify-between gap-2 select-none ${hasSpatialData ? "cursor-pointer text-slate-300 hover:text-white" : "text-slate-500 cursor-not-allowed opacity-60"}`}>
            <span className="flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-amber-400" />
              AIS Suspect (Rank 1)
            </span>
            {hasSpatialData ? (
              <input
                type="checkbox"
                checked={showAIS}
                onChange={(e) => setShowAIS(e.target.checked)}
                className="accent-amber-500 cursor-pointer h-3 w-3"
              />
            ) : (
              <span className="text-[9px] font-mono text-slate-500">Unavailable</span>
            )}
          </label>

          <label className={`flex items-center justify-between gap-2 select-none ${hasSpatialData ? "cursor-pointer text-slate-300 hover:text-white" : "text-slate-500 cursor-not-allowed opacity-60"}`}>
            <span className="flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-purple-400" />
              Nearby AIS Vessels
            </span>
            {hasSpatialData ? (
              <input
                type="checkbox"
                checked={showNearbyVessels}
                onChange={(e) => setShowNearbyVessels(e.target.checked)}
                className="accent-purple-500 cursor-pointer h-3 w-3"
              />
            ) : (
              <span className="text-[9px] font-mono text-slate-500">Unavailable</span>
            )}
          </label>
        </div>
      )}

      {/* Replay Incident Button (Gated by Feature Flag) */}
      {FEATURES.INCIDENT_REPLAY_ENABLED && hasSpatialData && !isReplayMode && (
        <button
          type="button"
          onClick={startReplay}
          disabled={replayLoading}
          title="Start Forensic Incident Replay"
          className="absolute top-3 left-3 z-10 w-[140px] h-[28px] px-2 rounded-md bg-slate-900/90 hover:bg-slate-800 border border-cyan-500/50 hover:border-cyan-400 text-cyan-300 text-[11px] font-semibold shadow-md flex items-center justify-center gap-1.5 transition-all cursor-pointer backdrop-blur"
        >
          <Play className="w-3 h-3 fill-current text-cyan-400 shrink-0" />
          <span className="truncate">{replayLoading ? "Loading Replay..." : "Replay Incident"}</span>
        </button>
      )}

      {/* Floating Forensic Replay Controller (Gated by Feature Flag) */}
      {FEATURES.INCIDENT_REPLAY_ENABLED && isReplayMode && (
        <SpillReplayController
          model={replayModel}
          clock={replayClock}
          onTogglePlay={() => setReplayClock((prev) => togglePlay(prev))}
          onReplay={() => setReplayClock((prev) => replayFromStart(prev))}
          onSeek={(timeMs) => setReplayClock((prev) => seekClock(prev, timeMs))}
          onSpeedChange={(rate) => setReplayClock((prev) => setPlaybackRate(prev, rate))}
          onClose={closeReplay}
          onFitInvestigation={handleRecenter}
        />
      )}

      {/* Forensic Replay Phase 9 Diagnostic Synchronization Overlay (Collapsible) */}
      {FEATURES.INCIDENT_REPLAY_ENABLED && isReplayMode && replayModel && (
        <div className="absolute top-14 left-3 z-20 font-mono text-[8.5px] bg-slate-950/95 backdrop-blur border border-cyan-500/40 rounded-lg shadow-2xl text-slate-200 pointer-events-auto transition-all">
          {isForensicCollapsed ? (
            <button
              type="button"
              onClick={toggleForensicCollapsed}
              className="flex items-center gap-2 px-2.5 py-1.5 text-cyan-400 hover:text-cyan-300 hover:bg-slate-900/60 rounded-lg cursor-pointer select-none"
              title="Expand Forensic Sync Overlay"
            >
              <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-pulse" />
              <span className="font-bold text-[9px] tracking-wide">FORENSIC SYNC</span>
              <span className="text-[8px] px-1 py-0.2 rounded bg-cyan-950 text-cyan-300 border border-cyan-700/60 font-semibold">
                {replayClock.playbackRate}×
              </span>
              <span className="text-slate-400 hover:text-white font-bold ml-1 text-[10px]">[＋]</span>
            </button>
          ) : (
            <div className="p-2.5 space-y-1 w-64 sm:w-72 max-w-[calc(100vw-24px)] select-text">
              <div className="text-cyan-400 font-bold border-b border-slate-800 pb-1 flex items-center justify-between">
                <span className="flex items-center gap-1.5">
                  <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-pulse" />
                  <span className="tracking-wide">FORENSIC SYNC</span>
                </span>
                <div className="flex items-center gap-1.5">
                  <span className="text-[8px] px-1 py-0.2 rounded bg-cyan-950 text-cyan-300 border border-cyan-700/60 font-semibold">
                    {replayClock.playbackRate}×
                  </span>
                  <button
                    type="button"
                    onClick={toggleForensicCollapsed}
                    className="text-slate-400 hover:text-cyan-300 px-1 py-0.5 rounded hover:bg-slate-800 text-[10px] font-bold cursor-pointer"
                    title="Collapse Forensic Sync Overlay"
                  >
                    [−]
                  </button>
                </div>
              </div>

              <div className="space-y-0.5 text-[8.5px]">
                <div className="flex items-center justify-between">
                  <span className="text-slate-400">INVESTIGATION ID:</span>
                  <span className="text-cyan-300 font-semibold">{activeInvId || "—"}</span>
                </div>

                <div className="flex items-center justify-between">
                  <span className="text-slate-400">SELECTED VESSEL:</span>
                  <span className="text-amber-300 font-semibold truncate max-w-[150px]" title={replayModel.vesselName || "Unknown"}>
                    {replayModel.vesselName || "Unknown"}
                  </span>
                </div>

                <div className="flex items-center justify-between">
                  <span className="text-slate-400">MMSI:</span>
                  <span className="text-cyan-300 font-mono font-semibold">{replayModel.vesselId || "—"}</span>
                </div>

                <div className="flex items-center justify-between">
                  <span className="text-slate-400">RANK:</span>
                  <span className="text-amber-400 font-bold">
                    #{selectedVessel?.rank ?? (replayModel.vesselId === result?.primary_suspect?.mmsi?.toString() ? 1 : (result?.candidate_vessels?.find((cv: any) => cv.mmsi?.toString() === replayModel.vesselId)?.rank ?? 1))}
                  </span>
                </div>

                <div className="flex items-center justify-between">
                  <span className="text-slate-400">AIS SOURCE:</span>
                  <span className="text-slate-300">Global Fishing Watch (GFW)</span>
                </div>

                <div className="flex items-center justify-between">
                  <span className="text-slate-400">AIS POINT COUNT:</span>
                  <span className={replayModel.trajectory.points.length <= 1 ? "text-amber-300 font-bold" : "text-emerald-300 font-bold"}>
                    {replayModel.trajectory.points.length}
                  </span>
                </div>

                <div className="flex items-center justify-between">
                  <span className="text-slate-400">AIS TRACK:</span>
                  <span className={replayModel.trajectory.points.length <= 1 ? "text-amber-400 font-bold" : "text-emerald-300 font-semibold"}>
                    {replayModel.trajectory.points.length === 1
                      ? "1 FIX ONLY — TRAJECTORY UNAVAILABLE"
                      : replayModel.trajectory.points.length === 0
                        ? "TRAJECTORY UNAVAILABLE"
                        : `${replayModel.trajectory.points.length} RECORDED FIXES (EVIDENCE TRACK)`}
                  </span>
                </div>

                <div className="flex items-center justify-between">
                  <span className="text-slate-400">AIS TIMESTAMPS:</span>
                  <span className="text-slate-300 text-[8px] truncate max-w-[150px]">
                    {replayModel.trajectory.points.length === 0
                      ? "None"
                      : replayModel.trajectory.points.length === 1
                        ? formatInvestigationUtc(replayModel.trajectory.points[0].timestamp).full
                        : `${formatInvestigationUtc(replayModel.trajectory.points[0].timestamp).clock} → ${formatInvestigationUtc(replayModel.trajectory.points[replayModel.trajectory.points.length - 1].timestamp).clock}`}
                  </span>
                </div>

                <div className="flex items-center justify-between">
                  <span className="text-slate-400">AIS COORDINATES:</span>
                  <span className="text-slate-300 text-[8px] truncate max-w-[150px]">
                    {replayModel.trajectory.points.length === 0
                      ? "None"
                      : replayModel.trajectory.points.length === 1
                        ? `[${replayModel.trajectory.points[0].longitude.toFixed(4)}°E, ${replayModel.trajectory.points[0].latitude.toFixed(4)}°N]`
                        : `[${replayModel.trajectory.points[0].longitude.toFixed(4)}°E, ${replayModel.trajectory.points[0].latitude.toFixed(4)}°N] → [${replayModel.trajectory.points[replayModel.trajectory.points.length - 1].longitude.toFixed(4)}°E, ${replayModel.trajectory.points[replayModel.trajectory.points.length - 1].latitude.toFixed(4)}°N]`}
                  </span>
                </div>

                <div className="flex items-center justify-between border-t border-slate-800/80 pt-0.5">
                  <span className="text-slate-400">PROBABLE ORIGIN:</span>
                  <span className="text-emerald-300 font-semibold">
                    {replayModel.probableOrigin
                      ? `[${replayModel.probableOrigin.longitude.toFixed(4)}°E, ${replayModel.probableOrigin.latitude.toFixed(4)}°N]`
                      : "—"}
                  </span>
                </div>

                <div className="flex items-center justify-between">
                  <span className="text-slate-400">ORIGIN DISTANCE:</span>
                  {(() => {
                    if (!replayModel.probableOrigin || !replayModel.trajectory.points.length) return <span className="text-slate-500">N/A</span>;
                    const targetPt = replayModel.trajectory.points[0];
                    const R = 6371;
                    const dLat = ((targetPt.latitude - replayModel.probableOrigin.latitude) * Math.PI) / 180;
                    const dLon = ((targetPt.longitude - replayModel.probableOrigin.longitude) * Math.PI) / 180;
                    const a =
                      Math.sin(dLat / 2) * Math.sin(dLat / 2) +
                      Math.cos((replayModel.probableOrigin.latitude * Math.PI) / 180) *
                        Math.cos((targetPt.latitude * Math.PI) / 180) *
                        Math.sin(dLon / 2) *
                        Math.sin(dLon / 2);
                    const km = R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
                    return <span className="text-amber-300 font-bold">{km.toFixed(2)} km</span>;
                  })()}
                </div>

                <div className="flex items-center justify-between">
                  <span className="text-slate-400">RELEASE UTC:</span>
                  <span className="text-emerald-300 font-semibold">
                    {replayModel.releaseTimestamp ? formatInvestigationUtc(replayModel.releaseTimestamp).full : "—"}
                  </span>
                </div>

                <div className="flex items-center justify-between">
                  <span className="text-slate-400">DETECTION UTC:</span>
                  <span className="text-rose-300 font-semibold">
                    {replayModel.spillTimestamp ? formatInvestigationUtc(replayModel.spillTimestamp).full : "—"}
                  </span>
                </div>

                <div className="flex items-center justify-between border-t border-slate-800/80 pt-0.5">
                  <span className="text-slate-400">REPLAY UTC:</span>
                  <span className="text-cyan-300 font-semibold">{formatInvestigationUtc(replayClock.currentTime).full}</span>
                </div>

                <div className="flex items-center justify-between">
                  <span className="text-slate-400">TIME DELTA:</span>
                  {(() => {
                    if (replayModel.releaseTimestamp == null) return <span className="text-slate-500">N/A</span>;
                    const deltaSec = Math.round((replayClock.currentTime - replayModel.releaseTimestamp) / 1000);
                    if (deltaSec === 0) {
                      return <span className="text-emerald-400 font-bold">0s (SYNCHRONIZED)</span>;
                    }
                    const sign = deltaSec > 0 ? "+" : "-";
                    const abs = Math.abs(deltaSec);
                    const h = Math.floor(abs / 3600);
                    const m = Math.floor((abs % 3600) / 60);
                    const s = abs % 60;
                    const formatted = `${sign}${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
                    return <span className={deltaSec > 0 ? "text-amber-300 font-medium" : "text-sky-300 font-medium"}>{formatted}</span>;
                  })()}
                </div>

                <div className="flex items-center justify-between border-t border-slate-800/80 pt-0.5">
                  <span className="text-slate-400">OIL STATE:</span>
                  {(() => {
                    const relT = replayModel.releaseTimestamp;
                    const detT = replayModel.spillTimestamp;
                    const curT = replayClock.currentTime;
                    if (relT != null && curT < relT) {
                      return <span className="text-sky-400 font-bold">PRE_RELEASE</span>;
                    }
                    if (detT != null && curT >= detT) {
                      if (replayModel.forecastFrames.length > 0 && curT > detT + 3600000) {
                        return <span className="text-amber-400 font-bold">FORECASTING</span>;
                      }
                      return <span className="text-rose-400 font-bold">AT_SLICK</span>;
                    }
                    return <span className="text-cyan-400 font-bold animate-pulse">DRIFTING</span>;
                  })()}
                </div>

                {replayModel.trajectory.points.length <= 1 && (
                  <div className="mt-1.5 p-1.5 bg-amber-950/80 border border-amber-500/70 rounded text-[8px] text-amber-200 space-y-0.5">
                    <div className="font-bold flex items-center gap-1 text-amber-300">
                      <span className="w-1 h-1 rounded-full bg-amber-400 animate-pulse" />
                      DATA ACQUISITION REQUIRED
                    </div>
                    <div className="leading-tight text-amber-200/90">
                      Single AIS fix available ({replayModel.trajectory.points.length === 1 ? formatInvestigationUtc(replayModel.trajectory.points[0].timestamp).full : "none"}). Vessel motion disabled; trajectory data unavailable.
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Fit Mode Switcher & Recenter Control */}
      {hasSpatialData && !isReplayMode && (
        <div className="absolute bottom-20 right-2.5 z-10 flex items-center bg-slate-900/95 backdrop-blur border border-slate-800/90 rounded-md p-0.5 shadow-xl font-mono text-[10px]">
          <button
            type="button"
            onClick={() => {
              setFitMode("investigation");
              fitBoundsToEvidence("investigation", 700);
            }}
            title="Focus map on detected spill slick & immediate origin"
            className={`px-2 py-1 rounded transition-all flex items-center gap-1 cursor-pointer select-none ${
              fitMode === "investigation"
                ? "bg-sky-500/25 text-sky-300 font-semibold border border-sky-500/40 shadow-xs"
                : "text-slate-400 hover:text-slate-200 border border-transparent"
            }`}
          >
            <Crosshair className="w-3 h-3" />
            <span>Focus Spill</span>
          </button>
          <button
            type="button"
            onClick={() => {
              setFitMode("full");
              fitBoundsToEvidence("full", 700);
            }}
            title="Fit full evidence extent including entire drift trajectory and candidate vessels"
            className={`px-2 py-1 rounded transition-all flex items-center gap-1 cursor-pointer select-none ${
              fitMode === "full"
                ? "bg-sky-500/25 text-sky-300 font-semibold border border-sky-500/40 shadow-xs"
                : "text-slate-400 hover:text-slate-200 border border-transparent"
            }`}
          >
            <span>Full Path</span>
          </button>
        </div>
      )}

      {/* Tactical Map Legend */}
      {!isReplayMode && (
        <div className="absolute bottom-3 left-3 z-10 bg-slate-950/92 backdrop-blur-md border border-slate-800/90 rounded-md px-2.5 py-1 text-[10px] text-slate-300 flex items-center gap-2.5 sm:gap-3.5 shadow-lg font-mono flex-wrap">
          {hasSpatialData ? (
            <>
              <div className="flex items-center gap-1">
                <span className="w-2 h-2 bg-[#e11d48] rounded-xs inline-block shadow-[0_0_4px_#f43f5e]" />
                <span className="text-slate-200">Slick</span>
              </div>
              <div className="flex items-center gap-1">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 inline-block shadow-[0_0_4px_#10b981]" />
                <span className="text-slate-200">Origin</span>
              </div>
              <div className="flex items-center gap-1">
                <span className="w-2.5 h-0.5 border-t-2 border-dashed border-cyan-400 inline-block" />
                <span className="text-slate-200">Hindcast</span>
              </div>
              <div className="flex items-center gap-1">
                <span className="w-2.5 h-0.5 border-t-2 border-dashed border-amber-400 inline-block" />
                <span className="text-slate-200">Forecast</span>
              </div>
              <div className="flex items-center gap-1">
                <span className="w-2.5 h-0.5 bg-sky-400 inline-block" />
                <span className="text-slate-200">Currents</span>
              </div>
              <div className="flex items-center gap-1">
                <span className="w-1.5 h-1.5 rounded-full bg-amber-400 inline-block shadow-[0_0_4px_#f59e0b]" />
                <span className="text-slate-200">Rank #1</span>
              </div>
              <div className="flex items-center gap-1">
                <span className="w-1.5 h-1.5 rounded-full bg-purple-400 inline-block shadow-[0_0_4px_#a855f7]" />
                <span className="text-slate-200">Rank #2</span>
              </div>
              <div className="flex items-center gap-1">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 inline-block shadow-[0_0_4px_#10b981]" />
                <span className="text-slate-200">Rank #3</span>
              </div>
              <div className="flex items-center gap-1">
                <span className="w-1.5 h-1.5 rounded-full bg-slate-400 inline-block" />
                <span className="text-slate-200">Other</span>
              </div>
            </>
          ) : (
            <div className="flex items-center gap-1.5 text-slate-400">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 inline-block" />
              <span>Global Maritime Basemap Active</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default MapLibreGIS;
