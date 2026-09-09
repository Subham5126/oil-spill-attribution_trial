/**
 * OilTrace - Authoritative TypeScript Data Contracts
 * Defined in accordance with docs/architecture/ARCHITECTURE.md,
 * integration/contracts/spill_contract.py, and demo/output/end_to_end_result.json
 */

export interface GeoPoint {
  latitude: number;
  longitude: number;
}

export interface BoundingBox {
  min_lon: number;
  min_lat: number;
  max_lon: number;
  max_lat: number;
  width_meters?: number;
  height_meters?: number;
}

export interface SpillMetadata {
  spill_id: string;
  sensor: string;
  source_sensor?: string;
  detection_timestamp: string; // ISO 8601 UTC
  observation_time?: string;
  confidence: number; // 0.0 - 1.0
  crs: string; // e.g. "EPSG:4326"
  properties?: {
    mission?: string;
    polarization?: string;
    resolution_meters?: number;
    analyst_notes?: string;
    [key: string]: any;
  };
}

export interface GisMeasurement {
  spill_id: string;
  crs: string;
  area: {
    sq_meters: number;
    sq_kilometers: number;
  };
  perimeter: {
    meters: number;
    kilometers: number;
  };
  centroid: {
    longitude: number;
    latitude: number;
  };
  bounding_box: BoundingBox;
  shape_characteristics: {
    aspect_ratio: number;
    compactness: number;
  };
}

export interface ProbableOrigin {
  latitude: number;
  longitude: number;
  timestamp: string; // ISO 8601 UTC
  relative_heuristic_score: number; // Relative heuristic score, NOT probability
  drift_direction_deg?: number;
}

export interface SpatialUncertainty {
  radius_km: number; // 95% empirical spatial dispersion estimate radius
  empirical_coverage_level: number; // 0.95
  dispersion_description: string; // "95% empirical spatial dispersion estimate"
  spread_km: number;
  bounding_envelope: {
    min_lat: number;
    max_lat: number;
    min_lon: number;
    max_lon: number;
  };
}

export interface OceanDriftResult {
  model_type: string; // "Lagrangian Forward/Backward Euler"
  particles_simulated: number;
  forecast: {
    steps: number;
    timestep_seconds: number;
    duration_hours: number;
  };
  hindcast: {
    duration_hours: number;
    timestep_seconds: number;
    observation_time: string;
  };
  probable_origin: ProbableOrigin;
  uncertainty: SpatialUncertainty;
}

export interface AISSearchSummary {
  data_mode: string; // "DEMO / SYNTHETIC AIS" or "REAL AIS"
  search_center: {
    latitude: number;
    longitude: number;
  };
  effective_radius_km: number;
  search_window: {
    start_time: string;
    end_time: string;
  };
  raw_records_matched: number;
  vessels_tracked: number;
  vessels_surviving_filter: number;
}

export interface CandidateVesselScores {
  overall: number; // 0.0 - 1.0 (Composite multi-criteria score)
  spatial: number; // 40% weight
  temporal: number; // 35% weight
  trajectory: number; // 15% weight
  behaviour: number; // 10% weight
}

export interface CandidateVesselMetrics {
  min_distance_km: number;
  time_difference_minutes: number;
  transit_speed_knots: number;
}

export interface CandidateVessel {
  rank: number;
  mmsi: number;
  vessel_name: string;
  imo: string;
  vessel_type: number | string;
  scores: CandidateVesselScores;
  metrics: CandidateVesselMetrics;
  suspicious_flags: string[];
  explanation?: string[];
  confidence_category?: "High Suspect" | "Moderate Suspect" | "Low Suspect" | "Eliminated";
}

export interface GisExportConfig {
  map_view_config: {
    center: [number, number]; // [lat, lon]
    zoom: number;
    bounds: [[number, number], [number, number]];
  };
  feature_collection_summary?: {
    feature_count: number;
    layer_types: string[];
  };
}

export interface PipelineExecutionStatus {
  status: "PASS" | "FAIL" | "RUNNING";
  stage_statuses: Record<string, string>;
  notes: string[];
  execution_timestamp: string;
}

export interface EndToEndResult {
  spill_metadata: SpillMetadata;
  gis_measurement: GisMeasurement;
  ocean_drift: OceanDriftResult;
  ais_search: AISSearchSummary;
  candidate_vessels: CandidateVessel[];
  attribution_ranking: CandidateVessel[];
  primary_suspect: CandidateVessel;
  gis_export: GisExportConfig;
  pipeline_execution: PipelineExecutionStatus;
}

// Map Layer & GeoJSON Feature types
export interface GeoJSONFeature<G = any, P = Record<string, any>> {
  type: "Feature";
  id?: string | number;
  geometry: G;
  properties: P;
}

export interface GeoJSONFeatureCollection<G = any, P = Record<string, any>> {
  type: "FeatureCollection";
  crs?: {
    type: string;
    properties: {
      name: string;
    };
  };
  features: GeoJSONFeature<G, P>[];
}

export interface Investigation {
  id: string;
  title: string;
  status: "Active" | "Completed" | "Under Review" | "Archived";
  priority: "High" | "Medium" | "Low";
  region: string;
  coordinates: {
    latitude: number;
    longitude: number;
  };
  spill_area_km2: number;
  detection_time: string;
  suspect_vessel?: string;
  match_confidence?: number;
  evidence_nodes_count: number;
  sar_epoch: string;
}

export interface Report {
  id: string;
  investigation_id: string;
  title: string;
  generated_at: string;
  author: string;
  status: "Final" | "Draft" | "Submitted";
  target_vessel: string;
  imo: string;
  mmsi: number;
  attribution_score: number;
  summary: string;
  marpol_violation_risk: "High" | "Medium" | "Low";
  sha256_hash: string;
  jurisdiction: string;
}
