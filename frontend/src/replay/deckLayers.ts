import { PathLayer, PolygonLayer, ScatterplotLayer } from "@deck.gl/layers";
import { TripsLayer } from "@deck.gl/geo-layers";
import type { IncidentReplayModel } from "./types";
import { interpolateVessel, splitTrack } from "./ais";
import { detectedSpillVisible, forecastGeometryAtTime } from "./geometry";
import { particlesAtTime } from "./particles";

function polygonToPolygons(geom: GeoJSON.Polygon | GeoJSON.MultiPolygon): number[][][] {
  return geom.type === "Polygon" ? geom.coordinates : geom.coordinates.flat();
}

export function buildReplayDeckLayers(model: IncidentReplayModel, currentTime: number) {
  const layers = [];
  const showSpill = detectedSpillVisible(currentTime, model.spillTimestamp);

  if (model.tripsPath.length >= 2) {
    layers.push(
      new TripsLayer({
        id: "vessel-trip",
        data: [{ path: model.tripsPath, timestamps: model.tripsTimestamps }],
        getPath: (d: { path: [number, number][] }) => d.path,
        getTimestamps: (d: { timestamps: number[] }) => d.timestamps,
        getColor: [56, 189, 248, 230],
        getWidth: 3,
        widthMinPixels: 2,
        widthMaxPixels: 5,
        capRounded: true,
        jointRounded: true,
        trailLength: Math.max(30 * 60 * 1000, (model.endTime - model.startTime) * 0.35),
        currentTime,
      })
    );
  }

  const split = splitTrack(model.trajectory.points, currentTime);
  if (split.future.length >= 2) {
    layers.push(
      new PathLayer({
        id: "vessel-future-path",
        data: [{ path: split.future }],
        getPath: (d: { path: [number, number][] }) => d.path,
        getColor: [2, 132, 199, 120],
        getWidth: 1.5,
        widthMinPixels: 1,
      })
    );
  }

  if (showSpill && model.spillGeometry) {
    layers.push(
      new PolygonLayer({
        id: "detected-spill",
        data: polygonToPolygons(model.spillGeometry).map((polygon) => ({ polygon })),
        getPolygon: (d: { polygon: number[][] }) => d.polygon,
        getFillColor: [136, 19, 55, 90],
        getLineColor: [225, 29, 72, 230],
        getLineWidth: 1.6,
        lineWidthMinPixels: 1,
        stroked: true,
        filled: true,
      })
    );
  }

  const forecastGeom = forecastGeometryAtTime(model.spillGeometry, model.forecastFrames, currentTime, model.spillTimestamp);
  if (forecastGeom && currentTime > (model.spillTimestamp ?? currentTime)) {
    layers.push(
      new PolygonLayer({
        id: "forecast-spill",
        data: polygonToPolygons(forecastGeom).map((polygon) => ({ polygon })),
        getPolygon: (d: { polygon: number[][] }) => d.polygon,
        getFillColor: [245, 158, 11, 40],
        getLineColor: [251, 191, 36, 200],
        getLineWidth: 1.4,
        lineWidthMinPixels: 1,
        stroked: true,
        filled: true,
        lineWidthUnits: "pixels",
      })
    );
  }

  const particles = particlesAtTime(model.particles, currentTime, model.spillTimestamp);
  if (particles.length) {
    layers.push(
      new ScatterplotLayer({
        id: "oil-particles",
        data: particles,
        getPosition: (d: { longitude: number; latitude: number }) => [d.longitude, d.latitude],
        getRadius: (d: { size: number }) => d.size,
        radiusUnits: "pixels",
        getFillColor: (d: { opacity: number }) => [15, 23, 42, Math.round(d.opacity * 255)],
        getLineColor: [82, 82, 91, 90],
        lineWidthMinPixels: 0.4,
        stroked: true,
        pickable: false,
      })
    );
  }

  const pose = interpolateVessel(model.trajectory.points, currentTime);
  if (pose) {
    layers.push(
      new ScatterplotLayer({
        id: "vessel-position-dot",
        data: [pose],
        getPosition: (d: { longitude: number; latitude: number }) => [d.longitude, d.latitude],
        getRadius: 5,
        radiusUnits: "pixels",
        getFillColor: [14, 165, 233, 0],
        pickable: false,
      })
    );
  }

  return layers;
}
