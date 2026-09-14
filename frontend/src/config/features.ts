/**
 * OILTRACE System Feature Flags
 * Controls feature enablement and forensic display modes across the platform.
 */

export const FEATURES = {
  /**
   * Incident Replay Animation Mode
   * Paused to prioritize static GIS evidence, morphometry, ocean currents, and AIS attribution.
   * When false, replay controls and procedural particle loops are cleanly bypassed.
   */
  INCIDENT_REPLAY_ENABLED: false,
} as const;

export type FeatureKey = keyof typeof FEATURES;
