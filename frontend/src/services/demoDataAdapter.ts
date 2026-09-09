/**
 * OilTrace Development & Demo Data Adapter
 * Provides access to authoritative end-to-end demo outputs:
 * demo/output/end_to_end_result.json and demo/output/end_to_end_layers.geojson
 */

import {
  EndToEndResult,
  GeoJSONFeatureCollection,
  Investigation,
  Report,
} from "../types";

let cachedResult: EndToEndResult | null = null;
let cachedLayers: GeoJSONFeatureCollection | null = null;

// Built-in baseline data mirroring demo/output/end_to_end_result.json
export const BASELINE_DEMO_RESULT: EndToEndResult = {
  spill_metadata: {
    spill_id: "SAR-20250101-IND-0042",
    sensor: "Sentinel-1 SAR C-Band (IW)",
    detection_timestamp: "2025-01-01T05:00:00+00:00",
    confidence: 0.94,
    crs: "EPSG:4326",
    properties: {
      mission: "Sentinel-1B",
      polarization: "VV+VH",
      resolution_meters: 10.0,
      analyst_notes:
        "Continuous linear sheen with heavy core patch offshore Mumbai shipping corridor.",
    },
  },
  gis_measurement: {
    spill_id: "SAR-20250101-IND-0042",
    crs: "EPSG:4326",
    area: {
      sq_meters: 3927470.14,
      sq_kilometers: 3.9275,
    },
    perimeter: {
      meters: 9963.0,
      kilometers: 9.963,
    },
    centroid: {
      longitude: 72.481513,
      latitude: 18.523598,
    },
    bounding_box: {
      min_lon: 72.462,
      min_lat: 18.512,
      max_lon: 72.501,
      max_lat: 18.536,
      width_meters: 4111.93,
      height_meters: 2668.68,
    },
    shape_characteristics: {
      aspect_ratio: 1.54,
      compactness: 0.4972,
    },
  },
  ocean_drift: {
    model_type: "Lagrangian Forward/Backward Euler",
    particles_simulated: 40,
    forecast: {
      steps: 2,
      timestep_seconds: 3600,
      duration_hours: 2.0,
    },
    hindcast: {
      duration_hours: 4.0,
      timestep_seconds: 3600,
      observation_time: "2025-01-01T05:00:00+00:00",
    },
    probable_origin: {
      latitude: 18.525307,
      longitude: 72.503247,
      timestamp: "2025-01-01T01:00:00+00:00",
      relative_heuristic_score: 2.9981,
      drift_direction_deg: 270.0,
    },
    uncertainty: {
      radius_km: 1.885,
      empirical_coverage_level: 0.95,
      dispersion_description: "95% empirical spatial dispersion estimate",
      spread_km: 0.955,
      bounding_envelope: {
        min_lat: 18.513543,
        max_lat: 18.533653,
        min_lon: 72.484371,
        max_lon: 72.512971,
      },
    },
  },
  ais_search: {
    data_mode: "DEMO / SYNTHETIC AIS",
    search_center: {
      latitude: 18.525307,
      longitude: 72.503247,
    },
    effective_radius_km: 9.385,
    search_window: {
      start_time: "2025-01-01T00:15:00+00:00",
      end_time: "2025-01-01T01:45:00+00:00",
    },
    raw_records_matched: 8,
    vessels_tracked: 2,
    vessels_surviving_filter: 2,
  },
  candidate_vessels: [
    {
      rank: 1,
      mmsi: 413999001,
      vessel_name: "PACIFIC VOYAGER",
      imo: "IMO9384813",
      vessel_type: 80,
      scores: {
        overall: 0.9536,
        spatial: 1.0,
        temporal: 1.0,
        trajectory: 0.7404,
        behaviour: 0.925,
      },
      metrics: {
        min_distance_km: 0.572,
        time_difference_minutes: 0.0,
        transit_speed_knots: 12.2,
      },
      suspicious_flags: ["PROXIMITY_INTERSECT", "TEMPORAL_CONCURRENT"],
      confidence_category: "High Suspect",
      explanation: [
        "Transit trajectory intersected origin uncertainty zone within 0.572 km.",
        "Exact temporal coincidence (0.0 minutes offset) with backward hindcast release window.",
        "Speed profile indicates steady cruising (12.2 kn) consistent with operational bilge/sludge discharge.",
      ],
    },
    {
      rank: 2,
      mmsi: 211888002,
      vessel_name: "NORDIC TRADER",
      imo: "IMO9245172",
      vessel_type: 70,
      scores: {
        overall: 0.885,
        spatial: 0.871,
        temporal: 1.0,
        trajectory: 0.6272,
        behaviour: 0.925,
      },
      metrics: {
        min_distance_km: 4.866,
        time_difference_minutes: 10.0,
        transit_speed_knots: 13.8,
      },
      suspicious_flags: ["PARALLEL_PASSAGE"],
      confidence_category: "Moderate Suspect",
      explanation: [
        "Passed within 4.866 km of probable origin during release window.",
        "Parallel track to dominant ocean current vector.",
        "Secondary correlation; lower spatial proximity compared to primary suspect.",
      ],
    },
  ],
  attribution_ranking: [
    {
      rank: 1,
      mmsi: 413999001,
      vessel_name: "PACIFIC VOYAGER",
      imo: "IMO9384813",
      vessel_type: 80,
      scores: {
        overall: 0.9536,
        spatial: 1.0,
        temporal: 1.0,
        trajectory: 0.7404,
        behaviour: 0.925,
      },
      metrics: {
        min_distance_km: 0.572,
        time_difference_minutes: 0.0,
        transit_speed_knots: 12.2,
      },
      suspicious_flags: ["PROXIMITY_INTERSECT", "TEMPORAL_CONCURRENT"],
      confidence_category: "High Suspect",
    },
    {
      rank: 2,
      mmsi: 211888002,
      vessel_name: "NORDIC TRADER",
      imo: "IMO9245172",
      vessel_type: 70,
      scores: {
        overall: 0.885,
        spatial: 0.871,
        temporal: 1.0,
        trajectory: 0.6272,
        behaviour: 0.925,
      },
      metrics: {
        min_distance_km: 4.866,
        time_difference_minutes: 10.0,
        transit_speed_knots: 13.8,
      },
      suspicious_flags: ["PARALLEL_PASSAGE"],
      confidence_category: "Moderate Suspect",
    },
  ],
  primary_suspect: {
    rank: 1,
    mmsi: 413999001,
    vessel_name: "PACIFIC VOYAGER",
    imo: "IMO9384813",
    vessel_type: 80,
    scores: {
      overall: 0.9536,
      spatial: 1.0,
      temporal: 1.0,
      trajectory: 0.7404,
      behaviour: 0.925,
    },
    metrics: {
      min_distance_km: 0.572,
      time_difference_minutes: 0.0,
      transit_speed_knots: 12.2,
    },
    suspicious_flags: ["PROXIMITY_INTERSECT", "TEMPORAL_CONCURRENT"],
    confidence_category: "High Suspect",
  },
  gis_export: {
    map_view_config: {
      center: [18.52736, 72.505125],
      zoom: 11,
      bounds: [
        [18.48336, 72.462],
        [18.57136, 72.54825],
      ],
    },
    feature_collection_summary: {
      feature_count: 4,
      layer_types: ["vessel_track", "bounding_box", "oil_spill"],
    },
  },
  pipeline_execution: {
    status: "PASS",
    stage_statuses: {
      "GIS → Ocean/Drift": "PASS",
      "Ocean/Drift → AIS": "PASS",
      "AIS → Attribution": "PASS",
      "End-to-end workflow": "PASS",
    },
    notes: [
      "Stage 1 completed: Spill measured (3.927 km²), 40 particles initialized, forward/backward drift, origin, and uncertainty computed.",
      "Stage 2 completed: AIS queried (8 fixes), reconstructed, interpolated, and filtered.",
      "Stage 3 completed: Attributed 2 candidate vessels with explanation report.",
      "Stage 4 completed: Generated GIS FeatureCollection with 4 layers.",
    ],
    execution_timestamp: "2026-09-08T16:31:30.808106+00:00",
  },
};

export async function fetchEndToEndResult(): Promise<EndToEndResult> {
  if (cachedResult) return cachedResult;

  try {
    const res = await fetch("/data/end_to_end_result.json");
    if (res.ok) {
      const data = await res.json();
      cachedResult = data;
      return data;
    }
  } catch (err) {
    // Fall back to baseline
  }

  cachedResult = BASELINE_DEMO_RESULT;
  return BASELINE_DEMO_RESULT;
}

export async function fetchLayersGeoJSON(): Promise<GeoJSONFeatureCollection> {
  if (cachedLayers) return cachedLayers;

  try {
    const res = await fetch("/data/end_to_end_layers.geojson");
    if (res.ok) {
      const data = await res.json();
      cachedLayers = data;
      return data;
    }
  } catch (err) {
    // Fall back
  }

  // Fallback feature collection constructed from baseline
  const fallbackCollection: GeoJSONFeatureCollection = {
    type: "FeatureCollection",
    features: [
      {
        type: "Feature",
        id: "SAR-20250101-IND-0042",
        geometry: {
          type: "Polygon",
          coordinates: [
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
          ],
        },
        properties: {
          layer_type: "oil_spill",
          spill_id: "SAR-20250101-IND-0042",
          area_sq_km: 3.9275,
          perimeter_km: 9.963,
          color: "#d90429",
          fillColor: "#ef233c",
          fillOpacity: 0.6,
        },
      },
      {
        type: "Feature",
        id: "vessel_413999001",
        geometry: {
          type: "LineString",
          coordinates: [
            [72.48325, 18.57136],
            [72.49425, 18.54836],
            [72.50525, 18.52736],
            [72.51625, 18.50536],
            [72.52725, 18.48336],
          ],
        },
        properties: {
          layer_type: "vessel_track",
          mmsi: 413999001,
          vessel_name: "PACIFIC VOYAGER",
          rank: 1,
          attribution_score: 0.9536,
          color: "#f43f5e",
        },
      },
      {
        type: "Feature",
        id: "vessel_211888002",
        geometry: {
          type: "LineString",
          coordinates: [
            [72.54425, 18.56436],
            [72.54625, 18.53136],
            [72.54825, 18.49836],
          ],
        },
        properties: {
          layer_type: "vessel_track",
          mmsi: 211888002,
          vessel_name: "NORDIC TRADER",
          rank: 2,
          attribution_score: 0.885,
          color: "#0077b6",
        },
      },
    ],
  };

  cachedLayers = fallbackCollection;
  return fallbackCollection;
}

export const DEMO_INVESTIGATIONS: Investigation[] = [
  {
    id: "SAR-20250101-IND-0042",
    title: "Offshore Mumbai Shipping Corridor Incident",
    status: "Active",
    priority: "High",
    region: "Arabian Sea (Sector IND-West)",
    coordinates: { latitude: 18.523598, longitude: 72.481513 },
    spill_area_km2: 3.9275,
    detection_time: "2025-01-01T05:00:00 UTC",
    suspect_vessel: "PACIFIC VOYAGER (MMSI: 413999001)",
    match_confidence: 95.4,
    evidence_nodes_count: 8,
    sar_epoch: "05:00Z",
  },
  {
    id: "SAR-20250102-GOM-0019",
    title: "Gulf of Mexico Mississippi Canyon Sector 4A",
    status: "Completed",
    priority: "Medium",
    region: "Gulf of Mexico",
    coordinates: { latitude: 27.382, longitude: -90.0841 },
    spill_area_km2: 6.84,
    detection_time: "2025-01-02T11:24:00 UTC",
    suspect_vessel: "BALTIC TRADER",
    match_confidence: 78.2,
    evidence_nodes_count: 5,
    sar_epoch: "11:24Z",
  },
];

export const DEMO_REPORTS: Report[] = [
  {
    id: "REP-2025-0042",
    investigation_id: "SAR-20250101-IND-0042",
    title: "MARPOL Annex I Hydrocarbon Discharge Forensic Dossier: PACIFIC VOYAGER",
    generated_at: "2025-01-01T08:30:00 UTC",
    author: "Indian Coast Guard / Maritime Forensic Taskforce",
    status: "Final",
    target_vessel: "PACIFIC VOYAGER",
    imo: "IMO9384813",
    mmsi: 413999001,
    attribution_score: 95.36,
    summary:
      "Integrated forensic attribution established through backward Lagrangian drift hindcasting (4h), Sentinel-1 C-Band morphology (3.927 km²), and coincident AIS Class-A trajectory match (0.572 km minimum distance at 01:00 UTC).",
    marpol_violation_risk: "High",
    sha256_hash: "a4c28f11d9487c65c2718ecbf928821a4de8b39c0fa1107d6bc388ea210cfbc4",
    jurisdiction: "UNCLOS / MARPOL 73/78 Annex I / DG Shipping India",
  },
];
