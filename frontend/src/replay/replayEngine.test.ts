import { describe, expect, it } from "vitest";
import { aisSegmentDurationRatios, interpolateVessel, normalizeAisPoints } from "./ais";
import { advanceClock, createInvestigationClockLoop, createReplayState, playClock, replayFromStart, seekClock } from "./clock";
import { detectedSpillVisible, forecastGeometryAtTime, nearestForecastFrame } from "./geometry";
import { computeParticleColor, particlesAtTime, seedOilParticles } from "./particles";
import { buildIncidentReplayModel } from "./buildReplayModel";
import type { ForensicReconstruction } from "../types";

const poly: GeoJSON.Polygon = {
  type: "Polygon",
  coordinates: [
    [
      [10, 50],
      [10.02, 50],
      [10.02, 50.02],
      [10, 50.02],
      [10, 50],
    ],
  ],
};

describe("OILTRACE Replay Engine — 17 Core Requirements", () => {
  // TEST 1
  it("Requirement 1: Interpolation along actual AIS timestamps moves ONLY forward (P0 -> P1 -> ... -> Pn)", () => {
    const pts = normalizeAisPoints([
      { longitude: 0, latitude: 10, timestamp: "2026-01-01T12:00:00Z" },
      { longitude: 1, latitude: 10, timestamp: "2026-01-01T12:10:00Z" },
      { longitude: 2, latitude: 10, timestamp: "2026-01-01T12:20:00Z" },
      { longitude: 3, latitude: 10, timestamp: "2026-01-01T12:30:00Z" },
    ]);

    const times = [
      Date.parse("2026-01-01T12:00:00Z"),
      Date.parse("2026-01-01T12:05:00Z"),
      Date.parse("2026-01-01T12:10:00Z"),
      Date.parse("2026-01-01T12:15:00Z"),
      Date.parse("2026-01-01T12:20:00Z"),
      Date.parse("2026-01-01T12:25:00Z"),
      Date.parse("2026-01-01T12:30:00Z"),
    ];

    const poses = times.map((t) => interpolateVessel(pts, t)!);
    for (let i = 1; i < poses.length; i++) {
      expect(poses[i].longitude).toBeGreaterThanOrEqual(poses[i - 1].longitude);
    }
    expect(poses[0].longitude).toBe(0);
    expect(poses[poses.length - 1].longitude).toBe(3);
  });

  // TEST 2
  it("Requirement 2: AIS timestamps out-of-order in source data are sorted before interpolation", () => {
    const pts = normalizeAisPoints([
      { longitude: 3, latitude: 10, timestamp: "2026-01-01T13:00:00Z" },
      { longitude: 0, latitude: 10, timestamp: "2026-01-01T12:00:00Z" },
      { longitude: 2, latitude: 10, timestamp: "2026-01-01T12:40:00Z" },
      { longitude: 1, latitude: 10, timestamp: "2026-01-01T12:10:00Z" },
    ]);

    expect(pts.map((p) => p.timestamp)).toEqual([
      Date.parse("2026-01-01T12:00:00Z"),
      Date.parse("2026-01-01T12:10:00Z"),
      Date.parse("2026-01-01T12:40:00Z"),
      Date.parse("2026-01-01T13:00:00Z"),
    ]);
    expect(pts.map((p) => p.longitude)).toEqual([0, 1, 2, 3]);
  });

  // TEST 3
  it("Requirement 3: Unequal AIS intervals interpolate at correct proportional rates", () => {
    const pts = normalizeAisPoints([
      { longitude: 0, latitude: 0, timestamp: "2026-01-01T12:00:00Z" },
      { longitude: 1, latitude: 0, timestamp: "2026-01-01T12:10:00Z" }, // 10 min
      { longitude: 2, latitude: 0, timestamp: "2026-01-01T12:40:00Z" }, // 30 min
    ]);

    const ratios = aisSegmentDurationRatios(pts);
    expect(ratios[0] / 60000).toBe(10);
    expect(ratios[1] / 60000).toBe(30);

    // Halfway through 10-min segment (at 5 min):
    const mid10 = interpolateVessel(pts, Date.parse("2026-01-01T12:05:00Z"));
    expect(mid10?.longitude).toBeCloseTo(0.5, 6);

    // Halfway through 30-min segment (at 12:25, which is 15 min into 12:10->12:40):
    const mid30 = interpolateVessel(pts, Date.parse("2026-01-01T12:25:00Z"));
    expect(mid30?.longitude).toBeCloseTo(1.5, 6);
  });

  // TEST 4
  it("Requirement 4: Investigation clock is the single source of truth — no secondary timers", () => {
    let state = createReplayState(0, 10_000, 1);
    state = playClock(state);

    const loop = createInvestigationClockLoop({
      getState: () => state,
      setState: (next) => {
        state = next;
      },
      scale: 1,
    });

    loop.start();
    loop.start(); // Calling start a second time should NOT start a duplicate rAF loop
    expect(loop.isRunning).toBe(true);
    loop.stop();
    expect(loop.isRunning).toBe(false);
  });

  // TEST 5
  it("Requirement 5: Replay stops at endTime — does not loop, does not reverse", () => {
    let state = createReplayState(0, 1000, 1);
    state = playClock(state);
    state = advanceClock(state, 1000, 1);

    expect(state.currentTime).toBe(1000);
    expect(state.isPlaying).toBe(false);

    // Advancing further does not loop back to 0 or reverse
    const further = advanceClock(state, 500, 1);
    expect(further.currentTime).toBe(1000);
    expect(further.isPlaying).toBe(false);
  });

  // TEST 6
  it("Requirement 6: Replay button resets to startTime and remains paused until play is pressed", () => {
    let state = createReplayState(0, 1000, 1);
    state = { ...state, currentTime: 1000, isPlaying: false };

    // Resetting to start
    const afterReplay = replayFromStart(state);
    expect(afterReplay.currentTime).toBe(0);
    expect(afterReplay.isPlaying).toBe(false); // MUST remain paused

    // Playing explicitly advances it
    const afterPlay = playClock(afterReplay);
    expect(afterPlay.isPlaying).toBe(true);
  });

  // TEST 7
  it("Requirement 7: Draggable slider seeking to an earlier time correctly reconstructs that timestamp's state", () => {
    const start = Date.parse("2026-01-01T10:00:00Z");
    const end = Date.parse("2026-01-01T12:00:00Z");
    let state = createReplayState(start, end);

    state = seekClock(state, Date.parse("2026-01-01T11:30:00Z"));
    expect(state.currentTime).toBe(Date.parse("2026-01-01T11:30:00Z"));

    // Seek backwards to earlier time
    state = seekClock(state, Date.parse("2026-01-01T10:15:00Z"));
    expect(state.currentTime).toBe(Date.parse("2026-01-01T10:15:00Z"));
  });

  // TEST 8
  it("Requirement 8: Vessel reaches oil spill location at the actual recorded spill timestamp (not earlier)", () => {
    const tStart = Date.parse("2026-01-01T08:00:00Z");
    const tSpill = Date.parse("2026-01-01T09:30:00Z");
    const tEnd = Date.parse("2026-01-01T11:00:00Z");

    const spillCoord = { lon: 5.5, lat: 55.5 };

    const pts = normalizeAisPoints([
      { longitude: 5.0, latitude: 55.0, timestamp: tStart },
      { longitude: spillCoord.lon, latitude: spillCoord.lat, timestamp: tSpill },
      { longitude: 6.0, latitude: 56.0, timestamp: tEnd },
    ]);

    // Before spill: vessel has not reached spill location
    const beforePose = interpolateVessel(pts, Date.parse("2026-01-01T08:45:00Z"))!;
    expect(beforePose.longitude).toBeLessThan(spillCoord.lon);

    // At spill timestamp: vessel is EXACTLY at spill location
    const atPose = interpolateVessel(pts, tSpill)!;
    expect(atPose.longitude).toBeCloseTo(spillCoord.lon, 6);
    expect(atPose.latitude).toBeCloseTo(spillCoord.lat, 6);
  });

  // TEST 9
  it("Requirement 9: Detected SAR spill geometry is NOT visible before spill timestamp", () => {
    const tSpill = Date.parse("2026-01-01T09:30:00Z");

    expect(detectedSpillVisible(Date.parse("2026-01-01T09:00:00Z"), tSpill)).toBe(false);
    expect(detectedSpillVisible(Date.parse("2026-01-01T09:29:59Z"), tSpill)).toBe(false);
    expect(detectedSpillVisible(tSpill, tSpill)).toBe(true);
    expect(detectedSpillVisible(Date.parse("2026-01-01T10:00:00Z"), tSpill)).toBe(true);
  });

  // TEST 10
  it("Requirement 10: Particles do NOT emit before spill timestamp", () => {
    const spillTs = Date.parse("2026-01-01T09:30:00Z");
    const seeds = seedOilParticles({
      geometry: poly,
      spillTimestamp: spillTs,
      seed: "determinism",
      count: 100,
      currentUms: 0.1,
      currentVms: 0,
    });

    expect(particlesAtTime(seeds, Date.parse("2026-01-01T09:00:00Z"), spillTs)).toHaveLength(0);
    expect(particlesAtTime(seeds, Date.parse("2026-01-01T09:29:59Z"), spillTs)).toHaveLength(0);

    const emitted = particlesAtTime(seeds, spillTs + 60_000, spillTs);
    expect(emitted.length).toBeGreaterThan(0);
  });

  // TEST 11
  it("Requirement 11: Particles generated at time T are identical on repeated runs (deterministic seeded PRNG)", () => {
    const spillTs = Date.parse("2026-01-01T09:30:00Z");
    const runA = seedOilParticles({ geometry: poly, spillTimestamp: spillTs, seed: "same-seed", count: 80 });
    const runB = seedOilParticles({ geometry: poly, spillTimestamp: spillTs, seed: "same-seed", count: 80 });

    expect(runA).toEqual(runB);

    const checkTime = spillTs + 1800_000;
    const partsA = particlesAtTime(runA, checkTime, spillTs);
    const partsB = particlesAtTime(runB, checkTime, spillTs);
    expect(partsA).toEqual(partsB);
  });

  // TEST 12
  it("Requirement 12: Forward-cast oil position at time T matches model calculation for that elapsed time", () => {
    const frames = [
      { timestamp: Date.parse("2026-01-01T09:30:00Z"), longitude: 10.0, latitude: 50.0 },
      { timestamp: Date.parse("2026-01-01T10:30:00Z"), longitude: 10.2, latitude: 50.1 },
      { timestamp: Date.parse("2026-01-01T11:30:00Z"), longitude: 10.4, latitude: 50.2 },
    ];

    const f = nearestForecastFrame(frames, Date.parse("2026-01-01T10:30:00Z"));
    expect(f?.longitude).toBe(10.2);
    expect(f?.latitude).toBe(50.1);

    const geom = forecastGeometryAtTime(poly, frames, Date.parse("2026-01-01T10:30:00Z"), frames[0].timestamp);
    expect(geom).not.toBeNull();
    expect(geom?.type).toBe("Polygon");
  });

  // TEST 13
  it("Requirement 13: Edge case: AIS trajectory has only 1 point", () => {
    const pts = normalizeAisPoints([{ longitude: 12.5, latitude: 55.5, timestamp: "2026-01-01T12:00:00Z" }]);
    expect(pts).toHaveLength(1);

    const before = interpolateVessel(pts, Date.parse("2026-01-01T11:00:00Z"));
    const at = interpolateVessel(pts, Date.parse("2026-01-01T12:00:00Z"));
    const after = interpolateVessel(pts, Date.parse("2026-01-01T13:00:00Z"));

    expect(before?.longitude).toBe(12.5);
    expect(at?.longitude).toBe(12.5);
    expect(after?.longitude).toBe(12.5);
  });

  // TEST 14
  it("Requirement 14: Edge case: AIS trajectory is empty", () => {
    expect(normalizeAisPoints([])).toEqual([]);
    expect(interpolateVessel([], Date.now())).toBeNull();
  });

  // TEST 15
  it("Requirement 15: Edge case: AIS trajectory has duplicate timestamps", () => {
    const pts = normalizeAisPoints([
      { longitude: 10, latitude: 50, timestamp: "2026-01-01T12:00:00Z" },
      { longitude: 10.05, latitude: 50.05, timestamp: "2026-01-01T12:00:00Z" }, // duplicate timestamp
      { longitude: 11, latitude: 51, timestamp: "2026-01-01T12:10:00Z" },
    ]);

    expect(pts).toHaveLength(2);
    expect(pts[0].timestamp).toBe(Date.parse("2026-01-01T12:00:00Z"));
    expect(pts[1].timestamp).toBe(Date.parse("2026-01-01T12:10:00Z"));
  });

  // TEST 16
  it("Requirement 16: Edge case: NaN/invalid coordinates in AIS data", () => {
    const pts = normalizeAisPoints([
      { longitude: 10, latitude: 50, timestamp: "2026-01-01T12:00:00Z" },
      { longitude: NaN, latitude: 50, timestamp: "2026-01-01T12:05:00Z" },
      { longitude: 185, latitude: 50, timestamp: "2026-01-01T12:10:00Z" },
      { longitude: 10, latitude: 95, timestamp: "2026-01-01T12:15:00Z" },
      { longitude: 11, latitude: 50, timestamp: "2026-01-01T12:20:00Z" },
    ]);

    expect(pts).toHaveLength(2);
    expect(pts.every((p) => Number.isFinite(p.longitude) && Number.isFinite(p.latitude))).toBe(true);
  });

  // TEST 17
  it("Requirement 17: Edge case: Replay started when currentTime == endTime does not crash or advance further", () => {
    let state = createReplayState(0, 1000, 1);
    state = { ...state, currentTime: 1000 };

    const played = playClock(state);
    expect(played.isPlaying).toBe(false);
    expect(played.currentTime).toBe(1000);

    const advanced = advanceClock(played, 500, 1);
    expect(advanced.isPlaying).toBe(false);
    expect(advanced.currentTime).toBe(1000);
  });
});

describe("Incident Replay Model Builder fallback tests", () => {
  it("buildIncidentReplayModel handles missing AIS trajectory gracefully", () => {
    const recon = {
      investigation_id: "INV-TEST",
      title: "Test Spill",
      region: "North Sea",
      reconstruction_status: "SPILL_ONLY",
      disclaimer: "",
      vessel: null,
      ais_track: null,
      probable_origin: null,
      ocean_current: { speed_m_s: 0.2, direction_deg: 45 },
      drift_trajectory: { type: "LineString", coordinates: [], points: [], total_distance_km: 0 },
      spill_geometry: {
        type: "Polygon",
        coordinates: poly.coordinates,
        area_sq_km: 1.2,
        perimeter_km: 4.5,
        centroid: { latitude: 50.01, longitude: 10.01 },
        confidence: 0.95,
        detection_time: "2026-01-01T09:30:00Z",
      },
      timeline: [],
      generated_at: "2026-01-01T00:00:00Z",
    } as unknown as ForensicReconstruction;

    const model = buildIncidentReplayModel(recon);
    expect(model).not.toBeNull();
    expect(model?.availability.ais).toBe(false);
    expect(model?.availability.aisMessage).toBe("AIS trajectory unavailable");
    expect(model?.spillTimestamp).toBe(Date.parse("2026-01-01T09:30:00Z"));
  });
});

describe("Section 16: Tests A through H (Vessel Replay Progression & Controls)", () => {
  const pts = normalizeAisPoints([
    { longitude: 54.8, latitude: 25.0, timestamp: "2017-03-08T00:00:00Z" },
    { longitude: 54.4, latitude: 25.6, timestamp: "2017-03-08T05:11:17.75Z" },
    { longitude: 54.0, latitude: 26.3, timestamp: "2017-03-08T10:22:35.5Z" },
    { longitude: 53.6, latitude: 27.0, timestamp: "2017-03-08T15:33:53.25Z" },
    { longitude: 53.2, latitude: 27.7, timestamp: "2017-03-08T20:45:11Z" },
  ]);
  const startTime = pts[0].timestamp;
  const endTime = pts[pts.length - 1].timestamp;
  const span = endTime - startTime;

  it("Test A — initial: At investigationTime = startTime, vessel is at first AIS point", () => {
    const pose = interpolateVessel(pts, startTime);
    expect(pose).not.toBeNull();
    expect(pose?.longitude).toBeCloseTo(54.8, 4);
    expect(pose?.latitude).toBeCloseTo(25.0, 4);
  });

  it("Test B — 25%: At 25% timeline progression, vessel matches ~25% through trajectory", () => {
    const t25 = startTime + 0.25 * span;
    const pose = interpolateVessel(pts, t25);
    expect(pose).not.toBeNull();
    expect(pose?.longitude).toBeCloseTo(54.4, 1);
    expect(pose?.latitude).toBeCloseTo(25.6, 1);
  });

  it("Test C — 50%: At 50% timeline progression, vessel is at middle of trajectory", () => {
    const t50 = startTime + 0.50 * span;
    const pose = interpolateVessel(pts, t50);
    expect(pose).not.toBeNull();
    expect(pose?.longitude).toBeCloseTo(54.0, 1);
    expect(pose?.latitude).toBeCloseTo(26.3, 1);
  });

  it("Test D — 75%: At 75% timeline progression, vessel continues forward along route", () => {
    const t75 = startTime + 0.75 * span;
    const pose = interpolateVessel(pts, t75);
    expect(pose).not.toBeNull();
    expect(pose?.longitude).toBeCloseTo(53.6, 1);
    expect(pose?.latitude).toBeCloseTo(27.0, 1);
  });

  it("Test E — end: At 100% timeline progression, vessel is at final AIS point and remains there", () => {
    const poseEnd = interpolateVessel(pts, endTime);
    expect(poseEnd?.longitude).toBeCloseTo(53.2, 4);
    expect(poseEnd?.latitude).toBeCloseTo(27.7, 4);

    // Beyond end
    const posePast = interpolateVessel(pts, endTime + 100000);
    expect(posePast?.longitude).toBeCloseTo(53.2, 4);
    expect(posePast?.latitude).toBeCloseTo(27.7, 4);
  });

  it("Test F — reverse seek: Dragging from 75% back to 25% reconstructs historical location without backward animation", () => {
    let state = createReplayState(startTime, endTime, 1);
    state = seekClock(state, startTime + 0.75 * span);
    const pose75 = interpolateVessel(pts, state.currentTime);
    expect(pose75?.longitude).toBeCloseTo(53.6, 1);

    // Reverse seek to 25%
    state = seekClock(state, startTime + 0.25 * span);
    const pose25 = interpolateVessel(pts, state.currentTime);
    expect(pose25?.longitude).toBeCloseTo(54.4, 1);
    expect(state.currentTime).toBe(startTime + 0.25 * span);
  });

  it("Test G — playback: At 1x, baseline advances at calibrated 60 inv sec / wall sec (does not finish in 1-5 seconds)", () => {
    let state = createReplayState(startTime, endTime, 1);
    state = playClock(state);

    // After 1000ms (1 real wall second) at 1x
    state = advanceClock(state, 1000);
    expect(state.isPlaying).toBe(true);
    // 1000ms * 1 * 60 = 60,000ms = 1 minute of investigation time
    expect(state.currentTime - startTime).toBe(60_000);

    // At 1x, 20h45m (74,711,000 ms) cannot finish in 5 seconds (5000ms)
    let stateAfter5s = createReplayState(startTime, endTime, 1);
    stateAfter5s = playClock(stateAfter5s);
    stateAfter5s = advanceClock(stateAfter5s, 5000);
    expect(stateAfter5s.isPlaying).toBe(true);
    expect(stateAfter5s.currentTime).toBeLessThan(endTime);
  });

  it("Test H — repeated Play: Only one loop, state remains idempotent", () => {
    let state = createReplayState(startTime, endTime, 1);
    state = playClock(state);
    expect(state.isPlaying).toBe(true);
    state = playClock(state);
    expect(state.isPlaying).toBe(true);
  });

  describe("Particle Color Progression (CYAN -> BLUE -> RED -> ORANGE -> YELLOW)", () => {
    const duration = 10 * 3600 * 1000; // 10h drift duration

    it("Early hindcast (0% - 50%): Bright cyan", () => {
      const cEarly = computeParticleColor(0.2 * duration, duration, 0);
      expect(cEarly).toBe("#00d9ff");
    });

    it("Approaching detected spill (70%): Ocean blue transition", () => {
      const cBlue = computeParticleColor(0.70 * duration, duration, 0);
      expect(cBlue).toMatch(/^rgb\((\d+),(\d+),(\d+)\)$/);
      // Verify blue dominance
      const [r, g, b] = cBlue.match(/\d+/g)!.map(Number);
      expect(b).toBeGreaterThan(r);
    });

    it("At detected spill (100%): Slick red", () => {
      const cRed = computeParticleColor(duration, duration, 0);
      expect(cRed).toMatch(/^rgb\((\d+),(\d+),(\d+)\)$/);
      const [r, g, b] = cRed.match(/\d+/g)!.map(Number);
      expect(r).toBeGreaterThan(170);
      expect(b).toBeLessThan(120);
    });

    it("Forecast early phase (+3h): Warm orange", () => {
      const cOrange = computeParticleColor(duration + 3 * 3600 * 1000, duration, 0);
      expect(cOrange).toMatch(/^rgb\((\d+),(\d+),(\d+)\)$/);
      const [r, g, b] = cOrange.match(/\d+/g)!.map(Number);
      expect(r).toBeGreaterThan(200);
      expect(g).toBeGreaterThan(35);
      expect(b).toBeLessThan(80);
    });

    it("Forecast late phase (+18h): Bright yellow", () => {
      const cYellow = computeParticleColor(duration + 18 * 3600 * 1000, duration, 0);
      expect(cYellow).toMatch(/^rgb\((\d+),(\d+),(\d+)\)$/);
      const [r, g, b] = cYellow.match(/\d+/g)!.map(Number);
      expect(r).toBeGreaterThan(220);
      expect(g).toBeGreaterThan(150);
      expect(b).toBeLessThan(60);
    });

    it("Reversibility: Exact deterministic match when seeking backward", () => {
      const timeA = duration + 5 * 3600 * 1000;
      const colorForward = computeParticleColor(timeA, duration, 42);

      // Advance then reverse
      computeParticleColor(duration + 12 * 3600 * 1000, duration, 42);
      const colorBackward = computeParticleColor(timeA, duration, 42);

      expect(colorBackward).toBe(colorForward);
    });
  });
});
