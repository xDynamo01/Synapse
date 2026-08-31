# Real-time Voice V1

## Pipeline and activation

The opt-in `RealtimeVoiceRuntime` composes consumer-owned microphone, speech,
conversation and output ports:

```text
microphone stream -> WebRTC VAD -> transient utterance -> local STT
-> neutral conversation request -> correlated response -> TTS boundary -> playback port
```

Construction is inert: it does not enumerate a default device, open a stream, load an
STT model, synthesize or play audio. The runtime is not bound by production bootstrap.
An explicit caller must supply device references and all ports. An invalid configured
device fails closed and is never replaced silently by the operating-system default.

## Turn-taking facts

The state machine distinguishes waiting, listening, user speaking, utterance
finalization, transcription pending, waiting for response, synthesis pending, system
speaking, interruption pending, cancellation pending, reconciliation required, error
and closed. These states describe observable pipeline coordination only.

The legacy `thinking` state in `VoiceRuntime` remains for API compatibility. It means
only “waiting for an externally authorized conversation response”; it is not evidence
of Agent reasoning and grants Voice no reasoning or Agent-selection authority.

## VAD and utterances

WebRTC VAD processes mono PCM16 frames at an explicit sample rate and 10, 20 or 30 ms
frame duration. Aggressiveness, minimum speech duration and end-of-speech silence are
explicit configuration. Silence below the configured threshold remains part of the
same utterance, avoiding splits on micro-pauses. VAD classifies speech presence only;
it never interprets content.

Finalized utterances have an identity, session correlation, device reference,
frame range, duration, checksum and a `transient://` PCM reference. PCM bytes remain
in memory and are never sent to the Slice 5 journal by the real-time runtime.

## STT and conversation boundary

Faster-Whisper receives the finalized WAV with the configured model and language. Its
adapter is `local_files_only=True`: a missing model fails rather than downloading or
selecting another model. The utterance fact remains visible when transcription fails.

A valid transcript creates a neutral conversation request containing session,
utterance, transcription, actor, correlation and provenance. Voice does not interpret
intent, choose an Agent or manufacture a response. Responses require exact request,
session and correlation correspondence. Stale responses and responses received after
cancellation/closure cannot reopen the session.

## TTS and playback

Text response acceptance does not imply synthesis or playback. TTS uses the Slice 6
execution boundary; no subprocess fallback exists. Piper remains degraded when its
executor, executable or model is unavailable.

Playback separately records requested, started, completed, failed and interrupted
facts. Completion means only that the backend completed playback; it does not prove
the user heard or understood the response. Output disconnects become factual failures
instead of crashing the process.

## Barge-in, cancellation and restart

Speech detected during active playback records barge-in before requesting stop.
`stop_requested` and `stop_confirmed` remain separate. If termination is unverified,
the runtime stays interruption-pending and does not claim playback stopped.

Cancellation is also two-step: request changes the state to cancellation-pending;
only explicit confirmation closes resources. After restart, microphone, STT, TTS and
playback state are unknown. The runtime records reconciliation-required, does not
reopen streams and does not redispatch external work automatically.

## Capability matrix and limitations

Capability reporting keeps input, output, VAD, STT local-only status, TTS execution
boundary, playback, barge-in and overall readiness separate. Overall support is never
reported when an input/output/VAD prerequisite is absent; missing TTS execution keeps
the pipeline degraded.

Real device adapters use the already locked PortAudio/sounddevice dependency, but are
not globally activated. Piper is not required for Slice 7 when its executable/model
are absent. Slice 8 may add an explicitly authorized composition surface and durable
operational controls without changing privacy, egress or authority boundaries.
