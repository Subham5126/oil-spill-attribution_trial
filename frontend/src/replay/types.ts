export type InvestigationReplayState = {
  currentTime: number;
  startTime: number;
  endTime: number;
  isPlaying: boolean;
  playbackRate: number;
};

export type AISPoint = {
  longitude: number;
  latitude: number;
  timestamp: number;
  heading?: number;
  speedKnots?: number;
};

export type VesselTrajectory = {
  vesselId: string;
  vesselName?: string;
  points: AISPoint[];
};

export type VesselPose = {
  longitude: number;
  latitude: number;
  heading: number;
};

export type ForecastFrame = {
  timestamp: number;
  longitude: number;
  latitude: number;
  geometry?: GeoJSON.Polygon | GeoJSON.MultiPolygon;
};

export type OilParticleSeed = {
  id: number;
  birthTime: number;
  longitude: number;
  latitude: number;
  velocityLonPerMs: number;
  velocityLatPerMs: number;
  lifetimeMs: number;
  size: number;
  opacity: number;
  color?: string;
  path?: [number, number][];
  driftDurationMs?: number;
  jitterLon?: number;
  jitterLat?: number;
  targetLon?: number;
  targetLat?: number;
  forecastFrames?: ForecastFrame[];
};

export type ReplayEventMarker = {
  id: string;
  label: string;
  kind: "start" | "end" | "ais" | "spill" | "forecast" | "attribution";
  timestamp: number;
};

export type ReplayAvailability = {
  ais: boolean;
  spillTimestamp: boolean;
  spillGeometry: boolean;
  forecast: boolean;
  driftModel: boolean;
  forecastIsApproximation: boolean;
  aisMessage?: string;
  forecastMessage?: string;
};

export type NearbyVessel = {
  mmsi: number;
  name: string;
  type: string;
  flag?: string;
  latitude: number;
  longitude: number;
  heading: number;
  speedKnots?: number;
  distanceToSpillKm?: number;
  rank?: number;
  attributionScore?: number;
  track?: AISPoint[];
};

export type CurrentVector = {
  longitude: number;
  latitude: number;
  u: number;
  v: number;
  speedMs: number;
  speedKnots: number;
  headingDeg: number;
};

export type IncidentReplayModel = {
  vesselId: string;
  vesselName?: string;
  trajectory: VesselTrajectory;
  tripsPath: [number, number][];
  tripsTimestamps: number[];
  spillGeometry: GeoJSON.Polygon | GeoJSON.MultiPolygon | null;
  spillTimestamp: number | null;
  releaseTimestamp: number | null;
  probableOrigin?: { longitude: number; latitude: number; timestamp?: number | null };
  driftTrajectory: [number, number][];
  forecastFrames: ForecastFrame[];
  particles: OilParticleSeed[];
  detectedSpillParticles?: Array<{ id: number; longitude: number; latitude: number; size: number; opacity: number; color: string }>;
  events: ReplayEventMarker[];
  startTime: number;
  endTime: number;
  availability: ReplayAvailability;
  nearbyVessels: NearbyVessel[];
  currentVectors: CurrentVector[];
  oceanCurrent?: {
    uEastwardMs?: number;
    vNorthwardMs?: number;
    speedMs: number;
    directionDeg: number;
  };
};

