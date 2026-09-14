import type { BackendConnectionState, ConversationModeState, ConversationRuntimeState, VoiceCaptureState } from "./types.js";

export type PresenceOperationalState =
  | "idle"
  | "listening"
  | "capturing"
  | "finalizing"
  | "transcribing"
  | "generating"
  | "synthesizing"
  | "processing"
  | "speaking"
  | "cooldown"
  | "interrupted"
  | "failed"
  | "disconnected";

export interface PresenceApplicationFacts {
  backendState: BackendConnectionState;
  conversationStatus: ConversationRuntimeState;
  manualVoiceState: VoiceCaptureState;
  conversationModeState: ConversationModeState;
  audioAmplitude: number;
  reducedMotion: boolean;
  focused: boolean;
}

export interface PresenceSceneState {
  state: PresenceOperationalState;
  label: string;
  amplitude: number;
  particleCount: number;
  pulseRate: number;
  coreRadius: number;
  haloOpacity: number;
  motionScale: number;
  accent: "cyan" | "amber" | "red" | "gray";
}

export const presencePerformanceBudget = {
  maxParticles: 96,
  reducedMotionParticles: 28,
  focusedFps: 45,
  unfocusedFps: 12
} as const;

export function derivePresenceState(facts: PresenceApplicationFacts): PresenceSceneState {
  const state = operationalState(facts);
  const reduced = facts.reducedMotion;
  const focusScale = facts.focused ? 1 : 0.42;
  const motionScale = reduced ? 0.12 : focusScale;
  const amplitude = clamp01(facts.audioAmplitude);
  const base = baseScene(state);
  return {
    ...base,
    label: `Synapse ${state}`,
    amplitude: state === "listening" || state === "capturing" || state === "speaking" ? amplitude : 0,
    particleCount: reduced
      ? Math.min(base.particleCount, presencePerformanceBudget.reducedMotionParticles)
      : base.particleCount,
    pulseRate: base.pulseRate * motionScale,
    motionScale
  };
}

function operationalState(facts: PresenceApplicationFacts): PresenceOperationalState {
  if (facts.backendState === "disconnected" || facts.conversationStatus === "disconnected") {
    return "disconnected";
  }
  if (facts.backendState === "error" || facts.conversationStatus === "failed") {
    return "failed";
  }
  if (facts.conversationModeState !== "inactive") {
    if (facts.conversationModeState === "failed") {
      return "failed";
    }
    if (facts.conversationModeState === "idle") {
      return "idle";
    }
    return facts.conversationModeState;
  }
  if (facts.manualVoiceState === "recording") {
    return "listening";
  }
  if (facts.manualVoiceState === "transcribing") {
    return "transcribing";
  }
  if (facts.manualVoiceState === "failed") {
    return "failed";
  }
  if (facts.conversationStatus === "sending" || facts.conversationStatus === "streaming" || facts.conversationStatus === "restoring") {
    return "processing";
  }
  if (facts.conversationStatus === "cancelled") {
    return "interrupted";
  }
  return "idle";
}

function baseScene(state: PresenceOperationalState): Omit<PresenceSceneState, "label" | "amplitude" | "motionScale"> {
  switch (state) {
    case "listening":
      return { state, particleCount: 76, pulseRate: 1.4, coreRadius: 74, haloOpacity: 0.32, accent: "cyan" };
    case "capturing":
      return { state, particleCount: 82, pulseRate: 1.55, coreRadius: 74, haloOpacity: 0.34, accent: "cyan" };
    case "finalizing":
      return { state, particleCount: 78, pulseRate: 1.3, coreRadius: 70, haloOpacity: 0.28, accent: "cyan" };
    case "transcribing":
      return { state, particleCount: 84, pulseRate: 1.7, coreRadius: 68, haloOpacity: 0.28, accent: "cyan" };
    case "generating":
      return { state, particleCount: 94, pulseRate: 2.0, coreRadius: 76, haloOpacity: 0.35, accent: "cyan" };
    case "synthesizing":
      return { state, particleCount: 86, pulseRate: 1.6, coreRadius: 76, haloOpacity: 0.33, accent: "cyan" };
    case "processing":
      return { state, particleCount: 96, pulseRate: 2.1, coreRadius: 76, haloOpacity: 0.36, accent: "cyan" };
    case "speaking":
      return { state, particleCount: 88, pulseRate: 1.8, coreRadius: 78, haloOpacity: 0.34, accent: "cyan" };
    case "cooldown":
      return { state, particleCount: 72, pulseRate: 0.45, coreRadius: 76, haloOpacity: 0.26, accent: "cyan" };
    case "interrupted":
      return { state, particleCount: 54, pulseRate: 0.6, coreRadius: 64, haloOpacity: 0.18, accent: "amber" };
    case "failed":
      return { state, particleCount: 36, pulseRate: 0.35, coreRadius: 60, haloOpacity: 0.14, accent: "red" };
    case "disconnected":
      return { state, particleCount: 28, pulseRate: 0.22, coreRadius: 58, haloOpacity: 0.10, accent: "gray" };
    case "idle":
      return { state, particleCount: 72, pulseRate: 0.55, coreRadius: 76, haloOpacity: 0.30, accent: "cyan" };
  }
}

function clamp01(value: number): number {
  if (!Number.isFinite(value)) {
    return 0;
  }
  return Math.max(0, Math.min(1, value));
}
