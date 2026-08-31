# ADR 0070: Perception Signal Runtime

## Status

Accepted.

## Context

Audio and Vision runtimes define their own contracts. Future stages will add STT, TTS, voice analysis, face tracking, body tracking, gaze, gestures, and other multimodal signals. Context Fusion needs a single normalized signal format before any real perception provider is integrated.

## Decision

Introduce `PerceptionRuntime` as a passive signal normalization layer.

The runtime defines:

- `PerceptionSignal`
- `PerceptionBatch`
- `SignalSummary`
- `SignalType`

Initial signal types:

- `speech`
- `voice`
- `face`
- `body`
- `gaze`
- `emotion`
- `engagement`
- `stress`
- `silence`
- `gesture`
- `system`

Signals persist under:

```text
DATA_DIR/perception/signals.jsonl
DATA_DIR/perception/batches/{batch_id}.yaml
```

## Converters

This stage adds deterministic converters only:

- `SpeechToTextResult` to `speech`
- `TextToSpeechResult` to `voice`
- `FaceObservation` to `face`
- `BodyObservation` to `body`
- `VisionAnalysisResult` to `PerceptionBatch`

Converters do not infer emotion, intent, social meaning, stress, gaze, or engagement beyond copying existing payload fields.

## Multimodal Boundary

`emit_signal()` can publish a `CommunicationEvent` to a linked multimodal session using the appropriate channel. This is still event normalization, not real perception.

## Non-Goals

This stage does not implement:

- SpeechBrain
- OpenSMILE
- Whisper
- MediaPipe
- OpenCV
- DeepFace
- OpenSeeFace
- emotion AI
- LLM reasoning
- Context Fusion
- memory writes
- embeddings
- UI

## Consequences

Benefits:

- Future perception providers share one normalized signal format.
- Context Fusion can consume a stable runtime later.
- Audio and Vision runtimes remain independent.

Limitations:

- Signals are only as meaningful as their source payloads.
- No real emotional or social inference exists.
- No fusion or agent context injection exists yet.
