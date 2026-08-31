# Architecture stabilization — Attention/World State boundary

Date: **2026-07-15**

Worktree: `backend-freeze-cleanup` at
`8196eb11c34442af563b20082bc1666755f4d8a9` (dirty before this phase)

## Result

The single authorized dependency `world_state -> attention` was removed.
Behavior is unchanged, the `attention/world_state` SCC is gone, and the only
remaining SCC is unchanged at 13 contexts / 35 internal edges.

No API, command, provider, health/readiness, Voice, Speech, Audio, Context
Fusion, Tool Runtime, Mission Runtime, Storage, Provider Catalog, Primary
Agent, Ephemeral Agent, Swarm or Model Router behavior was changed.

## Architecture before

Attention legitimately read the World State snapshot while an event projection
class inside the World State package depended on Attention:

```text
attention.runtime / attention.decision
  -> world_state.models.WorldStateSnapshot

world_state.sources.RuntimeEventStateAdapter
  -> world_state.runtime.WorldStateRuntime
  -> attention.runtime.AttentionRuntime
  -> attention.models.AttentionEvent
```

This produced the direct 2-context / 2-edge SCC
`attention <-> world_state`. The projection was composition behavior located
inside a domain package.

## Architecture final

```text
attention.runtime
  -> attention.contracts.WorldStateReadPort.snapshot()

bootstrap.adapters.world_state.WorldStateReadAdapter
  -> world_state.runtime.WorldStateRuntime.snapshot()

bootstrap.adapters.world_state.RuntimeEventStateAdapter
  -> world_state runtime
  -> attention runtime

bootstrap.features.world
  -> constructs and binds all four objects exactly once
```

World State now has zero imports from Attention. Attention has no import of the
concrete World State runtime or persistence implementation. All concrete
coordination is confined to the composition root.

## Reason for the change

The read direction belongs to Attention: scoring needs the current World State
snapshot. The return direction did not express domain ownership; it came from
an event projector coordinating two runtimes. Moving that projector to
bootstrap removes the false domain dependency without changing projection,
ordering, error isolation or Agent Loop behavior.

## Dependency removed

Removed production imports from `world_state.sources`:

- `synapse.attention.models.AttentionEvent`;
- `synapse.attention.runtime.AttentionRuntime`.

The required `attention -> world_state` model dependency remains and is no
longer reciprocal.

## Contract used

No equivalent minimal consumer-owned contract existed. The new
`WorldStateReadPort` exposes only:

```python
def snapshot(self) -> WorldStateSnapshot: ...
```

It is deliberately synchronous because the existing read is synchronous. It
does not expose mutation, reconciliation, history, storage, health or event
operations.

## Adapter and wiring

`WorldStateReadAdapter` is bootstrap-owned and delegates only
`WorldStateRuntime.snapshot()`. It adds no timeout, retry, caching or exception
translation, preserving the previous semantics. A 500-read local probe
measured a 2.6033 ms mean through the adapter versus a 2.7261 ms mean baseline
over 200 direct reads; this is evidence of no material regression, not a
performance guarantee.

`RuntimeEventStateAdapter` was moved intact from `world_state.sources` to
bootstrap. Its event-to-state mappings, Attention event mappings, correlation,
provenance, deduplication inputs, severity/disposition rules and outer failure
isolation remain unchanged. The only call-site change lets Attention obtain the
same current snapshot through its injected port.

## Functional equivalence

Controlled before/after coverage confirms unchanged outcomes for:

- state revision, presence projection, history, correlation and provenance;
- Attention relevance, priority, status, occurrence count and deduplication;
- repeated-event idempotency;
- TTL expiry and restart persistence;
- escalation from suppressed to pending/critical;
- do-not-disturb deferral without approval;
- state-unavailable fallback;
- Agent Loop `record_only` completion and item resolution.

The new focused tests also prove that a failing snapshot read remains isolated
by the event projection: the authoritative state update persists and the source
event is not broken. No timeout existed on the old synchronous read and none was
introduced.

## SCC impact

| Measure | Before | After |
| --- | ---: | ---: |
| Governed bounded-context edges | 248 | 247 |
| Non-trivial bounded-context SCCs | 2 | 1 |
| Attention/World State SCC | 2 / 2 | absent |
| Remaining global SCC | 13 / 35 | 13 / 35 |
| Exact-module SCCs | 0 | 0 |

No new inverse dependency, port family, adapter family or redundant
abstraction was introduced. No other SCC changed.

## Tests executed

- focused functional and affected-domain suite: 52 passed in 27.83 s;
- architecture boundary tests: 13 passed in 5.52 s;
- full architecture suite: 92 passed in 24.66 s;
- affected acceptance suite: 8 passed in 2.33 s;
- global `uv run --extra dev pytest`: 1,138 collected; 1,136 passed;
  2 skipped; 0 failed in 673.43 s;
- `uv run --extra dev ruff check .`: passed;
- `git diff --check`: passed, with only pre-existing line-ending warnings.

## OpenAPI equivalence

Before and after values are identical:

| Measure | Before | After |
| --- | ---: | ---: |
| Paths | 443 | 443 |
| Operations | 490 | 490 |
| Unique operation IDs | 490 | 490 |
| Schemas | 107 | 107 |
| Duplicate operation IDs | 0 | 0 |
| Canonical OpenAPI SHA-256 | `94a03c0c8ce5a829e0af5f3754f626bbcf83d442a4050ff76dffe241360f1a34` | same |
| Operation matrix SHA-256 | `7537ec22d3406f73ceb7792c454d51fc6c2271e768e15029b15a6d66648b93a1` | same |

No operation, route, operation ID, public schema or command was added, removed
or renamed.

## Files changed by this phase

Production:

- `backend/synapse/attention/contracts.py`;
- `backend/synapse/attention/runtime.py`;
- `backend/synapse/bootstrap/adapters/world_state.py`;
- `backend/synapse/bootstrap/features/world.py`;
- `backend/synapse/world_state/__init__.py`;
- `backend/synapse/world_state/sources.py`.

Tests:

- `tests/architecture/test_attention_world_state_boundary.py`;
- `tests/test_attention_world_state_boundary.py`;
- the preceding Audio/Speech graph expectation was advanced from the prior
  248/two-SCC baseline to the current 247/one-SCC baseline.

Authorized documentation:

- `docs/audit/current-scc-inventory.md`;
- `docs/audit/current-dependency-graph.md`;
- `docs/audit/next-cycle-target.md`;
- `docs/validation/backend-freeze-baseline.md`;
- this report.

No other pre-existing worktree change is owned by this phase.

## Scope confirmation

No file was renamed, no DTO moved, no service/factory/provider abstraction was
created, and no logging, event, observability or unrelated test cleanup was
performed. Work stops at removal of the requested cycle.

The backend remains **NOT READY**. No commit, push or pull request was created.
