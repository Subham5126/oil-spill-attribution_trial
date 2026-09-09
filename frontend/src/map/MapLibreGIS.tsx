import React, { useEffect, useRef, useState } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { EndToEndResult, GeoJSONFeatureCollection, CandidateVessel } from "../types";
import { BASELINE_DEMO_RESULT } from "../services/demoDataAdapter";
import { Layers, Crosshair, Ship, Compass, AlertCircle } from "lucide-react";

interface MapLibreGISProps {
  result?: EndToEndResult;
  layersGeoJSON?: GeoJSONFeatureCollection | null;
  selectedVessel?: CandidateVessel | null;
  onSelectVessel?: (vessel: CandidateVessel) => void;
  className?: string;
  height?: string;
  showControls?: boolean;
}

// Generate circular polygon points for origin uncertainty
function createGeoCircle(centerLon: number, centerLat: number, radiusKm: number, points = 64): number[][] {
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

export const MapLibreGIS: React.FC<MapLibreGISProps> = ({
  result = BASELINE_DEMO_RESULT,
  layersGeoJSON,
  selectedVessel,
  onSelectVessel,
  className = "",
  height = "560px",
  showControls = true,
}) => {
  const mapContainer = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const [mapLoaded, setMapLoaded] = useState(false);
  const [basemapUnavailable, setBasemapUnavailable] = useState(false);

  // Layer toggles
  const [showSpill, setShowSpill] = useState(true);
  const [showOrigin, setShowOrigin] = useState(true);
  const [showUncertainty, setShowUncertainty] = useState(true);
  const [showHindcast, setShowHindcast] = useState(true);
  const [showForecast, setShowForecast] = useState(true);
  const [showAIS, setShowAIS] = useState(true);

  const centroid = result.gis_measurement.centroid;
  const origin = result.ocean_drift.probable_origin;
  const uncertainty = result.ocean_drift.uncertainty;

  // Initialize MapLibre GL
  useEffect(() => {
    if (!mapContainer.current || map.current) return;

    const rawKey = import.meta.env.VITE_MAPTILER_KEY;
    const hasValidKey =
      typeof rawKey === "string" &&
      rawKey.trim() !== "" &&
      rawKey.trim() !== "PASTE_MAPTILER_KEY_HERE";

    const fallbackStyle: maplibregl.StyleSpecification = {
      version: 8,
      sources: {},
      layers: [
        {
          id: "background",
          type: "background",
          paint: {
            "background-color": "#0b132b",
          },
        },
      ],
    };

    if (!hasValidKey) {
      setBasemapUnavailable(true);
    }

    const styleToUse = hasValidKey
      ? `https://api.maptiler.com/maps/streets-v4/style.json?key=${rawKey.trim()}`
      : fallbackStyle;

    const mapInstance = new maplibregl.Map({
      container: mapContainer.current,
      style: styleToUse,
      center: [centroid.longitude, centroid.latitude],
      zoom: 11.2,
      attributionControl: false,
    });

    mapInstance.addControl(new maplibregl.NavigationControl({ showCompass: true }), "top-left");
    mapInstance.addControl(new maplibregl.ScaleControl({ unit: "metric" }), "bottom-right");

    let fallbackApplied = false;
    mapInstance.on("error", (e) => {
      // Catch tile or style loading errors (e.g. invalid MapTiler key, 401/403, network failure)
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
      map.current = mapInstance;
      setMapLoaded(true);
    });

    // Guard against case where initial style failed before load, but fallback succeeded
    mapInstance.on("styledata", () => {
      if (!map.current && mapInstance.isStyleLoaded()) {
        map.current = mapInstance;
        setMapLoaded(true);
      }
    });

    return () => {
      mapInstance.remove();
      map.current = null;
    };
  }, []);

  // Update Vector Layers
  useEffect(() => {
    const m = map.current;
    if (!m || !mapLoaded) return;

    // 1. Observed Spill Polygon & Bounding Box
    const spillCoords = [
      [
        [72.465, 18.512],
        [72.478, 18.515],
        [72.492, 18.525],
        [72.501, 18.532],
        [72.496, 18.536],
        [72.482, 18.53],
        [72.471, 18.522],
        [72.462, 18.516],
        [72.465, 18.512],
      ],
    ];

    const spillGeoJSON: GeoJSON.FeatureCollection = {
      type: "FeatureCollection",
      features: [
        {
          type: "Feature",
          properties: {
            name: result.spill_metadata.spill_id,
            area_km2: result.gis_measurement.area.sq_kilometers,
            perimeter_km: result.gis_measurement.perimeter.kilometers,
            sensor: result.spill_metadata.sensor,
          },
          geometry: {
            type: "Polygon",
            coordinates: spillCoords,
          },
        },
      ],
    };

    // 2. Spill Centroid
    const centroidGeoJSON: GeoJSON.FeatureCollection = {
      type: "FeatureCollection",
      features: [
        {
          type: "Feature",
          properties: { title: "Spill Centroid" },
          geometry: {
            type: "Point",
            coordinates: [centroid.longitude, centroid.latitude],
          },
        },
      ],
    };

    // 3. Probable Origin Point
    const originGeoJSON: GeoJSON.FeatureCollection = {
      type: "FeatureCollection",
      features: [
        {
          type: "Feature",
          properties: {
            title: "Probable Spill Origin",
            score: origin.relative_heuristic_score,
            time: origin.timestamp,
          },
          geometry: {
            type: "Point",
            coordinates: [origin.longitude, origin.latitude],
          },
        },
      ],
    };

    // 4. Origin Uncertainty Region (95% Empirical Spatial Dispersion Estimate)
    const uncertaintyRing = createGeoCircle(origin.longitude, origin.latitude, uncertainty.radius_km);
    const uncertaintyGeoJSON: GeoJSON.FeatureCollection = {
      type: "FeatureCollection",
      features: [
        {
          type: "Feature",
          properties: {
            title: "95% Empirical Spatial Dispersion Estimate",
            radius_km: uncertainty.radius_km,
          },
          geometry: {
            type: "Polygon",
            coordinates: [uncertaintyRing],
          },
        },
      ],
    };

    // 5. Backward Hindcast Trajectories (-4h)
    const hindcastGeoJSON: GeoJSON.FeatureCollection = {
      type: "FeatureCollection",
      features: [
        {
          type: "Feature",
          properties: { type: "hindcast", label: "Backward Hindcast Path (-4h)" },
          geometry: {
            type: "LineString",
            coordinates: [
              [centroid.longitude, centroid.latitude],
              [72.489, 18.524],
              [72.496, 18.525],
              [origin.longitude, origin.latitude],
            ],
          },
        },
      ],
    };

    // 6. Forward Forecast Trajectories (+2h)
    const forecastGeoJSON: GeoJSON.FeatureCollection = {
      type: "FeatureCollection",
      features: [
        {
          type: "Feature",
          properties: { type: "forecast", label: "Forward Forecast Spread (+2h)" },
          geometry: {
            type: "LineString",
            coordinates: [
              [centroid.longitude, centroid.latitude],
              [72.470, 18.522],
              [72.458, 18.520],
            ],
          },
        },
      ],
    };

    // 7. AIS Tracks (Primary Suspect & Secondary Candidate)
    const primaryTrack = [
      [72.48325, 18.57136],
      [72.48692, 18.56369],
      [72.49058, 18.55603],
      [72.49425, 18.54836],
      [72.49792, 18.54136],
      [72.50158, 18.53436],
      [72.50525, 18.52736],
      [72.50892, 18.52003],
      [72.51258, 18.51269],
      [72.51625, 18.50536],
      [72.51992, 18.49803],
      [72.52358, 18.49069],
      [72.52725, 18.48336],
    ];

    const secondaryTrack = [
      [72.54425, 18.56436],
      [72.54492, 18.55336],
      [72.54558, 18.54236],
      [72.54625, 18.53136],
      [72.54692, 18.52036],
      [72.54758, 18.50936],
      [72.54825, 18.49836],
    ];

    const aisGeoJSON: GeoJSON.FeatureCollection = {
      type: "FeatureCollection",
      features: [
        {
          type: "Feature",
          properties: {
            mmsi: 413999001,
            name: "PACIFIC VOYAGER",
            rank: 1,
            score: 0.9536,
            min_dist: 0.572,
            isPrimary: true,
          },
          geometry: {
            type: "LineString",
            coordinates: primaryTrack,
          },
        },
        {
          type: "Feature",
          properties: {
            mmsi: 211888002,
            name: "NORDIC TRADER",
            rank: 2,
            score: 0.885,
            min_dist: 4.866,
            isPrimary: false,
          },
          geometry: {
            type: "LineString",
            coordinates: secondaryTrack,
          },
        },
      ],
    };

    // Helper to safely add or update source
    const setSourceData = (id: string, data: any) => {
      const src = m.getSource(id) as maplibregl.GeoJSONSource;
      if (src) {
        src.setData(data);
      } else {
        m.addSource(id, { type: "geojson", data });
      }
    };

    setSourceData("spill-source", spillGeoJSON);
    setSourceData("centroid-source", centroidGeoJSON);
    setSourceData("uncertainty-source", uncertaintyGeoJSON);
    setSourceData("origin-source", originGeoJSON);
    setSourceData("hindcast-source", hindcastGeoJSON);
    setSourceData("forecast-source", forecastGeoJSON);
    setSourceData("ais-source", aisGeoJSON);

    // Uncertainty Region Layer
    if (!m.getLayer("uncertainty-fill")) {
      m.addLayer({
        id: "uncertainty-fill",
        type: "fill",
        source: "uncertainty-source",
        paint: {
          "fill-color": "#10b981",
          "fill-opacity": 0.16,
        },
      });
      m.addLayer({
        id: "uncertainty-line",
        type: "line",
        source: "uncertainty-source",
        paint: {
          "line-color": "#10b981",
          "line-width": 2,
          "line-dasharray": [4, 3],
        },
      });
    }

    // Spill Layers
    if (!m.getLayer("spill-fill")) {
      m.addLayer({
        id: "spill-fill",
        type: "fill",
        source: "spill-source",
        paint: {
          "fill-color": "#ef233c",
          "fill-opacity": 0.65,
        },
      });
      m.addLayer({
        id: "spill-line",
        type: "line",
        source: "spill-source",
        paint: {
          "line-color": "#d90429",
          "line-width": 2.5,
        },
      });
    }

    // Hindcast Drift Path
    if (!m.getLayer("hindcast-line")) {
      m.addLayer({
        id: "hindcast-line",
        type: "line",
        source: "hindcast-source",
        paint: {
          "line-color": "#38bdf8",
          "line-width": 3,
          "line-dasharray": [3, 2],
        },
      });
    }

    // Forecast Drift Path
    if (!m.getLayer("forecast-line")) {
      m.addLayer({
        id: "forecast-line",
        type: "line",
        source: "forecast-source",
        paint: {
          "line-color": "#f59e0b",
          "line-width": 2.5,
          "line-dasharray": [2, 2],
        },
      });
    }

    // AIS Vessel Tracks
    if (!m.getLayer("ais-tracks")) {
      m.addLayer({
        id: "ais-tracks",
        type: "line",
        source: "ais-source",
        paint: {
          "line-color": [
            "case",
            ["get", "isPrimary"],
            "#f43f5e",
            "#0077b6",
          ],
          "line-width": [
            "case",
            ["get", "isPrimary"],
            4,
            2.5,
          ],
        },
      });
    }

    // Spill Centroid Point
    if (!m.getLayer("centroid-circle")) {
      m.addLayer({
        id: "centroid-circle",
        type: "circle",
        source: "centroid-source",
        paint: {
          "circle-radius": 6,
          "circle-color": "#38bdf8",
          "circle-stroke-width": 2,
          "circle-stroke-color": "#ffffff",
        },
      });
    }

    // Probable Origin Point Marker
    if (!m.getLayer("origin-circle")) {
      m.addLayer({
        id: "origin-circle",
        type: "circle",
        source: "origin-source",
        paint: {
          "circle-radius": 8,
          "circle-color": "#10b981",
          "circle-stroke-width": 3,
          "circle-stroke-color": "#ffffff",
        },
      });
    }

    // Popups
    m.on("click", "origin-circle", (e) => {
      new maplibregl.Popup()
        .setLngLat([origin.longitude, origin.latitude])
        .setHTML(`
          <div class="font-sans text-xs text-slate-100">
            <div class="font-bold text-emerald-400 text-sm">Probable Spill Origin</div>
            <div class="mt-1 space-y-1 font-mono text-[11px] text-slate-300">
              <div>Time: <strong>${origin.timestamp.replace("T", " ").replace("+00:00", "")} UTC</strong></div>
              <div>Coords: <strong>${origin.latitude.toFixed(4)}°N, ${origin.longitude.toFixed(4)}°E</strong></div>
              <div>Heuristic Score: <strong>${origin.relative_heuristic_score.toFixed(4)}</strong></div>
              <div>95% Dispersion Est.: <strong>${uncertainty.radius_km.toFixed(3)} km</strong></div>
            </div>
          </div>
        `)
        .addTo(m);
    });

    m.on("click", "spill-fill", (e) => {
      new maplibregl.Popup()
        .setLngLat([centroid.longitude, centroid.latitude])
        .setHTML(`
          <div class="font-sans text-xs text-slate-100">
            <div class="font-bold text-rose-400 text-sm">${result.spill_metadata.spill_id}</div>
            <div class="mt-1 space-y-1 font-mono text-[11px] text-slate-300">
              <div>Sensor: <strong>${result.spill_metadata.sensor}</strong></div>
              <div>Area: <strong>${result.gis_measurement.area.sq_kilometers.toFixed(4)} km²</strong></div>
              <div>Perimeter: <strong>${result.gis_measurement.perimeter.kilometers.toFixed(3)} km</strong></div>
              <div>Compactness: <strong>${result.gis_measurement.shape_characteristics.compactness.toFixed(4)}</strong></div>
            </div>
          </div>
        `)
        .addTo(m);
    });

    m.on("click", "ais-tracks", (e) => {
      const feat = e.features?.[0];
      if (!feat) return;
      const props = feat.properties;
      const matching = result.candidate_vessels.find((c) => c.mmsi === props.mmsi);
      if (matching && onSelectVessel) {
        onSelectVessel(matching);
      }
    });

  }, [mapLoaded, result]);

  // Visibility toggling
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
    setVis("centroid-circle", showSpill);
    setVis("origin-circle", showOrigin);
    setVis("uncertainty-fill", showUncertainty);
    setVis("uncertainty-line", showUncertainty);
    setVis("hindcast-line", showHindcast);
    setVis("forecast-line", showForecast);
    setVis("ais-tracks", showAIS);
  }, [showSpill, showOrigin, showUncertainty, showHindcast, showForecast, showAIS, mapLoaded]);

  const handleRecenter = () => {
    if (!map.current) return;
    map.current.flyTo({
      center: [centroid.longitude, centroid.latitude],
      zoom: 11.2,
      essential: true,
    });
  };

  return (
    <div
      className={`relative w-full rounded-xl overflow-hidden border border-slate-800 shadow-2xl bg-slate-950 ${className}`}
      style={{ height }}
    >
      <div ref={mapContainer} className="w-full h-full" />

      {/* Basemap Status / Unavailable Warning Banner */}
      {basemapUnavailable && (
        <div className="absolute top-3 left-14 z-10 flex items-center gap-2 bg-slate-900/90 backdrop-blur border border-amber-500/40 text-amber-300 text-xs px-3 py-1.5 rounded-lg shadow-lg">
          <AlertCircle className="w-3.5 h-3.5 text-amber-400 shrink-0" />
          <span>
            Map basemap unavailable — configure <code className="font-mono text-[11px] bg-slate-800 px-1 py-0.5 rounded text-amber-200">VITE_MAPTILER_KEY</code>
          </span>
        </div>
      )}

      {/* Floating Layer Controls */}
      {showControls && (
        <div className="absolute top-3 right-3 z-10 bg-slate-900/90 backdrop-blur border border-slate-700/80 rounded-lg p-2.5 shadow-xl text-xs space-y-1.5 min-w-[190px]">
          <div className="font-semibold text-slate-300 flex items-center justify-between pb-1 border-b border-slate-800">
            <span className="flex items-center gap-1.5 font-bold">
              <Layers className="w-3.5 h-3.5 text-sky-400" />
              GIS Vector Layers
            </span>
          </div>

          <label className="flex items-center justify-between gap-2 cursor-pointer text-slate-300 hover:text-white">
            <span className="flex items-center gap-1.5">
              <span className="w-2.5 h-2.5 rounded-full bg-red-500" />
              Observed Spill Slick
            </span>
            <input
              type="checkbox"
              checked={showSpill}
              onChange={(e) => setShowSpill(e.target.checked)}
              className="accent-primary"
            />
          </label>

          <label className="flex items-center justify-between gap-2 cursor-pointer text-slate-300 hover:text-white">
            <span className="flex items-center gap-1.5">
              <span className="w-2.5 h-2.5 rounded-full bg-emerald-400" />
              Probable Origin Point
            </span>
            <input
              type="checkbox"
              checked={showOrigin}
              onChange={(e) => setShowOrigin(e.target.checked)}
              className="accent-primary"
            />
          </label>

          <label className="flex items-center justify-between gap-2 cursor-pointer text-slate-300 hover:text-white">
            <span className="flex items-center gap-1.5">
              <span className="w-2.5 h-2.5 rounded border border-emerald-400 bg-emerald-400/20" />
              95% Dispersion Region
            </span>
            <input
              type="checkbox"
              checked={showUncertainty}
              onChange={(e) => setShowUncertainty(e.target.checked)}
              className="accent-primary"
            />
          </label>

          <label className="flex items-center justify-between gap-2 cursor-pointer text-slate-300 hover:text-white">
            <span className="flex items-center gap-1.5">
              <span className="w-2.5 h-0.5 bg-sky-400" />
              Backward Hindcast (-4h)
            </span>
            <input
              type="checkbox"
              checked={showHindcast}
              onChange={(e) => setShowHindcast(e.target.checked)}
              className="accent-primary"
            />
          </label>

          <label className="flex items-center justify-between gap-2 cursor-pointer text-slate-300 hover:text-white">
            <span className="flex items-center gap-1.5">
              <span className="w-2.5 h-0.5 bg-amber-400" />
              Forward Forecast (+2h)
            </span>
            <input
              type="checkbox"
              checked={showForecast}
              onChange={(e) => setShowForecast(e.target.checked)}
              className="accent-primary"
            />
          </label>

          <label className="flex items-center justify-between gap-2 cursor-pointer text-slate-300 hover:text-white">
            <span className="flex items-center gap-1.5">
              <span className="w-2.5 h-0.5 bg-rose-500" />
              AIS Candidate Tracks
            </span>
            <input
              type="checkbox"
              checked={showAIS}
              onChange={(e) => setShowAIS(e.target.checked)}
              className="accent-primary"
            />
          </label>
        </div>
      )}

      {/* Recenter Button */}
      <button
        onClick={handleRecenter}
        title="Recenter Map to Spill Area"
        className="absolute bottom-4 right-4 z-10 p-2.5 rounded-lg bg-slate-900/90 hover:bg-slate-800 border border-slate-700 text-slate-200 shadow-xl transition-all"
      >
        <Crosshair className="w-4 h-4" />
      </button>

      {/* Map Legend Overlay */}
      <div className="absolute bottom-4 left-4 z-10 bg-slate-900/90 backdrop-blur border border-slate-800 rounded-lg p-2.5 text-[11px] text-slate-300 flex items-center gap-4 shadow-xl">
        <div className="flex items-center gap-1.5">
          <span className="w-3 h-3 bg-red-600/60 border border-red-500 rounded-sm inline-block" />
          <span>Observed Spill</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded-full bg-emerald-400 inline-block" />
          <span>Origin (95% Radius {uncertainty.radius_km} km)</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="w-3 h-0.5 bg-sky-400 inline-block" />
          <span>Hindcast</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="w-3 h-0.5 bg-rose-500 inline-block" />
          <span>Primary Suspect</span>
        </div>
      </div>
    </div>
  );
};

export default MapLibreGIS;
