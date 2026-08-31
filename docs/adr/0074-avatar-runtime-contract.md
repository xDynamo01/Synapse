# ADR 0074: Avatar Runtime Contract v1

Status: **Superseded / historical** by Voice / Audio / Perception Slice 4.

This ADR records a removed design only. No Avatar Runtime exists in the target
architecture; visualization and animation belong to the frontend. The package,
API, commands, wiring, health/readiness fields, capabilities and renderer
manifests described below were physically removed.

## Status

Accepted.

## Context

Synapse now has provider manifests, multimodal communication primitives, audio and vision contracts, perception signals, context fusion, and agent embodiment records. Future avatar work needs a stable backend contract before any renderer, model format, animation system, lip sync engine, or UI is introduced.

Without this layer, avatar-facing features would risk coupling directly to embodiment profiles, provider manifests, or frontend-specific state.

## Decision

Add `AvatarRuntime` as a local-first contract runtime under `backend/synapse/avatar/`.

The runtime persists avatar sessions under:

```text
DATA_DIR/avatar/sessions/{session_id}.yaml
```

It manages:

- `AvatarSession`
- `AvatarState`
- `AvatarExpression`
- `AvatarPose`
- `LipSyncState`
- `AvatarSummary`

Avatar sessions reference an agent and may reference an embodiment/avatar profile. Avatar state records expression, pose, eye direction, speaking/listening flags, animation state, and mock lip sync metadata.

Provider resolution is passive. `AvatarRuntime` can resolve `avatar.render` via Agent Embodiment Runtime and Provider Runtime, but it does not execute a renderer.

## Non-Goals

- No Three.js, React Three Fiber, Babylon, Unity, Unreal, VRM, Live2D, GLB, Ready Player Me, NVIDIA ACE, or Avatar SDK integration.
- No rendering.
- No blendshape solving.
- No real animation.
- No real lip sync.
- No camera or MediaPipe integration.
- No frontend changes.

## Consequences

Future UI, Avatar Runtime implementations, and provider adapters can consume a stable session/state contract without depending on internal agent identity or provider models.

Health and readiness can report avatar runtime availability and provider reference issues.

The runtime remains safe for local-first development because it stores only structured state and never invokes external providers or GPU/native renderer code.
