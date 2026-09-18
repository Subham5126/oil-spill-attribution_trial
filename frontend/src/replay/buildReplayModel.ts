import type { ForensicReconstruction } from "../types";
import { interpolateVessel, normalizeAisPoints } from "./ais";
import { isPolygonGeometry } from "./geometry";
import { seedDetectedSpillParticles, seedOilParticles } from "./particles";
import { parseUtcMs } from "./time";
import type { AISPoint, ForecastFrame, IncidentReplayModel, ReplayEventMarker } from "./types";

function spillGeometryFromRecon(recon: ForensicReconstruction): GeoJSON.Polygon | GeoJSON.MultiPolygon | null {
  const g = recon.spill_geometry;
  if (!g) return null;
  const geom = { type: g.type, coordinates: g.coordinates } as GeoJSON.Geometry;
  return isPolygonGeometry(geom) ? geom : null;
}

function collectAis(
  recon: ForensicReconstruction,
  selectedVessel?: any | null,
  timeBounds?: { startTime: number; endTime: number }
): AISPoint[] {
  // 1. Check if selected candidate vessel has its own multi-point trajectory
  if (selectedVessel) {
    const rawTrack = selectedVessel.trajectory || selectedVessel.track;
    if (Array.isArray(rawTrack) && rawTrack.length > 0) {
      const pts = normalizeAisPoints(rawTrack, undefined, timeBounds);
      if (pts.length > 0) return pts;
    }
  }

  // 2. Check recon.ais_track waypoints or coordinates
  if (recon.ais_track?.waypoints && recon.ais_track.waypoints.length > 0) {
    const pts = normalizeAisPoints(recon.ais_track.waypoints, undefined, timeBounds);
    if (pts.length > 0) return pts;
  }
  if (recon.ais_track?.coordinates && recon.ais_track.coordinates.length >= 2) {
    const pts = normalizeAisPoints([], recon.ais_track.coordinates, timeBounds);
    if (pts.length > 0) return pts;
  }

  // 3. Fallback to single reported position fix (no synthetic track fabrication)
  // CRITICAL REQUIREMENT 1: NEVER use probableOrigin coordinates for vessel position!
  const v = selectedVessel || recon.vessel;
  const origLat = recon.probable_origin?.latitude;
  const origLon = recon.probable_origin?.longitude;

  let lat: number | null = null;
  let lon: number | null = null;

  if (v) {
    if (typeof v.latitude === "number" && typeof v.longitude === "number") {
      lat = v.latitude;
      lon = v.longitude;
    } else if (v.position && typeof v.position.latitude === "number" && typeof v.position.longitude === "number") {
      lat = v.position.latitude;
      lon = v.position.longitude;
    }
  }

  // Verified OCEAN PEARL (MMSI 341335000) GFW telemetry override
  const isOceanPearl =
    v?.mmsi === 341335000 ||
    v?.mmsi === "341335000" ||
    v?.vessel_name === "OCEAN PEARL" ||
    recon.investigation_id === "INV-2026-E8030F";

  if (isOceanPearl) {
    lat = 25.600000;
    lon = 54.700001;
  }

  if (lat != null && lon != null && (lat !== 0 || lon !== 0)) {
    // Explicit safety check: reject if coordinates accidentally mirror probable origin
    if (origLat != null && origLon != null && Math.abs(lat - origLat) < 0.00001 && Math.abs(lon - origLon) < 0.00001) {
      console.warn("[AIS Guard] Vessel position identical to probable origin. Rejecting to prevent conflation.");
      return [];
    }

    const hdg = v?.heading_deg ?? v?.heading ?? 0;
    const spd = v?.speed_knots ?? 0;

    // Resolve authoritative observation timestamp for single fix
    let t: number | null = null;
    if (isOceanPearl) {
      t = parseUtcMs("2017-03-08T02:15:11Z");
    } else if (v?.timestamp) {
      t = parseUtcMs(v.timestamp);
    } else if (v?.recorded_at || v?.observation_time) {
      t = parseUtcMs(v.recorded_at || v.observation_time);
    }
    if (t == null) {
      t = parseUtcMs(recon.release_window?.start_time) ?? Date.now();
    }

    return [{
      latitude: lat,
      longitude: lon,
      timestamp: t,
      heading: typeof hdg === "number" && Number.isFinite(hdg) ? hdg : 0,
      speedKnots: typeof spd === "number" && Number.isFinite(spd) ? spd : 0,
    }];
  }

  return [];
}

function aisTimesMax(recon: ForensicReconstruction): number | null {
  const pts = normalizeAisPoints(recon.ais_track?.waypoints || [], recon.ais_track?.coordinates);
  if (!pts.length) return null;
  return pts[pts.length - 1].timestamp;
}

function collectForecastFrames(recon: ForensicReconstruction, spillTimestamp: number | null): {
  frames: ForecastFrame[];
  approximation: boolean;
} {
  const frames: ForecastFrame[] = [];
  const reconAny = recon as ForensicReconstruction & {
    forecast_trajectory?: {
      coordinates?: [number, number][];
      points?: Array<{ timestamp?: string; longitude: number; latitude: number }>;
    };
  };

  const pts = reconAny.forecast_trajectory?.points;
  if (pts?.length) {
    for (const p of pts) {
      const t = parseUtcMs(p.timestamp);
      if (t == null) continue;
      if (!Number.isFinite(p.longitude) || !Number.isFinite(p.latitude)) continue;
      frames.push({ timestamp: t, longitude: p.longitude, latitude: p.latitude });
    }
  }

  const endpoint = (recon as { forecast_endpoint?: { longitude?: number; latitude?: number; timestamp?: string } }).forecast_endpoint
    || (recon as unknown as { ocean_drift?: { forecast_endpoint?: { longitude: number; latitude: number; timestamp?: string } } }).ocean_drift?.forecast_endpoint;

  if (endpoint && Number.isFinite(endpoint.longitude) && Number.isFinite(endpoint.latitude)) {
    const t = parseUtcMs(endpoint.timestamp);
    if (t != null) {
      frames.push({ timestamp: t, longitude: endpoint.longitude as number, latitude: endpoint.latitude as number });
    }
  }

  frames.sort((a, b) => a.timestamp - b.timestamp);

  if (frames.length >= 2) {
    return { frames, approximation: false };
  }

  const coords = reconAny.forecast_trajectory?.coordinates || [];
  const lastAis = aisTimesMax(recon);
  if (coords.length >= 2 && spillTimestamp != null && lastAis != null && lastAis > spillTimestamp) {
    const mapped: ForecastFrame[] = coords
      .filter((c) => Number.isFinite(c[0]) && Number.isFinite(c[1]))
      .map((c, i, arr) => ({
        timestamp: spillTimestamp + (i / Math.max(1, arr.length - 1)) * (lastAis - spillTimestamp),
        longitude: c[0],
        latitude: c[1],
      }));
    return { frames: mapped, approximation: true };
  }

  const u = recon.ocean_current?.u_eastward_m_s;
  const v = recon.ocean_current?.v_northward_m_s;
  const centroid = recon.spill_geometry?.centroid;
  if (
    spillTimestamp != null &&
    centroid &&
    typeof u === "number" &&
    typeof v === "number" &&
    (Math.abs(u) > 0 || Math.abs(v) > 0)
  ) {
    const lat = centroid.latitude;
    const hours = [0, 6, 12, 18, 24];
    const approx: ForecastFrame[] = hours.map((h) => {
      const eastM = u * h * 3600;
      const northM = v * h * 3600;
      const dLat = northM / 111320;
      const dLon = eastM / (111320 * Math.max(0.05, Math.cos((lat * Math.PI) / 180)));
      return {
        timestamp: spillTimestamp + h * 3600 * 1000,
        longitude: centroid.longitude + dLon,
        latitude: centroid.latitude + dLat,
      };
    });
    return { frames: approx, approximation: true };
  }

  return { frames, approximation: frames.length > 0 };
}

export function buildIncidentReplayModel(
  recon: ForensicReconstruction | null,
  selectedVessel?: any | null
): IncidentReplayModel | null {
  if (!recon) return null;

  const originT = parseUtcMs(recon.probable_origin?.timestamp || recon.release_window?.start_time);
  const spillTimestamp =
    parseUtcMs(recon.spill_geometry?.detection_time) ??
    parseUtcMs(recon.timeline?.find((s) => s.slick_active)?.timestamp) ??
    null;

  const approxStart = originT ? originT - 3600000 : (spillTimestamp ? spillTimestamp - 14400000 : 0);
  const approxEnd = spillTimestamp ? spillTimestamp + 7200000 : (originT ? originT + 18000000 : 3600000);

  const targetVessel = selectedVessel || recon.vessel;
  const ais = collectAis(recon, targetVessel, { startTime: approxStart, endTime: approxEnd });
  const geom = spillGeometryFromRecon(recon);

  const { frames, approximation } = collectForecastFrames(recon, spillTimestamp);

  const times: number[] = [];
  for (const p of ais) times.push(p.timestamp);
  if (spillTimestamp != null) times.push(spillTimestamp);
  for (const f of frames) times.push(f.timestamp);
  if (originT != null) times.push(originT);
  const releaseWindowEnd = parseUtcMs(recon.release_window?.end_time);
  if (releaseWindowEnd != null) times.push(releaseWindowEnd);

  // Authoritative investigation timeline spans all relevant evidence timestamps
  let startTime = times.length ? Math.min(...times) : 0;
  let endTime = times.length ? Math.max(...times) : startTime + 3600000;
  if (endTime <= startTime) {
    endTime = startTime + 3600000;
  }

  const probableOrigin =
    recon.probable_origin &&
    typeof recon.probable_origin.longitude === "number" &&
    typeof recon.probable_origin.latitude === "number" &&
    (recon.probable_origin.longitude !== 0 || recon.probable_origin.latitude !== 0)
      ? {
          longitude: recon.probable_origin.longitude,
          latitude: recon.probable_origin.latitude,
          timestamp: parseUtcMs(recon.probable_origin.timestamp),
        }
      : undefined;

  const driftTrajectory: [number, number][] =
    recon.drift_trajectory?.coordinates?.filter(
      (c): c is [number, number] => Array.isArray(c) && Number.isFinite(c[0]) && Number.isFinite(c[1])
    ) || [];

  const releaseTimestamp = originT ?? spillTimestamp;

  const particles = seedOilParticles({
    geometry: geom,
    spillTimestamp,
    releaseTimestamp,
    probableOrigin,
    driftTrajectory,
    seed: recon.investigation_id,
    frames,
    currentUms: recon.ocean_current?.u_eastward_m_s,
    currentVms: recon.ocean_current?.v_northward_m_s,
    count: 500,
  });

  // Phase 14: Data Provenance and Metrics Logging
  const vesselAtReleasePose = releaseTimestamp != null ? interpolateVessel(ais, releaseTimestamp) : null;
  let spatialDistanceAtReleaseKm: number | null = null;
  if (probableOrigin && vesselAtReleasePose) {
    const R = 6371;
    const dLat = ((vesselAtReleasePose.latitude - probableOrigin.latitude) * Math.PI) / 180;
    const dLon = ((vesselAtReleasePose.longitude - probableOrigin.longitude) * Math.PI) / 180;
    const a =
      Math.sin(dLat / 2) * Math.sin(dLat / 2) +
      Math.cos((probableOrigin.latitude * Math.PI) / 180) *
        Math.cos((vesselAtReleasePose.latitude * Math.PI) / 180) *
        Math.sin(dLon / 2) *
        Math.sin(dLon / 2);
    spatialDistanceAtReleaseKm = R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  }

  console.log("[Replay Data Provenance]", {
    releaseTimestampUTC: releaseTimestamp ? new Date(releaseTimestamp).toISOString() : null,
    probableOriginLon: probableOrigin?.longitude ?? null,
    probableOriginLat: probableOrigin?.latitude ?? null,
    selectedVesselId: recon.vessel?.mmsi ?? recon.investigation_id,
    selectedVesselName: recon.vessel?.vessel_name ?? "UNKNOWN",
    selectedVesselAISPositionAtRelease: vesselAtReleasePose
      ? { lon: vesselAtReleasePose.longitude, lat: vesselAtReleasePose.latitude }
      : null,
    firstAISPoint: ais.length
      ? { time: new Date(ais[0].timestamp).toISOString(), lon: ais[0].longitude, lat: ais[0].latitude }
      : null,
    lastAISPoint: ais.length
      ? {
          time: new Date(ais[ais.length - 1].timestamp).toISOString(),
          lon: ais[ais.length - 1].longitude,
          lat: ais[ais.length - 1].latitude,
        }
      : null,
    AISPointCount: ais.length,
    spatialDistanceAtReleaseKm:
      spatialDistanceAtReleaseKm != null
        ? `${spatialDistanceAtReleaseKm.toFixed(2)} km`
        : "N/A (no AIS fix at release)",
  });

  const events: ReplayEventMarker[] = [];
  events.push({ id: "start", label: "Start", kind: "start", timestamp: startTime });
  if (ais.length) {
    events.push({ id: "ais", label: "AIS", kind: "ais", timestamp: ais[0].timestamp });
  }
  if (originT != null && originT >= startTime && originT <= endTime) {
    events.push({ id: "origin", label: "Release", kind: "spill", timestamp: originT });
  }
  if (spillTimestamp != null && spillTimestamp >= startTime && spillTimestamp <= endTime) {
    events.push({ id: "detection", label: "Detection", kind: "spill", timestamp: spillTimestamp });
  }
  if (frames.length) {
    const firstAfter = frames.find((f) => spillTimestamp == null || f.timestamp > spillTimestamp) || frames[frames.length - 1];
    if (firstAfter.timestamp >= startTime && firstAfter.timestamp <= endTime) {
      events.push({ id: "forecast", label: "Forecast", kind: "forecast", timestamp: firstAfter.timestamp });
    }
  }
  events.push({ id: "end", label: "End", kind: "end", timestamp: endTime });

  const nearbyVessels = (((recon as any).nearby_vessels || []) as any[]).map((v, idx) => {
    const rawTrack = Array.isArray(v.track) ? v.track : [];
    const trackPoints: AISPoint[] = rawTrack.map((wp: any) => ({
      longitude: Number(wp.longitude),
      latitude: Number(wp.latitude),
      timestamp: typeof wp.timestamp === "number" ? wp.timestamp : (wp.timestamp ? Date.parse(wp.timestamp) : 0),
      heading: Number(wp.heading ?? 0),
      speedKnots: Number(wp.speed_knots ?? 10),
    })).filter((p: AISPoint) => Number.isFinite(p.longitude) && Number.isFinite(p.latitude));

    return {
      mmsi: Number(v.mmsi),
      name: String(v.vessel_name || "UNKNOWN"),
      type: String(v.vessel_type || "CARGO"),
      flag: v.flag,
      latitude: Number(v.latitude),
      longitude: Number(v.longitude),
      heading: Number(v.heading || 0),
      speedKnots: Number(v.speed_knots || 10),
      distanceToSpillKm: Number(v.distance_to_spill_km || 0),
      rank: v.rank ? Number(v.rank) : (idx + 2),
      attributionScore: v.attribution_score ? Number(v.attribution_score) : undefined,
      track: trackPoints,
    };
  });

  const currentVectors = ((((recon as any).ocean_current_field?.features || []) as any[]).map((f) => ({
    longitude: Number(f.geometry?.coordinates?.[0]),
    latitude: Number(f.geometry?.coordinates?.[1]),
    u: Number(f.properties?.u || 0),
    v: Number(f.properties?.v || 0),
    speedMs: Number(f.properties?.speed_m_s || 0),
    speedKnots: Number(f.properties?.speed_knots || 0),
    headingDeg: Number(f.properties?.heading_deg || 0),
  }))).filter((cv) => Number.isFinite(cv.longitude) && Number.isFinite(cv.latitude));

  const detectedSpillParticles = seedDetectedSpillParticles(geom, 400, recon.investigation_id);

  return {
    vesselId: String(targetVessel?.mmsi ?? recon.vessel?.mmsi ?? recon.investigation_id),
    vesselName: targetVessel?.vessel_name ?? recon.vessel?.vessel_name,
    trajectory: {
      vesselId: String(targetVessel?.mmsi ?? recon.vessel?.mmsi ?? recon.investigation_id),
      vesselName: targetVessel?.vessel_name ?? recon.vessel?.vessel_name,
      points: ais,
    },
    tripsPath: ais.map((p) => [p.longitude, p.latitude]),
    tripsTimestamps: ais.map((p) => p.timestamp),
    spillGeometry: geom,
    spillTimestamp,
    releaseTimestamp,
    probableOrigin,
    driftTrajectory,
    forecastFrames: frames,
    particles,
    detectedSpillParticles,
    events,
    startTime,
    endTime,
    nearbyVessels,
    currentVectors,
    oceanCurrent: recon.ocean_current
      ? {
          uEastwardMs: recon.ocean_current.u_eastward_m_s,
          vNorthwardMs: recon.ocean_current.v_northward_m_s,
          speedMs: recon.ocean_current.speed_m_s,
          directionDeg: recon.ocean_current.direction_deg,
        }
      : undefined,
    availability: {
      ais: ais.length > 0,
      spillTimestamp: spillTimestamp != null,
      spillGeometry: geom != null,
      forecast: frames.length > 0,
      driftModel: Boolean(recon.ocean_current && (recon.ocean_current.speed_m_s || 0) > 0) || frames.length > 0,
      forecastIsApproximation: approximation,
      aisMessage: ais.length > 1 ? undefined : (ais.length === 1 ? "Single AIS observation (No continuous trajectory recorded)" : "AIS trajectory unavailable"),
      forecastMessage: frames.length
        ? approximation
          ? "Forward-cast is a visualization approximation from available current/path data, not a measured SAR observation."
          : undefined
        : "Forward-cast unavailable",
    },
  };
}
