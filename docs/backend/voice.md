# Voice Backend

Faster Whisper, Piper, local acoustic analysis and WebRTC VAD now have canonical
discovery projections. `SpeechAdapterRegistry` remains the STT/TTS/analysis
execution authority. Production projections exclude mock adapters; mocks are
eligible only in explicit test/development mode. Lazy-load and streaming claims are
descriptive and do not move lifecycle into the catalog.

`VoiceRuntime` is the domain orchestrator. It coordinates settings, sessions,
recordings, speech providers, ChatRuntime, retention, and the neutral Perception
port. Audio decoding, devices, STT/TTS/analysis, and VAD remain separate
components with their own state and tests. Further file splitting would only
move private persistence helpers without adding a consumer, so no artificial
store abstraction was introduced during freeze.

Voice settings schema v2 separates STT, TTS, analysis, VAD, input/output devices,
and retention. Legacy aliases are read through explicit migration metadata.

Voice Message creates/chunks/completes a recording, normalizes audio, runs
analysis and STT, persists result IDs, and never calls ChatRuntime. Conversation
Mode reuses that result and calls `ChatRuntime.submit_turn`; it does not call a
model provider, ModelRouter, Context Fusion, or ToolRuntime directly.

`VoicePerceptionSink` receives redacted structured signals. The default
`NullVoicePerceptionSink` is an explicit no-op. Sink absence or failure cannot
fail a voice turn, and neither raw audio nor full transcript is emitted.
The composition root accepts a real sink explicitly; state transitions emit
`speech.started`, `speech.ended`, and `voice.pause`, while transcription,
analysis, and barge-in emit their corresponding redacted signals. Every signal
has provenance and a correlation ID.

Retention supports dry-run and idempotent cleanup. Active recordings, paths
outside DATA_DIR, and symlinks are protected. Transcripts and analysis can remain
after audio deletion.

Global health includes `voice_diagnostics`: PyAV, input/output devices, all
speech adapter health records, WebRTC VAD, storage, retention, active/failed
sessions, last error, and provider latency when reported. Diagnostics never
open capture or playback devices.
