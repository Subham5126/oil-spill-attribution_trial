/**
 * ReplayParticleEngine — compatibility façade.
 * Particle state is derived from investigationTime; there is no independent clock.
 */
export { seedOilParticles, seedDetectedSpillParticles, particlesAtTime } from "../replay/particles";
export { computeParticleCloudHull } from "../replay/geometry";
export type { OilParticleSeed as ReplayParticle } from "../replay/types";

