# ADR 0069: Vision Runtime Contract

## Status

Accepted.

## Context

Future Synapse stages will need camera sessions, frames, face observations, body observations, posture tracking, visual signals, and provider integrations such as MediaPipe, OpenCV, DeepFace, or OpenSeeFace.

Those capabilities must not be embedded directly into core runtime modules. Synapse needs a stable vision contract before real providers or devices are introduced.

## Decision

Introduce `VisionRuntime` as a contract-only runtime.

The runtime defines:

- `VisionSession`
- `CameraDevice`
- `VisionFrame`
- `FaceObservation`
- `BodyObservation`
- `VisionAnalysisResult`

Vision sessions and mock camera devices persist under:

```text
DATA_DIR/vision/sessions/{session_id}.yaml
DATA_DIR/vision/cameras/{device_id}.yaml
```

The runtime can register mock cameras, capture mock frames, and produce deterministic mock face/body observations.

## Provider Boundary

Vision Runtime uses `ProviderRuntime` to resolve:

- `vision`
- `face_tracking`
- `body_tracking`

No provider is executed in this stage.

## Multimodal Boundary

If a `VisionSession` has `multimodal_session_id`, mock frame capture emits a `vision` channel event and mock analysis emits `face` and `body` channel events.

## Non-Goals

This stage does not implement:

- real camera access
- webcam streaming
- OpenCV
- MediaPipe
- DeepFace
- OpenSeeFace
- pose tracking
- face tracking
- body tracking
- emotion detection
- image/video files
- UI

## Consequences

Benefits:

- Future vision providers have stable request/result contracts.
- Provider resolution stays separate from capability authorization.
- Multimodal sessions can observe mock visual events without real devices.

Limitations:

- Mock frames use `mock://` references only.
- Mock observations are deterministic placeholders.
- Camera registry contains only mock devices.
