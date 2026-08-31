# Voice / Audio / Perception final freeze audit

Date: 2026-08-11
Scope: Slices 1-14
Profile: `bounded-context-change`

## Formal classification

**Voice / Audio / Perception — IMPLEMENTED / ARCHITECTURALLY COMPLETE / FROZEN**

This classification is local to these bounded contexts. It does not make the
Synapse backend globally ready and does not claim operational TTS or full-duplex
Voice.

| Capability | Frozen classification | Factual basis |
|---|---|---|
| Voice persistence | FROZEN / OPERATIONALLY COMPLETE | Append-only SQLite V1, schema/checksum validation, replay and exact identities |
| Audio input | FROZEN / OPERATIONALLY COMPLETE | Real device enumeration and explicit session-start stream opening |
| Playback/output device | FROZEN / OPERATIONALLY COMPLETE | Real output port accepts valid WAV independently of synthesis |
| WebRTC VAD | FROZEN / OPERATIONALLY COMPLETE | Local provider and deterministic turn boundary tests |
| Faster-Whisper STT | FROZEN / OPERATIONALLY COMPLETE | Local installed provider/model evidence; `local_files_only=True` |
| Turn-taking | FROZEN / IMPLEMENTED | Ordered factual state machine with superseding-turn history |
| Interruption/barge-in | FROZEN / IMPLEMENTED | Detection, stop request and stop confirmation remain separate facts |
| Restart/reconciliation | FROZEN / OPERATIONALLY COMPLETE | Replay does not restart streams or external work; unknown state is explicit |
| Acoustic Perception | FROZEN / OPERATIONALLY COMPLETE | Real local DSP for energy, pitch, pause and speech-rate proxies |
| Perception taxonomy | FROZEN / IMPLEMENTED | Observation, derived feature, inference and contextual interpretation remain distinct |
| Voice to Perception | FROZEN / OPERATIONALLY COMPLETE | Transient PCM analysis with provenance and no raw PCM bundle retention |
| Voice to Conversation | FROZEN / OPERATIONALLY COMPLETE | Real ConversationRuntime, explicit Agent target and factual request/response path |
| Frontend event boundary | FROZEN / IMPLEMENTED | Versioned transport-neutral factual events; no UI or animation authority |
| TTS contract/Piper adapter | FROZEN / IMPLEMENTED | Piper adapter and immutable SpeechExecutionPort request/result contracts exist |
| TTS operational execution | FROZEN / EXTERNALLY BLOCKED | Executable/model not configured and no concrete execution authority is composed |
| Full-duplex Voice | FROZEN / EXTERNALLY BLOCKED | Input-to-Conversation works; speech output remains unavailable |
| Visual non-verbal Perception | FROZEN / INTENTIONALLY UNAVAILABLE | No face, gaze, head/body pose or gesture provider is configured |

`OPERATIONALLY COMPLETE` applies only to the rows that carry that exact
classification. It does not apply to the set as a whole.

## Frozen public surface

The executable freeze gate fixes 36 Python modules:

- Audio: 8 modules, 17 public exports;
- Voice: 10 modules, 29 public exports;
- Perception: 6 modules, 19 public exports;
- Speech adapters/execution boundary: 9 modules, 11 public exports;
- local Voice composition: 3 modules, 9 public exports.

The gate fingerprints each ordered `__all__` surface and freezes:

- `voice-record-v1`, SQLite schema version 1 and the migration checksum;
- Voice settings schema 3 and `voice-configuration-v1`;
- `voice-frontend-event-v1` and its closed event/presentation taxonomies;
- `speech-execution-request-v1` and `speech-execution-result-v1`;
- Voice persistence/completeness and realtime lifecycle states;
- Perception artifact, bundle, modality and retention taxonomies;
- capability and operational-completion taxonomies.

Legacy Avatar, Embodiment and Wardrobe runtime packages remain physically absent.
One-way readers may discard historical fields, but they do not restore those
runtimes or public models. There is no Agent-owned `VoiceProfile`.

## Authority baseline

- Voice owns sessions, utterances, input/STT lifecycle, turn-taking,
  interruption, synthesis/playback lifecycle and factual frontend events.
- Audio owns device, stream, WAV and playback primitives/adapters.
- Perception owns observations, derived features, inference artifacts,
  provenance, confidence, retention and factual temporal correlation.
- Conversation and Agents own response content, semantic interpretation,
  reasoning and Agent/tool decisions. Voice composition requires an explicit
  target and never invokes `AgentRuntime`.
- Frontend owns waveform, particles, animation and rendering.
- A future Sandbox-compatible execution authority owns concrete external-process
  isolation and execution evidence.

## E2E evidence

The supported controlled journey covers microphone frames, WebRTC VAD,
utterance finalization, Faster-Whisper-shaped STT results, acoustic DSP, the real
ConversationRuntime with explicit target, response-reference creation and Voice
acceptance. It verifies that raw PCM is not journaled, Perception provenance is
preserved, no tools are attached and response acceptance does not start TTS or
playback.

A separate real-host smoke enumerates hardware without opening a stream during
build. On the audited host it observed 11 input and 17 output devices, supported
Voice input/STT/acoustic/Conversation paths, unavailable TTS, and degraded
full-duplex Voice.

Playback is frozen independently from synthesis: a valid WAV can be sent to the
output port even when Piper is unavailable. `playback supported` never implies
`speech synthesis supported`.

The final host smoke played a 100 ms in-memory silent mono PCM16 WAV through the
real output adapter. Playback reported `requested=True`, `started=True`, no
error, followed by a separately observed stop request and confirmation. It did
not invoke Piper.

## Recovery, concurrency and privacy

Restart/reopen tests cover pending STT, pending Perception, pending Conversation,
accepted response without synthesis, synthesis/playback external states and
interruption/cancellation facts. Reopen appends or projects
`reconciliation_required`; it does not reopen devices or reexecute STT,
Perception, reasoning, TTS or playback.

Concurrency tests preserve superseded turns, late Conversation responses, late
Perception bundles, interruption during playback, cancellation, duplicate versus
contradictory results and frontend reconnect ordering. Late facts never rewrite
prior journal history.

Privacy defaults remain: raw microphone audio is transient, `store_raw_audio` is
false, synthesis audio is not retained, Perception transcript persistence and
raw visual persistence are false, camera is disabled, frontend events reject
transcript/PCM/waveform fields, and Faster-Whisper cannot download implicitly.
Acoustic derived features may be retained with provenance without retaining raw
audio.

## External blocker record

The Piper adapter and `SpeechExecutionPort` exist. On the audited host the Piper
executable and model are absent or unconfigured, and no concrete production
execution authority is composed. The frozen Sandbox contracts do not yet provide
the concrete driver for this consumer. Voice and Piper do not bypass this with
`subprocess`, shell execution or an implicit download.

The exact unfreeze condition is:

> Sandbox concrete execution authority + valid Piper executable/model/artifacts
> + integration evidence.

The driver must accept the existing immutable structured execution request and
return a correlated, fingerprinted result with factual acceptance/start/outcome,
termination evidence, exit observation and expected artifact references. Piper
must then verify the produced WAV. No Sandbox admission, grants or
materialization assumptions are added by this audit.

## Graph and accepted debt

The frozen runtime graph has 280 edges. Its preexisting 11-context/31-edge SCC
contains Voice, Agents, Tools and related orchestration contexts. The frozen
source graph has 315 edges and retains the preexisting Audio/Multimodal/Perception
3-context/4-edge SCC plus the 24-context/80-edge global SCC.

These SCCs are architectural debt and a tolerated baseline, not blockers for
this bounded-context freeze: the local composition adds only outward integration
edges and no domain or bootstrap reverse dependency. Any future edge or SCC
change requires explicit unfreeze review.

## Change governance

The executable gate is
`tests/architecture/test_voice_audio_perception_freeze.py`. Any future Sandbox
execution integration for Piper, visual Perception provider, new Voice
capability, public export, module, schema, migration, taxonomy, integration edge
or global activation must intentionally update the gate and this audit under the
applicable change/unfreeze governance. A stale test must not be weakened merely
to make such a change green.

## Final gate evidence

- freeze gate and bounded-context selection: 192 passed, 4 subtests passed;
- architecture suite: 212 passed;
- Ruff global: clean;
- Mypy global authoritative source set: 684 files, zero errors;
- global regression: 3,549 passed, 4 skipped, 4 subtests passed;
- global enumeration: 279 unique `test_*.py` files, zero omitted and zero duplicated;
- `git diff --check`: clean;
- runtime/source graphs: 280/315 edges with unchanged SCC baselines;
- staging, commit and push: none.
