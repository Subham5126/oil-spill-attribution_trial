/**
 * OILTRACE System Feature Flags
 * Controls feature enablement and forensic display modes across the platform.
 */

export const FEATURES = {
  /**
   * Incident Replay Animation Mode
   * Enables interactive forensic playback and procedural particle loops.
   */
  INCIDENT_REPLAY_ENABLED: true,
} as const;

export type FeatureKey = keyof typeof FEATURES;
