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
  drift_distance_km?: number;
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
  dataset_id?: string;
  product_id?: string;
  temporal_coverage?: string;
  is_cached?: boolean;
  status?: string;
  status_message?: string;
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
  surface_velocity?: {
    u_eastward_m_s: number;
    v_northward_m_s: number;
    speed_m_s: number;
    direction_deg: number;
  };
  probable_origin: ProbableOrigin;
  forecast_endpoint?: {
    latitude: number;
    longitude: number;
    timestamp?: string;
    drift_distance_km?: number;
  };
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

export interface ConfidenceFactors {
  spatial_proximity?: number | null;
  temporal_overlap?: number | null;
  drift_consistency?: number | null;
  track_consistency?: number | null;
  vessel_type_relevance?: number | null;
  ais_quality?: number | null;
  supporting?: string[];
  limitations?: string[];
}

export type ConfidenceLevel = "VERY HIGH" | "HIGH" | "MODERATE" | "LOW" | "VERY LOW";

export interface CandidateVessel {
  rank: number;
  mmsi: number | string;
  vessel_name: string;
  imo: string;
  vessel_type: number | string;
  scores: CandidateVesselScores;
  metrics: CandidateVesselMetrics;
  suspicious_flags?: string[];
  explanation?: string[];
  confidence_category?: "High Suspect" | "Moderate Suspect" | "Low Suspect" | "Eliminated";
  confidence_score?: number; // 0 - 100
  confidence_level?: ConfidenceLevel;
  confidence_factors?: ConfidenceFactors;
  min_distance_km?: number;
  distance_to_spill_km?: number;
  distance_to_track_km?: number;
  callsign?: string;
  flag?: string;
  latitude?: number;
  longitude?: number;
  heading_deg?: number;
  speed_knots?: number;
  timestamp?: string;
  presence_hours?: number;
  trajectory?: any[];
  overall_score?: number;
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
  pipeline_run_id?: string;
  snapshot_id?: string;
  forensic_result_version?: string;
  stage_statuses: Record<string, string>;
  notes: string[];
  execution_timestamp: string;
}

export interface EndToEndResult {
  spill_metadata: SpillMetadata;
  gis_measurement: GisMeasurement;
  ocean_drift: OceanDriftResult;
  ais_search?: AISSearchSummary;
  candidate_vessels: CandidateVessel[];
  attribution_ranking: CandidateVessel[];
  primary_suspect: CandidateVessel | null;
  gis_export?: GisExportConfig;
  pipeline_execution: PipelineExecutionStatus;
  provenance?: {
    data_source_mode?: string;
    satellite_file?: string;
    satellite_path?: string;
    satellite_crs?: string;
    satellite_bounds?: number[];
    satellite_timestamp?: string | null;
    m1_model?: string;
    m1_checkpoint?: string;
    ocean_data_source?: string;
    ais_data_source?: string;
    ais_coverage?: any;
    [key: string]: any;
  };
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

export interface SentinelImage {
  image_id: string;
  filename: string;
  source_path?: string;
  exists_on_disk: boolean;
  latitude?: number;
  longitude?: number;
  region?: string;
  observation_timestamp?: string;
  has_matching_ocean?: boolean;
  recommended?: boolean;
}

export interface TemporalAnchorCandidate {
  source: string;
  timestamp: string;
  confidence: string;
  description: string;
}

export interface TemporalAnchorConflict {
  source_a: string;
  timestamp_a: string;
  source_b: string;
  timestamp_b: string;
  difference_seconds: number;
}

export interface TemporalAnchor {
  status: "resolved" | "unresolved" | "conflict";
  sar_acquisition_time: string | null;
  source: string | null;
  verified: boolean;
  provenance_badge: string;
  description: string;
  candidates?: TemporalAnchorCandidate[];
  conflicts?: TemporalAnchorConflict[];
  requires_user_action: boolean;
}

export interface UploadedSceneMetadata {
  status: string;
  upload_id: string;
  image_id: string;
  filename: string;
  safe_filename: string;
  file_path: string;
  file_size: number;
  file_size_formatted: string;
  width: number;
  height: number;
  num_bands: number;
  crs: string;
  pixel_res_m: number;
  bounds: {
    min_lon: number;
    min_lat: number;
    max_lon: number;
    max_lat: number;
  };
  centroid_lat: number | null;
  centroid_lon: number | null;
  region: string;
  acquisition_time: string | null;
  temporal_anchor?: TemporalAnchor;
  source_file: string;
  is_uploaded: boolean;
}

export interface InvestigationArtifacts {
  detection_overlay?: string | null;
  segmentation_mask?: string | null;
  source_tiff?: string | null;
}

export interface Investigation {
  id: string;
  title: string;
  status: "Active" | "Completed" | "Under Review" | "Archived" | "Pending" | string;
  priority: "High" | "Medium" | "Low" | string;
  region: string;
  coordinates: {
    latitude: number;
    longitude: number;
  };
  spill_area_km2: number;
  detection_time: string;
  sar_acquisition_time?: string;
  sar_acquisition_time_source?: string;
  sar_acquisition_time_verified?: boolean;
  temporal_anchor?: TemporalAnchor;
  suspect_vessel?: string;
  match_confidence?: number;
  evidence_nodes_count: number;
  sar_epoch: string;
  image_id?: string;
  source_image_path?: string;
  pipeline_status?: string;
  pipeline_stages_json?: Record<string, string>;
  result_json?: EndToEndResult;
  created_at?: string;
  updated_at?: string;
  observation_timestamp?: string;
  centroid_lat?: number;
  centroid_lon?: number;
  is_starred?: boolean;
  is_archived?: boolean;
  is_deleted?: boolean;
  parent_investigation_id?: string;
  artifacts?: InvestigationArtifacts;
}

export interface DashboardSummary {
  total_investigations: number;
  completed_investigations: number;
  active_investigations: number;
  running_investigations: number;
  failed_investigations: number;
  total_spill_area_km2: number;
  candidate_vessels_tracked: number;
  forensic_readiness?: {
    status: "READY" | "PROCESSING" | "ATTENTION" | "BLOCKED" | "STANDBY" | string;
    detail: string;
  };
  recent_investigations: Investigation[];
  latest_completed_investigation?: Investigation | null;
}

export interface TimelineEvent {
  event: string;
  timestamp: string;
  details: string;
  user: string;
}

export interface EvidenceItem {
  artifact_type?: string;
  name: string;
  category: "SATELLITE" | "SEGMENTATION" | "GIS" | "OCEAN_DRIFT" | "AIS_ATTRIBUTION" | "LEGAL_REPORT" | string;
  status: "AVAILABLE" | "GENERATING" | "UNAVAILABLE" | string;
  file_name: string;
  file_path?: string | null;
  file_size_bytes: number;
  generated_at?: string | null;
  provenance_source: string;
  download_url?: string | null;
  preview_type: "image" | "json" | "geojson" | "text" | "table" | "none";
  sha256?: string | null;
  mime_type?: string;
  unavailable_reason?: string | null;
  expected_storage_path?: string | null;
  can_regenerate?: boolean;
}

export interface VesselIncidentAppearance {
  investigation_id: string;
  title: string;
  date?: string | null;
  region: string;
  rank: number;
  min_distance_km: number;
  score: number;
}

export interface VesselIntelligenceItem {
  mmsi: number | string;
  vessel_name: string;
  imo: string;
  callsign: string;
  flag: string;
  vessel_type: string;
  appearances_count: number;
  min_distance_km: number;
  highest_score: number;
  last_observed?: string | null;
  incidents: VesselIncidentAppearance[];
}

export interface SystemSubsystem {
  name: string;
  status: "Operational" | "Warning" | "Unavailable" | "Degraded" | string;
  details: string;
  category: string;
}

export interface SystemStatus {
  overall: string;
  subsystems: SystemSubsystem[];
}

export interface DatasetItem {
  id: string;
  name: string;
  provider: string;
  status: string;
  format: string;
  records_count: number;
  coverage: string;
  local_path: string;
  verified: boolean;
}

export interface Report {
  id: string;
  investigation_id: string;
  title: string;
  generated_at: string;
  author: string;
  status: "Final" | "Draft" | "Submitted" | string;
  target_vessel: string;
  imo: string;
  mmsi: number | string;
  attribution_score: number;
  summary: string;
  marpol_violation_risk: "High" | "Medium" | "Low" | string;
  sha256_hash: string;
  jurisdiction: string;
  sections?: Record<string, any>;
  markdown?: string;
}

export type ReconstructionStatus =
  | "FULL_RECONSTRUCTION"
  | "AIS_ONLY"
  | "SPILL_ONLY"
  | "OCEAN_UNAVAILABLE"
  | "DRIFT_UNAVAILABLE"
  | "VESSEL_UNAVAILABLE"
  | "VESSEL_TRACK_UNAVAILABLE"
  | "GEOMETRY_UNAVAILABLE";

export interface ReconstructionVessel {
  mmsi: number | string;
  vessel_name: string;
  vessel_type: string;
  imo: string;
  callsign: string;
  flag: string;
  rank: number;
  score: number;
  speed_knots: number;
  heading_deg: number;
  has_track: boolean;
  position: { latitude: number; longitude: number };
}

export interface ReconstructionAisTrack {
  type: "LineString";
  coordinates: [number, number][];
  waypoints?: Array<{
    latitude: number;
    longitude: number;
    timestamp?: string;
    speed_knots?: number;
    heading?: number;
    heading_deg?: number;
  }>;
  has_track: boolean;
  start_timestamp?: string;
  end_timestamp?: string;
}

export interface ReconstructionReleaseWindow {
  start_time: string;
  end_time: string;
  progress_range: [number, number];
  location: { latitude: number; longitude: number };
}

export interface ReconstructionDrift {
  type: "LineString";
  coordinates: [number, number][];
  points: Array<{
    timestamp: string;
    latitude: number;
    longitude: number;
    active?: boolean;
  }>;
  total_distance_km: number;
  origin?: any;
  uncertainty?: { radius_km: number; spread_km: number };
}

export interface ReconstructionSpillGeometry {
  type: "Polygon" | "MultiPolygon";
  coordinates: any;
  area_sq_km: number;
  perimeter_km: number;
  centroid: { latitude: number; longitude: number };
  confidence: number;
  detection_time?: string;
}

export interface ReconstructionTimelineStage {
  stage: number;
  name: string;
  progress_range: [number, number];
  timestamp: string;
  description: string;
  active_vessel: boolean;
  release_active: boolean;
  particles_active: boolean;
  slick_active: boolean;
}

export interface ForensicReconstruction {
  investigation_id: string;
  title: string;
  region: string;
  reconstruction_status: ReconstructionStatus;
  disclaimer: string;
  vessel: ReconstructionVessel | null;
  ais_track: ReconstructionAisTrack | null;
  release_window?: ReconstructionReleaseWindow;
  probable_origin: any;
  ocean_current: {
    u_eastward_m_s?: number;
    v_northward_m_s?: number;
    speed_m_s: number;
    direction_deg: number;
    model_type?: string;
  };
  drift_trajectory: ReconstructionDrift;
  spill_geometry: ReconstructionSpillGeometry | null;
  timeline: ReconstructionTimelineStage[];
  generated_at: string;
}

export interface UserProfile {
  id?: string;
  full_name: string;
  call_sign: string;
  title: string;
  organization: string;
  department?: string;
  station: string;
  clearance_level: string;
  email: string;
  phone: string;
  radio_frequency: string;
  node_id: string;
  surveillance_sector: string;
  authorization_scope: string;
  specialization?: string;
  signing_key_id: string;
  avatar_url?: string | null;
  bio?: string | null;
}

export interface HeaderSearchResult {
  id: string;
  investigation_id: string;
  title: string;
  region: string;
  status: string;
  spill_area_km2?: number | null;
  suspect_vessel?: string | null;
  match_type: "id" | "title" | "vessel" | "mmsi" | "spill_id" | "general";
  match_label: string;
  created_at?: string | null;
}

export interface AppNotification {
  id: number;
  event_key: string;
  notification_type: "NEW_INVESTIGATION" | "INVESTIGATION_COMPLETED" | "INVESTIGATION_FAILED" | "INVESTIGATION_BLOCKED" | "PIPELINE_ATTENTION" | string;
  title: string;
  message: string;
  investigation_id?: string | null;
  status?: string | null;
  link_path?: string | null;
  is_read: boolean;
  created_at: string;
}

export interface NotificationsResponse {
  items: AppNotification[];
  unread_count: number;
}

export interface AttributionCalibration {
  version: string;
  is_active: boolean;
  notes?: string;
  weights: {
    spatial_proximity: number;
    temporal_overlap: number;
    drift_consistency: number;
    track_consistency: number;
    vessel_type_relevance?: number;
    ais_quality?: number;
  };
  percentages: {
    spatial_proximity: number;
    temporal_overlap: number;
    drift_consistency: number;
    track_consistency: number;
    vessel_type_relevance?: number;
    ais_quality?: number;
  };
  total_percentage: number;
  updated_at: string;
}


