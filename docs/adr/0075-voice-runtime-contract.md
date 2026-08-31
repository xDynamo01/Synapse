# ADR 0075: Voice Runtime Contract

## Status

Accepted.

## Context

Synapse has provider manifests and audio contracts. Historical Voice sessions also carried Avatar/Embodiment identifiers and directly drove visual speaking/animation state, coupling factual speech lifecycle to rendering concerns.

## Decision

Add `VoiceRuntime` under `backend/synapse/voice/`.

Voice Runtime owns system voice configuration. Synapse uses one default system voice. Agents do not own voice profiles, and Avatar/Embodiment do not participate in STT or TTS selection.

The versioned global configuration explicitly identifies the STT provider/model, TTS provider/model/default voice, locale, input/output devices, provider configuration references, and policy version. Provider resolution is an exact match against Speech Adapter capabilities and reports `supported`, `degraded`, or `unavailable`; it does not silently choose another adapter or a mock. A mock remains valid only when explicitly configured for development or tests.

The default preference is `female`, but it is only a desired characteristic. Voice Runtime does not infer gender from a model or voice name. A provider must declare the characteristic explicitly before the preference can be treated as satisfied. Piper may therefore be configured as desired while still being reported unavailable when its executable or model is absent.

The runtime persists voice sessions and utterances under:

```text
DATA_DIR/voice/sessions/{session_id}.yaml
DATA_DIR/voice/utterances/{utterance_id}.yaml
```

Voice owns only factual voice lifecycle: `idle`, `listening`, `recording`, `processing`, `thinking`, `queued`, `speaking`, `paused`, `cancelling`, `cancelled`, `closed`, `error`, and `failed`, plus speech-started, speech-ended, and interruption events where applicable. `speaking` describes Voice activity; it is not visual state.

Voice neither imports nor consults Avatar/Embodiment and never writes animation, expression, pose, lip-sync, presence, or display state. A future frontend integration may render Voice facts, but frontend rendering remains outside backend Voice authority.

## Non-Goals

- No Piper installation, model download, or execution change in this slice.
- No audio playback, streaming, websocket, real lip sync, Emotion AI, or UI changes.
- No multiple voices or per-agent personalization; those are future capabilities.

## Consequences

Provider selection belongs to Voice and remains factual when configured software is unavailable. Visual metadata, character/persona, expression, pose, display mode, lip-sync, animation, and presence state remain outside Voice configuration.

New Voice records contain no Avatar/Embodiment references. The reader discards historical `embodiment_id`, `avatar_session_id`, and `animation_state` keys and the next Voice write removes them; no compatibility alias is exposed or newly persisted. This one-way legacy reader is reserved for removal after legacy data retirement evidence is available.

Slice 4 completed the physical removal of Avatar/Embodiment. The one-way legacy
reader remains the sole compatibility exception; redesign of Voice persistence
is reserved for a separately authorized slice.
