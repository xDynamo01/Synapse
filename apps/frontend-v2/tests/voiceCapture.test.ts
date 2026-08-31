import { describe, expect, it, vi } from "vitest";
import {
  isEmptyRecording,
  mergeTranscriptionIntoDraft,
  normalizeVoiceError,
  conversationModeStatusLabel,
  releaseAudioTracks,
  voiceStatusLabel
} from "../src/shared/voiceCapture";

describe("explicit voice recording capture helpers", () => {
  it("detects empty recordings before STT", () => {
    expect(isEmptyRecording(new Blob([]))).toBe(true);
    expect(isEmptyRecording(new Blob(["audio"]))).toBe(false);
  });

  it("fills an empty composer draft with editable transcription", () => {
    expect(mergeTranscriptionIntoDraft("", " hello from stt ")).toBe("hello from stt");
  });

  it("appends transcription without deleting existing draft", () => {
    expect(mergeTranscriptionIntoDraft("manual context", "voice text")).toBe("manual context voice text");
  });

  it("keeps empty transcription from mutating the draft", () => {
    expect(mergeTranscriptionIntoDraft("keep me", "   ")).toBe("keep me");
  });

  it("releases microphone tracks after stop or cancel", () => {
    const stop = vi.fn();
    releaseAudioTracks({ getTracks: () => [{ stop }] } as unknown as MediaStream);

    expect(stop).toHaveBeenCalledOnce();
  });

  it("maps recoverable microphone errors to user-safe copy", () => {
    expect(normalizeVoiceError(new DOMException("denied", "NotAllowedError"))).toBe("Microphone permission was denied.");
    expect(normalizeVoiceError(new DOMException("missing", "NotFoundError"))).toBe("No microphone is available.");
  });

  it("exposes clear composer states", () => {
    expect(voiceStatusLabel("idle", null)).toBeNull();
    expect(voiceStatusLabel("recording", null)).toContain("Recording");
    expect(voiceStatusLabel("transcribing", null)).toContain("Transcribing");
    expect(voiceStatusLabel("failed", "STT unavailable")).toBe("STT unavailable");
  });

  it("exposes clear continuous conversation mode states", () => {
    expect(conversationModeStatusLabel("inactive", null)).toBeNull();
    expect(conversationModeStatusLabel("listening", null)).toContain("listening");
    expect(conversationModeStatusLabel("processing", null)).toContain("processing");
    expect(conversationModeStatusLabel("speaking", null)).toContain("speaking");
    expect(conversationModeStatusLabel("interrupted", null)).toContain("interrupted");
    expect(conversationModeStatusLabel("failed", "TTS unavailable")).toBe("TTS unavailable");
  });
});
