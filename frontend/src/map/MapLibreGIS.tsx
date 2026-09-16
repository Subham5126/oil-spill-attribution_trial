import React, { useEffect, useRef, useState, useMemo, useCallback } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { EndToEndResult, GeoJSONFeatureCollection, CandidateVessel, ForensicReconstruction } from "../types";
import { ReplayParticleEngine } from "./ReplayParticleEngine";
import { SpillReplayController } from "../components/SpillReplayController";
import { getInvestigationReconstruction } from "../services/api";
import { Layers, Crosshair, AlertCircle, Info, Play, Film } from "lucide-react";
import { FEATURES } from "../config/features";

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

// Create clean vector SVG vessel element for MapLibre Marker with tactical selection halo
function createVesselMarkerElement(vesselName?: string, isReplay = false, isSelected = false): HTMLElement {
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
  el.style.zIndex = isReplay ? "55" : (isSelected ? "50" : "45");
  el.style.transition = "transform 0.06s linear";

  const svgSize = isReplay ? 24 : (isSelected ? 22 : 18);
  el.innerHTML = `
    <div style="position: relative; width: ${svgSize}px; height: ${svgSize}px; display: flex; align-items: center; justify-content: center;">
      ${isSelected ? `<div class="selected-vessel-halo"></div>` : ""}
      <svg width="${svgSize}" height="${svgSize}" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" style="filter: drop-shadow(0 2px 5px rgba(0,0,0,0.85));">
        <!-- Professional Sleek Vessel Hull -->
        <path d="M12 2 L16.5 8 L15.5 20 C15.5 21.5 13.8 22.5 12 22.5 C10.2 22.5 8.5 21.5 8.5 20 L7.5 8 Z" fill="${isSelected ? "#0284c7" : "#0369a1"}" stroke="${isSelected ? "#38bdf8" : "#7dd3fc"}" stroke-width="${isSelected ? "1.8" : "1.2"}"/>
        <!-- Bridge Structure -->
        <rect x="9.5" y="15" width="5" height="4.5" rx="1" fill="#0f172a" stroke="#7dd3fc" stroke-width="0.8"/>
        <!-- Bow Azimuth Heading Indicator -->
        <polygon points="12,2.5 13.8,7 10.2,7" fill="${isSelected ? "#38bdf8" : "#facc15"}"/>
      </svg>
      ${
        vesselName
          ? `<div style="position: absolute; bottom: ${isReplay ? "-14px" : "-12px"}; white-space: nowrap; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; font-size: ${isReplay ? "8.5px" : "8px"}; font-weight: 700; background: rgba(2,6,23,0.92); color: ${isSelected ? "#38bdf8" : "#7dd3fc"}; border: 1px solid ${isSelected ? "rgba(56,189,248,0.7)" : "rgba(56,189,248,0.4)"}; padding: 0.5px 4px; border-radius: 3px; pointer-events: none; text-shadow: 0 1px 2px #000; letter-spacing: 0.02em;">${vesselName}</div>`
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
  const [showSceneFootprint, setShowSceneFootprint] = useState(false);
  const [fitMode, setFitMode] = useState<"investigation" | "full">("investigation");

  // Replay Mode State
  const [isReplayMode, setIsReplayMode] = useState(false);
  const [replayPlaying, setReplayPlaying] = useState(false);
  const [replayProgress, setReplayProgress] = useState(0); // 0.0 to 1.0
  const [replaySpeed, setReplaySpeed] = useState(1); // 0.5, 1, 2, 4
  const [reconstruction, setReconstruction] = useState<ForensicReconstruction | null>(null);
  const [replayLoading, setReplayLoading] = useState(false);
  const [followVessel, setFollowVessel] = useState(false);

  const particleEngine = useRef(new ReplayParticleEngine(320));
  const vesselMarker = useRef<maplibregl.Marker | null>(null);
  const normalVesselMarker = useRef<maplibregl.Marker | null>(null);
  const spillLabelMarker = useRef<maplibregl.Marker | null>(null);
  const originBeaconMarker = useRef<maplibregl.Marker | null>(null);
  const animFrameRef = useRef<number | null>(null);
  const lastTimeRef = useRef<number | null>(null);

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

    const rawKey = import.meta.env.VITE_MAPTILER_KEY;
    const hasValidKey =
      typeof rawKey === "string" &&
      rawKey.trim() !== "" &&
      rawKey.trim() !== "PASTE_MAPTILER_KEY_HERE";

    const fallbackStyle: maplibregl.StyleSpecification = {
      version: 8,
      sources: {
        "carto-voyager": {
          type: "raster",
          tiles: [
            "https://basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}@2x.png",
            "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
          ],
          tileSize: 256,
          attribution: "© OpenStreetMap contributors © CARTO",
        },
      },
      layers: [
        {
          id: "carto-voyager-layer",
          type: "raster",
          source: "carto-voyager",
          minzoom: 0,
          maxzoom: 20,
        },
      ],
    };

    if (!hasValidKey) {
      setBasemapUnavailable(true);
    }

    const styleToUse = hasValidKey
      ? `https://api.maptiler.com/maps/streets-v4/style.json?key=${rawKey.trim()}`
      : fallbackStyle;

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
          mapInstance.setStyle(fallbackStyle);
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
      aisFeatures = geoAis as GeoJSON.Feature[];
    } else if (result?.candidate_vessels && result.candidate_vessels.length > 0) {
      aisFeatures = result.candidate_vessels
        .filter((v) => typeof v.longitude === "number" && typeof v.latitude === "number")
        .slice(0, 15)
        .map((v) => ({
          type: "Feature",
          properties: {
            mmsi: v.mmsi,
            name: v.vessel_name,
            rank: v.rank,
            score: v.scores.overall,
            min_dist: v.distance_to_spill_km,
            isPrimary: v.rank === 1,
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

    // 5. AIS Vessel Trajectory Lines (distinct electric blue navigation track)
    if (!m.getLayer("ais-lines")) {
      m.addLayer({
        id: "ais-lines",
        type: "line",
        source: "ais-source",
        filter: ["==", ["geometry-type"], "LineString"],
        paint: {
          "line-color": "#0284c7",
          "line-width": 2.2,
          "line-opacity": 0.85,
        },
      });
    }

    // 5b. AIS Vessels / Candidates Points (subtle 3.0px point dots for vessels)
    if (!m.getLayer("ais-tracks")) {
      m.addLayer({
        id: "ais-tracks",
        type: "circle",
        source: "ais-source",
        filter: ["==", ["geometry-type"], "Point"],
        paint: {
          "circle-radius": 3.0,
          "circle-color": "#38bdf8",
          "circle-opacity": 0.85,
          "circle-stroke-width": 1.0,
          "circle-stroke-color": "#0f172a",
        },
      });
    }

    // Replay mode forensic layers
    setSourceData("replay-vessel-track-future-source", { type: "FeatureCollection", features: [] });
    setSourceData("replay-vessel-track-traversed-source", { type: "FeatureCollection", features: [] });
    setSourceData("replay-drift-source", { type: "FeatureCollection", features: [] });
    setSourceData("replay-forecast-source", { type: "FeatureCollection", features: [] });
    setSourceData("replay-release-source", { type: "FeatureCollection", features: [] });
    setSourceData("replay-particles-source", { type: "FeatureCollection", features: [] });

    // 6. Future AIS Route in Replay (subdued dashed line)
    if (!m.getLayer("replay-vessel-track-future-line")) {
      m.addLayer({
        id: "replay-vessel-track-future-line",
        type: "line",
        source: "replay-vessel-track-future-source",
        paint: {
          "line-color": "#0284c7",
          "line-width": 1.8,
          "line-dasharray": [3, 2],
          "line-opacity": 0.60,
        },
      });
    }

    // 7. Traversed AIS Route in Replay (solid illuminated cyan line)
    if (!m.getLayer("replay-vessel-track-traversed-line")) {
      m.addLayer({
        id: "replay-vessel-track-traversed-line",
        type: "line",
        source: "replay-vessel-track-traversed-source",
        paint: {
          "line-color": "#38bdf8",
          "line-width": 2.8,
          "line-opacity": 0.95,
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

    // 8b. Replay Forward Forecast Drift Trajectory (Predictive amber dashed line)
    if (!m.getLayer("replay-forecast-line")) {
      m.addLayer({
        id: "replay-forecast-line",
        type: "line",
        source: "replay-forecast-source",
        paint: {
          "line-color": "#f59e0b",
          "line-width": 1.8,
          "line-dasharray": [4, 3],
          "line-opacity": 0.80,
        },
      });
    }

    // 9. Observed Spill Polygon (Top visual priority: dark petroleum crimson fill 35% opacity + crisp 1.6px outline)
    if (!m.getLayer("spill-fill")) {
      m.addLayer({
        id: "spill-fill",
        type: "fill",
        source: "spill-source",
        paint: { "fill-color": "#881337", "fill-opacity": 0.35 },
      });
      m.addLayer({
        id: "spill-line",
        type: "line",
        source: "spill-source",
        paint: { "line-color": "#e11d48", "line-width": 1.6, "line-opacity": 0.95 },
      });
    }

    // 10. Replay Procedural Hydrocarbon Particles (thin surface sheen)
    if (!m.getLayer("replay-particles-layer")) {
      m.addLayer({
        id: "replay-particles-layer",
        type: "circle",
        source: "replay-particles-source",
        paint: {
          "circle-radius": ["get", "size"],
          "circle-color": ["get", "color"],
          "circle-opacity": ["get", "opacity"],
          "circle-stroke-width": 0.5,
          "circle-stroke-color": ["coalesce", ["get", "strokeColor"], "#52525b"],
          "circle-stroke-opacity": ["coalesce", ["get", "strokeOpacity"], 0.45],
          "circle-blur": 0.15,
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
    if (m.getLayer("ais-tracks")) {
      m.setPaintProperty("ais-tracks", "circle-radius", 2.5);
      m.setPaintProperty("ais-tracks", "circle-stroke-width", 0.8);
      m.setPaintProperty("ais-tracks", "circle-color", "#38bdf8");
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
        element: createVesselMarkerElement(primaryVessel.vessel_name, false, isSelected),
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

    m.on("mouseenter", "spill-fill", () => { m.getCanvas().style.cursor = "pointer"; });
    m.on("mouseleave", "spill-fill", () => { m.getCanvas().style.cursor = ""; });
    m.on("mouseenter", "origin-circle", () => { m.getCanvas().style.cursor = "pointer"; });
    m.on("mouseleave", "origin-circle", () => { m.getCanvas().style.cursor = ""; });
    m.on("mouseenter", "ais-tracks", () => { m.getCanvas().style.cursor = "pointer"; });
    m.on("mouseleave", "ais-tracks", () => { m.getCanvas().style.cursor = ""; });

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
    setVis("forecast-line", showForecast);
    setVis("ais-lines", showAIS);
    setVis("ais-tracks", showAIS);

    if (normalVesselMarker.current) {
      normalVesselMarker.current.getElement().style.display = showAIS && !isReplayMode ? "flex" : "none";
    }
    if (spillLabelMarker.current) {
      spillLabelMarker.current.getElement().style.display = showSpill && !isReplayMode ? "flex" : "none";
    }
    if (originBeaconMarker.current) {
      originBeaconMarker.current.getElement().style.display = showOrigin && !isReplayMode ? "flex" : "none";
    }
  }, [showSpill, showOrigin, showUncertainty, showHindcast, showForecast, showAIS, showSceneFootprint, mapLoaded, isReplayMode]);

  // -------------------------------------------------------------
  // Forensic Incident Replay Methods & State Management
  // -------------------------------------------------------------
  const startReplay = async () => {
    if (!activeInvId) return;
    setReplayLoading(true);
    try {
      let recon = reconstruction;
      if (!recon || recon.investigation_id !== activeInvId) {
        recon = await getInvestigationReconstruction(activeInvId);
        setReconstruction(recon);
      }
      const forecastEndpoint: [number, number] | null =
        forecast?.longitude && forecast?.latitude
          ? [forecast.longitude, forecast.latitude]
          : null;
      particleEngine.current.setReconstruction(recon, forecastEndpoint);
      setIsReplayMode(true);
      setReplayProgress(0);
      setReplayPlaying(true);

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

      const m = map.current;
      if (m && recon) {
        const setSrc = (id: string, data: any) => {
          const s = m.getSource(id) as maplibregl.GeoJSONSource;
          if (s) s.setData(data);
        };

        // Populate hindcast trajectory line strictly from particle engine's validated centerline
        const hindCoords = particleEngine.current.getHindcastCoordinates();
        if (hindCoords.length >= 2) {
          setSrc("replay-drift-source", {
            type: "FeatureCollection",
            features: [
              {
                type: "Feature",
                properties: { type: "drift_trajectory" },
                geometry: {
                  type: "LineString",
                  coordinates: hindCoords,
                },
              },
            ],
          });
        } else {
          setSrc("replay-drift-source", { type: "FeatureCollection", features: [] });
        }

        // Populate forecast trajectory line strictly from particle engine's validated forecast path
        const fwdCoords = particleEngine.current.getForecastCoordinates();
        if (fwdCoords.length >= 2) {
          setSrc("replay-forecast-source", {
            type: "FeatureCollection",
            features: [
              {
                type: "Feature",
                properties: { type: "forecast_trajectory" },
                geometry: {
                  type: "LineString",
                  coordinates: fwdCoords,
                },
              },
            ],
          });
        } else {
          setSrc("replay-forecast-source", { type: "FeatureCollection", features: [] });
        }

        const rawTrackCoords = recon.ais_track?.coordinates || [];
        const trackCoords = [...rawTrackCoords].reverse();
        if (trackCoords.length >= 2) {
          // Future route initially shows complete upcoming route along reversed replay path
          setSrc("replay-vessel-track-future-source", {
            type: "FeatureCollection",
            features: [
              {
                type: "Feature",
                properties: { type: "future_route" },
                geometry: {
                  type: "LineString",
                  coordinates: trackCoords,
                },
              },
            ],
          });
          // Traversed route initially empty
          setSrc("replay-vessel-track-traversed-source", {
            type: "FeatureCollection",
            features: [],
          });
        }

        // Add vector vessel marker ONLY if candidate vessel exists
        if (vesselMarker.current) {
          vesselMarker.current.remove();
          vesselMarker.current = null;
        }

        if (recon.vessel && trackCoords.length >= 1) {
          const [initLon, initLat, initHdg] = particleEngine.current.getVesselPositionAndHeadingAtProgress(0);
          vesselMarker.current = new maplibregl.Marker({
            element: createVesselMarkerElement(recon.vessel.vessel_name, true),
            rotationAlignment: "map",
          })
            .setLngLat([initLon, initLat])
            .setRotation(initHdg)
            .addTo(m);
        }

        // Calculate initial camera bounds encompassing vessel route, origin, and detected slick
        const bounds = new maplibregl.LngLatBounds();
        let hasCoords = false;

        if (trackCoords.length >= 1) {
          for (const c of trackCoords) {
            bounds.extend([c[0], c[1]]);
            hasCoords = true;
          }
        }
        if (recon.probable_origin) {
          bounds.extend([recon.probable_origin.longitude, recon.probable_origin.latitude]);
          hasCoords = true;
        }
        if (recon.spill_geometry?.centroid) {
          bounds.extend([recon.spill_geometry.centroid.longitude, recon.spill_geometry.centroid.latitude]);
          hasCoords = true;
        }

        if (hasCoords) {
          const sw = bounds.getSouthWest();
          const ne = bounds.getNorthEast();
          const w = Math.max(ne.lng - sw.lng, 0.025);
          const h = Math.max(ne.lat - sw.lat, 0.025);
          const padX = w * 0.14;
          const padY = h * 0.14;
          const paddedReplayBounds: [[number, number], [number, number]] = [
            [sw.lng - padX, sw.lat - padY],
            [ne.lng + padX, ne.lat + padY],
          ];
          m.fitBounds(paddedReplayBounds, {
            padding: { top: 65, bottom: 60, left: 55, right: 65 },
            maxZoom: 13.0,
            duration: 900,
          });
        }
      }
    } catch (e) {
      console.error("Failed to initialize incident replay:", e);
    } finally {
      setReplayLoading(false);
    }
  };

  const closeReplay = useCallback(() => {
    setIsReplayMode(false);
    setReplayPlaying(false);
    setReplayProgress(0);
    particleEngine.current.reset();

    if (animFrameRef.current) {
      cancelAnimationFrame(animFrameRef.current);
      animFrameRef.current = null;
    }
    lastTimeRef.current = null;

    if (vesselMarker.current) {
      vesselMarker.current.remove();
      vesselMarker.current = null;
    }

    const m = map.current;
    if (m) {
      const setSrc = (id: string) => {
        const s = m.getSource(id) as maplibregl.GeoJSONSource;
        if (s) s.setData({ type: "FeatureCollection", features: [] });
      };
      setSrc("replay-particles-source");
      setSrc("replay-release-source");
      setSrc("replay-drift-source");
      setSrc("replay-forecast-source");
      setSrc("replay-vessel-track-future-source");
      setSrc("replay-vessel-track-traversed-source");

      // Restore standard slick visibility and refined subtle opacity
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
        normalVesselMarker.current = new maplibregl.Marker({
          element: createVesselMarkerElement(primaryVessel.vessel_name, false),
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
  }, [showSpill, showOrigin, showAIS, selectedVessel, result, centroid, origin, fitMode, fitBoundsToEvidence]);

  // Reset replay and reset fitMode on investigation change
  useEffect(() => {
    closeReplay();
    setReconstruction(null);
    setFitMode("investigation");
  }, [activeInvId, closeReplay]);

  // Compute current stage: 1 to 5
  const currentStage = useMemo(() => {
    if (replayProgress < 0.25) return 1;
    if (replayProgress < 0.40) return 2;
    if (replayProgress < 0.60) return 3;
    if (replayProgress < 0.85) return 4;
    return 5;
  }, [replayProgress]);

  // Animation Loop (requestAnimationFrame)
  useEffect(() => {
    if (!isReplayMode || !replayPlaying) {
      if (animFrameRef.current) {
        cancelAnimationFrame(animFrameRef.current);
        animFrameRef.current = null;
      }
      lastTimeRef.current = null;
      return;
    }

    const loop = (time: number) => {
      if (lastTimeRef.current != null) {
        const deltaMs = time - lastTimeRef.current;
        const deltaP = (deltaMs / 25000) * replaySpeed; // 25s base replay duration
        setReplayProgress((prev) => {
          const next = prev + deltaP;
          if (next >= 1.0) {
            setReplayPlaying(false);
            return 1.0;
          }
          return next;
        });
      }
      lastTimeRef.current = time;
      animFrameRef.current = requestAnimationFrame(loop);
    };

    animFrameRef.current = requestAnimationFrame(loop);

    return () => {
      if (animFrameRef.current) {
        cancelAnimationFrame(animFrameRef.current);
        animFrameRef.current = null;
      }
    };
  }, [isReplayMode, replayPlaying, replaySpeed]);

  // Replay Frame Updates (vessel position, traversed route, release window, particles, slick illumination)
  useEffect(() => {
    if (!isReplayMode) return;
    const m = map.current;
    if (!m) return;

    const p = replayProgress;
    const recon = reconstruction;

    // 1. Update vessel position & heading along reversed AIS track & split route lines
    if (recon?.vessel) {
      const rawTrack = recon.ais_track?.coordinates || [];
      if (rawTrack.length >= 2) {
        // Reverse order so vessel sails away from probable origin in forward replay time
        const track = [...rawTrack].reverse();
        const [vLon, vLat, vHdg] = particleEngine.current.getVesselPositionAndHeadingAtProgress(p);

        if (vesselMarker.current) {
          vesselMarker.current.setLngLat([vLon, vLat]);
          vesselMarker.current.setRotation(vHdg);
        }

        // Split track into traversed (solid) and upcoming (dashed)
        const totalSegs = track.length - 1;
        const exact = Math.max(0, Math.min(1.0, p)) * totalSegs;
        const idx = Math.min(Math.floor(exact), totalSegs - 1);

        const traversedCoords = [...track.slice(0, idx + 1), [vLon, vLat]];
        const futureCoords = [[vLon, vLat], ...track.slice(idx + 1)];

        const travSrc = m.getSource("replay-vessel-track-traversed-source") as maplibregl.GeoJSONSource;
        if (travSrc) {
          travSrc.setData({
            type: "FeatureCollection",
            features: [
              {
                type: "Feature",
                properties: { type: "traversed_route" },
                geometry: {
                  type: "LineString",
                  coordinates: traversedCoords,
                },
              },
            ],
          });
        }

        const futSrc = m.getSource("replay-vessel-track-future-source") as maplibregl.GeoJSONSource;
        if (futSrc) {
          futSrc.setData({
            type: "FeatureCollection",
            features: [
              {
                type: "Feature",
                properties: { type: "future_route" },
                geometry: {
                  type: "LineString",
                  coordinates: futureCoords,
                },
              },
            ],
          });
        }
        // If Follow Vessel is active, smoothly center camera on the vessel position
        if (followVessel) {
          m.easeTo({
            center: [vLon, vLat],
            duration: 120,
            easing: (t) => t,
          });
        }
      } else if (recon.vessel.position && vesselMarker.current) {
        vesselMarker.current.setLngLat([recon.vessel.position.longitude, recon.vessel.position.latitude]);
        vesselMarker.current.setRotation(recon.vessel.heading_deg || 45);
        if (followVessel) {
          m.easeTo({
            center: [recon.vessel.position.longitude, recon.vessel.position.latitude],
            duration: 120,
            easing: (t) => t,
          });
        }
      }
    }

    // 2. Update release point marker (pulsing beacon at probable release point)
    const relSrc = m.getSource("replay-release-source") as maplibregl.GeoJSONSource;
    if (relSrc) {
      let relCoords: [number, number] | null = null;
      if (recon?.release_window?.location && Array.isArray(recon.release_window.location)) {
        relCoords = [recon.release_window.location[0], recon.release_window.location[1]];
      } else if (recon?.probable_origin) {
        if (typeof recon.probable_origin.longitude === "number" && typeof recon.probable_origin.latitude === "number") {
          relCoords = [recon.probable_origin.longitude, recon.probable_origin.latitude];
        } else if (Array.isArray(recon.probable_origin) && recon.probable_origin.length >= 2) {
          relCoords = [recon.probable_origin[0], recon.probable_origin[1]];
        }
      }

      const relProg = particleEngine.current.getReleaseProgress();
      if (p >= relProg && relCoords) {
        relSrc.setData({
          type: "FeatureCollection",
          features: [
            {
              type: "Feature",
              properties: { title: "Possible Release Point" },
              geometry: {
                type: "Point",
                coordinates: relCoords,
              },
            },
          ],
        });
      } else {
        relSrc.setData({ type: "FeatureCollection", features: [] });
      }
    }

    // 3. Update particle engine (wake emission, dispersion, current advection)
    const partSrc = m.getSource("replay-particles-source") as maplibregl.GeoJSONSource;
    if (partSrc) {
      const partGeoJSON = particleEngine.current.update(p);
      partSrc.setData(partGeoJSON);
    }

    // 4. Spill geometry reveal & smooth cross-fade at Stage 5 (delicate translucent reference)
    if (m.getLayer("spill-fill")) {
      if (p < 0.80) {
        m.setLayoutProperty("spill-fill", "visibility", "none");
        m.setLayoutProperty("spill-line", "visibility", "none");
      } else {
        const stageNorm = Math.min(1.0, (p - 0.80) / 0.15);
        m.setLayoutProperty("spill-fill", "visibility", "visible");
        m.setLayoutProperty("spill-line", "visibility", "visible");
        m.setPaintProperty("spill-fill", "fill-opacity", 0.08 + stageNorm * 0.12);
        m.setPaintProperty("spill-line", "line-width", 1.2 + stageNorm * 0.4);
      }
    }
  }, [isReplayMode, replayProgress, reconstruction, followVessel]);

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
              <span className="w-2.5 h-0.5 border-t border-dashed border-amber-400" />
              Forecast Drift
            </span>
            {hasSpatialData ? (
              <input
                type="checkbox"
                checked={showForecast}
                onChange={(e) => setShowForecast(e.target.checked)}
                className="accent-sky-500 cursor-pointer h-3 w-3"
              />
            ) : (
              <span className="text-[9px] font-mono text-slate-500">Unavailable</span>
            )}
          </label>

          <label className={`flex items-center justify-between gap-2 select-none ${hasSpatialData ? "cursor-pointer text-slate-300 hover:text-white" : "text-slate-500 cursor-not-allowed opacity-60"}`}>
            <span className="flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-sky-400" />
              AIS Vessels
            </span>
            {hasSpatialData ? (
              <input
                type="checkbox"
                checked={showAIS}
                onChange={(e) => setShowAIS(e.target.checked)}
                className="accent-sky-500 cursor-pointer h-3 w-3"
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
          reconstruction={reconstruction}
          isPlaying={replayPlaying}
          progress={replayProgress}
          playbackSpeed={replaySpeed}
          currentStage={currentStage}
          onTogglePlay={() => setReplayPlaying(!replayPlaying)}
          onRestart={() => {
            setReplayProgress(0);
            setReplayPlaying(true);
          }}
          onSeek={(p) => {
            setReplayProgress(p);
          }}
          onSpeedChange={(s) => setReplaySpeed(s)}
          onClose={closeReplay}
          onFitInvestigation={handleRecenter}
          followVessel={followVessel}
          onToggleFollowVessel={() => setFollowVessel(!followVessel)}
        />
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
                <span className="w-2 h-0.5 bg-[#0284c7] inline-block" />
                <span className="w-1.5 h-1.5 rounded-full bg-sky-400 inline-block" />
                <span className="text-slate-200">AIS</span>
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
