import type { ConversationModeState, VoiceCaptureState } from "./types.js";

export const minimumRecordingBytes = 1;

export interface ConversationVadConfig {
  speechThreshold: number;
  silenceThreshold: number;
  minSpeechMs: number;
  minSilenceMs: number;
  maxCaptureMs: number;
}

export interface ConversationVadSnapshot {
  amplitude: number;
  speechMs: number;
  silenceMs: number;
  elapsedMs: number;
  started: boolean;
  shouldStart: boolean;
  shouldStop: boolean;
}

export const defaultConversationVadConfig: ConversationVadConfig = {
  speechThreshold: 0.025,
  silenceThreshold: 0.012,
  minSpeechMs: 240,
  minSilenceMs: 780,
  maxCaptureMs: 12_000
};

export function isEmptyRecording(blob: Pick<Blob, "size"> | null | undefined): boolean {
  return !blob || blob.size < minimumRecordingBytes;
}

export function mergeTranscriptionIntoDraft(draft: string, transcript: string): string {
  const cleanTranscript = transcript.trim();
  if (!cleanTranscript) {
    return draft;
  }
  const cleanDraft = draft.trimEnd();
  return cleanDraft ? `${cleanDraft} ${cleanTranscript}` : cleanTranscript;
}

export function isLikelyConversationModeEcho(transcript: string): boolean {
  const words = transcript
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^\p{L}\p{N}\s]/gu, " ")
    .trim()
    .split(/\s+/)
    .filter(Boolean);
  if (words.length < 16) {
    return false;
  }
  const trigrams = new Map<string, number>();
  for (let index = 0; index <= words.length - 3; index += 1) {
    const key = words.slice(index, index + 3).join(" ");
    trigrams.set(key, (trigrams.get(key) ?? 0) + 1);
  }
  const maxTrigramCount = Math.max(0, ...trigrams.values());
  const repeatedQuePattern = words.filter((word) => word === "que" || word === "e").length / words.length;
  return maxTrigramCount >= 4 || repeatedQuePattern > 0.72;
}

export function updateConversationVad(
  previous: ConversationVadSnapshot | null,
  amplitude: number,
  deltaMs: number,
  config: ConversationVadConfig = defaultConversationVadConfig
): ConversationVadSnapshot {
  const safeDeltaMs = Math.max(0, deltaMs);
  const elapsedMs = (previous?.elapsedMs ?? 0) + safeDeltaMs;
  const hadStarted = previous?.started ?? false;
  const speechMs = amplitude >= config.speechThreshold
    ? (previous?.speechMs ?? 0) + safeDeltaMs
    : (hadStarted ? (previous?.speechMs ?? 0) : 0);
  const shouldStart = !hadStarted && speechMs >= config.minSpeechMs;
  const started = hadStarted || shouldStart;
  const silenceMs = started && amplitude <= config.silenceThreshold
    ? (previous?.silenceMs ?? 0) + safeDeltaMs
    : 0;
  const shouldStop =
    (started && silenceMs >= config.minSilenceMs) ||
    elapsedMs >= config.maxCaptureMs;
  return {
    amplitude,
    speechMs,
    silenceMs,
    elapsedMs,
    started,
    shouldStart,
    shouldStop
  };
}

export function releaseAudioTracks(stream: MediaStream | null | undefined): void {
  for (const track of stream?.getTracks() ?? []) {
    track.stop();
  }
}

export function voiceStatusLabel(state: VoiceCaptureState, error: string | null): string | null {
  if (state === "recording") {
    return "Recording… click stop to transcribe or cancel to discard.";
  }
  if (state === "transcribing") {
    return "Transcribing audio…";
  }
  if (state === "failed") {
    return error ?? "Voice transcription failed.";
  }
  return null;
}

export function conversationModeStatusLabel(state: ConversationModeState, error: string | null): string | null {
  if (state === "inactive") {
    return null;
  }
  if (state === "idle") {
    return "Conversation Mode active.";
  }
  if (state === "listening") {
    return "Conversation Mode listening…";
  }
  if (state === "capturing") {
    return "Conversation Mode recording speech…";
  }
  if (state === "finalizing") {
    return "Conversation Mode finishing recording…";
  }
  if (state === "transcribing") {
    return "Conversation Mode transcribing…";
  }
  if (state === "generating") {
    return "Conversation Mode generating response…";
  }
  if (state === "synthesizing") {
    return "Conversation Mode preparing audio…";
  }
  if (state === "processing") {
    return "Conversation Mode processing response…";
  }
  if (state === "speaking") {
    return "Conversation Mode speaking…";
  }
  if (state === "cooldown") {
    return "Conversation Mode preparing to listen…";
  }
  if (state === "interrupted") {
    return "Conversation Mode interrupted.";
  }
  return error ?? "Conversation Mode failed.";
}

export function conversationModeCapturesMicrophone(state: ConversationModeState): boolean {
  return state === "listening" || state === "capturing" || state === "finalizing";
}

export function normalizeVoiceError(error: unknown): string {
  if (error instanceof DOMException && error.name === "NotAllowedError") {
    return "Microphone permission was denied.";
  }
  if (error instanceof DOMException && error.name === "NotFoundError") {
    return "No microphone is available.";
  }
  if (error instanceof Error) {
    return error.message;
  }
  return String(error);
}
