# Architecture stabilization — Audio/Speech boundary

Date: **2026-07-15**

Worktree: `backend-freeze-cleanup` at
`8196eb11c34442af563b20082bc1666755f4d8a9` (dirty before this phase)

## Result

The single authorized dependency `audio -> speech_adapters` was removed.
Behavior is unchanged, the `audio/speech_adapters` SCC is gone, and neither
remaining SCC changed.

No Voice, Speech Pipeline, Conversation Mode, Voice Message, Provider, Health,
Readiness, Command, API, Context Fusion, Tool, Mission, Storage, Provider
Catalog, Primary Agent, Ephemeral Agent, Swarm or Model Router code was changed.

## Architecture before

`AudioRuntime` imported and exposed the concrete supplier runtime:

```text
audio/runtime.py
  -> speech_adapters/runtime.py::SpeechAdapterRuntime
  -> audio/models.py and audio/ingestion.py
```

The forward edge existed solely because `AudioRuntime.__init__` annotated its
injected dependency as `SpeechAdapterRuntime`. The runtime called only
`transcribe` and `synthesize`. Speech adapters legitimately imported Audio-owned
requests, results and ingestion helpers, producing a 2-node / 2-edge SCC.

## Architecture after

```text
audio/runtime.py
  -> audio/contracts.py::SpeechExecutionPort

speech_adapters/runtime.py
  -> audio/models.py and audio/ingestion.py

bootstrap/features/interaction.py
  -> AudioRuntime(..., SpeechAdapterRuntime, ...)
```

Audio has zero imports from `synapse.speech_adapters`. The existing
`SpeechAdapterRuntime` instance is still supplied by the composition root, which
is the only production construction site for `AudioRuntime`.

## Contract used

No equivalent contract could be reused without retaining the forbidden
dependency. The supplier-owned protocols in `speech_adapters/interfaces.py`
also expose manifest and health behavior and therefore are not the minimal
consumer contract. The generic Voice provider contracts have different DTO and
method surfaces.

The new consumer-owned `SpeechExecutionPort` contains exactly:

```python
def transcribe(request: AudioInputRequest) -> SpeechToTextResult: ...
def synthesize(request: AudioOutputRequest) -> TextToSpeechResult: ...
```

`SpeechToTextResult` is the existing alias of `TranscriptResult`, preserving the
current runtime return type. No DTO, schema, exception, event or public method
was changed.

## Adapter and wiring

No adapter was created. Python structural protocols allow the existing
`SpeechAdapterRuntime` to implement the two methods directly. Adding a wrapper
would have been redundant.

Wiring was already correctly located in
`bootstrap/features/interaction.py` and remains unchanged. The architecture
guardrail verifies that this is the sole production `AudioRuntime` construction
site and that bootstrap supplies `dependencies.speech_adapters` there.

## Files changed by this phase

Production and architecture test:

- `backend/synapse/audio/contracts.py` — new two-method consumer port;
- `backend/synapse/audio/runtime.py` — concrete type import replaced by port;
- `tests/architecture/test_audio_speech_boundary.py` — three focused guards.

Authorized documentation:

- `docs/audit/current-scc-inventory.md`;
- `docs/audit/current-dependency-graph.md`;
- `docs/validation/backend-freeze-baseline.md`;
- this report.

No other file was changed by this phase. The surrounding worktree already
contained extensive user-owned modifications and untracked files.

## Architectural validation

The new AST guardrail differentiates runtime imports from imports below
`TYPE_CHECKING`, matching the current audit methodology. It proves:

- no Audio production module imports `synapse.speech_adapters`;
- `AudioRuntime` uses `SpeechExecutionPort` and contains no
  `SpeechAdapterRuntime` reference;
- bootstrap contains the only production AudioRuntime construction;
- the governed graph has 248 edges;
- remaining SCCs are exactly SCC-01 at 13/35 and
  `attention/world_state` at 2/2.

The historical Phase-1 helper still retains a larger allowance because it
counts `TYPE_CHECKING` imports as runtime edges. It was not weakened or modified.

| Measure | Before | After |
| --- | ---: | ---: |
| Governed bounded-context edges | 249 | 248 |
| Non-trivial bounded-context SCCs | 3 | 2 |
| Audio/Speech SCC | 2 nodes / 2 edges | absent |
| SCC-01 | 13 / 35 | 13 / 35 |
| Attention/World State SCC | 2 / 2 | 2 / 2 |
| Exact-module SCCs | 0 | 0 |

No new inverse dependency, port family, adapter or redundant abstraction was
introduced.

## Functional validation

Focused checks:

- Audio and Speech behavior suite: 41 tests passed;
- final boundary guardrail: 3 tests passed in 5.22 s;
- combined focused execution exercised 44 tests; an initial assertion in the
  newly written graph test counted process modules as contexts, while all 43
  preceding behavior/boundary checks passed. The test aggregation was aligned
  with the audited graph and then passed; production code was unchanged by that
  correction.

Final global gates:

- `uv run --extra dev pytest`: 1,128 collected; 1,126 passed; 2 skipped;
  0 failed; 1,131.59 s;
- `uv run --extra dev ruff check .`: passed;
- `git diff --check`: passed, with only pre-existing LF-to-CRLF warnings.

## OpenAPI equivalence

Before and after values are identical:

| Measure | Before | After |
| --- | ---: | ---: |
| Paths | 443 | 443 |
| Operations | 490 | 490 |
| Schemas | 107 | 107 |
| Duplicate operation IDs | 0 | 0 |
| Canonical OpenAPI SHA-256 | `94a03c0c8ce5a829e0af5f3754f626bbcf83d442a4050ff76dffe241360f1a34` | same |
| Operation matrix SHA-256 | `7537ec22d3406f73ceb7792c454d51fc6c2271e768e15029b15a6d66648b93a1` | same |

No operation, schema, route, operation ID or command changed.

## Scope confirmation

This phase did not rename or move files, extract services, create factories,
move DTOs, change providers, improve logging/events/observability, address TODOs
or attack another SCC. It stops at the removal of the single concrete edge.

The backend remains **NOT READY**. No commit, push or pull request was created.
