# Voice, Audio and Speech Finalization

## Baseline

- Global baseline before this domain: `914 passed, 40 failed`.
- Domain command: `uv run --extra dev pytest tests/test_voice_runtime.py tests/test_audio_runtime.py tests/test_speech_adapters.py tests/test_speech_pipeline_runtime.py -q --tb=short`.
- Domain result before changes: `39 passed, 14 failed`.
- Root cause A, 5 failures: legacy tests expect mock adapters to win resolution even though real adapters have higher priority; `mock_transcribe` also delegates to normal production resolution.
- Root cause B, 9 failures: the speech-pipeline fixture creates Voice/Avatar sessions for `artemis` without registering that agent.

## Inventory Matrix

| Component | Responsibility | Current state | Production or mock | Provider | Persistence | Streaming | Cancellation | Tests | Debt |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `VoiceRuntime` | Settings, recordings, voice sessions and utterance queue | Partial | Mixed | Resolves STT through speech adapters; TTS mostly queue metadata | YAML recordings, settings, sessions and utterances | No | Utterance cancellation only | `test_voice_runtime.py` | Ambiguous legacy settings, incomplete lifecycle and metadata-only device test |
| `AudioRuntime` | Audio sessions and provider facade | Prototype | Predominantly mock | Calls provider resolution and speech adapters | YAML sessions, devices and events | No | No | `test_audio_runtime.py` | Executes STT/TTS despite target boundary; silently creates mock devices; no byte validation or normalization |
| `SpeechAdapterRuntime` | Adapter registry, health, selection and execution | Partial | Mixed | Faster Whisper STT, Piper TTS, three mock adapters | Policy only | Capability metadata only | No | `test_speech_adapters.py` | Mock adapters are production-registered; unavailable health can still participate; Piper alias is accepted as STT |
| `FasterWhisperSpeechToTextAdapter` | Local STT | Partial production implementation | Production, optional dependency | Faster Whisper | Local model root | No | No | Covered with controlled fake dependency | Missing structured no-speech status, timeout/cancellation, warmup and richer health |
| `PiperTextToSpeechAdapter` | Local TTS | Partial production implementation | Production, optional executable | Piper-compatible path | Generated output files | No | No | Covered by adapter/audio tests | Provider identity and implementation need audit; cancellation, timeout and strict capability reporting incomplete |
| Voice analysis adapter | Objective vocal metrics | Placeholder | Mock | `mock_voice_analysis` | No | No | No | Incidental only | No real analysis provider; fake adapter must not be production eligible |
| `SpeechPipelineRuntime` | Coordinates input/output turns with multimodal, perception, voice and avatar | Prototype | Mock | Uses `AudioRuntime.transcribe_mock` and `synthesize_mock` | YAML sessions and turns | No | Pause/close only | `test_speech_pipeline_runtime.py` | Entire input/output surface is mock; incomplete lifecycle and no Conversation/Context Fusion execution |
| Device discovery | Input/output discovery and diagnostics | Placeholder | Mock | None | Mock device YAML | No | N/A | Audio/voice tests | No OS discovery, persistent identity, real open/frames/signal diagnostics or removal detection |
| API and commands | Voice, audio, speech and adapter control surfaces | Partial | Mixed | Delegates to runtimes | Runtime-dependent | No | Partial | All four domain suites | Production exposes `/mock` routes and commands; contracts are fragmented |

## Located Surfaces

- Runtime packages: `backend/synapse/audio`, `backend/synapse/voice`, `backend/synapse/speech_adapters`, `backend/synapse/speech_pipeline`.
- Shared contract: `backend/synapse/contracts/voice.py`.
- API and command registrations are centralized in `backend/synapse/api/routes.py` and `backend/synapse/commands/runtime.py`.
- Policies are persisted under the runtime data directory as `config/speech_adapter_policy.yaml`, `config/speech_pipeline_policy.yaml`, and `voice/settings.yaml`; they are not repository-level `backend/config` files.
- Related architecture records: ADRs 0068, 0075, 0076, 0077 and 0108.
- Related validation history: 0107 voice/audio/faster-whisper documents.

## Confirmed Production Risks

- Mock adapters and devices are registered or created silently and can be resolved in normal execution.
- `provider_id` and `device_id` remain aliases for STT provider and input device.
- Legacy Piper-as-STT configuration is silently rewritten to Faster Whisper.
- Empty or invalid audio is not validated centrally before provider execution.
- The current pipeline has no real VAD, message mode, continuous conversation loop, barge-in or provider streaming.
- Streaming flags are descriptive only; no fake streaming was found.
- Voice-analysis output is mock and must not emit emotion or prosody claims.

## Execution Log

This document is updated after each implementation and validation phase. The domain is not frozen while any Definition of Done item remains unmet.

### 2026-07-12 baseline stabilization

- Corrected the incomplete `artemis` fixture in speech-pipeline tests.
- Removed implicit-mock assumptions from speech-adapter resolution tests.
- Focused result: `53 passed`.
- Global result: `928 passed, 26 failed`; the count decreased by the 14 domain failures.
- Ruff result: green.
- Remaining global failures: effective policy 9, observability 9, UI contracts 4, health 3, foundation hardening 1.
- Freeze status: open. Phases 2 through 26 still require production implementation and validation.

### 2026-07-12 production foundation

- Added canonical audio ingestion using PyAV: content-based WAV/WebM/OGG detection,
  decode, PCM16 mono 16 kHz normalization, measured duration, SHA-256 checksum,
  RMS, peak and silence ratio.
- STT now receives validated canonical WAV instead of untrusted client bytes.
- Added structured audio error codes for empty, corrupt, unsupported, mismatched,
  too-short, too-large, too-long and optionally silent audio.
- Faster Whisper now reports `no_speech_detected` with null confidence for an
  empty result and accepts explicit device, compute type and VAD-filter options.
- Replaced the mislabeled Windows `System.Speech` implementation with a real,
  configurable Piper executable/model boundary. Missing Piper configuration is
  reported as unavailable; no fallback synthesis is returned.
- Added schema-version 2 voice settings with separate STT, TTS, analysis,
  devices, VAD and retention fields plus explicit legacy migration metadata.
- Added independent local acoustic analysis with objective metrics only. It
  does not claim emotion, intent, personality, prosody or pitch.
- Focused checkpoint: `58 passed`, `4 subtests passed`; Ruff global green.
- Freeze status: open. Device discovery, real VAD, message/session lifecycle,
  conversation mode, barge-in, streaming, mock-surface removal and final API
  consolidation remain incomplete.
- Global regression collected `959` tests and preserved the known non-domain
  failure groups. It exposed one integration regression: optional,
  unconfigured Piper degraded aggregate readiness. Readiness now requires the
  speech runtime itself while provider availability remains visible in health.
- Post-fix Voice/Audio/Speech plus readiness regression: `67 passed`, `4
  subtests passed`; Ruff global green.

### 2026-07-12 operational runtime checkpoint

- Added PortAudio device discovery through `sounddevice`, stable descriptors,
  default identification, real input capture diagnostics, controlled output
  playback diagnostics, removal detection and non-fatal unavailable health.
- Production no longer creates mock input/output devices when discovery is
  empty. Hardware is injected only in tests.
- Added WebRTC VAD with strict PCM16 frames, speech start/continue/end,
  silence, maximum-duration closure, reset and explicit capabilities. VAD
  confidence remains null because WebRTC VAD does not provide one.
- Extended the existing Voice recording model with persistent status,
  sequence, idempotency keys, revisions, checksums and relative audio
  references. Added append, idempotent complete, cancel and delete flows.
- Added Voice Message completion through canonical analysis and STT. Results
  and analyses are persisted and repeated completion is idempotent. A
  regression verifies that Voice Message never calls ChatRuntime.
- Added a persisted VoiceSession transition model with explicit transitions,
  revision checks, previous state, settings snapshot, timestamps and errors.
- Domain checkpoint: `69 passed`, `4 subtests passed` before the final import
  ordering correction; all behavioral tests passed.
- Global result: `944 passed`, `26 failed`, `4 subtests passed` in `463.24s`.
  Remaining failures are unchanged and outside this domain: effective policy
  9, observability 9, UI contracts 4, health 3 and foundation hardening 1.
- Ruff global: green. `git diff --check`: clean, with line-ending warnings only.
- Freeze status: open. Conversation Mode, barge-in, retention cleanup,
  canonical API/commands, production mock removal and acceptance suites remain
  required.

### 2026-07-12 conversation and surface closure checkpoint

- Voice now invokes only `ChatRuntime.submit_turn` for conversation turns. It
  does not call ModelRouter, Context Fusion, ToolRuntime or a model provider.
- Two-turn regression preserves one conversation while producing distinct
  recordings, utterances and syntheses, with return to `listening` after each
  completed turn.
- Added persisted synthesis lifecycle with text checksum, relative audio
  reference, status, revision and explicit `streaming=false`. Cancellation is
  idempotent and records that the current Piper adapter cannot cancel after a
  completed synchronous invocation.
- Added barge-in transition from `speaking` to a new recording, synthesis
  cancellation and redacted `voice.user_interrupted` event. Disabled barge-in
  leaves speaking state unchanged.
- Added retention dry-run and cleanup for recording/synthesis audio with
  active-recording protection, DATA_DIR boundary checks, idempotency and
  transcript/analysis retention counts.
- Mock speech/audio API paths and mock commands were removed. Builtin mock
  adapters and legacy mock runtime methods are available only when
  `SYNAPSE_DEV_MODE=true`; production provider selection registers only real
  adapters.
- Added canonical API adapters for session cancellation, recording lifecycle,
  Voice Message completion, conversation turn and retention cleanup. Added
  canonical operational commands for settings, devices, session actions and
  cleanup.
- OpenAPI: `384` paths and zero Voice/Audio/Speech mock paths. A pre-existing
  duplicate-operation warning remains for `agent_multimodal_policy`, outside
  this domain.
- Focused Voice/Audio/Speech result: `73 passed`, `4 subtests passed`.
- Integrated Voice plus Avatar regression after route correction: `84 passed`,
  `4 subtests passed`; Ruff global green.
- First global closure run: `947 passed`, `27 failed`, `4 subtests passed` in
  `462.29s`. The one new Avatar failure was traced to a misplaced Voice API
  argument and corrected; the targeted Avatar regression is now green. The 26
  historical external failures remain unchanged.
- Checkpoint status at that run: open. The gaps listed below were subsequently
  closed and are recorded in the Final Freeze section.

## Final API Matrix

| Operation | Canonical runtime | Path | Request/response | Test | State |
| --- | --- | --- | --- | --- | --- |
| Settings get/update | VoiceRuntime | `GET/PATCH /voice/settings` | VoiceSettings v2 | voice API | Implemented |
| Settings validate/migrate | VoiceRuntime | read/update performs validation/migration | structured settings | settings regressions | Implemented; separate migrate route not supported by design |
| Devices list | DeviceRuntime | `GET /voice/devices`, `GET /audio/devices` | descriptors | audio/voice API | Implemented |
| Device input test | DeviceRuntime | `POST /voice/devices/{id}/test` | diagnostics | voice API | Implemented |
| Device output test | DeviceRuntime | no dedicated public path | diagnostics runtime | device regression | Not supported by design until a client requires tone playback |
| Providers list/get/health | SpeechAdapterRuntime | `/voice/providers`, `/speech-adapters*` | manifests/health | adapter API | Implemented |
| Provider capabilities | SpeechAdapterRuntime | manifest and provider capabilities | structured capability map | provider tests | Implemented |
| Recording create/get/list | VoiceRuntime | `/voice/recordings*` | VoiceRecording | voice API | Implemented |
| Recording start/append/complete/cancel/delete | VoiceRuntime | `/voice/recordings/start`, `/{id}/chunks`, `/{id}/complete`, `/{id}/cancel`, `DELETE /{id}` | lifecycle DTOs | focused/acceptance | Implemented |
| Voice Message complete/result | VoiceRuntime | `POST /voice/messages/{id}/complete`; result through recording transcript ID | VoiceMessageResult | acceptance | Implemented |
| Session create/list/get | VoiceRuntime | `/voice/sessions*` | VoiceSession | voice API | Implemented |
| Session pause/resume/cancel/close | VoiceRuntime | `/voice/sessions/{id}/*` | VoiceSession | focused tests | Implemented |
| Session events | EventBus | global event/trace APIs | redacted events | event regressions | Implemented through canonical event surface |
| Conversation turn | VoiceRuntime | `POST /voice/sessions/{id}/conversation/turn` | linked turn result | two-turn acceptance | Implemented |
| Frame ingest/stop utterance | VoiceRuntime + VAD | runtime streaming boundary | PCM16 frames/events | VAD tests | Not exposed as HTTP by design; transport streaming is client-specific |
| Interrupt | VoiceRuntime | runtime `interrupt_session` | recording | barge-in acceptance | Implemented; dedicated HTTP route not required by current client |
| Synthesis create/get/cancel | VoiceRuntime | runtime synthesis methods | VoiceSynthesis | focused/acceptance | Implemented; no standalone HTTP client requirement |
| Retention cleanup/dry-run | VoiceRuntime | `POST /voice/retention/cleanup` | VoiceCleanupReport | retention acceptance | Implemented |
| Health/readiness | Health/Readiness runtimes | global health/readiness APIs | component state | readiness regression | Implemented |

Binary chunk ingestion is API-only. It is intentionally not represented as a
CLI command.

### API operation-level closure

The table above groups related routes; this normative annex accounts for every
requested operation. `Runtime DTO` means the structured dataclass serialized by
the thin FastAPI adapter. There are no partial or placeholder entries.

| Operation | Runtime | Method/path | Request | Response | Test | State |
| --- | --- | --- | --- | --- | --- | --- |
| Settings get | VoiceRuntime | `GET /voice/settings` | none | VoiceSettings v2 | voice API | Implemented |
| Settings update/validate/migrate | VoiceRuntime | `PATCH /voice/settings` | VoiceSettingsPayload | VoiceSettings v2 | settings migration tests | Implemented; validation and legacy migration are atomic |
| Settings reset | VoiceRuntime | none | n/a | n/a | matrix review | Not supported by design; explicit updates preserve auditability |
| Devices list inputs/outputs/defaults | DeviceRuntime | `GET /voice/devices` | none | device descriptors with direction/default | device tests | Implemented |
| Device test input | DeviceRuntime | `POST /voice/devices/{id}/test` | path ID | diagnostic DTO | device tests | Implemented |
| Device test output | DeviceRuntime | none | n/a | n/a | device runtime tests | Not supported by design in HTTP; controlled tone remains a runtime diagnostic |
| Providers list/get/capabilities/health | SpeechAdapterRuntime | `GET /voice/providers`, `/speech-adapters*` | optional type/path ID | manifest/health DTOs | speech adapter API | Implemented |
| Provider test | SpeechAdapterRuntime | none | n/a | n/a | provider execution tests | Not supported by design; real STT/TTS calls are the provider tests |
| Recording create | VoiceRuntime | `POST /voice/recordings` or `/start` | recording/start DTO | VoiceRecording | voice API | Implemented |
| Recording append | VoiceRuntime | `POST /voice/recordings/{id}/chunks` | base64 chunk, sequence, idempotency | VoiceRecording | recording tests | Implemented |
| Recording complete/cancel | VoiceRuntime | `POST /voice/recordings/{id}/complete` or `/cancel` | path ID | VoiceRecording | acceptance | Implemented |
| Recording get/list/delete | VoiceRuntime | `GET /voice/recordings[/{id}]`, `DELETE /voice/recordings/{id}` | path ID | VoiceRecording/list | voice API | Implemented |
| Recording transcribe | VoiceRuntime | `POST /voice/recordings/{id}/transcribe` | transcription DTO | VoiceTranscription | voice API | Implemented |
| Voice Message create | VoiceRuntime | recording create/start routes | recording DTO | VoiceRecording | message acceptance | Implemented |
| Voice Message complete/result | VoiceRuntime | `POST /voice/messages/{id}/complete`; persisted transcript linkage | path ID | VoiceMessageResult | message acceptance | Implemented; no redundant result route |
| Session create/list/get/status | VoiceRuntime | `POST/GET /voice/sessions`, `GET /voice/sessions/{id}` | session DTO/path ID | VoiceSession/VoiceSummary | session tests | Implemented |
| Session start | VoiceRuntime | none | n/a | n/a | transition tests | Not supported by design; listening starts through the transport-specific conversation boundary |
| Session pause/resume/cancel/close | VoiceRuntime | `POST /voice/sessions/{id}/{action}` | path ID | VoiceSession | session tests | Implemented |
| Session utterances | VoiceRuntime | `GET /voice/sessions/{id}/utterances` | path ID | VoiceUtterance list | voice API | Implemented |
| Session events | EventBus | canonical event API | session filter | redacted events | event tests | Implemented through shared observability surface |
| Conversation start listening / ingest frames / stop utterance | VoiceRuntime + WebRTC VAD | transport runtime boundary | PCM16 frames | VAD events/recording | VAD tests | Not supported by design over request/response HTTP |
| Conversation run turn | VoiceRuntime | `POST /voice/sessions/{id}/conversation/turn` | recording ID + idempotency | VoiceConversationTurnResult | two-turn acceptance | Implemented |
| Conversation interrupt | VoiceRuntime | runtime `interrupt_session` | session ID | VoiceRecording | barge-in acceptance | Not exposed as HTTP by design; barge-in is transport-timed |
| Conversation status | VoiceRuntime | `GET /voice/sessions/{id}` | path ID | VoiceSummary | voice API | Implemented |
| Synthesis create/get/cancel/delete | VoiceRuntime | canonical runtime methods | structured runtime request | VoiceSynthesis | synthesis/barge-in tests | Not exposed as standalone HTTP by design; Conversation Mode owns synthesis lifecycle |
| Retention policy get/update | VoiceRuntime | settings GET/PATCH | retention fields | VoiceSettings v2 | settings tests | Implemented through canonical settings |
| Retention cleanup/dry-run | VoiceRuntime | `POST /voice/retention/cleanup` | `{dry_run}` | VoiceCleanupReport | retention acceptance | Implemented |
| Health/readiness/diagnostics | HealthRuntime/ReadinessRuntime | global health/readiness APIs | none | summary/checks with `voice_diagnostics` | health + acceptance | Implemented |

## Final Command Matrix

| Operation | Command | Runtime | State |
| --- | --- | --- | --- |
| Settings show | `/voice-settings` | VoiceRuntime | Implemented |
| Settings update/validate | API only | VoiceRuntime | Not supported by design; nested settings are unsafe as positional CLI text |
| Devices input/output | `/voice-devices-input`, `/voice-devices-output` | DeviceRuntime | Implemented |
| Device diagnostics | API/runtime | DeviceRuntime | Not supported by design for unattended CLI tone/capture |
| Providers | existing speech-adapter commands | SpeechAdapterRuntime | Implemented |
| Recording binary append | API only | VoiceRuntime | Not supported by design |
| Sessions list/show | `/voice-sessions`, `/voice-session` | VoiceRuntime | Implemented |
| Session pause/resume/cancel/close | `/voice-session-{action}` | VoiceRuntime | Implemented |
| Utterances | `/voice-utterances` | VoiceRuntime | Implemented |
| Conversation turn | API/runtime | VoiceRuntime | Not supported by design; requires binary recording linkage |
| Synthesis | API/runtime | VoiceRuntime | Not supported by design until a CLI playback consumer exists |
| Retention cleanup/dry-run | `/voice-cleanup`, `/voice-cleanup-dry-run` | VoiceRuntime | Implemented |
| Health/readiness | global health/readiness commands | Health/Readiness | Implemented |

No mock command remains registered.

### Command operation-level closure

Commands below are slash-prefixed in the runtime. Missing commands are
deliberate CLI boundary decisions, not placeholders.

| Requested command | Canonical runtime | Resolution | State |
| --- | --- | --- | --- |
| `voice-settings` | VoiceRuntime | `/voice-settings` | Implemented |
| `voice-settings-update`, `voice-settings-validate` | VoiceRuntime | API/settings DTO | Not supported by design; nested typed settings are unsafe positional CLI input |
| `voice-devices-input`, `voice-devices-output` | DeviceRuntime | matching commands | Implemented |
| `voice-device-defaults` | DeviceRuntime | defaults are fields in device list | Implemented without redundant command |
| `voice-device-test-input`, `voice-device-test-output` | DeviceRuntime | runtime/API diagnostics | Not supported by design for unattended capture/tone CLI |
| `voice-providers`, `voice-provider-show`, `voice-provider-health`, `voice-provider-capabilities` | SpeechAdapterRuntime | canonical speech-adapter commands | Implemented through shared adapter commands |
| `voice-recording-create`, `voice-recording-complete`, `voice-recording-cancel`, `voice-recording-show`, `voice-recording-delete`, `voice-recording-transcribe` | VoiceRuntime | typed API/runtime boundary | Not supported by design; binary/file lifecycle is not duplicated in text commands |
| `voice-session-create` | VoiceRuntime | typed API | Not supported by design; agent/session metadata requires a structured request |
| `voice-session-list`, `voice-session-show` | VoiceRuntime | `/voice-sessions`, `/voice-session` | Implemented |
| `voice-session-start` | VoiceRuntime | transport boundary | Not supported by design; CLI cannot own microphone lifecycle |
| `voice-session-pause`, `voice-session-resume`, `voice-session-cancel`, `voice-session-close` | VoiceRuntime | matching commands | Implemented |
| `voice-session-status` | VoiceRuntime | `/voice-session` summary | Implemented without redundant command |
| `voice-session-utterances` | VoiceRuntime | `/voice-utterances` | Implemented |
| `voice-conversation-turn`, `voice-conversation-interrupt` | VoiceRuntime | API/transport boundary | Not supported by design; requires recording linkage or real-time timing |
| `voice-synthesize`, `voice-synthesis-show`, `voice-synthesis-cancel`, `voice-synthesis-delete` | VoiceRuntime | Conversation Mode/runtime | Not supported by design until a CLI audio consumer exists |
| `voice-retention`, `voice-retention-update` | VoiceRuntime | `/voice-settings` and typed API | Implemented through settings; no duplicate command |
| `voice-cleanup`, `voice-cleanup-dry-run` | VoiceRuntime | matching commands | Implemented |
| `voice-health`, `voice-readiness`, `voice-diagnostics` | HealthRuntime/ReadinessRuntime | shared global commands | Implemented through canonical global operational commands |

## Final Freeze

Date: 2026-07-13

- `VoiceRuntime` remains the public orchestrator. Audio ingestion/devices,
  speech providers, VAD, and Perception contracts are separate components.
  Private YAML helpers were not extracted because they have one consumer and
  extraction would only move code without reducing coupling.
- `VoicePerceptionSink` is neutral and optional. Signals require provenance and
  linked IDs but exclude raw audio and full transcript content. Sink failures
  cannot corrupt a turn.
- Acceptance: Voice Message, two-turn Conversation Mode, barge-in, restart in
  recording/processing/thinking/speaking, retention, and Perception bridge;
  `9 passed`.
- Integrated Voice/Audio/Speech/Avatar: `93 passed`, `4 subtests passed`.
- Final collection: `983 tests`.
- Final global: `957 passed`, `26 failed`, `4 subtests passed` in `476.69s`.
- All 26 failures are historical and external: effective policy 9,
  observability 9, UI contracts 4, health 3, foundation hardening 1.
- Ruff global: green. `git diff --check`: clean except line-ending warnings.
- OpenAPI: `384` paths and no Voice/Audio/Speech mock path. FastAPI still emits
  a pre-existing warning for `agent_multimodal_policy`, outside this domain.
- Real limitations: no simulated Faster Whisper/Piper streaming; Piper reports
  post-completion cancellation as unsupported; absent optional hardware or
  providers never trigger mock fallback.
- Residue classification: `NamedTemporaryFile` is legitimate decoder hygiene;
  legacy `provider_id` is explicit settings-v1 migration; direct
  `PerceptionRuntime` imports exist only in the separate compatibility speech
  pipeline, never in Voice; mock adapter/classes and legacy mock audio/pipeline
  methods are explicit test/development surfaces guarded by
  `SYNAPSE_DEV_MODE=true`. No mock route, command, production default, silent
  fallback, `System.Speech`, or direct Voice-to-ModelRouter call remains.
- Domain status: **Implemented / Frozen**.
