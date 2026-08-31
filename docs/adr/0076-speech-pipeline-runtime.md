# ADR 0076: Speech Pipeline Runtime v1

## Status

Accepted.

## Context

Synapse has separate contracts for Audio Runtime, Voice Runtime, Perception Runtime, Multimodal Runtime, and Provider Runtime. These runtimes can represent audio sessions, mock STT/TTS results, queued utterances, perception signals, and multimodal events, but there was no single runtime that exercised the end-to-end speech flow.

Before real providers such as Whisper, Piper, Kokoro, Coqui, or cloud TTS are introduced, the system needs a deterministic local pipeline that validates the architecture without using microphone, speaker, streaming, or external provider execution.

## Decision

Add `SpeechPipelineRuntime` under `backend/synapse/speech_pipeline/`.

The runtime persists:

```text
DATA_DIR/speech_pipeline/sessions/{pipeline_session_id}.yaml
DATA_DIR/speech_pipeline/input_turns/{turn_id}.yaml
DATA_DIR/speech_pipeline/output_turns/{turn_id}.yaml
```

It manages:

- `SpeechPipelineSession`
- `SpeechInputTurn`
- `SpeechOutputTurn`
- `SpeechPipelineSummary`

`process_mock_input()` orchestrates Audio Runtime mock transcription, optional Perception Runtime speech signal creation, optional multimodal event emission, and input turn persistence.

`process_mock_output()` orchestrates Voice Runtime utterance queueing, Audio Runtime mock synthesis, utterance ready/completed transitions, optional perception signal creation, optional multimodal event emission, and output turn persistence.

The runtime is controlled by:

```text
DATA_DIR/config/speech_pipeline_policy.yaml
```

## Non-Goals

- No real STT.
- No real TTS.
- No microphone access.
- No speaker playback.
- No audio files.
- No streaming.
- No websocket.
- No lip sync.
- No Emotion AI.
- No UI changes.

## Consequences

The speech architecture can now be validated end to end with deterministic local mocks while preserving separation between Audio Runtime, Voice Runtime, Perception Runtime, and Multimodal Runtime. Frontend visualization and animation remain outside backend authority.

Future real providers can replace mock STT/TTS behind existing runtimes without changing the pipeline contract.
