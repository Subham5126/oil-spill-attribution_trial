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
  CandidateVessel,
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

export async function getActivePipelineResult(): Promise<EndToEndResult & { _source?: DataSourceOrigin }> {
  try {
    const res = await fetch(`${API_BASE_URL}/api/pipeline/latest`);
    if (res.ok) {
      const data = await res.json();
      return { ...data, _source: "BACKEND" as DataSourceOrigin };
    }
  } catch (e) {
    if (!ENABLE_DEMO_FALLBACK) {
      throw new Error(`Failed to fetch active pipeline result from backend: ${e}`);
    }
  }
  const demoData = await loadDemoResult();
  return { ...demoData, _source: "DEMO_FALLBACK" as DataSourceOrigin };
}

export async function getGISLayersGeoJSON(): Promise<GeoJSONFeatureCollection & { _source?: DataSourceOrigin }> {
  try {
    const res = await fetch(`${API_BASE_URL}/api/layers/geojson`);
    if (res.ok) {
      const data = await res.json();
      return { ...data, _source: "BACKEND" as DataSourceOrigin };
    }
  } catch (e) {
    if (!ENABLE_DEMO_FALLBACK) {
      throw new Error(`Failed to fetch GIS layers GeoJSON from backend: ${e}`);
    }
  }
  const demoLayers = await loadDemoLayers();
  return { ...demoLayers, _source: "DEMO_FALLBACK" as DataSourceOrigin };
}

export async function getInvestigations(): Promise<Investigation[]> {
  try {
    const res = await fetch(`${API_BASE_URL}/api/investigations`);
    if (res.ok) {
      return await res.json();
    }
  } catch (e) {
    if (!ENABLE_DEMO_FALLBACK) {
      throw new Error(`Failed to fetch investigations from backend: ${e}`);
    }
  }
  return DEMO_INVESTIGATIONS;
}

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

  // Return realistic drift result matching active pipeline
  const active = await loadDemoResult();
  return active.ocean_drift;
}

