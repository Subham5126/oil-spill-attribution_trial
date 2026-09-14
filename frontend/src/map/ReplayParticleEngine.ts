/**
 * ReplayParticleEngine: Browser-friendly physical particle system for forensic oil spill simulation.
 *
 * Implements an authentic continuous hydrocarbon wake trail:
 * 1. Particles emit dynamically behind the vessel's stern during the possible release window.
 * 2. Persistent trail remains visible behind the vessel as the ship continues sailing along its AIS track.
 * 3. Droplets undergo turbulent wake dispersion and advect under Copernicus ocean currents (u, v) and Lagrangian drift.
 * 4. In Stage 5 (80%-95%), droplets align with interior target coordinates within the genuine M3 polygon and smoothly fade out as the real vector slick illuminates.
 * 5. If no vessel is attributed (e.g. North Sea), particles emit at the probable release origin and demonstrate hydrodynamic drift to the M3 slick.
 */

import { ForensicReconstruction } from "../types";

export interface ReplayParticle {
  id: number;
  birthProgress: number; // Replay progress [0, 1] when particle was emitted
  initialLon: number;
  initialLat: number;
  currentLon: number;
  currentLat: number;
  targetSlickLon: number;
  targetSlickLat: number;
  lateralOffsetKm: number;
  baseSize: number;
  baseOpacity: number;
  opacity: number;
  dispersionRate: number;
}

export class ReplayParticleEngine {
  private particles: ReplayParticle[] = [];
  private maxParticles: number;
  private reconstruction: ForensicReconstruction | null = null;

  constructor(maxParticles = 120) {
    this.maxParticles = maxParticles;
    this.initParticles();
  }

  private initParticles() {
    this.particles = [];
    const count = this.maxParticles;

    // Release window is normalized across progress [0.25, 0.45]
    const releaseStart = 0.25;
    const releaseEnd = 0.45;
    const windowSpan = releaseEnd - releaseStart;

    for (let i = 0; i < count; i++) {
      // Stagger birth progress sequentially across the release window
      const birthProgress = releaseStart + (i / count) * windowSpan;

      // Lateral offset perpendicular to vessel wake (-0.15 to +0.15 km)
      const u = Math.random() * 2 - 1;
      const lateralOffsetKm = (u * 0.12) * (0.8 + Math.random() * 0.4);

      this.particles.push({
        id: i,
        birthProgress,
        initialLon: 0,
        initialLat: 0,
        currentLon: 0,
        currentLat: 0,
        targetSlickLon: 0,
        targetSlickLat: 0,
        lateralOffsetKm,
        baseSize: 1.1 + Math.random() * 0.7, // 1.1px to 1.8px radius (2.2px to 3.6px diameter)
        baseOpacity: 0.30 + Math.random() * 0.20, // 0.30 to 0.50 thin sheen
        opacity: 0,
        dispersionRate: 0.5 + Math.random() * 0.6,
      });
    }
  }

  /**
   * Set reconstruction model and precalculate particle emission coordinates along vessel track
   * and target convergence points inside the real M3 geometry.
   */
  public setReconstruction(recon: ForensicReconstruction | null) {
    this.reconstruction = recon;
    this.reset();
    if (!recon) return;

    // 1. Precalculate interior target coordinates within the genuine M3 spill geometry
    const targetPoints = this.sampleInteriorPointsFromM3(recon, this.maxParticles);

    // 2. Precalculate emission coordinates along the vessel track or release point
    const hasVessel = recon.vessel && recon.ais_track?.coordinates && recon.ais_track.coordinates.length >= 2;
    const orig = recon.probable_origin;
    const fallbackLon = orig ? orig.longitude : (recon.vessel?.position.longitude || 0);
    const fallbackLat = orig ? orig.latitude : (recon.vessel?.position.latitude || 0);

    for (let i = 0; i < this.particles.length; i++) {
      const p = this.particles[i];
      p.targetSlickLon = targetPoints[i][0];
      p.targetSlickLat = targetPoints[i][1];

      if (hasVessel) {
        // Sample vessel stern position at the particle's birth progress
        const [vLon, vLat, hdg] = this.getVesselPositionAndHeadingAtProgress(p.birthProgress);

        // Stern offset: position ~0.08 km behind the vessel's heading
        const radHdg = ((hdg + 180) * Math.PI) / 180;
        const radPerp = ((hdg + 90) * Math.PI) / 180;

        const kmPerDegLat = 111.0;
        const kmPerDegLon = Math.max(10.0, 111.0 * Math.cos((vLat * Math.PI) / 180));

        const sternDistKm = 0.06;
        const sternLon = vLon + (sternDistKm * Math.sin(radHdg)) / kmPerDegLon;
        const sternLat = vLat + (sternDistKm * Math.cos(radHdg)) / kmPerDegLat;

        // Apply wake lateral offset
        p.initialLon = sternLon + (p.lateralOffsetKm * Math.sin(radPerp)) / kmPerDegLon;
        p.initialLat = sternLat + (p.lateralOffsetKm * Math.cos(radPerp)) / kmPerDegLat;
      } else {
        // No candidate vessel: emit at probable release origin with small dispersion
        const kmPerDegLat = 111.0;
        const kmPerDegLon = Math.max(10.0, 111.0 * Math.cos((fallbackLat * Math.PI) / 180));
        p.initialLon = fallbackLon + (p.lateralOffsetKm * 0.5) / kmPerDegLon;
        p.initialLat = fallbackLat + (p.lateralOffsetKm * 0.5) / kmPerDegLat;
      }

      p.currentLon = p.initialLon;
      p.currentLat = p.initialLat;
      p.opacity = 0;
    }
  }

  public reset() {
    for (const p of this.particles) {
      p.opacity = 0;
      p.currentLon = p.initialLon;
      p.currentLat = p.initialLat;
    }
  }

  /**
   * Sample interior coordinates from within the real M3 GeoJSON polygon.
   */
  private sampleInteriorPointsFromM3(recon: ForensicReconstruction, count: number): [number, number][] {
    const points: [number, number][] = [];
    const geom = recon.spill_geometry;
    const cent = geom?.centroid;
    const centLon = cent?.longitude || 0;
    const centLat = cent?.latitude || 0;

    if (!geom || !geom.coordinates || geom.coordinates.length === 0) {
      for (let i = 0; i < count; i++) {
        points.push([centLon, centLat]);
      }
      return points;
    }

    // Extract contour exterior ring vertices
    let exteriorRing: [number, number][] = [];
    if (geom.type === "Polygon") {
      exteriorRing = geom.coordinates[0] || [];
    } else if (geom.type === "MultiPolygon") {
      // Pick largest polygon component
      let maxLen = 0;
      for (const poly of geom.coordinates) {
        if (poly && poly[0] && poly[0].length > maxLen) {
          maxLen = poly[0].length;
          exteriorRing = poly[0];
        }
      }
    }

    if (exteriorRing.length < 3) {
      for (let i = 0; i < count; i++) {
        points.push([centLon, centLat]);
      }
      return points;
    }

    // Distribute sample points between exterior vertices and centroid
    for (let i = 0; i < count; i++) {
      const vIdx = i % exteriorRing.length;
      const v = exteriorRing[vIdx];
      // Random interior fraction: 0.15 to 0.85 from centroid to vertex
      const alpha = 0.15 + (Math.random() * 0.70);
      const lon = centLon + (v[0] - centLon) * alpha;
      const lat = centLat + (v[1] - centLat) * alpha;
      points.push([lon, lat]);
    }

    return points;
  }

  /**
   * Interpolate vessel position and heading at normalized replay progress (0.0 to 1.0).
   */
  public getVesselPositionAndHeadingAtProgress(normT: number): [number, number, number] {
    if (!this.reconstruction?.vessel) return [0, 0, 45];
    const track = this.reconstruction.ais_track?.coordinates;
    if (!track || track.length < 2) {
      const pos = this.reconstruction.vessel.position;
      return [pos.longitude, pos.latitude, this.reconstruction.vessel.heading_deg || 45];
    }

    const clampedT = Math.max(0, Math.min(1.0, normT));
    const totalSegs = track.length - 1;
    const exact = clampedT * totalSegs;
    const idx = Math.min(Math.floor(exact), totalSegs - 1);
    const sub = exact - idx;

    const pA = track[idx];
    const pB = track[idx + 1];

    const lon = pA[0] + (pB[0] - pA[0]) * sub;
    const lat = pA[1] + (pB[1] - pA[1]) * sub;

    // Heading calculation between pA and pB
    const dLon = ((pB[0] - pA[0]) * Math.PI) / 180;
    const lat1 = (pA[1] * Math.PI) / 180;
    const lat2 = (pB[1] * Math.PI) / 180;
    const y = Math.sin(dLon) * Math.cos(lat2);
    const x = Math.cos(lat1) * Math.sin(lat2) - Math.sin(lat1) * Math.cos(lat2) * Math.cos(dLon);
    const hdg = ((Math.atan2(y, x) * 180) / Math.PI + 360) % 360;

    return [lon, lat, hdg];
  }

  /**
   * Interpolate coordinates along the drift trajectory for a given normalized progress (0.0 to 1.0).
   */
  private getDriftPositionAtProgress(normT: number): [number, number] {
    if (!this.reconstruction) return [0, 0];
    const traj = this.reconstruction.drift_trajectory?.coordinates;
    if (!traj || traj.length === 0) {
      const orig = this.reconstruction.probable_origin;
      const cent = this.reconstruction.spill_geometry?.centroid;
      if (orig && cent) {
        return [
          orig.longitude + (cent.longitude - orig.longitude) * normT,
          orig.latitude + (cent.latitude - orig.latitude) * normT,
        ];
      }
      return [0, 0];
    }

    if (traj.length === 1) return [traj[0][0], traj[0][1]];

    const clampedT = Math.max(0, Math.min(1.0, normT));
    const totalSegments = traj.length - 1;
    const exactIdx = clampedT * totalSegments;
    const idx = Math.min(Math.floor(exactIdx), totalSegments - 1);
    const subT = exactIdx - idx;

    const pA = traj[idx];
    const pB = traj[idx + 1];

    const lon = pA[0] + (pB[0] - pA[0]) * subT;
    const lat = pA[1] + (pB[1] - pA[1]) * subT;
    return [lon, lat];
  }

  /**
   * Update particle positions and opacity based on continuous wake emission,
   * hydrodynamic advection, and M3 geometry convergence.
   */
  public update(progress: number): GeoJSON.FeatureCollection {
    if (!this.reconstruction) {
      return { type: "FeatureCollection", features: [] };
    }

    const features: GeoJSON.Feature[] = [];

    // Degree conversion constants
    const refLat = this.reconstruction.probable_origin?.latitude || this.reconstruction.spill_geometry?.centroid.latitude || 25.0;
    const kmPerDegLat = 111.0;
    const kmPerDegLon = Math.max(10.0, 111.0 * Math.cos((refLat * Math.PI) / 180));

    // Ocean surface current velocity components
    const u_east = this.reconstruction.ocean_current?.u_eastward_m_s || 0.0;
    const v_north = this.reconstruction.ocean_current?.v_northward_m_s || 0.0;

    // Check if investigation has drift coordinates
    const hasDriftTraj = (this.reconstruction.drift_trajectory?.coordinates?.length || 0) >= 2;

    for (const p of this.particles) {
      // 1. Particle has not yet been emitted
      if (progress < p.birthProgress) {
        p.opacity = 0;
        continue;
      }

      // 2. Particle is active: compute elapsed time since emission
      const ageNorm = progress - p.birthProgress; // >= 0

      // A. Wake Dispersion (widens with square root of time)
      const wakeExpansionKm = Math.sqrt(ageNorm) * 1.6 * p.dispersionRate;

      // B. Ocean Current Advection Displacement
      let advectLon = p.initialLon;
      let advectLat = p.initialLat;

      if (hasDriftTraj) {
        // Follow the model-derived Lagrangian drift path
        // As progress moves from birth towards 0.85, particle advects along the drift line
        const driftFraction = Math.min(1.0, Math.max(0.0, (progress - 0.35) / 0.45));
        const [dLon, dLat] = this.getDriftPositionAtProgress(driftFraction);
        const [dOrigLon, dOrigLat] = this.getDriftPositionAtProgress(0.0);

        // Vector displacement from origin
        const deltaDriftLon = dLon - dOrigLon;
        const deltaDriftLat = dLat - dOrigLat;

        advectLon = p.initialLon + deltaDriftLon;
        advectLat = p.initialLat + deltaDriftLat;
      } else {
        // Advect using surface velocity (u, v in m/s converted to degrees over hours)
        const elapsedHours = ageNorm * 48.0; // 48h simulated time
        const dispKmEast = (u_east * elapsedHours * 3600) / 1000.0;
        const dispKmNorth = (v_north * elapsedHours * 3600) / 1000.0;

        advectLon = p.initialLon + dispKmEast / kmPerDegLon;
        advectLat = p.initialLat + dispKmNorth / kmPerDegLat;
      }

      // Add lateral wake spread
      const lateralLon = (p.lateralOffsetKm * (1.0 + wakeExpansionKm)) / kmPerDegLon;
      const lateralLat = (p.lateralOffsetKm * (1.0 + wakeExpansionKm)) / kmPerDegLat;

      // C. Target M3 Convergence in Stage 5 (progress 0.80 -> 1.0)
      if (progress < 0.80) {
        p.currentLon = advectLon + lateralLon;
        p.currentLat = advectLat + lateralLat;
        // Semi-transparent hydrocarbon sheen
        p.opacity = p.baseOpacity * Math.min(1.0, ageNorm / 0.04);
      } else {
        // Smoothly interpolate from advection position towards assigned interior M3 coordinate
        const convProgress = Math.min(1.0, (progress - 0.80) / 0.15); // 0.0 to 1.0
        const easeConv = convProgress * convProgress * (3 - 2 * convProgress); // smoothstep

        const intermediateLon = advectLon + lateralLon;
        const intermediateLat = advectLat + lateralLat;

        p.currentLon = intermediateLon + (p.targetSlickLon - intermediateLon) * easeConv;
        p.currentLat = intermediateLat + (p.targetSlickLat - intermediateLat) * easeConv;

        // Cross-fade: procedural particles fade down while real M3 polygon illuminates
        const fadeDown = Math.max(0.0, 1.0 - convProgress);
        p.opacity = p.baseOpacity * fadeDown;
      }

      // Add feature if visible
      if (p.opacity > 0.04) {
        features.push({
          type: "Feature",
          properties: {
            id: p.id,
            size: Math.min(2.4, p.baseSize + Math.min(0.8, wakeExpansionKm * 0.3)), // Max ~4.8px diameter
            opacity: p.opacity,
            color: p.opacity > 0.32 ? "#1c1917" : "#292524", // Iridescent dark petroleum tone
          },
          geometry: {
            type: "Point",
            coordinates: [p.currentLon, p.currentLat],
          },
        });
      }
    }

    return {
      type: "FeatureCollection",
      features,
    };
  }
}
