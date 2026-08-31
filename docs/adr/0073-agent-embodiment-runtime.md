# ADR 0073: Agent Embodiment Runtime

Status: **Superseded / historical** by Voice / Audio / Perception Slice 4.

This ADR records a removed design only. Its package, API, commands, wiring,
health/readiness fields and provider capabilities no longer exist and must not
be used as an active architecture reference. Frontend owns visualization and
animation; Voice owns factual voice states/events; Perception owns multimodal
observations/features/inferences.

## Status

Accepted.

## Context

Agent runtime identity and behavior are already represented by agent config,
SOUL, effective policy, and runtime execution. Future voice, avatar, and
multimodal UI layers need a separate representation for how an agent manifests
to a user.

This presentation layer must not alter agent logic or execute rendering,
speech synthesis, animation, or real providers.

## Decision

Introduce `AgentEmbodimentRuntime` under `backend/synapse/embodiment/`.

It persists one embodiment record per agent:

```text
DATA_DIR/embodiment/{agent_id}.yaml
```

The runtime manages:

- `AgentEmbodiment`
- `AvatarProfile`
- `VoiceProfile`
- `ExpressionProfile`
- `PresenceProfile`
- `EmbodimentSummary`

Provider resolution is delegated to `ProviderRuntime` only. The runtime can
resolve `avatar.render` and `text_to_speech` provider candidates and check
provider health, but it never loads avatar models, starts renderers, synthesizes
voice, runs animation, or calls a provider implementation.

## Events

- `embodiment.registered`
- `embodiment.activated`
- `embodiment.deactivated`
- `embodiment.provider_resolved`
- `embodiment.provider_unavailable`

## Interfaces

Commands:

- `/embodiments`
- `/embodiment <agent_id>`
- `/activate-embodiment <agent_id>`
- `/deactivate-embodiment <agent_id>`

API:

- `GET /embodiments`
- `GET /embodiments/{agent_id}`
- `POST /embodiments/{agent_id}/activate`
- `POST /embodiments/{agent_id}/deactivate`

Health/readiness:

- `embodiment_runtime_available`
- `embodiment_provider_unavailable_count`
- `embodiment.ready`

## Consequences

- Agent identity, behavior, and presentation are separated.
- Future Avatar Runtime, Voice Runtime, and UI can consume embodiment metadata
  without coupling to Agent Runtime internals.
- Provider Runtime remains the resolver for external capability candidates.
- No provider is executed and no real avatar or voice technology is introduced.

## Non-Goals

- No Live2D, VRM, GLB loading, Ready Player Me, NVIDIA ACE, Unity, Unreal,
  ThreeJS, BabylonJS, lip sync, blendshapes, animation, real TTS, or UI.
- No Emotion AI or social inference.
- No automatic permission grants.
