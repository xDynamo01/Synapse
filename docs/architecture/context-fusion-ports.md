# Context Fusion Read Ports

`ContextFusionRuntime` is a consumer-owned coordinator. It imports no functional
domain implementation and receives six explicit read ports from the composition
root.

| Port | Methods | Owner adapter | Required |
| --- | --- | --- | --- |
| `ConversationContextReader` | `participants`, `read` | Conversation | with conversation ID |
| `MissionContextReader` | `get_mission`, `list_task_ids`, `get_task`, `summarize` | Missions + Delegation | with mission ID |
| `PerceptionContextReader` | `list_signals`, `list_observations` | Perception | runtime required; empty valid |
| `MultimodalContextReader` | `participants` | Multimodal | with session ID |
| `MemoryContextReader` | `retrieve` | Memory | optional |
| `RuntimeStatusContextReader` | `health_summary`, `readiness_summary` | Health + Readiness | only when requested |

DTOs live in `synapse.context_fusion.contracts`, contain only consumed fields,
and expose no stores, DataDir, administration or persistence. There is no Agent
or World State port because neither is a current source.

Adapters live under `synapse.bootstrap.adapters`, use public read facades and
are created once by bootstrap. A compatibility-only `list_conversations` on the
Conversation adapter preserves frozen Health behavior without changing Health.

Reads copy the correlation context into a daemon thread and have a five-second
technical timeout. Missing optional Memory is an empty source. Existing
`NotFound` handling and propagation of other exceptions remain. Missing required
constructor ports raise `context_source_unavailable`; absent confidence remains
`None`.

Priority, deduplication, token estimates, budget, omissions, provenance,
sensitivity and snapshot persistence remain in Context Fusion. Snapshot output
uses the domain's injected snapshot root, not a mutating cross-domain port.

With the established AST graph (excluding API, Commands, bootstrap and Core),
Context Fusion moved from the 26-context/79-edge SCC to a 1/0 singleton. The
remaining related SCC is 25/75; unrelated 4/6 and 2/2 SCCs are unchanged.
