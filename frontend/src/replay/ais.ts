import type { AISPoint, VesselPose, VesselTrajectory } from "./types";
import { parseUtcMs } from "./time";

const MAX_LON = 180;
const MAX_LAT = 90;

export function isValidLongitude(lon: unknown): lon is number {
  return typeof lon === "number" && Number.isFinite(lon) && lon >= -MAX_LON && lon <= MAX_LON;
}

export function isValidLatitude(lat: unknown): lat is number {
  return typeof lat === "number" && Number.isFinite(lat) && lat >= -MAX_LAT && lat <= MAX_LAT;
}

export function normalizeAisPoints(
  raw: Array<{
    longitude?: number;
    latitude?: number;
    lon?: number;
    lat?: number;
    timestamp?: string | number;
    heading?: number;
    heading_deg?: number;
    speed_knots?: number;
  }>,
  fallbackCoordinates?: [number, number][],
  timeBounds?: { startTime: number; endTime: number }
): AISPoint[] {
  const points: AISPoint[] = [];

  for (const wp of raw) {
    const lon = wp.longitude ?? wp.lon;
    const lat = wp.latitude ?? wp.lat;
    if (!isValidLongitude(lon) || !isValidLatitude(lat)) continue;
    const timestamp = parseUtcMs(wp.timestamp ?? null);
    if (timestamp == null) continue;
    const heading = typeof wp.heading === "number" ? wp.heading : wp.heading_deg;
    points.push({
      longitude: lon,
      latitude: lat,
      timestamp,
      heading: typeof heading === "number" && Number.isFinite(heading) ? heading : undefined,
      speedKnots: typeof wp.speed_knots === "number" && Number.isFinite(wp.speed_knots) ? wp.speed_knots : undefined,
    });
  }

  if (points.length === 0 && fallbackCoordinates && fallbackCoordinates.length > 0) {
    const validCoords = fallbackCoordinates.filter(
      (c) => Array.isArray(c) && isValidLongitude(c[0]) && isValidLatitude(c[1])
    );
    const startMs = timeBounds ? timeBounds.startTime : 0;
    const endMs = timeBounds ? timeBounds.endTime : Math.max(1000, validCoords.length * 1000);
    const span = Math.max(1000, endMs - startMs);

    for (let i = 0; i < validCoords.length; i++) {
      points.push({
        longitude: validCoords[i][0],
        latitude: validCoords[i][1],
        timestamp: startMs + (i / Math.max(1, validCoords.length - 1)) * span,
      });
    }
  }

  points.sort((a, b) => a.timestamp - b.timestamp);

  const deduped: AISPoint[] = [];
  for (const p of points) {
    const prev = deduped[deduped.length - 1];
    if (prev && prev.timestamp === p.timestamp) {
      deduped[deduped.length - 1] = p;
      continue;
    }
    if (
      prev &&
      prev.longitude === p.longitude &&
      prev.latitude === p.latitude &&
      Math.abs(p.timestamp - prev.timestamp) < 1
    ) {
      continue;
    }
    deduped.push(p);
  }
  return deduped;
}

export function bearingDegrees(lon1: number, lat1: number, lon2: number, lat2: number): number {
  const dLon = ((lon2 - lon1) * Math.PI) / 180;
  const lat1Rad = (lat1 * Math.PI) / 180;
  const lat2Rad = (lat2 * Math.PI) / 180;
  const y = Math.sin(dLon) * Math.cos(lat2Rad);
  const x = Math.cos(lat1Rad) * Math.sin(lat2Rad) - Math.sin(lat1Rad) * Math.cos(lat2Rad) * Math.cos(dLon);
  return ((Math.atan2(y, x) * 180) / Math.PI + 360) % 360;
}

export function interpolateVessel(points: AISPoint[], timeMs: number): VesselPose | null {
  if (!points || !points.length) return null;

  // Defensive Case N == 1: Single AIS observation fix
  if (points.length === 1) {
    return {
      longitude: points[0].longitude,
      latitude: points[0].latitude,
      heading: points[0].heading ?? 0,
    };
  }

  // Defensive Case N >= 2: Multi-point AIS trajectory
  if (timeMs <= points[0].timestamp) {
    return {
      longitude: points[0].longitude,
      latitude: points[0].latitude,
      heading: points[0].heading ?? bearingDegrees(points[0].longitude, points[0].latitude, points[1].longitude, points[1].latitude),
    };
  }
  const last = points[points.length - 1];
  if (timeMs >= last.timestamp) {
    const prev = points[points.length - 2];
    return {
      longitude: last.longitude,
      latitude: last.latitude,
      heading: last.heading ?? bearingDegrees(prev.longitude, prev.latitude, last.longitude, last.latitude),
    };
  }
  for (let i = 0; i < points.length - 1; i++) {
    const a = points[i];
    const b = points[i + 1];
    if (timeMs >= a.timestamp && timeMs <= b.timestamp) {
      const dt = Math.max(1, b.timestamp - a.timestamp);
      const alpha = (timeMs - a.timestamp) / dt;
      return {
        longitude: a.longitude + alpha * (b.longitude - a.longitude),
        latitude: a.latitude + alpha * (b.latitude - a.latitude),
        heading: bearingDegrees(a.longitude, a.latitude, b.longitude, b.latitude),
      };
    }
  }
  return {
    longitude: last.longitude,
    latitude: last.latitude,
    heading: last.heading ?? 0,
  };
}

export function splitTrack(points: AISPoint[], timeMs: number): {
  traversed: [number, number][];
  future: [number, number][];
} {
  if (!points || !points.length) return { traversed: [], future: [] };
  // Requirement 5: No synthetic line for single-point fix (N <= 1)
  if (points.length <= 1) {
    return { traversed: [], future: [] };
  }
  const pose = interpolateVessel(points, timeMs);
  if (!pose) return { traversed: [], future: [] };
  if (timeMs <= points[0].timestamp) {
    return { traversed: [], future: points.map((p) => [p.longitude, p.latitude]) };
  }
  if (timeMs >= points[points.length - 1].timestamp) {
    return { traversed: points.map((p) => [p.longitude, p.latitude]), future: [] };
  }
  for (let i = 0; i < points.length - 1; i++) {
    const a = points[i];
    const b = points[i + 1];
    if (timeMs >= a.timestamp && timeMs <= b.timestamp) {
      return {
        traversed: [...points.slice(0, i + 1).map((p): [number, number] => [p.longitude, p.latitude]), [pose.longitude, pose.latitude]],
        future: [[pose.longitude, pose.latitude], ...points.slice(i + 1).map((p): [number, number] => [p.longitude, p.latitude])],
      };
    }
  }
  return { traversed: points.map((p) => [p.longitude, p.latitude]), future: [] };
}

export function toTripsLayerData(trajectory: VesselTrajectory) {
  return {
    path: trajectory.points.map((p): [number, number] => [p.longitude, p.latitude]),
    timestamps: trajectory.points.map((p) => p.timestamp),
  };
}

export function aisSegmentDurationRatios(points: AISPoint[]): number[] {
  const ratios: number[] = [];
  for (let i = 0; i < points.length - 1; i++) {
    ratios.push(Math.max(0, points[i + 1].timestamp - points[i].timestamp));
  }
  return ratios;
}
