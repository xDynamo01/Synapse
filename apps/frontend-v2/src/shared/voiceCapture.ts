import type { ConversationModeState, VoiceCaptureState } from "./types.js";

export const minimumRecordingBytes = 1;

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
  if (state === "transcribing") {
    return "Conversation Mode transcribing…";
  }
  if (state === "processing") {
    return "Conversation Mode processing response…";
  }
  if (state === "speaking") {
    return "Conversation Mode speaking…";
  }
  if (state === "interrupted") {
    return "Conversation Mode interrupted.";
  }
  return error ?? "Conversation Mode failed.";
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
