# ADR 0067: Multimodal Communication Architecture

## Status

Accepted.

## Context

Future Synapse stages will need speech, voice, vision, face, body, emotion, presence, and interaction context. Those areas must share one language for sessions, channels, events, and metadata before real audio, video, camera, microphone, or perception providers are integrated.

## Decision

Introduce `MultimodalCommunicationRuntime` as a passive foundation for multimodal communication.

The runtime defines:

- `CommunicationChannel`
- `CommunicationEvent`
- `CommunicationSession`
- `SignalMetadata`

Supported initial channels:

- `text`
- `audio`
- `voice`
- `vision`
- `face`
- `body`
- `system`

Sessions persist under:

```text
DATA_DIR/multimodal/sessions/{session_id}.yaml
DATA_DIR/multimodal/sessions/{session_id}.events.jsonl
```

## Boundaries

This runtime does not implement:

- STT
- TTS
- microphone access
- camera access
- video streaming
- audio streaming
- MediaPipe/OpenCV integration
- emotion analysis

Provider IDs may appear in event metadata, but Provider Runtime is not invoked by this stage.

## Relationship To Conversation Runtime

`CommunicationSession.metadata.conversation_id` can reference a conversation. This keeps multimodal sessions linkable without replacing or coupling to `ConversationRuntime`.

Conversation Runtime remains the source of truth for agent conversations.

## Relationship To Provider Runtime

Provider Runtime answers which provider can implement a capability. Multimodal Communication Runtime only records sessions and events. Provider resolution and provider execution remain future concerns.

## Consequences

Benefits:

- Future voice, vision, and perception runtimes can share consistent event/session models.
- DATA_DIR stays the persistence source.
- Events are observable through EventBus.
- No heavy external dependency is introduced.

Limitations:

- No signal processing exists yet.
- No real devices or streams exist yet.
- No UI is introduced.

## Future Strategy

Audio Runtime, Vision Runtime, Perception Signal Runtime, and Context Fusion Runtime build on these shared communication primitives. Frontend owns visualization and animation; no backend Avatar or Embodiment Runtime exists in the target architecture.
