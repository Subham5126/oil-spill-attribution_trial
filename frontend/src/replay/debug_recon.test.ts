import { describe, it } from "vitest";
import { buildIncidentReplayModel } from "./buildReplayModel";
import { interpolateVessel } from "./ais";

describe("Debug AIS Replay", () => {
  it("inspects real investigation reconstruction data", async () => {
    let recon: any = null;
    try {
      const res = await fetch("http://localhost:8000/api/investigations/INV-2026-C19B59/reconstruction");
      if (res.ok) {
        recon = await res.json();
      }
    } catch {
      // Backend not running in this test process
    }

    if (!recon || !recon.ais_track?.waypoints?.length) {
      recon = {
        investigation_id: "INV-2026-C19B59",
        status: "FULL_RECONSTRUCTION",
        vessel: { mmsi: 408602000, vessel_name: "HADI 44", vessel_type: "Offshore Supply / Tug" },
        spill_geometry: {
          type: "Polygon",
          coordinates: [[[54.49, 25.57], [54.52, 25.59], [54.51, 25.61], [54.48, 25.58], [54.49, 25.57]]],
        },
        spill_centroid: { latitude: 25.58, longitude: 25.50 },
        spill_timestamp: "2017-03-08T20:45:11Z",
        probable_origin: { latitude: 25.5727, longitude: 54.4956, timestamp: "2017-03-08T02:15:11Z" },
        drift_trajectory: [[54.4956, 25.5727], [54.5080, 25.5810]],
        ais_track: {
          type: "LineString",
          has_track: true,
          waypoints: [
            { latitude: 25.72, longitude: 54.35, timestamp: "2017-03-08T00:00:00Z", heading: 135, speed_knots: 12 },
            { latitude: 25.5727, longitude: 54.4956, timestamp: "2017-03-08T02:15:11Z", heading: 135, speed_knots: 13 },
            { latitude: 25.40, longitude: 54.60, timestamp: "2017-03-08T03:00:00Z", heading: 135, speed_knots: 12 },
            { latitude: 25.33, longitude: 54.80, timestamp: "2017-03-08T20:45:11Z", heading: 135, speed_knots: 1.5 },
          ],
        },
        nearby_vessels: [
          {
            rank: 2,
            mmsi: 352788000,
            vessel_name: "NLP JACKSON",
            latitude: 25.5,
            longitude: 54.5,
            heading: 110,
            speed_knots: 12.4,
            attribution_score: 0.969,
            track: [
              { latitude: 25.45, longitude: 54.40, timestamp: "2017-03-08T00:00:00Z", heading: 110, speed_knots: 12.4 },
              { latitude: 25.50, longitude: 54.50, timestamp: "2017-03-08T03:00:00Z", heading: 110, speed_knots: 12.4 },
              { latitude: 25.60, longitude: 54.70, timestamp: "2017-03-08T20:45:11Z", heading: 110, speed_knots: 12.4 },
            ],
          },
        ],
      };
    }

    const model = buildIncidentReplayModel(recon);
    if (!model) {
      console.log("Model is null!");
      return;
    }

    const pts = model.trajectory.points;
    console.log("=== AIS DEBUG INFO ===");
    console.log("AIS point count:", pts.length);
    console.log("first AIS timestamp:", pts[0]?.timestamp, new Date(pts[0]?.timestamp).toISOString());
    console.log("last AIS timestamp:", pts[pts.length - 1]?.timestamp, new Date(pts[pts.length - 1]?.timestamp).toISOString());
    console.log("first AIS coordinates:", [pts[0]?.longitude, pts[0]?.latitude]);
    console.log("last AIS coordinates:", [pts[pts.length - 1]?.longitude, pts[pts.length - 1]?.latitude]);
    console.log("minimum timestamp (startTime):", model.startTime, new Date(model.startTime).toISOString());
    console.log("maximum timestamp (endTime):", model.endTime, new Date(model.endTime).toISOString());
    console.log("total duration hours:", (model.endTime - model.startTime) / 3600000);
    console.log("timestamp unit: milliseconds since epoch");
    console.log("coordinate order: [longitude, latitude]");
    console.log("events:", model.events);

    // Test positions at 0%, 25%, 50%, 75%, 100% of AIS duration
    const aisStart = pts[0].timestamp;
    const aisEnd = pts[pts.length - 1].timestamp;
    const aisSpan = aisEnd - aisStart;

    console.log("=== AIS INTERPOLATION CHECK ===");
    for (const pct of [0, 0.25, 0.5, 0.75, 1.0]) {
      const t = aisStart + pct * aisSpan;
      const pose = interpolateVessel(pts, t);
      console.log(`AIS ${pct * 100}% (${new Date(t).toISOString()}):`, pose);
    }

    console.log("=== INVESTIGATION TIME INTERPOLATION CHECK ===");
    const invSpan = model.endTime - model.startTime;
    for (const pct of [0, 0.25, 0.5, 0.75, 1.0]) {
      const t = model.startTime + pct * invSpan;
      const pose = interpolateVessel(pts, t);
      console.log(`Inv ${pct * 100}% (${new Date(t).toISOString()}):`, pose);
    }

    console.log("=== PARTICLE CHECK ===");
    console.log("Model particle seeds:", model.particles.length);
    console.log("Model releaseTimestamp:", model.releaseTimestamp, new Date(model.releaseTimestamp || 0).toISOString());
    console.log("Model spillTimestamp:", model.spillTimestamp, new Date(model.spillTimestamp || 0).toISOString());
    console.log("Model driftTrajectory:", model.driftTrajectory.length);
    console.log("Nearby vessels in model:", model.nearbyVessels.length);
    console.log("Current vectors in model:", model.currentVectors.length);
    const { particlesAtTime } = await import("./particles");
    for (const pct of [0, 0.1, 0.15, 0.25, 0.5, 0.75, 1.0]) {
      const t = model.startTime + pct * invSpan;
      const parts = particlesAtTime(model.particles, t, model.releaseTimestamp ?? model.spillTimestamp);
      console.log(`Particles at ${pct * 100}% (${new Date(t).toISOString()}): count = ${parts.length}`, parts[0]);
    }
  });
});
