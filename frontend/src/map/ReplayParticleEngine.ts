/**
 * ReplayParticleEngine: Browser-friendly physical particle system for forensic oil spill simulation.
 *
 * Trajectory-Grounded Simulation:
 * 1. Single Source of Truth: Particle positions are strictly interpolated along the
 *    identical drift trajectory (hindcast LineString -> detected slick centroid -> forecast vector).
 * 2. Independent of Vessel Heading: The vessel navigates along its AIS track while
 *    oil particles advect strictly along the oceanographic drift path.
 * 3. Physical Dispersion: Droplets form a dense cluster at release (T=0.25-0.35),
 *    gradually disperse with along-track and cross-track Gaussian-like expansion,
 *    and arrive naturally at the detected slick centroid (T=0.80) without teleportation.
 * 4. Forecast Continuity: From T=0.80 to 1.00, particles continue forward along
 *    the forecast trajectory, smoothly transitioning from dark charcoal to luminous amber/orange.
 */

import { ForensicReconstruction } from "../types";

export interface ReplayParticle {
  id: number;
  stagger: number; // [0, 1] emission stagger
  birthProgress: number; // Replay progress [0, 1] when particle appears
  xi: number; // Normalized along-track offset factor [-1, 1]
  eta: number; // Normalized cross-track lateral offset factor [-1, 1]
  baseSize: number; // Base circle radius in px (1.3 to 2.2)
  baseOpacity: number; // Base circle opacity (0.55 to 0.85)
  dispersionRate: number; // Individual turbulent diffusion rate factor (0.75 to 1.25)
  noiseSeed: number; // Fixed phase offset for micro-turbulence
  charcoalTone: string; // Dark charcoal color variant for hindcast
  forecastTone: string; // Amber/orange color variant for forecast
}

interface PathSegment {
  pA: [number, number]; // [lon, lat]
  pB: [number, number]; // [lon, lat]
  distKm: number;
  cumDistStartKm: number;
  cumDistEndKm: number;
  tangentMetric: [number, number]; // [tx, ty] unit tangent in km
  normalMetric: [number, number]; // [nx, ny] unit normal in km (perpendicular to tangent)
  isForecast: boolean;
}

export class ReplayParticleEngine {
  private particles: ReplayParticle[] = [];
  private maxParticles: number;
  private reconstruction: ForensicReconstruction | null = null;
  private forecastEndpoint: [number, number] | null = null;

  // Arc-length parameterization of the combined continuous trajectory
  private segments: PathSegment[] = [];
  private hindcastCoords: [number, number][] = [];
  private forecastCoords: [number, number][] = [];
  private totalHindcastDistKm = 0;
  private totalForecastDistKm = 0;
  private totalDistKm = 0;
  private refLat = 25.0;
  private kmPerDegLat = 111.132;
  private kmPerDegLon = 100.0;
  private releaseProgress = 0.25;

  constructor(maxParticles = 350) {
    this.maxParticles = maxParticles;
    this.initParticles();
  }

  public getHindcastCoordinates(): [number, number][] {
    return this.hindcastCoords;
  }

  public getForecastCoordinates(): [number, number][] {
    return this.forecastCoords;
  }

  private initParticles() {
    this.particles = [];
    const count = this.maxParticles;

    // Dark charcoal / near-black color tones for historical hindcast oil
    const charcoalTones = [
      "#18181b", // zinc-900
      "#27272a", // zinc-800
      "#09090b", // zinc-950
      "#1c1917", // stone-900
      "#1e293b", // slate-800
    ];

    // Luminous amber / orange color tones for forward forecast projection
    const forecastTones = [
      "#f59e0b", // amber-500
      "#fbbf24", // amber-400
      "#d97706", // amber-600
      "#fb923c", // orange-400
    ];

    // Initial emission window defaults to releaseProgress (Stage 2: Possible Release)
    const releaseStart = this.releaseProgress;
    const releaseDuration = 0.05;

    for (let i = 0; i < count; i++) {
      const stagger = i / count;
      const birthProgress = releaseStart + stagger * releaseDuration;

      // Bell-shaped symmetric distributions for natural Gaussian dispersion
      const xi = (Math.random() - Math.random()) * 0.55;
      const eta = (Math.random() - Math.random()) * 0.55;

      this.particles.push({
        id: i,
        stagger,
        birthProgress,
        xi,
        eta,
        baseSize: 1.3 + Math.random() * 0.9, // 1.3px to 2.2px
        baseOpacity: 0.55 + Math.random() * 0.28,
        dispersionRate: 0.75 + Math.random() * 0.5,
        noiseSeed: i * 13.37 + Math.random() * 5.0,
        charcoalTone: charcoalTones[i % charcoalTones.length],
        forecastTone: forecastTones[i % forecastTones.length],
      });
    }
  }

  /**
   * Set reconstruction model and optional forward forecast endpoint.
   * Parameterizes the combined continuous trajectory using metric arc length.
   */
  public setReconstruction(
    recon: ForensicReconstruction | null,
    forecastPoint?: [number, number] | null
  ) {
    this.reconstruction = recon;
    this.forecastEndpoint = forecastPoint || null;
    this.hindcastCoords = [];
    this.forecastCoords = [];
    this.reset();
    if (!recon) {
      this.segments = [];
      this.totalDistKm = 0;
      return;
    }

    // Determine reference latitude for equirectangular projection
    const cent = recon.spill_geometry?.centroid;
    const orig = recon.probable_origin;
    this.refLat = orig?.latitude || cent?.latitude || recon.vessel?.position.latitude || 25.0;
    this.kmPerDegLat = 111.132;
    this.kmPerDegLon = Math.max(10.0, 111.132 * Math.cos((this.refLat * Math.PI) / 180));

    // 1. Extract and robustly segment hindcast and forecast drift coordinates
    let rawCoords: [number, number][] = [];
    const traj = recon.drift_trajectory?.coordinates;

    if (traj && traj.length >= 2) {
      rawCoords = traj.map((c) => [c[0], c[1]]);
    }

    if (rawCoords.length >= 2 && orig && cent) {
      const dOrig = rawCoords.map((c) => (c[0] - orig.longitude) ** 2 + (c[1] - orig.latitude) ** 2);
      const dCent = rawCoords.map((c) => (c[0] - cent.longitude) ** 2 + (c[1] - cent.latitude) ** 2);

      const minOrigIdx = dOrig.indexOf(Math.min(...dOrig));
      const minCentIdx = dCent.indexOf(Math.min(...dCent));

      if (minOrigIdx > 0 && minCentIdx === 0) {
        // Raw CSV concatenated format: [0..minOrigIdx] is Centroid -> Origin, [minOrigIdx+1..end] is Forecast
        this.hindcastCoords = rawCoords.slice(0, minOrigIdx + 1).reverse();
        if (rawCoords.length > minOrigIdx + 1) {
          this.forecastCoords = rawCoords.slice(minOrigIdx + 1);
        }
      } else if (minOrigIdx === rawCoords.length - 1 && minCentIdx === 0) {
        // Reversed hindcast: Centroid -> Origin
        this.hindcastCoords = [...rawCoords].reverse();
      } else if (minOrigIdx === 0) {
        // Clean chronological hindcast: Origin -> Centroid
        this.hindcastCoords = [...rawCoords];
      } else {
        const d0 = (rawCoords[0][0] - orig.longitude) ** 2 + (rawCoords[0][1] - orig.latitude) ** 2;
        const dLast = (rawCoords[rawCoords.length - 1][0] - orig.longitude) ** 2 + (rawCoords[rawCoords.length - 1][1] - orig.latitude) ** 2;
        this.hindcastCoords = dLast < d0 ? [...rawCoords].reverse() : [...rawCoords];
      }
    } else if (rawCoords.length >= 2) {
      this.hindcastCoords = [...rawCoords];
    } else if (orig && cent) {
      this.hindcastCoords = [
        [orig.longitude, orig.latitude],
        [cent.longitude, cent.latitude],
      ];
    } else if (cent) {
      this.hindcastCoords = [[cent.longitude, cent.latitude]];
    }

    // 2. Set up or complete forecast coordinates
    const lastHindcastPt =
      this.hindcastCoords.length > 0
        ? this.hindcastCoords[this.hindcastCoords.length - 1]
        : cent
        ? [cent.longitude, cent.latitude]
        : [0, 0];

    if (this.forecastCoords.length === 0) {
      if (this.forecastEndpoint && (this.forecastEndpoint[0] !== 0 || this.forecastEndpoint[1] !== 0)) {
        const fPt = this.forecastEndpoint;
        const dFwd = Math.hypot(
          (fPt[0] - lastHindcastPt[0]) * this.kmPerDegLon,
          (fPt[1] - lastHindcastPt[1]) * this.kmPerDegLat
        );
        if (dFwd > 0.05) {
          this.forecastCoords = [[lastHindcastPt[0], lastHindcastPt[1]], [fPt[0], fPt[1]]];
        }
      }

      // Fallback forecast if explicit endpoint is missing: project forward along last segment
      if (this.forecastCoords.length === 0 && this.hindcastCoords.length >= 2) {
        const n = this.hindcastCoords.length;
        const pPrev = this.hindcastCoords[n - 2];
        const pCurr = this.hindcastCoords[n - 1];
        const dxDeg = pCurr[0] - pPrev[0];
        const dyDeg = pCurr[1] - pPrev[1];
        const lenDeg = Math.hypot(dxDeg, dyDeg);
        if (lenDeg > 1e-6) {
          const projKm = 6.0;
          const normX = dxDeg / lenDeg;
          const normY = dyDeg / lenDeg;
          const fwdLon = pCurr[0] + (normX * projKm) / this.kmPerDegLon;
          const fwdLat = pCurr[1] + (normY * projKm) / this.kmPerDegLat;
          this.forecastCoords = [[pCurr[0], pCurr[1]], [fwdLon, fwdLat]];
        }
      }
    }

    // 3. Build metric arc-length parameterization table
    this.segments = [];
    let cumDist = 0;

    // A. Hindcast segments
    for (let i = 0; i < this.hindcastCoords.length - 1; i++) {
      const pA = this.hindcastCoords[i];
      const pB = this.hindcastCoords[i + 1];
      const dxKm = (pB[0] - pA[0]) * this.kmPerDegLon;
      const dyKm = (pB[1] - pA[1]) * this.kmPerDegLat;
      const distKm = Math.hypot(dxKm, dyKm);
      if (distKm < 1e-5) continue;

      const tx = dxKm / distKm;
      const ty = dyKm / distKm;
      // Normal vector rotated 90 degrees counter-clockwise
      const nx = -ty;
      const ny = tx;

      this.segments.push({
        pA,
        pB,
        distKm,
        cumDistStartKm: cumDist,
        cumDistEndKm: cumDist + distKm,
        tangentMetric: [tx, ty],
        normalMetric: [nx, ny],
        isForecast: false,
      });
      cumDist += distKm;
    }
    this.totalHindcastDistKm = cumDist;

    // B. Forecast segments
    for (let i = 0; i < this.forecastCoords.length - 1; i++) {
      const pA = this.forecastCoords[i];
      const pB = this.forecastCoords[i + 1];
      const dxKm = (pB[0] - pA[0]) * this.kmPerDegLon;
      const dyKm = (pB[1] - pA[1]) * this.kmPerDegLat;
      const distKm = Math.hypot(dxKm, dyKm);
      if (distKm < 1e-5) continue;

      const tx = dxKm / distKm;
      const ty = dyKm / distKm;
      const nx = -ty;
      const ny = tx;

      this.segments.push({
        pA,
        pB,
        distKm,
        cumDistStartKm: cumDist,
        cumDistEndKm: cumDist + distKm,
        tangentMetric: [tx, ty],
        normalMetric: [nx, ny],
        isForecast: true,
      });
      cumDist += distKm;
    }
    this.totalForecastDistKm = Math.max(0, cumDist - this.totalHindcastDistKm);
    this.totalDistKm = cumDist;

    // Dynamically synchronize release timing with the vessel's arrival at the probable origin
    this.releaseProgress = this.calculateReleaseProgress(recon);
    this.updateParticleBirthTimes();
  }

  public reset() {
    // Reset internal engine state if needed
  }

  /**
   * Return the normalized progress (0.0 to 1.0) where the vessel reaches the release location.
   */
  public getReleaseProgress(): number {
    return this.releaseProgress;
  }

  /**
   * Synchronize particle birth windows strictly to the dynamically calculated release progress.
   */
  private updateParticleBirthTimes() {
    const releaseStart = this.releaseProgress;
    const releaseDuration = 0.05;

    for (let i = 0; i < this.particles.length; i++) {
      const p = this.particles[i];
      p.birthProgress = releaseStart + p.stagger * releaseDuration;
    }
  }

  /**
   * Determine the exact normalized replay progress where the candidate vessel makes its
   * closest physical approach to the probable origin / release location.
   */
  private calculateReleaseProgress(recon: ForensicReconstruction | null): number {
    if (!recon) return 0.25;

    const orig = recon.probable_origin;
    const origLon = typeof orig?.longitude === "number" ? orig.longitude : (Array.isArray(orig) ? orig[0] : null);
    const origLat = typeof orig?.latitude === "number" ? orig.latitude : (Array.isArray(orig) ? orig[1] : null);

    const rawTrack = recon.ais_track?.coordinates;
    if (!rawTrack || rawTrack.length < 2 || origLon === null || origLat === null) {
      return recon.release_window?.progress_range?.[0] ?? 0.25;
    }

    const track = [...rawTrack].reverse();
    const totalSegs = track.length - 1;

    let minD = Infinity;
    let bestT = 0.25;

    // High-resolution sampling along the reversed vessel path to find closest approach to probable origin
    const samples = 400;
    for (let i = 0; i <= samples; i++) {
      const t = i / samples;
      const exact = t * totalSegs;
      const idx = Math.min(Math.floor(exact), totalSegs - 1);
      const sub = exact - idx;
      const pA = track[idx];
      const pB = track[idx + 1];
      const lon = pA[0] + (pB[0] - pA[0]) * sub;
      const lat = pA[1] + (pB[1] - pA[1]) * sub;

      const dxKm = (lon - origLon) * this.kmPerDegLon;
      const dyKm = (lat - origLat) * this.kmPerDegLat;
      const d = Math.hypot(dxKm, dyKm);
      if (d < minD) {
        minD = d;
        bestT = t;
      }
    }

    // Ensure release progress stays safely within Stage 2 bounds [0.20, 0.45]
    return Math.max(0.20, Math.min(0.45, bestT));
  }

  /**
   * Interpolate vessel position and heading at normalized replay progress (0.0 to 1.0).
   * Consumes existing AIS coordinates in reverse playback order (AIS[N] -> AIS[0]),
   * so the vessel sails away from the probable origin / release point into the open sea.
   */
  public getVesselPositionAndHeadingAtProgress(normT: number): [number, number, number] {
    if (!this.reconstruction?.vessel) return [0, 0, 45];
    const rawTrack = this.reconstruction.ais_track?.coordinates;
    if (!rawTrack || rawTrack.length < 2) {
      const pos = this.reconstruction.vessel.position;
      return [pos.longitude, pos.latitude, this.reconstruction.vessel.heading_deg || 45];
    }

    // Reverse the AIS track coordinates so that T=0 is at rawTrack[N] and T=1 is at rawTrack[0]
    const track = [...rawTrack].reverse();

    const clampedT = Math.max(0, Math.min(1.0, normT));
    const totalSegs = track.length - 1;
    const exact = clampedT * totalSegs;
    const idx = Math.min(Math.floor(exact), totalSegs - 1);
    const sub = exact - idx;

    const pA = track[idx];
    const pB = track[idx + 1];

    const lon = pA[0] + (pB[0] - pA[0]) * sub;
    const lat = pA[1] + (pB[1] - pA[1]) * sub;

    // Direct segment heading calculation pointing forward in direction of motion (from pA to pB)
    const dLon = ((pB[0] - pA[0]) * Math.PI) / 180;
    const lat1 = (pA[1] * Math.PI) / 180;
    const lat2 = (pB[1] * Math.PI) / 180;
    const y = Math.sin(dLon) * Math.cos(lat2);
    const x = Math.cos(lat1) * Math.sin(lat2) - Math.sin(lat1) * Math.cos(lat2) * Math.cos(dLon);
    const targetHdg = ((Math.atan2(y, x) * 180) / Math.PI + 360) % 360;

    return [lon, lat, targetHdg];
  }

  /**
   * Sample position and unit normal vector at a given arc-length distance along the combined trajectory.
   */
  private sampleTrajectoryAtDistance(
    targetDistKm: number
  ): { lon: number; lat: number; nx: number; ny: number; isForecast: boolean } {
    if (this.segments.length === 0) {
      const cent = this.reconstruction?.spill_geometry?.centroid;
      const orig = this.reconstruction?.probable_origin;
      return {
        lon: orig?.longitude || cent?.longitude || 0,
        lat: orig?.latitude || cent?.latitude || 0,
        nx: 0,
        ny: 1,
        isForecast: false,
      };
    }

    const clampedDist = Math.max(0, Math.min(this.totalDistKm, targetDistKm));

    // Find the corresponding segment (linear search is instantaneous for N < 150)
    let seg = this.segments[0];
    for (let i = 0; i < this.segments.length; i++) {
      const s = this.segments[i];
      if (clampedDist >= s.cumDistStartKm && clampedDist <= s.cumDistEndKm) {
        seg = s;
        break;
      }
      if (i === this.segments.length - 1) {
        seg = s;
      }
    }

    const span = Math.max(1e-6, seg.distKm);
    const alpha = Math.max(0, Math.min(1.0, (clampedDist - seg.cumDistStartKm) / span));

    const lon = seg.pA[0] + alpha * (seg.pB[0] - seg.pA[0]);
    const lat = seg.pA[1] + alpha * (seg.pB[1] - seg.pA[1]);

    return {
      lon,
      lat,
      nx: seg.normalMetric[0],
      ny: seg.normalMetric[1],
      isForecast: seg.isForecast,
    };
  }

  /**
   * Update particle positions, styling, and continuous hydrodynamic advection.
   *
   * Guarantees:
   * - Trajectory-grounded: Particle coordinates derive 100% from the displayed map trajectory.
   * - No teleportation: Particles arrive naturally at the detected slick centroid at T=0.80,
   *   then smoothly continue forward along the forecast trajectory.
   * - Realistic styling: Dark charcoal oil droplets for hindcast, vivid amber for forecast.
   */
  public update(progress: number): GeoJSON.FeatureCollection {
    const relProg = this.releaseProgress;
    if (!this.reconstruction || progress < relProg || this.segments.length === 0) {
      return { type: "FeatureCollection", features: [] };
    }

    const features: GeoJSON.Feature[] = [];

    // 1. Calculate centerline progress along the continuous trajectory
    // T in [relProg, 0.80]: Hindcast drift from Origin (s=0) to Centroid (s=totalHindcastDistKm)
    // T in [0.80, 1.00]: Forecast drift from Centroid to Forecast Endpoint
    const hindcastSpan = Math.max(0.05, 0.80 - relProg);
    const hindcastProg = Math.min(1.0, Math.max(0.0, (progress - relProg) / hindcastSpan));
    const forecastProg = Math.max(0.0, (progress - 0.80) / 0.20);

    let centerDistKm = 0;
    if (progress <= 0.80) {
      centerDistKm = hindcastProg * this.totalHindcastDistKm;
    } else {
      centerDistKm = this.totalHindcastDistKm + forecastProg * this.totalForecastDistKm;
    }

    // 2. Compute dynamic dispersion envelopes
    // Cross-track lateral width W_perp (turbulent wake expansion):
    // Starts at ~0.05 km (50m wake) at release, widens with sqrt(time) to ~0.35 km at detection
    const baseWakeWidthKm = 0.05;
    const maxHindcastSpreadKm = 0.35;
    const fwdSpreadKm = 0.20;

    const currentSpreadKm =
      baseWakeWidthKm +
      maxHindcastSpreadKm * Math.sqrt(hindcastProg) +
      fwdSpreadKm * Math.sqrt(forecastProg);

    // Along-track longitudinal length L_par (slick elongation under shear):
    const alongTrackLengthKm =
      (0.02 + 0.12 * Math.sqrt(hindcastProg) + 0.08 * Math.sqrt(forecastProg)) *
      Math.max(2.0, this.totalHindcastDistKm);

    for (const p of this.particles) {
      // Check if particle has been released
      if (progress < p.birthProgress) {
        continue;
      }

      const ageNorm = progress - p.birthProgress; // >= 0

      // Particle's along-track arc-length coordinate
      const pDistKm = centerDistKm + p.xi * alongTrackLengthKm * p.dispersionRate;

      // Sample trajectory centerline position and normal vector
      const sample = this.sampleTrajectoryAtDistance(pDistKm);

      // Compute cross-track lateral offset in kilometers
      const latOffsetKm = p.eta * currentSpreadKm * p.dispersionRate;

      // Organic micro-turbulent wandering (simulates fluid shear & surface eddies)
      const turbPhase = p.noiseSeed + progress * 14.0;
      const turbX = (Math.sin(turbPhase) * (0.02 * currentSpreadKm)) / this.kmPerDegLon;
      const turbY = (Math.cos(turbPhase * 1.3) * (0.02 * currentSpreadKm)) / this.kmPerDegLat;

      // Final geographic position
      const finalLon = sample.lon + (sample.nx * latOffsetKm) / this.kmPerDegLon + turbX;
      const finalLat = sample.lat + (sample.ny * latOffsetKm) / this.kmPerDegLat + turbY;

      // Smooth fade-in right after release
      const fadeIn = Math.min(1.0, ageNorm / 0.025);

      // Color and stroke properties based on hindcast vs. forecast state
      let color = p.charcoalTone;
      let strokeColor = "#52525b"; // zinc-600 subtle sheen
      let strokeOpacity = 0.45;
      let opacity = p.baseOpacity * fadeIn;
      let size = p.baseSize + 0.35 * Math.sqrt(hindcastProg);

      if (sample.isForecast || pDistKm > this.totalHindcastDistKm) {
        // Particle has crossed the centroid into the forward forecast zone
        const fwdFraction = Math.min(
          1.0,
          Math.max(0.0, (pDistKm - this.totalHindcastDistKm) / Math.max(0.1, this.totalForecastDistKm))
        );

        if (fwdFraction < 0.12) {
          // Subtle organic blend at the interface
          color = "#78350f"; // warm dark amber
          strokeColor = "#d97706";
        } else {
          color = p.forecastTone; // vibrant amber/orange
          strokeColor = "#fef08a"; // luminous yellow sheen
        }

        strokeOpacity = 0.65;
        opacity = p.baseOpacity * fadeIn * (0.95 - 0.12 * fwdFraction);
        size = p.baseSize + 0.45;
      }

      features.push({
        type: "Feature",
        properties: {
          id: p.id,
          size,
          color,
          opacity,
          strokeColor,
          strokeOpacity,
        },
        geometry: {
          type: "Point",
          coordinates: [finalLon, finalLat],
        },
      });
    }

    return {
      type: "FeatureCollection",
      features,
    };
  }
}
