# ADR 0068: Audio Runtime Contract

## Status

Accepted.

## Context

Future Synapse stages will need speech-to-text, text-to-speech, voice analysis, audio input, audio output, and audio sessions. These capabilities must be modeled before integrating providers such as Whisper, Vosk, Piper, Kokoro, SpeechBrain, or OpenSMILE.

## Decision

Introduce `AudioRuntime` as a contract-only runtime.

The runtime defines:

- `AudioSession`
- `AudioDevice`
- `AudioInputRequest`
- `AudioOutputRequest`
- `SpeechToTextResult`
- `TextToSpeechResult`

Audio sessions persist under:

```text
DATA_DIR/audio/sessions/{session_id}.yaml
DATA_DIR/audio/devices/{device_id}.yaml
```

The runtime can register mock devices and produce deterministic mock STT/TTS results.

## Provider Boundary

Audio Runtime uses `ProviderRuntime` to resolve:

- `speech_to_text`
- `text_to_speech`
- `voice_analysis`

This does not execute a provider. The current providers are still mock/unconfigured manifests.

## Multimodal Boundary

If an `AudioSession` has `multimodal_session_id`, mock transcription and synthesis append `CommunicationEvent` records to the linked multimodal session.

## Non-Goals

This stage does not implement:

- real microphone access
- real speaker access
- audio streaming
- audio recording
- audio files
- Whisper/faster-whisper/Vosk
- Piper/Kokoro/Coqui
- SpeechBrain/OpenSMILE
- emotion analysis
- UI

## Consequences

Benefits:

- Future real audio providers have stable request/result contracts.
- Provider resolution stays separate from capability authorization.
- Multimodal sessions can observe audio mock events without real devices.

Limitations:

- Mock transcription accepts text directly.
- Mock synthesis returns a `mock://` reference, not an audio artifact.
- Device registry contains only mock devices.
