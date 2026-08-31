# Voice Frontend Event Boundary V1

## Authority and format

`voice-frontend-event-v1` is an immutable, transport-neutral notification
contract derived from Voice facts. Voice owns operational lifecycle facts. The
frontend owns animation, waveform rendering, color, easing, particles, and every
other visual decision. These events are not a second lifecycle source of truth.

Each event carries event/session identity, closed event type, occurrence time,
correlation, monotonic event revision, causal Voice revision, provenance, and
optional utterance/Conversation-turn/capability references. Metadata is bounded
to factual operational values and rejects transcript text, PCM, audio payloads,
waveform/amplitude/frequency, reasoning, animation, Avatar, expression, and
emotion fields.

## Event taxonomy and projection

The closed V1 taxonomy is `IDLE`, `LISTENING`, `SPEECH_STARTED`, `SPEECH_ENDED`,
`PROCESSING`, `SPEAKING_STARTED`, `SPEAKING_ENDED`, `INTERRUPTION_DETECTED`,
`INTERRUPTION_REQUESTED`, `INTERRUPTION_CONFIRMED`, `PAUSED`, `CANCELLING`,
`CANCELLED`, `RECONCILIATION_REQUIRED`, `UNAVAILABLE`, and `ERROR`.

The rebuildable presentation projection is limited to `idle`, `listening`,
`speech-detected`, `processing`, `speaking`, `interrupted`, `paused`,
`unavailable`, and `error`. It cannot mutate Voice.

`processing` means only an operational pending phase: transcription,
Perception/Conversation response, or synthesis before playback. It never means
Agent cognition, reasoning, chain-of-thought, or the legacy API label `thinking`.

VAD `speech.started`/`speech.ended` are the only speech-detection authority.
Synthesis readiness/request does not imply speaking. `SPEAKING_STARTED` requires
observed playback start, and playback completion produces `SPEAKING_ENDED`.

Interruption detection, stop request, and confirmed stop remain separate events.
Detection never projects confirmation that playback actually stopped.

## Delivery, ordering, and reconnect

`VoiceFrontendEventSink` is the consumer-facing port. No WebSocket, SSE, UI
framework, or production transport is selected. Voice continues normally with
no subscriber, and subscriber failure cannot block Voice operation.

`VoiceFrontendEventStream` demonstrates ordering/reconnect behavior. Identical
duplicates are idempotent; contradictory duplicate identities, stale revisions,
wrong sessions, and wrong correlations are rejected. A reconnect consumes a
current factual snapshot followed by events after its last revision; it need not
replay the full history.

Frontend events are not written to a second journal. Existing Voice facts remain
the durable source. After restart, the emitted snapshot is
`reconciliation_required`, with external state unknown; it never invents an
active microphone or playback stream.

## Availability, privacy, and waveform decision

Capability snapshots distinguish `supported`, `degraded`, and `unavailable`
without exposing device paths, credentials, model locations, or sensitive
configuration. Operational failure remains distinct from capability absence.

Waveform, amplitude, and frequency telemetry are excluded from V1 and are never
journaled. When the frontend owns capture/playback it should calculate visual
telemetry locally through its audio APIs. A future transport may carry optional
transient telemetry when the frontend lacks audio access, but that would require
a separate non-durable protocol decision.

## Controlled journey and limitations

The controlled journey covers microphone listening, VAD speech facts, STT,
Perception/Conversation processing, response acceptance, explicit synthesis,
playback start/completion, interruption, cancellation, error, and restart.
Controlled TTS validates sequencing only and is not reported as production-ready.

Slice 12 may select an authorized delivery adapter. This slice does not add a
frontend, WebSocket/SSE wiring, global bootstrap activation, animation, waveform,
Avatar/Embodiment, providers, or production Piper execution.
