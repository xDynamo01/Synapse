import { describe, expect, it, vi } from "vitest";
import {
  conversationModeCapturesMicrophone,
  conversationModeStatusLabel,
  defaultConversationVadConfig,
  isEmptyRecording,
  isLikelyConversationModeEcho,
  mergeTranscriptionIntoDraft,
  normalizeVoiceError,
  releaseAudioTracks,
  updateConversationVad,
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

  it("detects repeated conversation-mode echo transcripts", () => {
    expect(isLikelyConversationModeEcho("O que é o que é o que é o que é o que é o que é o que é o que é o que é")).toBe(true);
    expect(isLikelyConversationModeEcho("qual é o seu nome e como voce pode me ajudar hoje")).toBe(false);
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
    expect(conversationModeStatusLabel("capturing", null)).toContain("recording speech");
    expect(conversationModeStatusLabel("finalizing", null)).toContain("finishing");
    expect(conversationModeStatusLabel("processing", null)).toContain("processing");
    expect(conversationModeStatusLabel("generating", null)).toContain("generating");
    expect(conversationModeStatusLabel("synthesizing", null)).toContain("preparing audio");
    expect(conversationModeStatusLabel("speaking", null)).toContain("speaking");
    expect(conversationModeStatusLabel("cooldown", null)).toContain("preparing");
    expect(conversationModeStatusLabel("interrupted", null)).toContain("interrupted");
    expect(conversationModeStatusLabel("failed", "TTS unavailable")).toBe("TTS unavailable");
  });

  it("does not reserve manual STT after conversation mode stops or fails", () => {
    expect(conversationModeCapturesMicrophone("inactive")).toBe(false);
    expect(conversationModeCapturesMicrophone("interrupted")).toBe(false);
    expect(conversationModeCapturesMicrophone("failed")).toBe(false);
    expect(conversationModeCapturesMicrophone("idle")).toBe(false);
    expect(conversationModeCapturesMicrophone("listening")).toBe(true);
    expect(conversationModeCapturesMicrophone("capturing")).toBe(true);
    expect(conversationModeCapturesMicrophone("finalizing")).toBe(true);
    expect(conversationModeCapturesMicrophone("transcribing")).toBe(false);
    expect(conversationModeCapturesMicrophone("processing")).toBe(false);
    expect(conversationModeCapturesMicrophone("generating")).toBe(false);
    expect(conversationModeCapturesMicrophone("synthesizing")).toBe(false);
    expect(conversationModeCapturesMicrophone("speaking")).toBe(false);
    expect(conversationModeCapturesMicrophone("cooldown")).toBe(false);
  });

  it("starts a conversation turn after sustained speech", () => {
    const config = { ...defaultConversationVadConfig, minSpeechMs: 200 };
    const first = updateConversationVad(null, 0.03, 100, config);
    const second = updateConversationVad(first, 0.03, 100, config);

    expect(first.started).toBe(false);
    expect(second.started).toBe(true);
    expect(second.shouldStart).toBe(true);
  });

  it("closes a conversation turn after sustained silence", () => {
    const config = { ...defaultConversationVadConfig, minSpeechMs: 100, minSilenceMs: 200 };
    const speech = updateConversationVad(null, 0.04, 120, config);
    const firstSilence = updateConversationVad(speech, 0.001, 100, config);
    const secondSilence = updateConversationVad(firstSilence, 0.001, 100, config);

    expect(speech.started).toBe(true);
    expect(firstSilence.shouldStop).toBe(false);
    expect(secondSilence.shouldStop).toBe(true);
  });
});
