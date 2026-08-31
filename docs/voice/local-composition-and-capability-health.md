# Voice/Audio/Perception local composition

## Boundary

`synapse.voice_composition` is an opt-in composition root. It connects the durable
Voice journal, realtime Voice, audio ports, WebRTC VAD, Faster-Whisper, Piper's
execution boundary, acoustic Perception, Conversation handoff, and the optional
frontend event sink. Domain packages do not import it, and the global bootstrap
does not activate it.

The builder receives device, Conversation, frontend, and execution ports
explicitly. It does not use a service locator or global singleton. Building is
not starting: build does not open a microphone, start playback, transcribe,
synthesize, analyze PCM, submit a Conversation request, or publish a frontend
event.

## Configuration and optional dependencies

`VoicePerceptionConfiguration` owns only composition inputs: the relative SQLite
path, device references, VAD format, STT/TTS provider and model references,
declarative default voice preference, Perception enablement, and policy/retention
references. The default voice preference remains declarative; it is never
evidence that a provider or model is available.

Partial compositions are valid. Missing hardware, Conversation runtime/target,
frontend sink,
Perception, TTS executor, executable, or model is represented in the health
snapshot. A registered or constructed adapter is not operational evidence.
Development mocks are never promoted to production capability.

## Health and derivation

Each component reports `supported`, `degraded`, `unavailable`, or
`not_configured`; persistence additionally preserves `corrupt`,
`schema_mismatch`, and `migration_mismatch`.

- Persistence reports the SQLite schema and migration evidence.
- Audio input and playback distinguish configuration from device availability.
- VAD requires a usable provider/classifier.
- STT distinguishes provider presence from a local model artifact.
- Perception reports acoustic, pitch, pause, and speech-rate support separately;
  visual capabilities remain `not_configured`.
- Conversation health distinguishes contract, runtime, explicit target Agent,
  request path, and response path. All five must be evidenced before support.
- Piper health distinguishes provider/model configuration, executable/model
  evidence, the existing execution contract, injected execution authority, and
  operational execution. A contract alone never means executable authority.
- The frontend contract remains available without a sink; sink absence does not
  block Voice.

The aggregate is decomposed into `voice_input`, `speech_to_text`,
`voice_conversation`, `speech_output`, and `full_duplex_voice`. Full duplex is
`supported` only when both the input-to-Conversation and speech-output paths are
operational. It is `degraded` when Voice Conversation works but output/TTS is
missing, and `unavailable` when the fundamental input path is absent.

## Conversation operational wiring

`LocalConversationHandoff` is consumer-owned by the composition package. It uses
the real `ConversationRuntime` and requires an explicit `PermissionContext` and
target Agent identity. It never resolves a default Agent. A missing or unknown
target is `not_configured` or `unavailable`, not silently replaced.

Submitting a Voice request records a factual `local_chat -> target Agent`
Conversation message with the Voice request, session, utterance, transcription,
turn, correlation, deadline, and provenance identities. It carries a transcript
reference, not durable transcript content. It does not invoke a model, reasoning,
tools, missions, workers, synthesis, or playback.

An authority records its response explicitly through the same Conversation
runtime. The handoff then creates the consumer-owned response reference with all
correspondence identities intact. Voice separately accepts that reference.
Acceptance does not request synthesis. `AgentRuntime` is deliberately not used
by this adapter because its general path may execute model-requested tools.

## Lifecycle and restart

`build()` validates configuration and the SQLite schema/migration checksum, then
returns an inspectable runtime without opening streams. `start_session()`
revalidates configured devices through the realtime boundary and opens the
microphone. `close()` is idempotent; use after close is rejected.

Reopening the same SQLite journal preserves facts. `restore_session()` reconstructs
pending references and reports `reconciliation_required`; it does not open a
stream or reexecute STT, TTS, Perception, playback, or Conversation work. Current
capability health remains separate from historical session state. Raw PCM remains
transient and is not stored in the journal or Perception bundle.

## Piper and the future Sandbox handoff

The Piper adapter and `SpeechExecutionPort` contract exist. Operational Piper
still requires all of: configured provider/model, an available executable and
model artifact, and an injected production execution authority. This repository
currently has no authorized production executor for this composition. Direct
`subprocess`, shell execution, or a provisional local bypass is forbidden.

The future Sandbox concrete driver must accept the existing immutable
`SpeechExecutionRequest`: structured `tool_reference` and `argv`, transient stdin
reference/checksum, working-directory reference, bounded timeout, environment
references, input artifacts, expected output artifacts, correlation, policy, and
capability references. `shell` remains false.

It must return a matching `SpeechExecutionResult` binding request ID and
fingerprint, factual accepted/started observations, one of `exited`,
`timeout_observed`, `cancellation_observed`, `unavailable`, or `failed`, an exit
code only for an observed exit, termination proof when claimed, canonical
stdout/stderr and produced-artifact references, diagnostics, and a valid result
fingerprint. Piper additionally requires the expected WAV artifact reference and
verifies a real non-empty WAV before reporting synthesis success. This is a
consumer requirement only; it does not invent Sandbox admission, grants, or
materialization.

## Operational completion matrix for Slice 14

The health snapshot assigns one freeze classification per capability:

- `voice_input`: internally complete when persistence, input device, and VAD are supported;
- `speech_to_text`: internally complete when Voice input and the local STT model work;
- `acoustic_perception`: internally complete when DSP is enabled and supported;
- `voice_conversation`: internally complete only with runtime, permission, explicit target,
  and both factual message paths;
- `speech_output`: externally blocked while execution authority or required Piper artifacts
  are absent;
- `visual_perception`: intentionally unavailable;
- `full_duplex_voice`: externally blocked when Voice Conversation is complete but speech
  output still depends on the future execution authority.

Slice 14 may declare `OPERATIONALLY COMPLETE` only for entries classified
`internally_complete`. It must preserve `externally_blocked`,
`intentionally_unavailable`, and `incomplete` as distinct outcomes.

## Current limitations and next boundary

Piper/full-duplex Voice remains externally blocked until executable/model and a
Sandbox-compatible production execution authority are evidenced. Visual
Perception providers are intentionally absent. This package adds no
WebSocket/SSE/API delivery and no global bootstrap wiring.

## Frozen baseline

The Slice 14 baseline is frozen by
`tests/architecture/test_voice_audio_perception_freeze.py` and recorded in
`docs/audits/voice-audio-perception-final-freeze-audit.md`. The bounded-context
set is `IMPLEMENTED / ARCHITECTURALLY COMPLETE / FROZEN`; this is not a claim
that speech output, full-duplex Voice, or the backend as a whole is operationally
complete. Future Piper execution, visual Perception providers, public surface or
taxonomy changes require explicit unfreeze/change governance.
