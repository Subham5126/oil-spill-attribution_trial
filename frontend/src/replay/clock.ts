import type { InvestigationReplayState } from "./types";
import { clampTime } from "./time";

/** At 1×, 1 real wall second advances 60 investigation seconds (1 minute). (60_000 inv ms / 1_000 wall ms = 60 scale) */
export const INVESTIGATION_MS_PER_WALL_MS_AT_1X = 60;

const PLAYBACK_RATES = [0.5, 1, 2, 5, 10, 20] as const;
export type PlaybackRate = (typeof PLAYBACK_RATES)[number];

export function isPlaybackRate(value: number): value is PlaybackRate {
  return (PLAYBACK_RATES as readonly number[]).includes(value as PlaybackRate);
}

export function createReplayState(startTime: number, endTime: number, playbackRate: number = 1): InvestigationReplayState {
  const start = Number.isFinite(startTime) ? startTime : 0;
  const end = Number.isFinite(endTime) && endTime > start ? endTime : start;
  return {
    currentTime: start,
    startTime: start,
    endTime: end,
    isPlaying: false,
    playbackRate: isPlaybackRate(playbackRate) ? playbackRate : 1,
  };
}

export function advanceClock(
  state: InvestigationReplayState,
  elapsedWallMs: number,
  scale: number = INVESTIGATION_MS_PER_WALL_MS_AT_1X
): InvestigationReplayState {
  if (!state.isPlaying) return state;
  if (elapsedWallMs <= 0) return state;
  if (state.endTime <= state.startTime) {
    return { ...state, currentTime: state.endTime, isPlaying: false };
  }
  const next = state.currentTime + elapsedWallMs * state.playbackRate * scale;
  if (next >= state.endTime) {
    return { ...state, currentTime: state.endTime, isPlaying: false };
  }
  return { ...state, currentTime: next };
}

export function playClock(state: InvestigationReplayState): InvestigationReplayState {
  if (state.currentTime >= state.endTime && state.endTime > state.startTime) {
    return { ...state, isPlaying: false, currentTime: state.endTime };
  }
  return { ...state, isPlaying: true };
}

export function pauseClock(state: InvestigationReplayState): InvestigationReplayState {
  return { ...state, isPlaying: false };
}

export function togglePlay(state: InvestigationReplayState): InvestigationReplayState {
  return state.isPlaying ? pauseClock(state) : playClock(state);
}

export function replayFromStart(state: InvestigationReplayState): InvestigationReplayState {
  return { ...state, currentTime: state.startTime, isPlaying: false };
}

export function seekClock(state: InvestigationReplayState, timeMs: number): InvestigationReplayState {
  return {
    ...state,
    currentTime: clampTime(timeMs, state.startTime, state.endTime),
  };
}

export function seekNormalized(state: InvestigationReplayState, t01: number): InvestigationReplayState {
  const span = state.endTime - state.startTime;
  const clamped = Math.min(1, Math.max(0, t01));
  return seekClock(state, state.startTime + clamped * span);
}

export function setPlaybackRate(state: InvestigationReplayState, rate: number): InvestigationReplayState {
  return { ...state, playbackRate: isPlaybackRate(rate) ? rate : state.playbackRate };
}

const safeRaf =
  typeof requestAnimationFrame !== "undefined"
    ? requestAnimationFrame
    : (cb: (t: number) => void) => setTimeout(() => cb(Date.now()), 16) as unknown as number;

const safeCaf =
  typeof cancelAnimationFrame !== "undefined"
    ? cancelAnimationFrame
    : (id: number) => clearTimeout(id as unknown as ReturnType<typeof setTimeout>);

/**
 * Single-owner rAF loop. Calling start() while already running is a no-op.
 * The loop only advances the canonical clock; visualization must be derived from currentTime.
 */
export function createInvestigationClockLoop(options: {
  getState: () => InvestigationReplayState;
  setState: (next: InvestigationReplayState) => void;
  onFrame?: (state: InvestigationReplayState) => void;
  scale?: number;
}) {
  let rafId: number | null = null;
  let lastWall: number | null = null;

  const tick = (now: number) => {
    const state = options.getState();
    if (!state.isPlaying) {
      rafId = null;
      lastWall = null;
      return;
    }
    if (lastWall != null) {
      const next = advanceClock(state, now - lastWall, options.scale ?? INVESTIGATION_MS_PER_WALL_MS_AT_1X);
      options.setState(next);
      options.onFrame?.(next);
      if (!next.isPlaying) {
        rafId = null;
        lastWall = null;
        return;
      }
    }
    lastWall = now;
    rafId = safeRaf(tick);
  };

  return {
    start() {
      if (rafId != null) return;
      lastWall = null;
      rafId = safeRaf(tick);
    },
    stop() {
      if (rafId != null) safeCaf(rafId);
      rafId = null;
      lastWall = null;
    },
    get isRunning() {
      return rafId != null;
    },
  };
}
