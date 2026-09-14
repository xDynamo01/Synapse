import { describe, expect, it } from "vitest";
import { derivePresenceState, presencePerformanceBudget } from "../src/shared/presenceAdapter";
import type { PresenceApplicationFacts } from "../src/shared/presenceAdapter";

const baseFacts: PresenceApplicationFacts = {
  backendState: "ready",
  conversationStatus: "idle",
  manualVoiceState: "idle",
  conversationModeState: "inactive",
  audioAmplitude: 0,
  reducedMotion: false,
  focused: true
};

describe("presence adapter", () => {
  it("maps idle facts to a Synapse idle scene", () => {
    const scene = derivePresenceState(baseFacts);

    expect(scene.state).toBe("idle");
    expect(scene.label).toBe("Synapse idle");
    expect(scene.amplitude).toBe(0);
  });

  it("maps manual recording to listening with clamped real amplitude", () => {
    const scene = derivePresenceState({ ...baseFacts, manualVoiceState: "recording", audioAmplitude: 2 });

    expect(scene.state).toBe("listening");
    expect(scene.amplitude).toBe(1);
  });

  it("maps manual transcription lifecycle without auto-speaking", () => {
    const scene = derivePresenceState({ ...baseFacts, manualVoiceState: "transcribing", audioAmplitude: 0.7 });

    expect(scene.state).toBe("transcribing");
    expect(scene.amplitude).toBe(0);
  });

  it("maps text turns to processing", () => {
    expect(derivePresenceState({ ...baseFacts, conversationStatus: "sending" }).state).toBe("processing");
    expect(derivePresenceState({ ...baseFacts, conversationStatus: "streaming" }).state).toBe("processing");
  });

  it("maps Conversation Mode states to scene states", () => {
    expect(derivePresenceState({ ...baseFacts, conversationModeState: "listening" }).state).toBe("listening");
    expect(derivePresenceState({ ...baseFacts, conversationModeState: "processing" }).state).toBe("processing");
    expect(derivePresenceState({ ...baseFacts, conversationModeState: "speaking", audioAmplitude: 0.4 }).state).toBe("speaking");
    expect(derivePresenceState({ ...baseFacts, conversationModeState: "speaking", audioAmplitude: 0.4 }).amplitude).toBe(0.4);
    expect(derivePresenceState({ ...baseFacts, conversationModeState: "cooldown" }).state).toBe("cooldown");
  });

  it("preserves interruption and error states explicitly", () => {
    expect(derivePresenceState({ ...baseFacts, conversationStatus: "cancelled" }).state).toBe("interrupted");
    expect(derivePresenceState({ ...baseFacts, conversationModeState: "interrupted" }).state).toBe("interrupted");
    expect(derivePresenceState({ ...baseFacts, manualVoiceState: "failed" }).state).toBe("failed");
    expect(derivePresenceState({ ...baseFacts, backendState: "disconnected" }).state).toBe("disconnected");
  });

  it("uses a reduced-motion and unfocused performance budget", () => {
    const reduced = derivePresenceState({ ...baseFacts, conversationStatus: "streaming", reducedMotion: true });
    const unfocused = derivePresenceState({ ...baseFacts, focused: false });

    expect(reduced.particleCount).toBeLessThanOrEqual(presencePerformanceBudget.reducedMotionParticles);
    expect(reduced.motionScale).toBe(0.12);
    expect(unfocused.motionScale).toBe(0.42);
  });
});
