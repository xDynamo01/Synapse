# Current SCC inventory

Audit date: **2026-07-15**

## Current result

The governed bounded-context graph has **one non-trivial SCC**. The exact
Python-module graph has zero non-trivial SCCs.

| SCC | Classification | Priority | Members | Contexts | Internal edges |
| --- | --- | --- | --- | ---: | ---: |
| SCC-01 | Critical global architectural SCC; reciprocal runtime and type ownership | P1, unchanged | agents, approvals, avatar, context, conversations, decisions, delegation, embodiment, missions, models, policies, tools, voice | 13 | 35 |

SCC-01 retains exactly the same 13 members and 35 internal edges. This phase
did not modify it.

## Intelligence Trust Boundary impact

`intelligence_boundary` remains outside SCC-01. The graph advances from
71/257 to 72 bounded contexts / 261 governed edges through four acyclic
consumer edges. Model Router and Tool Runtime import contracts/models only;
bootstrap owns Storage and Health adapters.

| Measure | Before boundary | After boundary |
| --- | ---: | ---: |
| Contexts | 71 | 72 |
| Governed edges | 257 | 261 |
| Non-trivial SCCs | 1 | 1 |
| Global SCC | 13 / 35 | 13 / 35 |
| Exact-module SCCs | 0 | 0 |

## Project Governance + RFC impact

`project_governance` remains outside SCC-01. The graph advances from 70/252 to
71 bounded contexts / 257 governed edges through five acyclic consumer and
delivery edges. Domain consumers import contracts/models only; bootstrap owns
Storage, document, Tool and Health adapters.

| Measure | Before governance | After governance |
| --- | ---: | ---: |
| Contexts | 70 | 71 |
| Governed edges | 252 | 257 |
| Non-trivial SCCs | 1 | 1 |
| Global SCC | 13 / 35 | 13 / 35 |
| Exact-module SCCs | 0 | 0 |

## Skills Runtime Phase 1 impact

Skills remains outside SCC-01. The graph advances from 69/247 to 70 bounded
contexts / 252 governed edges through five acyclic edges. `skills` imports no
Agents, Ephemeral Agents, Primary Agent, Missions, Swarm, API or Commands;
consumers import contracts only and bootstrap owns concrete adapters.

| Measure | Before Skills | After Skills |
| --- | ---: | ---: |
| Contexts | 69 | 70 |
| Governed edges | 247 | 252 |
| Non-trivial SCCs | 1 | 1 |
| Global SCC | 13 / 35 | 13 / 35 |
| Exact-module SCCs | 0 | 0 |

## Removed SCC

Before:

```text
attention
  -> world_state.models.WorldStateSnapshot

world_state.sources.RuntimeEventStateAdapter
  -> attention.models.AttentionEvent
  -> attention.runtime.AttentionRuntime
```

The return edge existed because a cross-domain event projector was located in
`world_state.sources`. That class both updated World State and submitted
important events to Attention, making World State depend on Attention.

After:

```text
attention.runtime
  -> attention.contracts.WorldStateReadPort.snapshot()

bootstrap.adapters.world_state.WorldStateReadAdapter
  -> world_state.runtime.WorldStateRuntime.snapshot()

bootstrap.adapters.world_state.RuntimeEventStateAdapter
  -> world_state runtime
  -> attention runtime
```

The projection behavior is unchanged but composition is now owned exclusively
by bootstrap. The legitimate consumer direction `attention -> world_state`
remains. The forbidden return direction `world_state -> attention` is absent.

## Contract and adapter assessment

No equivalent consumer-owned contract existed. `WorldStateReadPort` is the
only new port and exposes exactly one synchronous operation:

```python
def snapshot(self) -> WorldStateSnapshot: ...
```

One minimal read adapter binds that contract to the existing
`WorldStateRuntime.snapshot()` method. The moved `RuntimeEventStateAdapter` is
not a new behavioral adapter; it is the existing event projector relocated to
the composition root. No generic interface, factory, DTO or provider
abstraction was introduced.

## SCC impact

| Measure | Before | After |
| --- | ---: | ---: |
| Governed edges | 248 | 247 |
| Non-trivial context SCCs | 2 | 1 |
| Attention/World State SCC | 2 contexts / 2 edges | absent |
| Global SCC | 13 contexts / 35 edges | 13 contexts / 35 edges |
| Exact-module SCCs | 0 | 0 |

No new inverse dependency or cycle appeared. No other SCC changed membership
or internal-edge count.

## Executable guardrails

`tests/architecture/test_attention_world_state_boundary.py` verifies:

1. World State has no runtime import from Attention;
2. Attention uses the snapshot-only port and imports no concrete World State
   runtime/store;
3. the read adapter is bootstrap-owned and delegates only `snapshot()`;
4. composition constructs the runtimes and adapters exactly once;
5. Agent Loop retains its existing coordination dependencies;
6. the governed graph has 247 edges and exactly SCC-01 at 13/35.

The complete architecture suite passes with 92 tests.

## Priority after this phase

The requested phase stops here. SCC-01 remains recorded as pre-existing risk,
but it is not selected or authorized as a follow-on intervention. A separate
audit and explicit scope are required before any further architectural change.
