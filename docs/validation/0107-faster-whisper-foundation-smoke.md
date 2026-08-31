# 0107 — Faster-Whisper Foundation Smoke

Goal: verify the first real STT provider is wired through the existing Voice / Audio / Speech Adapter stack.

## Backend checks

- `GET /api/voice/providers` exposes `faster_whisper` alongside the existing mock adapters.
- `POST /api/audio/transcribe` accepts an uploaded audio payload and returns a structured `TranscriptResult`.
- `TranscriptResult` includes:
  - `text`
  - `language`
  - `segments`
  - `duration_ms`
  - `confidence`
  - `speech_features`

## Frontend checks

- Voice settings expose provider, model preset, language, microphone, and microphone test.
- The chat composer microphone button records only on explicit user click.
- Stopping recording sends the captured audio to the backend and fills the text input with the transcript.
- The transcript is never sent automatically.

## Safety checks

- No wake word.
- No background recording.
- No streaming conversation.
- No TTS playback.
- No automatic agent execution.
