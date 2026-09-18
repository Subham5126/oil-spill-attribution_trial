import type { ForecastFrame, OilParticleSeed } from "./types";
import { bboxOfGeometry, interpolateForecastAnchor, pointInRing } from "./geometry";

function mulberry32(seed: number) {
  let a = seed >>> 0;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function hashString(s: string): number {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

function metersToLonLat(eastM: number, northM: number, lat: number): { dLon: number; dLat: number } {
  const dLat = northM / 111320;
  const dLon = eastM / (111320 * Math.max(0.05, Math.cos((lat * Math.PI) / 180)));
  return { dLon, dLat };
}

export function samplePointsInGeometry(
  geom: GeoJSON.Polygon | GeoJSON.MultiPolygon,
  targetCount: number,
  rng: () => number
): Array<{ lon: number; lat: number }> {
  const bbox = bboxOfGeometry(geom);
  if (!bbox) return [];
  const [minLon, minLat, maxLon, maxLat] = bbox;

  type PolyRings = { outer: number[][]; holes: number[][][] };
  const polys: PolyRings[] = [];

  if (geom.type === "Polygon") {
    if (geom.coordinates.length > 0 && geom.coordinates[0].length >= 4) {
      polys.push({ outer: geom.coordinates[0], holes: geom.coordinates.slice(1) });
    }
  } else if (geom.type === "MultiPolygon") {
    for (const poly of geom.coordinates) {
      if (poly.length > 0 && poly[0].length >= 4) {
        polys.push({ outer: poly[0], holes: poly.slice(1) });
      }
    }
  }

  if (polys.length === 0) return [];

  const isInside = (lon: number, lat: number): boolean => {
    for (const p of polys) {
      if (pointInRing(lon, lat, p.outer)) {
        let inHole = false;
        for (const h of p.holes) {
          if (pointInRing(lon, lat, h)) {
            inHole = true;
            break;
          }
        }
        if (!inHole) return true;
      }
    }
    return false;
  };

  const sampled: Array<{ lon: number; lat: number }> = [];
  let attempts = 0;
  const maxAttempts = targetCount * 80;

  // Rejection sampling strictly inside authoritative detected slick polygon
  while (sampled.length < targetCount && attempts < maxAttempts) {
    attempts++;
    const lon = minLon + rng() * (maxLon - minLon);
    const lat = minLat + rng() * (maxLat - minLat);
    if (isInside(lon, lat)) {
      sampled.push({ lon, lat });
    }
  }

  // If rejection sampling needed more points (e.g. narrow slivers)
  if (sampled.length < targetCount && sampled.length > 0) {
    const existing = [...sampled];
    let idx = 0;
    while (sampled.length < targetCount) {
      const base = existing[idx % existing.length];
      idx++;
      const jLon = (rng() - 0.5) * (maxLon - minLon) * 0.04;
      const jLat = (rng() - 0.5) * (maxLat - minLat) * 0.04;
      const cLon = base.lon + jLon;
      const cLat = base.lat + jLat;
      if (isInside(cLon, cLat)) {
        sampled.push({ lon: cLon, lat: cLat });
      } else {
        sampled.push({ lon: base.lon, lat: base.lat });
      }
    }
  }

  return sampled;
}

export function seedOilParticles(options: {
  geometry: GeoJSON.Polygon | GeoJSON.MultiPolygon | null;
  spillTimestamp: number | null;
  releaseTimestamp?: number | null;
  probableOrigin?: { longitude: number; latitude: number; timestamp?: number | null };
  driftTrajectory?: [number, number][];
  count?: number;
  seed?: string | number;
  frames?: ForecastFrame[];
  currentUms?: number;
  currentVms?: number;
  lifetimeMs?: number;
}): OilParticleSeed[] {
  const { geometry, spillTimestamp, releaseTimestamp, probableOrigin, driftTrajectory } = options;
  const emissionStart = releaseTimestamp ?? spillTimestamp;
  if (emissionStart == null) return [];

  // Target: hundreds of particles (300 to 1000, default 500)
  const count = Math.min(1000, Math.max(300, options.count ?? 500));
  const rng = mulberry32(typeof options.seed === "number" ? options.seed : hashString(String(options.seed ?? "oiltrace")));

  let velLon = 0;
  let velLat = 0;
  const originAnchor = interpolateForecastAnchor(options.frames || [], spillTimestamp ?? emissionStart);
  const laterAnchor = interpolateForecastAnchor(options.frames || [], (spillTimestamp ?? emissionStart) + 60 * 60 * 1000);
  if (originAnchor && laterAnchor) {
    velLon = (laterAnchor.longitude - originAnchor.longitude) / (60 * 60 * 1000);
    velLat = (laterAnchor.latitude - originAnchor.latitude) / (60 * 60 * 1000);
  } else if (typeof options.currentUms === "number" && typeof options.currentVms === "number") {
    const latRef = probableOrigin?.latitude ?? 25.5;
    const d = metersToLonLat(options.currentUms, options.currentVms, latRef);
    velLon = d.dLon / 1000;
    velLat = d.dLat / 1000;
  }

  const rawDuration = Math.max(
    15 * 60 * 1000,
    spillTimestamp != null && emissionStart != null && spillTimestamp > emissionStart
      ? spillTimestamp - emissionStart
      : 18.5 * 3600 * 1000
  );
  const lifetimeMs = Math.max(
    options.lifetimeMs ?? 36 * 60 * 60 * 1000,
    rawDuration + 72 * 60 * 60 * 1000
  );

  // Dynamic oil transport palette: bright cyan / electric blue (#00D9FF)
  const dynamicOilCyanShades = [
    "#00d9ff", // electric cyan (primary)
    "#22d3ee", // cyan-400
    "#38bdf8", // sky-400
    "#00f0ff", // vivid cyan
    "#67e8f9", // bright cyan-300
  ];

  // MODE A: Hydrodynamic Drift along driftTrajectory starting from Probable Origin
  if (probableOrigin && driftTrajectory && driftTrajectory.length >= 2) {
    const duration = rawDuration;
    const emissionWindow = Math.min(90 * 60 * 1000, duration * 0.15);
    const particles: OilParticleSeed[] = [];

    // Sample targets from authoritative detected slick geometry using rejection sampling
    const targetPoints = geometry ? samplePointsInGeometry(geometry, count, rng) : [];
    const lastCoord = driftTrajectory[driftTrajectory.length - 1];

    for (let i = 0; i < count; i++) {
      // Anchor initial particles directly at emissionStart
      const birthFraction = i / Math.max(1, count - 1);
      const birthTime = i === 0 ? emissionStart : emissionStart + birthFraction * emissionWindow * (0.85 + rng() * 0.3);

      // Target position inside authoritative detected slick polygon
      const target = targetPoints[i % Math.max(1, targetPoints.length)] || {
        lon: lastCoord[0] + (rng() - 0.5) * 0.01,
        lat: lastCoord[1] + (rng() - 0.5) * 0.01,
      };

      // Release dispersion jitter (compact cluster at probable origin)
      const jLon = (rng() - 0.5) * 0.0035;
      const jLat = (rng() - 0.5) * 0.0035;
      const color = dynamicOilCyanShades[Math.floor(rng() * dynamicOilCyanShades.length)];

      particles.push({
        id: i,
        birthTime,
        longitude: probableOrigin.longitude,
        latitude: probableOrigin.latitude,
        velocityLonPerMs: velLon * (0.85 + rng() * 0.3),
        velocityLatPerMs: velLat * (0.85 + rng() * 0.3),
        lifetimeMs,
        size: 1.2 + rng() * 1.3, // Very small: 1.2px - 2.5px
        opacity: 0.55 + rng() * 0.40, // Subtle opacity variation: 0.55 - 0.95
        color,
        path: driftTrajectory,
        driftDurationMs: duration,
        jitterLon: jLon,
        jitterLat: jLat,
        targetLon: target.lon,
        targetLat: target.lat,
        forecastFrames: options.frames,
      });
    }
    return particles;
  }

  // MODE B: Classical Polygon Interior Seeding (fallback & unit tests)
  if (!geometry) return [];
  const targetPoints = samplePointsInGeometry(geometry, count, rng);
  if (targetPoints.length === 0) return [];

  const emissionWindow = 12 * 60 * 1000;
  const particles: OilParticleSeed[] = [];
  for (let i = 0; i < count; i++) {
    const pt = targetPoints[i % targetPoints.length];
    const jitter = (rng() - 0.5) * 0.25;
    const color = dynamicOilCyanShades[Math.floor(rng() * dynamicOilCyanShades.length)];
    particles.push({
      id: i,
      birthTime: emissionStart + rng() * emissionWindow,
      longitude: pt.lon,
      latitude: pt.lat,
      velocityLonPerMs: velLon * (0.85 + rng() * 0.3),
      velocityLatPerMs: velLat * (0.85 + rng() * 0.3) + jitter * velLat,
      lifetimeMs,
      size: 1.2 + rng() * 1.3,
      opacity: 0.55 + rng() * 0.40,
      color,
      targetLon: pt.lon,
      targetLat: pt.lat,
      forecastFrames: options.frames,
    });
  }

  return particles;
}

const COLOR_CYAN: [number, number, number] = [0, 217, 255];     // #00d9ff bright cyan
const COLOR_BLUE: [number, number, number] = [37, 99, 235];     // #2563eb ocean blue
const COLOR_RED: [number, number, number] = [225, 29, 72];      // #e11d48 slick red
const COLOR_ORANGE: [number, number, number] = [249, 115, 22];  // #f97316 warm orange
const COLOR_YELLOW: [number, number, number] = [250, 204, 21];  // #facc15 bright yellow

function lerpColor(c1: [number, number, number], c2: [number, number, number], t: number): string {
  const clampT = Math.max(0, Math.min(1, t));
  const r = Math.round(c1[0] + (c2[0] - c1[0]) * clampT);
  const g = Math.round(c1[1] + (c2[1] - c1[1]) * clampT);
  const b = Math.round(c1[2] + (c2[2] - c1[2]) * clampT);
  return `rgb(${r},${g},${b})`;
}

/**
 * Computes deterministic, reversible particle color based on normalized journey progression.
 * Progression stages:
 *   u in [0.0, 0.55):  bright cyan
 *   u in [0.55, 0.82): cyan -> ocean blue
 *   u in [0.82, 1.0]:  ocean blue -> detected slick red
 *   excess into forecast:
 *   excessRatio in [0.0, 0.45): red -> warm orange
 *   excessRatio in [0.45, 1.0]: orange -> bright yellow
 */
export function computeParticleColor(
  ageMs: number,
  driftDurationMs: number,
  particleId: number,
  forecastWindowMs = 24 * 3600 * 1000
): string {
  // Deterministic per-particle phase variation so particles transition individually and naturally
  const jitter = (((particleId * 17) % 23) - 11) / 250; // -0.044 to +0.044

  if (driftDurationMs <= 0) {
    return "#00d9ff";
  }

  const rawU = ageMs / driftDurationMs;
  const u = Math.max(0, rawU + jitter);

  // Phase 1: Hindcast drift toward detected slick (u <= 1.0)
  if (u < 0.55) {
    // Early hindcast: bright cyan
    return "#00d9ff";
  }
  if (u < 0.82) {
    // Approaching slick: cyan -> ocean blue
    const t = (u - 0.55) / (0.82 - 0.55);
    return lerpColor(COLOR_CYAN, COLOR_BLUE, t);
  }
  if (u <= 1.0) {
    // Entering detected slick: ocean blue -> detected slick red
    const t = (u - 0.82) / (1.0 - 0.82);
    return lerpColor(COLOR_BLUE, COLOR_RED, t);
  }

  // Phase 2: Excess into forecast beyond detection (u > 1.0)
  const excessMs = ageMs - driftDurationMs;
  const rawExcessRatio = Math.max(0, excessMs / Math.max(3600000, forecastWindowMs));
  const excessRatio = Math.min(1.0, Math.max(0, rawExcessRatio + jitter));

  if (excessRatio < 0.45) {
    // Transitioning from detected slick red -> warm orange
    const t = excessRatio / 0.45;
    return lerpColor(COLOR_RED, COLOR_ORANGE, t);
  } else {
    // Forecast advection: warm orange -> bright yellow
    const t = (excessRatio - 0.45) / (1.0 - 0.45);
    return lerpColor(COLOR_ORANGE, COLOR_YELLOW, t);
  }
}

/**
 * Seeds static RED evidence particles strictly inside the detected slick geometry.
 * Preserves the exact detected slick shape with red particles (1.2px - 2.5px).
 */
export function seedDetectedSpillParticles(
  geometry: GeoJSON.Polygon | GeoJSON.MultiPolygon | null,
  count = 400,
  seed: string | number = "detected-slick-red"
): VisibleParticle[] {
  if (!geometry) return [];
  const rng = mulberry32(typeof seed === "number" ? seed : hashString(String(seed)));
  const pts = samplePointsInGeometry(geometry, count, rng);
  const redShades = [
    "#e11d48", // rose-600
    "#f43f5e", // rose-500
    "#fb7185", // rose-400
    "#be123c", // rose-700
    "#ff2a55", // vivid bright red
  ];
  return pts.map((p, idx) => ({
    id: idx + 10000,
    longitude: p.lon,
    latitude: p.lat,
    size: 1.2 + rng() * 1.3,
    opacity: 0.65 + rng() * 0.30,
    color: redShades[Math.floor(rng() * redShades.length)],
  }));
}

export type VisibleParticle = {
  id: number;
  longitude: number;
  latitude: number;
  size: number;
  opacity: number;
  color: string;
};

export function particlesAtTime(
  seeds: OilParticleSeed[],
  currentTime: number,
  spillTimestamp: number | null
): VisibleParticle[] {
  if (!seeds || seeds.length === 0) return [];

  const out: VisibleParticle[] = [];
  for (const p of seeds) {
    if (currentTime < p.birthTime) continue;
    const age = currentTime - p.birthTime;
    if (age > p.lifetimeMs) continue;

    const fade = Math.max(0, 1 - age / p.lifetimeMs);

    // Mode A: Hydrodynamic Trajectory Flow
    if (p.path && p.path.length >= 2 && p.driftDurationMs && p.driftDurationMs > 0) {
      const progress = Math.min(1.0, age / p.driftDurationMs);
      const indexFloat = progress * (p.path.length - 1);
      const i0 = Math.floor(indexFloat);
      const i1 = Math.min(p.path.length - 1, i0 + 1);
      const frac = indexFloat - i0;

      const anchorLon = p.path[i0][0] + (p.path[i1][0] - p.path[i0][0]) * frac;
      const anchorLat = p.path[i0][1] + (p.path[i1][1] - p.path[i0][1]) * frac;

      let lon: number;
      let lat: number;

      if (p.targetLon != null && p.targetLat != null) {
        // Continuous transition into detected slick shape
        const lastCoord = p.path[p.path.length - 1];
        const targetDeltaLon = p.targetLon - lastCoord[0];
        const targetDeltaLat = p.targetLat - lastCoord[1];

        // Smooth cubic Hermite interpolation between initial dispersion and exact slick shape
        const s = progress * progress * (3 - 2 * progress);
        const curOffsetLon = (1 - s) * (p.jitterLon ?? 0) + s * targetDeltaLon;
        const curOffsetLat = (1 - s) * (p.jitterLat ?? 0) + s * targetDeltaLat;

        lon = anchorLon + curOffsetLon;
        lat = anchorLat + curOffsetLat;
      } else {
        const spreadScale = 0.5 + 1.2 * progress;
        lon = anchorLon + (p.jitterLon ?? 0) * spreadScale;
        lat = anchorLat + (p.jitterLat ?? 0) * spreadScale;
      }

      // After detection T0, particles continue into forecast advection
      if (age > p.driftDurationMs) {
        const excessMs = age - p.driftDurationMs;
        if (p.forecastFrames && p.forecastFrames.length >= 2) {
          const t0 = p.birthTime + p.driftDurationMs;
          const tNow = t0 + excessMs;
          const anchor0 = interpolateForecastAnchor(p.forecastFrames, t0) ?? p.forecastFrames[0];
          const anchorNow = interpolateForecastAnchor(p.forecastFrames, tNow);
          if (anchor0 && anchorNow) {
            const scale = 0.9 + 0.2 * ((p.id % 10) / 10);
            lon += (anchorNow.longitude - anchor0.longitude) * scale;
            lat += (anchorNow.latitude - anchor0.latitude) * scale;
          } else {
            lon += p.velocityLonPerMs * excessMs;
            lat += p.velocityLatPerMs * excessMs;
          }
        } else {
          lon += p.velocityLonPerMs * excessMs;
          lat += p.velocityLatPerMs * excessMs;
        }
      }

      const dynamicColor = computeParticleColor(age, p.driftDurationMs, p.id);

      out.push({
        id: p.id,
        longitude: lon,
        latitude: lat,
        size: p.size,
        opacity: Math.max(0.25, p.opacity * (0.7 + 0.3 * fade)),
        color: dynamicColor,
      });
    } else {
      // Mode B: Classical velocity advection (fallback / tests)
      if (spillTimestamp != null && currentTime < spillTimestamp) continue;

      const duration = spillTimestamp != null && p.birthTime < spillTimestamp ? Math.max(1, spillTimestamp - p.birthTime) : 18 * 3600 * 1000;
      const dynamicColor = computeParticleColor(age, duration, p.id);

      out.push({
        id: p.id,
        longitude: p.longitude + p.velocityLonPerMs * age,
        latitude: p.latitude + p.velocityLatPerMs * age,
        size: p.size,
        opacity: Math.max(0.20, p.opacity * (0.5 + 0.5 * fade)),
        color: dynamicColor,
      });
    }
  }
  return out;
}
