/**
 * OilTrace API Service Client
 * Connects React frontend to FastAPI / domain pipeline endpoints,
 * with fallback to demoDataAdapter for offline & development workflows.
 */

import {
  EndToEndResult,
  GeoJSONFeatureCollection,
  Investigation,
  Report,
  SentinelImage,
  CandidateVessel,
  DashboardSummary,
  EvidenceItem,
  TimelineEvent,
  VesselIntelligenceItem,
  SystemStatus,
  DatasetItem,
  UserProfile,
  HeaderSearchResult,
  AppNotification,
  NotificationsResponse,
  UploadedSceneMetadata,
  TemporalAnchor,
  AttributionCalibration,
} from "../types";
import {
  fetchEndToEndResult as loadDemoResult,
  fetchLayersGeoJSON as loadDemoLayers,
  DEMO_INVESTIGATIONS,
  DEMO_REPORTS,
} from "./demoDataAdapter";

const API_BASE_URL = (import.meta as any).env?.VITE_API_URL || "";
const ENABLE_DEMO_FALLBACK = (import.meta as any).env?.VITE_ENABLE_DEMO_FALLBACK !== "false";

export type DataSourceOrigin = "BACKEND" | "DEMO_FALLBACK";

/**
 * Check backend liveness and health status.
 */
export async function checkBackendHealth(): Promise<{ connected: boolean; details?: any }> {
  try {
    const res = await fetch(`${API_BASE_URL}/api/health`);
    if (res.ok) {
      const data = await res.json();
      return { connected: true, details: data };
    }
  } catch (e) {
    // Backend offline
  }
  return { connected: false };
}

/**
 * List available Sentinel-1 GeoTIFF scenes from disk / inventory.
 */
export async function listAvailableImages(): Promise<SentinelImage[]> {
  try {
    const res = await fetch(`${API_BASE_URL}/api/images`);
    if (res.ok) {
      return await res.json();
    }
  } catch (e) {
    console.warn("Failed to fetch available images from backend:", e);
  }
  return [
    {
      image_id: "00052",
      filename: "00052.tif",
      exists_on_disk: true,
      latitude: 25.567163,
      longitude: 54.634578,
      region: "Persian Gulf (Sirri / UAE Corridor)",
      observation_timestamp: "2017-03-11T02:15:11Z",
      has_matching_ocean: true,
      recommended: true,
    },
    {
      image_id: "00643",
      filename: "00643.tif",
      exists_on_disk: true,
      latitude: 21.050474,
      longitude: 38.318854,
      region: "Red Sea (Jeddah Corridor)",
      observation_timestamp: "2019-10-14T03:15:03Z",
      has_matching_ocean: true,
      recommended: true,
    },
  ];
}

/**
 * Get details of a specific Sentinel-1 image.
 */
export async function getImageDetails(imageId: string): Promise<SentinelImage | null> {
  try {
    const res = await fetch(`${API_BASE_URL}/api/images/${imageId}`);
    if (res.ok) {
      return await res.json();
    }
  } catch (e) {
    console.warn(`Failed to fetch image details for ${imageId}:`, e);
  }
  return null;
}

/**
 * Retrieve dashboard summary metrics from database.
 */
export async function getDashboardSummary(): Promise<DashboardSummary> {
  try {
    const res = await fetch(`${API_BASE_URL}/api/investigations/dashboard/summary`);
    if (res.ok) {
      return await res.json();
    }
  } catch (e) {
    console.warn("Failed to fetch dashboard summary from backend:", e);
  }
  return {
    total_investigations: 0,
    completed_investigations: 0,
    active_investigations: 0,
    running_investigations: 0,
    failed_investigations: 0,
    total_spill_area_km2: 0,
    candidate_vessels_tracked: 0,
    recent_investigations: [],
    latest_completed_investigation: null,
  };
}

/**
 * Retrieve registered investigations from database with multi-criteria filtering.
 */
export async function getInvestigations(params?: {
  search?: string;
  status?: string;
  region?: string;
  starred?: boolean;
  archived?: boolean;
  include_deleted?: boolean;
  sort_by?: string;
  sort_dir?: "asc" | "desc";
  limit?: number;
  offset?: number;
}): Promise<Investigation[]> {
  try {
    const query = new URLSearchParams();
    if (params?.search) query.set("search", params.search);
    if (params?.status && params.status !== "All") query.set("status", params.status);
    if (params?.region && params.region !== "All") query.set("region", params.region);
    if (params?.starred !== undefined) query.set("starred", String(params.starred));
    if (params?.archived !== undefined) query.set("archived", String(params.archived));
    if (params?.include_deleted !== undefined) query.set("include_deleted", String(params.include_deleted));
    if (params?.sort_by) query.set("sort_by", params.sort_by);
    if (params?.sort_dir) query.set("sort_dir", params.sort_dir);
    if (params?.limit) query.set("limit", String(params.limit));
    if (params?.offset) query.set("offset", String(params.offset));

    const res = await fetch(`${API_BASE_URL}/api/investigations?${query.toString()}`);
    if (res.ok) {
      const data = await res.json();
      return data;
    }
  } catch (e) {
    if (!ENABLE_DEMO_FALLBACK) {
      throw new Error(`Failed to fetch investigations from backend: ${e}`);
    }
  }
  return DEMO_INVESTIGATIONS;
}

/**
 * Retrieve historical investigations with chronological search.
 */
export async function getInvestigationHistory(params?: {
  search?: string;
  status?: string;
  region?: string;
  include_deleted?: boolean;
  sort_by?: string;
  sort_dir?: "asc" | "desc";
  limit?: number;
  offset?: number;
}): Promise<Investigation[]> {
  try {
    const query = new URLSearchParams();
    if (params?.search) query.set("search", params.search);
    if (params?.status && params.status !== "All" && params.status !== "ALL") query.set("status", params.status);
    if (params?.region && params.region !== "All" && params.region !== "ALL") query.set("region", params.region);
    if (params?.include_deleted !== undefined) query.set("include_deleted", String(params.include_deleted));
    if (params?.sort_by) query.set("sort_by", params.sort_by);
    if (params?.sort_dir) query.set("sort_dir", params.sort_dir);
    if (params?.limit) query.set("limit", String(params.limit));
    if (params?.offset) query.set("offset", String(params.offset));

    const res = await fetch(`${API_BASE_URL}/api/investigations/history?${query.toString()}`);
    if (res.ok) {
      return await res.json();
    }
  } catch (e) {
    console.warn("Failed to fetch investigation history:", e);
  }
  return [];
}

/**
 * Retrieve a specific investigation by ID.
 */
export async function getInvestigation(investigationId: string): Promise<Investigation | null> {
  try {
    const res = await fetch(`${API_BASE_URL}/api/investigations/${investigationId}`);
    if (res.ok) {
      return await res.json();
    }
  } catch (e) {
    console.warn(`Failed to fetch investigation ${investigationId}:`, e);
  }
  return null;
}

/**
 * Create a new incident investigation.
 */
export async function createInvestigation(payload: {
  title: string;
  image_id: string;
  source_image_path?: string;
  region?: string;
  priority?: "High" | "Medium" | "Low";
  observation_timestamp?: string;
  sar_acquisition_time?: string;
  sar_acquisition_time_source?: string;
  sar_acquisition_time_verified?: boolean;
  metadata?: Record<string, any>;
  coordinates?: { latitude: number; longitude: number };
}): Promise<Investigation> {
  const res = await fetch(`${API_BASE_URL}/api/investigations`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.message || `Failed to create investigation (${res.status})`);
  }
  return await res.json();
}

/**
 * Initialize a chunked upload session for a Sentinel-1 GeoTIFF.
 */
export async function initSentinelUpload(
  filename: string,
  fileSize: number,
  totalChunks: number,
  investigationId?: string,
  contentType?: string
): Promise<{ upload_id: string; chunk_size: number; total_chunks: number; max_file_size: number }> {
  const isTiff = filename.toLowerCase().endsWith(".tif") || filename.toLowerCase().endsWith(".tiff");
  const effContentType = contentType || (isTiff ? "image/tiff" : "application/octet-stream");

  const res = await fetch(`${API_BASE_URL}/api/investigations/upload/sentinel/init`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      filename,
      file_size: fileSize,
      total_chunks: totalChunks,
      content_type: effContentType,
      investigation_id: investigationId || null,
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    const rawMsg = err.detail || err.message;
    const safeError = rawMsg || (res.status === 413 ? "File exceeds the 1 GB maximum size limit." : res.status === 400 ? "Unsupported file type or invalid upload parameters." : `Server error (${res.status})`);
    throw new Error(`Failed to initialize upload: ${safeError}`);
  }
  return await res.json();
}

/**
 * Upload an individual chunk for a Sentinel-1 GeoTIFF session.
 */
export async function uploadSentinelChunk(
  uploadId: string,
  chunkIndex: number,
  chunkBlob: Blob,
  signal?: AbortSignal
): Promise<void> {
  const formData = new FormData();
  formData.append("upload_id", uploadId);
  formData.append("chunk_index", String(chunkIndex));
  formData.append("chunk", chunkBlob);

  const res = await fetch(`${API_BASE_URL}/api/investigations/upload/sentinel/chunk`, {
    method: "POST",
    body: formData,
    signal,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || err.message || `Failed to upload chunk ${chunkIndex} (${res.status})`);
  }
}

/**
 * Complete a chunked Sentinel-1 GeoTIFF upload, validate raster structure, and retrieve extracted metadata.
 */
export async function completeSentinelUpload(uploadId: string): Promise<UploadedSceneMetadata> {
  const res = await fetch(`${API_BASE_URL}/api/investigations/upload/sentinel/complete`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ upload_id: uploadId }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || err.message || `Failed to finalize upload (${res.status})`);
  }
  return await res.json();
}

/**
 * Confirm or manually set the authoritative Sentinel-1 SAR acquisition temporal anchor.
 */
export async function confirmTemporalAnchor(
  uploadId: string,
  payload: {
    sar_acquisition_time?: string;
    date?: string;
    time?: string;
    source?: string;
  }
): Promise<TemporalAnchor> {
  const res = await fetch(
    `${API_BASE_URL}/api/investigations/upload/sentinel/${encodeURIComponent(uploadId)}/temporal-anchor`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }
  );
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || err.message || `Failed to confirm temporal anchor (${res.status})`);
  }
  return await res.json();
}

/**
 * Cancel and delete an in-progress or completed upload session.
 */
export async function cancelSentinelUpload(uploadId: string): Promise<void> {
  try {
    await fetch(`${API_BASE_URL}/api/investigations/upload/sentinel/${encodeURIComponent(uploadId)}`, {
      method: "DELETE",
    });
  } catch (e) {
    console.warn("Error cancelling upload session:", e);
  }
}

/**
 * Upload a Sentinel-1 GeoTIFF file using robust chunked streaming (5 MB chunks) with real progress callbacks.
 */
export async function uploadSentinelGeoTiff(
  file: File,
  onProgress?: (percentage: number, loadedBytes: number, totalBytes: number) => void,
  signal?: AbortSignal
): Promise<UploadedSceneMetadata> {
  const CHUNK_SIZE = 5 * 1024 * 1024; // 5 MB chunks
  const totalBytes = file.size;
  const totalChunks = Math.max(1, Math.ceil(totalBytes / CHUNK_SIZE));

  // 1. Initialize upload session on server
  const init = await initSentinelUpload(file.name, totalBytes, totalChunks);
  const uploadId = init.upload_id;

  let loadedBytes = 0;

  try {
    // 2. Upload chunks sequentially
    for (let chunkIndex = 0; chunkIndex < totalChunks; chunkIndex++) {
      if (signal?.aborted) {
        await cancelSentinelUpload(uploadId);
        throw new Error("Upload aborted by user.");
      }

      const start = chunkIndex * CHUNK_SIZE;
      const end = Math.min(start + CHUNK_SIZE, totalBytes);
      const chunkBlob = file.slice(start, end);

      await uploadSentinelChunk(uploadId, chunkIndex, chunkBlob, signal);

      loadedBytes += (end - start);
      const pct = Math.min(99, Math.round((loadedBytes / totalBytes) * 100));
      if (onProgress) {
        onProgress(pct, loadedBytes, totalBytes);
      }
    }

    // 3. Finalize upload and validate GeoTIFF
    const metadata = await completeSentinelUpload(uploadId);
    if (onProgress) {
      onProgress(100, totalBytes, totalBytes);
    }
    return metadata;
  } catch (err) {
    await cancelSentinelUpload(uploadId).catch(() => {});
    throw err;
  }
}

/**
 * Delete an investigation (soft delete by default, purge if requested).
 */
export async function deleteInvestigation(
  investigationId: string,
  purge: boolean = false
): Promise<{ investigation_id: string; deleted: boolean; purged: boolean; message: string }> {
  const res = await fetch(`${API_BASE_URL}/api/investigations/${investigationId}?purge=${purge}`, {
    method: "DELETE",
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.message || `Failed to delete investigation (${res.status})`);
  }
  return await res.json();
}

/**
 * Restore a soft-deleted investigation from trash.
 */
export async function restoreInvestigation(investigationId: string): Promise<Investigation> {
  const res = await fetch(`${API_BASE_URL}/api/investigations/${investigationId}/restore`, {
    method: "POST",
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.message || `Failed to restore investigation (${res.status})`);
  }
  return await res.json();
}

/**
 * Spawn a re-run pipeline duplication from an existing investigation.
 */
export async function rerunInvestigation(investigationId: string): Promise<Investigation> {
  const res = await fetch(`${API_BASE_URL}/api/investigations/${investigationId}/rerun`, {
    method: "POST",
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.message || `Failed to rerun investigation (${res.status})`);
  }
  return await res.json();
}

/**
 * Patch mutable properties (title, priority, is_starred, is_archived).
 */
export async function patchInvestigation(
  investigationId: string,
  patch: Partial<Investigation>
): Promise<Investigation> {
  const res = await fetch(`${API_BASE_URL}/api/investigations/${investigationId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.message || `Failed to patch investigation (${res.status})`);
  }
  return await res.json();
}

/**
 * Fetch real chronological activity audit timeline.
 */
export async function getInvestigationTimeline(investigationId: string): Promise<TimelineEvent[]> {
  try {
    const res = await fetch(`${API_BASE_URL}/api/investigations/${investigationId}/timeline`);
    if (res.ok) {
      return await res.json();
    }
  } catch (e) {
    console.warn(`Failed to fetch timeline for ${investigationId}:`, e);
  }
  return [];
}

/**
 * Fetch verified evidence artifacts library for an incident.
 */
export async function getInvestigationEvidence(investigationId: string): Promise<EvidenceItem[]> {
  try {
    const res = await fetch(`${API_BASE_URL}/api/investigations/${investigationId}/evidence`);
    if (res.ok) {
      return await res.json();
    }
  } catch (e) {
    console.warn(`Failed to fetch evidence for ${investigationId}:`, e);
  }
  return [];
}

/**
 * Returns direct URL to download full forensic evidence bundle ZIP with manifest.json.
 */
export function getEvidenceBundleDownloadUrl(investigationId: string): string {
  return `${API_BASE_URL}/api/investigations/${investigationId}/evidence/bundle`;
}

/**
 * Returns direct URL to download an individual forensic artifact.
 */
export function getArtifactDownloadUrl(investigationId: string, artifactType: string): string {
  return `${API_BASE_URL}/api/investigations/${investigationId}/artifacts/${artifactType}/download`;
}

/**
 * Verifies disk presence, byte size, and cryptographic SHA-256 hash of an artifact.
 */
export async function verifyArtifactIntegrity(
  investigationId: string,
  artifactType: string
): Promise<{
  status: string;
  verified: boolean;
  sha256?: string;
  expected_sha256?: string;
  byte_size?: number;
  message?: string;
}> {
  const res = await fetch(
    `${API_BASE_URL}/api/investigations/${investigationId}/artifacts/${artifactType}/verify`,
    { method: "POST" }
  );
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Verification failed" }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return await res.json();
}

/**
 * Fetch aggregated cross-investigation vessel intelligence.
 */
export async function getVesselIntelligence(): Promise<VesselIntelligenceItem[]> {
  try {
    const res = await fetch(`${API_BASE_URL}/api/investigations/vessel-intelligence`);
    if (res.ok) {
      return await res.json();
    }
  } catch (e) {
    console.warn("Failed to fetch vessel intelligence:", e);
  }
  return [];
}

/**
 * Fetch real system diagnostic status across ML, Rasterio, Copernicus, AIS, DB.
 */
export async function getSystemStatus(): Promise<SystemStatus> {
  try {
    const res = await fetch(`${API_BASE_URL}/api/health/system-status`);
    if (res.ok) {
      return await res.json();
    }
  } catch (e) {
    console.warn("Failed to fetch system status:", e);
  }
  return {
    overall: "Warning",
    subsystems: [],
  };
}

/**
 * Fetch verified inventory and coverage of satellite and ocean datasets.
 */
export async function getDatasetsStatus(): Promise<{ datasets: DatasetItem[] }> {
  try {
    const res = await fetch(`${API_BASE_URL}/api/health/datasets`);
    if (res.ok) {
      return await res.json();
    }
  } catch (e) {
    console.warn("Failed to fetch datasets status:", e);
  }
  return { datasets: [] };
}

/**
 * Trigger the unified attribution pipeline for an investigation.
 */
export async function runInvestigationPipeline(
  investigationId: string,
  options?: {
    image_id?: string;
    image_path?: string;
    ocean_file?: string;
    skip_ais?: boolean;
    skip_drift?: boolean;
    sync?: boolean;
  }
): Promise<{ investigation_id: string; status: string; result?: EndToEndResult }> {
  const res = await fetch(`${API_BASE_URL}/api/investigations/${investigationId}/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(options || {}),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.message || `Failed to start pipeline (${res.status})`);
  }
  return await res.json();
}

/**
 * Get the live execution status of an investigation pipeline.
 */
export async function getInvestigationStatus(investigationId: string): Promise<{
  investigation_id: string;
  status: string;
  stage?: string;
  progress_percentage: number;
  stage_statuses: Record<string, string>;
  notes: string[];
  error?: string | null;
}> {
  const res = await fetch(`${API_BASE_URL}/api/investigations/${investigationId}/status`);
  if (!res.ok) {
    throw new Error(`Failed to check status for ${investigationId}`);
  }
  return await res.json();
}

function createEmptyResult(id?: string): EndToEndResult {
  return {
    spill_metadata: {
      spill_id: id || "N/A",
      sensor: "Sentinel-1 SAR C-Band",
      detection_timestamp: new Date().toISOString(),
      confidence: 0,
      crs: "EPSG:4326",
      properties: {},
    },
    gis_measurement: {
      spill_id: id || "N/A",
      crs: "EPSG:4326",
      area: { sq_meters: 0, sq_kilometers: 0 },
      perimeter: { meters: 0, kilometers: 0 },
      centroid: { latitude: 0, longitude: 0 },
      bounding_box: { min_lon: 0, min_lat: 0, max_lon: 0, max_lat: 0 },
      shape_characteristics: { aspect_ratio: 1, compactness: 1 },
    },
    ocean_drift: {
      model_type: "None",
      particles_simulated: 0,
      forecast: { steps: 0, timestep_seconds: 0, duration_hours: 0 },
      hindcast: { duration_hours: 0, timestep_seconds: 0, observation_time: "" },
      surface_velocity: { u_eastward_m_s: 0, v_northward_m_s: 0, speed_m_s: 0, direction_deg: 0 },
      probable_origin: { latitude: 0, longitude: 0, timestamp: "", drift_distance_km: 0, relative_heuristic_score: 0 },
      forecast_endpoint: { latitude: 0, longitude: 0, timestamp: "", drift_distance_km: 0 },
      uncertainty: {
        radius_km: 0,
        spread_km: 0,
        empirical_coverage_level: 0.95,
        dispersion_description: "95% empirical spatial dispersion estimate",
        bounding_envelope: { min_lat: 0, max_lat: 0, min_lon: 0, max_lon: 0 },
      },
    },
    candidate_vessels: [],
    attribution_ranking: [],
    primary_suspect: null,
    pipeline_execution: {
      status: "RUNNING",
      stage_statuses: {},
      notes: [],
      execution_timestamp: new Date().toISOString(),
    },
  };
}

/**
 * Retrieve the complete attribution result for an investigation or the active pipeline.
 */
export async function getActivePipelineResult(
  investigationId?: string
): Promise<EndToEndResult & { _source?: DataSourceOrigin }> {
  try {
    const url = investigationId
      ? `${API_BASE_URL}/api/investigations/${investigationId}/result`
      : `${API_BASE_URL}/api/pipeline/latest`;
    const res = await fetch(url);
    if (res.ok) {
      const data = await res.json();
      return { ...data, _source: "BACKEND" as DataSourceOrigin };
    }
  } catch (e) {
    if (!investigationId && !ENABLE_DEMO_FALLBACK) {
      throw new Error(`Failed to fetch pipeline result from backend: ${e}`);
    }
  }

  // Never fallback to demo data if an investigation ID was specified or for global overview!
  if (investigationId) {
    return { ...createEmptyResult(investigationId), _source: "BACKEND" as DataSourceOrigin };
  }

  return { ...createEmptyResult(), _source: "BACKEND" as DataSourceOrigin };
}

/**
 * Retrieve GeoJSON feature collection for an investigation or latest pipeline.
 */
export async function getGISLayersGeoJSON(
  investigationId?: string
): Promise<GeoJSONFeatureCollection & { _source?: DataSourceOrigin }> {
  try {
    const url = investigationId
      ? `${API_BASE_URL}/api/investigations/${investigationId}/map`
      : `${API_BASE_URL}/api/layers/geojson`;
    const res = await fetch(url);
    if (res.ok) {
      const data = await res.json();
      return { ...data, _source: "BACKEND" as DataSourceOrigin };
    }
  } catch (e) {
    if (!investigationId && !ENABLE_DEMO_FALLBACK) {
      throw new Error(`Failed to fetch GIS layers GeoJSON from backend: ${e}`);
    }
  }

  // Strictly isolate: never fallback to demo data for global overview or specific investigations!
  return { type: "FeatureCollection", features: [], _source: "BACKEND" as DataSourceOrigin };
}

/**
 * Get structured 11-section MARPOL report for an investigation.
 */
export async function getInvestigationReport(investigationId: string): Promise<Report | null> {
  try {
    const res = await fetch(`${API_BASE_URL}/api/investigations/${investigationId}/report`);
    if (res.ok) {
      return await res.json();
    }
  } catch (e) {
    console.warn(`Failed to fetch report for ${investigationId}:`, e);
  }
  return null;
}

/**
 * Get forensic PDF download URL.
 */
export function getReportDownloadUrl(investigationId: string): string {
  return `${API_BASE_URL}/api/investigations/${investigationId}/report/pdf`;
}

/**
 * Get forensic PDF inline view URL.
 */
export function getReportViewUrl(investigationId: string): string {
  return `${API_BASE_URL}/api/investigations/${investigationId}/report/pdf/view`;
}

/**
 * Get dynamic SAR Detection Overlay URL for an investigation.
 */
export function getDetectionOverlayUrl(investigationId: string, imageId?: string | null): string {
  const query = imageId ? `?img=${encodeURIComponent(imageId)}` : "";
  return `${API_BASE_URL}/api/investigations/${investigationId}/artifacts/detection-overlay${query}`;
}

/**
 * Get dynamic AI Segmentation Mask URL for an investigation.
 */
export function getSegmentationMaskUrl(investigationId: string, imageId?: string | null): string {
  const query = imageId ? `?img=${encodeURIComponent(imageId)}` : "";
  return `${API_BASE_URL}/api/investigations/${investigationId}/artifacts/segmentation-mask${query}`;
}

/**
 * Get raw Sentinel-1 GeoTIFF download URL for an investigation.
 */
export function getSourceTiffUrl(investigationId: string, imageId?: string | null): string {
  const query = imageId ? `?img=${encodeURIComponent(imageId)}` : "";
  return `${API_BASE_URL}/api/investigations/${investigationId}/artifacts/source-tiff${query}`;
}

/**
 * List all generated reports.
 */
export async function getReports(): Promise<Report[]> {
  try {
    const res = await fetch(`${API_BASE_URL}/api/reports`);
    if (res.ok) {
      return await res.json();
    }
  } catch (e) {
    if (!ENABLE_DEMO_FALLBACK) {
      throw new Error(`Failed to fetch reports from backend: ${e}`);
    }
  }
  return DEMO_REPORTS;
}

/**
 * Run custom hydrodynamic drift simulation.
 */
export async function runCustomDriftSimulation(params: {
  lat: number;
  lon: number;
  durationHours: number;
  timestepSeconds: number;
  mode: "hindcast" | "forecast";
}): Promise<any> {
  try {
    const res = await fetch(`${API_BASE_URL}/api/drift/simulate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(params),
    });
    if (res.ok) {
      return await res.json();
    }
  } catch (e) {
    if (!ENABLE_DEMO_FALLBACK) {
      throw new Error(`Failed to run drift simulation on backend: ${e}`);
    }
  }

  const active = await loadDemoResult();
  return active.ocean_drift;
}

/**
 * Retrieve normalized forensic reconstruction dataset for animated incident replay.
 */
export async function getInvestigationReconstruction(
  investigationId: string
): Promise<import("../types").ForensicReconstruction> {
  const res = await fetch(`${API_BASE_URL}/api/investigations/${investigationId}/reconstruction`);
  if (!res.ok) {
    throw new Error(`Failed to fetch forensic reconstruction for ${investigationId}: ${res.statusText}`);
  }
  return await res.json();
}

const LOCAL_STORAGE_PROFILE_KEY = "oiltrace_user_profile_v1";

export const DEFAULT_USER_PROFILE: UserProfile = {
  id: "default-analyst",
  full_name: "Cmdr. Rajesh K. Varma",
  call_sign: "CG-FOR-904",
  title: "Senior Marine Forensic Analyst",
  organization: "DG Shipping / Indian Coast Guard",
  department: "Maritime Environmental Enforcement Division",
  station: "Western Seaboard Command, Mumbai",
  clearance_level: "Class-I Maritime Forensic Authority",
  email: "rajesh.varma@dgshipping.gov.in",
  phone: "+91 (22) 2269-8000 (Ext 402)",
  radio_frequency: "VHF Ch 16 / DSC 2187.5 kHz",
  node_id: "Node #IND-WEST-01",
  surveillance_sector: "Exclusive Economic Zone (EEZ) — West Sector",
  authorization_scope: "MARPOL Annex I Enforcement & Legal Prosecution",
  specialization: "SAR Detection & Hydrodynamic Drift Reconstruction",
  signing_key_id: "ECDSA-P384-DG-SHIP-2026-KEY-7F9A",
  avatar_url: null,
  bio: "Principal investigator specializing in synthetic aperture radar (SAR) hydrocarbon detection, hydrodynamic drift hindcast analysis, and AIS maritime correlation for environmental enforcement.",
};

/**
 * Retrieve analyst profile from backend with local storage fallback.
 */
export async function getUserProfile(): Promise<UserProfile> {
  try {
    const res = await fetch(`${API_BASE_URL}/api/profile`);
    if (res.ok) {
      const data: UserProfile = await res.json();
      localStorage.setItem(LOCAL_STORAGE_PROFILE_KEY, JSON.stringify(data));
      return data;
    }
  } catch (e) {
    console.warn("Failed to fetch profile from backend, checking local storage:", e);
  }

  const cached = localStorage.getItem(LOCAL_STORAGE_PROFILE_KEY);
  if (cached) {
    try {
      return JSON.parse(cached);
    } catch {
      // ignore
    }
  }

  return DEFAULT_USER_PROFILE;
}

/**
 * Update analyst profile in backend and update local cache.
 */
export async function updateUserProfile(profile: Partial<UserProfile>): Promise<UserProfile> {
  let updatedProfile: UserProfile = { ...DEFAULT_USER_PROFILE, ...profile };

  try {
    const res = await fetch(`${API_BASE_URL}/api/profile`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(profile),
    });
    if (res.ok) {
      updatedProfile = await res.json();
    }
  } catch (e) {
    console.warn("Failed to save profile to backend, saving locally:", e);
  }

  localStorage.setItem(LOCAL_STORAGE_PROFILE_KEY, JSON.stringify(updatedProfile));
  return updatedProfile;
}

/**
 * Upload and persist profile avatar photo (JPG, PNG, WEBP).
 */
export async function uploadProfilePhoto(file: File): Promise<UserProfile> {
  const formData = new FormData();
  formData.append("file", file);

  const res = await fetch(`${API_BASE_URL}/api/profile/photo`, {
    method: "POST",
    body: formData,
  });

  if (!res.ok) {
    const errData = await res.json().catch(() => ({}));
    throw new Error(errData.detail || "Photo upload failed");
  }

  const updated: UserProfile = await res.json();
  localStorage.setItem(LOCAL_STORAGE_PROFILE_KEY, JSON.stringify(updated));
  return updated;
}

/**
 * Remove custom profile photo and revert to initials.
 */
export async function deleteProfilePhoto(): Promise<UserProfile> {
  const res = await fetch(`${API_BASE_URL}/api/profile/photo`, {
    method: "DELETE",
  });

  if (!res.ok) {
    const errData = await res.json().catch(() => ({}));
    throw new Error(errData.detail || "Failed to remove photo");
  }

  const updated: UserProfile = await res.json();
  localStorage.setItem(LOCAL_STORAGE_PROFILE_KEY, JSON.stringify(updated));
  return updated;
}

/**
 * Search investigations, candidate vessels, and spill IDs with backend priority ranking.
 */
export async function searchInvestigations(query: string, limit: number = 10): Promise<HeaderSearchResult[]> {
  if (!query || query.trim().length < 2) {
    return [];
  }

  try {
    const res = await fetch(
      `${API_BASE_URL}/api/investigations/search?q=${encodeURIComponent(query.trim())}&limit=${limit}`
    );
    if (res.ok) {
      return await res.json();
    }
  } catch (e) {
    console.warn("Backend search failed, using demo fallback if available:", e);
  }

  if (ENABLE_DEMO_FALLBACK) {
    const q = query.toLowerCase().trim();
    return DEMO_INVESTIGATIONS.filter(
      (inv) =>
        inv.title.toLowerCase().includes(q) ||
        inv.id.toLowerCase().includes(q) ||
        inv.region.toLowerCase().includes(q) ||
        (inv.suspect_vessel && inv.suspect_vessel.toLowerCase().includes(q))
    ).map((inv) => ({
      id: inv.id,
      investigation_id: inv.id,
      title: inv.title,
      region: inv.region,
      status: inv.status,
      spill_area_km2: inv.spill_area_km2,
      suspect_vessel: inv.suspect_vessel,
      match_type: inv.id.toLowerCase() === q ? "id" : "title",
      match_label: inv.id.toLowerCase() === q ? `Case ID: ${inv.id}` : "Title Match",
      created_at: inv.created_at,
    }));
  }

  return [];
}

/**
 * Retrieve system alerts and investigation lifecycle notifications with unread count.
 */
export async function getNotifications(limit: number = 50, unreadOnly: boolean = false): Promise<NotificationsResponse> {
  try {
    const res = await fetch(
      `${API_BASE_URL}/api/notifications?limit=${limit}&unread_only=${unreadOnly}`
    );
    if (res.ok) {
      return await res.json();
    }
  } catch (e) {
    console.warn("Failed to fetch notifications from backend:", e);
  }

  return { items: [], unread_count: 0 };
}

/**
 * Mark a specific notification as read.
 */
export async function markNotificationAsRead(id: number): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE_URL}/api/notifications/${id}/read`, {
      method: "PATCH",
    });
    return res.ok;
  } catch (e) {
    console.warn(`Failed to mark notification ${id} as read:`, e);
    return false;
  }
}

/**
 * Mark all notifications as read.
 */
export async function markAllNotificationsAsRead(): Promise<number> {
  try {
    const res = await fetch(`${API_BASE_URL}/api/notifications/mark-all-read`, {
      method: "POST",
    });
    if (res.ok) {
      const data = await res.json();
      return data.marked_count || 0;
    }
  } catch (e) {
    console.warn("Failed to mark all notifications as read:", e);
  }
  return 0;
}

/**
 * Fetch persisted attribution calibration settings and weights.
 */
export async function getAttributionCalibration(): Promise<AttributionCalibration> {
  const res = await fetch(`${API_BASE_URL}/api/settings/attribution`);
  if (!res.ok) {
    throw new Error(`Failed to load attribution settings (${res.status})`);
  }
  return await res.json();
}

/**
 * Persist updated attribution calibration weights (must sum to 100%).
 */
export async function updateAttributionCalibration(payload: {
  spatial_proximity: number;
  temporal_overlap: number;
  drift_consistency: number;
  track_consistency: number;
  vessel_type_relevance?: number;
  ais_quality?: number;
  notes?: string;
}): Promise<AttributionCalibration> {
  const res = await fetch(`${API_BASE_URL}/api/settings/attribution`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || err.message || `Failed to save calibration (${res.status})`);
  }
  return await res.json();
}


