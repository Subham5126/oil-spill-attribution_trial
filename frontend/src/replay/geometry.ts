import type { ForecastFrame } from "./types";

export function isPolygonGeometry(
  geom: GeoJSON.Geometry | null | undefined
): geom is GeoJSON.Polygon | GeoJSON.MultiPolygon {
  return geom?.type === "Polygon" || geom?.type === "MultiPolygon";
}

export function detectedSpillVisible(currentTime: number, spillTimestamp: number | null): boolean {
  if (spillTimestamp == null || !Number.isFinite(spillTimestamp)) return false;
  return currentTime >= spillTimestamp;
}

export function translatePolygon(
  geom: GeoJSON.Polygon | GeoJSON.MultiPolygon,
  dLon: number,
  dLat: number
): GeoJSON.Polygon | GeoJSON.MultiPolygon {
  const shiftPos = (pos: number[]): number[] => [pos[0] + dLon, pos[1] + dLat];
  if (geom.type === "Polygon") {
    return {
      type: "Polygon",
      coordinates: geom.coordinates.map((ring) => ring.map(shiftPos)),
    };
  }
  return {
    type: "MultiPolygon",
    coordinates: geom.coordinates.map((poly) => poly.map((ring) => ring.map(shiftPos))),
  };
}

function ringCentroid(ring: number[][]): { lon: number; lat: number } | null {
  if (!ring.length) return null;
  let lon = 0;
  let lat = 0;
  let n = 0;
  for (const p of ring) {
    if (p.length < 2 || !Number.isFinite(p[0]) || !Number.isFinite(p[1])) continue;
    lon += p[0];
    lat += p[1];
    n += 1;
  }
  if (!n) return null;
  return { lon: lon / n, lat: lat / n };
}

export function geometryCentroid(geom: GeoJSON.Polygon | GeoJSON.MultiPolygon): { lon: number; lat: number } | null {
  if (geom.type === "Polygon") {
    return ringCentroid(geom.coordinates[0] || []);
  }
  return ringCentroid(geom.coordinates[0]?.[0] || []);
}

export function bboxOfGeometry(geom: GeoJSON.Polygon | GeoJSON.MultiPolygon): [number, number, number, number] | null {
  let minLon = Infinity;
  let minLat = Infinity;
  let maxLon = -Infinity;
  let maxLat = -Infinity;
  const rings = geom.type === "Polygon" ? geom.coordinates : geom.coordinates.flat();
  for (const ring of rings) {
    for (const p of ring) {
      if (p.length < 2) continue;
      minLon = Math.min(minLon, p[0]);
      minLat = Math.min(minLat, p[1]);
      maxLon = Math.max(maxLon, p[0]);
      maxLat = Math.max(maxLat, p[1]);
    }
  }
  if (!Number.isFinite(minLon)) return null;
  return [minLon, minLat, maxLon, maxLat];
}

export function pointInRing(lon: number, lat: number, ring: number[][]): boolean {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const xi = ring[i][0];
    const yi = ring[i][1];
    const xj = ring[j][0];
    const yj = ring[j][1];
    const intersect = yi > lat !== yj > lat && lon < ((xj - xi) * (lat - yi)) / (yj - yi + 1e-12) + xi;
    if (intersect) inside = !inside;
  }
  return inside;
}

export function interpolateForecastAnchor(frames: ForecastFrame[], timeMs: number): ForecastFrame | null {
  if (!frames.length) return null;
  const sorted = [...frames].sort((a, b) => a.timestamp - b.timestamp);
  if (timeMs <= sorted[0].timestamp) return sorted[0];
  const last = sorted[sorted.length - 1];
  if (timeMs >= last.timestamp) return last;
  for (let i = 0; i < sorted.length - 1; i++) {
    const a = sorted[i];
    const b = sorted[i + 1];
    if (timeMs >= a.timestamp && timeMs <= b.timestamp) {
      const dt = Math.max(1, b.timestamp - a.timestamp);
      const alpha = (timeMs - a.timestamp) / dt;
      return {
        timestamp: timeMs,
        longitude: a.longitude + alpha * (b.longitude - a.longitude),
        latitude: a.latitude + alpha * (b.latitude - a.latitude),
        geometry: a.geometry,
      };
    }
  }
  return last;
}

export function forecastGeometryAtTime(
  detected: GeoJSON.Polygon | GeoJSON.MultiPolygon | null,
  frames: ForecastFrame[],
  timeMs: number,
  spillTimestamp: number | null
): GeoJSON.Polygon | GeoJSON.MultiPolygon | null {
  if (!detected || spillTimestamp == null || timeMs < spillTimestamp) return null;
  if (!frames.length) return null;
  const origin = interpolateForecastAnchor(frames, spillTimestamp) ?? frames[0];
  const now = interpolateForecastAnchor(frames, timeMs);
  if (!now) return null;
  const dLon = now.longitude - origin.longitude;
  const dLat = now.latitude - origin.latitude;
  if (now.geometry) return now.geometry;
  return translatePolygon(detected, dLon, dLat);
}

export function nearestForecastFrame(frames: ForecastFrame[], timeMs: number): ForecastFrame | null {
  if (!frames.length) return null;
  let best = frames[0];
  let bestD = Math.abs(frames[0].timestamp - timeMs);
  for (const f of frames) {
    const d = Math.abs(f.timestamp - timeMs);
    if (d < bestD) {
      best = f;
      bestD = d;
    }
  }
  return best;
}

/**
 * Computes a 2D Convex Hull around the current particle cloud using Andrew's Monotone Chain algorithm.
 * Returns a GeoJSON Polygon following the spatial extent of the active particle cloud.
 */
export function computeParticleCloudHull(
  particles: Array<{ longitude: number; latitude: number }>
): GeoJSON.Polygon | null {
  if (!particles || particles.length < 3) return null;

  const pts: Array<[number, number]> = [];
  for (let i = 0; i < particles.length; i++) {
    const p = particles[i];
    if (Number.isFinite(p.longitude) && Number.isFinite(p.latitude)) {
      pts.push([p.longitude, p.latitude]);
    }
  }
  if (pts.length < 3) return null;

  // Sort lexicographically by lon, then lat
  pts.sort((a, b) => (a[0] === b[0] ? a[1] - b[1] : a[0] - b[0]));

  // Deduplicate points within float tolerance
  const uniquePts: Array<[number, number]> = [];
  for (let i = 0; i < pts.length; i++) {
    const curr = pts[i];
    const prev = uniquePts[uniquePts.length - 1];
    if (!prev || Math.abs(curr[0] - prev[0]) > 1e-9 || Math.abs(curr[1] - prev[1]) > 1e-9) {
      uniquePts.push(curr);
    }
  }
  if (uniquePts.length < 3) return null;

  // Cross product of vectors OA and OB
  const cross = (o: [number, number], a: [number, number], b: [number, number]): number =>
    (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);

  // Build lower hull
  const lower: Array<[number, number]> = [];
  for (let i = 0; i < uniquePts.length; i++) {
    const p = uniquePts[i];
    while (lower.length >= 2 && cross(lower[lower.length - 2], lower[lower.length - 1], p) <= 0) {
      lower.pop();
    }
    lower.push(p);
  }

  // Build upper hull
  const upper: Array<[number, number]> = [];
  for (let i = uniquePts.length - 1; i >= 0; i--) {
    const p = uniquePts[i];
    while (upper.length >= 2 && cross(upper[upper.length - 2], upper[upper.length - 1], p) <= 0) {
      upper.pop();
    }
    upper.push(p);
  }

  lower.pop();
  upper.pop();
  const hull = lower.concat(upper);
  if (hull.length < 3) return null;

  // Close ring
  hull.push([hull[0][0], hull[0][1]]);

  return {
    type: "Polygon",
    coordinates: [hull],
  };
}

