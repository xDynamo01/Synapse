# ADR 0107: Voice / Audio Foundation v1

Status: accepted

## Context

Synapse already had durable voice-session scaffolding, but it lacked the first operator-facing voice/audio foundation needed for local STT workflows. The desktop app needed a predictable way to choose a speech-to-text provider, inspect microphone devices, record audio locally, persist recordings, and attach a manual transcription without introducing voice playback, wake word handling, or live streaming.

## Decision

Add a first-stage voice/audio foundation composed of:

- `VoiceRuntime` settings persistence under `DATA_DIR/voice/settings.yaml`
- local recording persistence under `DATA_DIR/voice/recordings/`
- microphone device listing and microphone availability testing
- provider summaries for STT-capable speech adapters
- manual audio capture and manual transcription in the frontend Voice panel
- a read-only tool runtime entry for inspecting stored recordings

The workspace exposes Voice as a secondary panel. The frontend consumes backend voice contracts only; it does not own provider state or recording persistence.

## Non-goals

- TTS playback
- wake word detection
- streaming transcription
- automatic microphone activation
- voice-driven agent execution
- agent listening loops
- browser-side speech inference

## Consequences

The project now has a stable STT-oriented voice foundation that can be expanded later without changing the basic data model. Future steps can add richer device validation, provider integrations, and streaming behavior while reusing the same persisted contracts.
