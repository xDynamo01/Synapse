# ADR 0077: Speech Provider Adapter Contract v1

## Status

Accepted.

## Context

Speech Pipeline Runtime currently validates speech flow with deterministic mocks. The next architectural step is not to install Whisper, Piper, Kokoro, Coqui, ElevenLabs, or any other engine directly into core runtimes. Synapse needs a contract layer for speech adapters so future engines can plug in without coupling the core to vendor libraries.

Provider Runtime answers which provider can implement a capability. Speech Adapter Runtime answers which speech-specific adapter exposes that provider implementation to the speech stack.

## Decision

Add `SpeechAdapterRuntime` under `backend/synapse/speech_adapters/`.

The runtime defines:

- `SpeechAdapterManifest`
- `SpeechAdapterHealth`
- `SpeechAdapterCapability`
- `SpeechAdapterResolution`
- `SpeechToTextAdapter`
- `TextToSpeechAdapter`
- `VoiceAnalysisAdapter`
- `SpeechAdapterRegistry`

The built-in registry includes only deterministic mock adapters:

- `mock_stt_adapter`
- `mock_tts_adapter`
- `mock_voice_analysis_adapter`

The runtime is configured by:

```text
DATA_DIR/config/speech_adapter_policy.yaml
```

Adapters point to existing provider IDs such as `mock_stt`, `mock_tts`, and `mock_voice_analysis`, but no real provider is executed.

## Non-Goals

- No Whisper, faster-whisper, Vosk, Piper, Kokoro, Coqui, ElevenLabs, OpenAI TTS, or cloud provider integration.
- No microphone, speaker, streaming, websocket, file audio, real transcription, or real synthesis.
- No frontend changes.
- No replacement of Provider Runtime.

## Consequences

Future speech engines can be implemented as adapters behind this contract. Audio Runtime, Voice Runtime, and Speech Pipeline Runtime can stay stable while adapter implementations evolve independently.

The current implementation keeps mocks deterministic and local-first.
