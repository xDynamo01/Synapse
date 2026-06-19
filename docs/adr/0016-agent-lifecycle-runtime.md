# ADR 0016: Agent Lifecycle Runtime

Date: 2026-06-19

## Status

Accepted

## Context

Synapse needs a durable operational lifecycle for agents before richer background, communication, voice, perception, and UI layers are added. Presence already records what an agent is doing now, but it should not also own lifecycle counters or operational stage management.

## Decision

Create `synapse.lifecycle` with durable records under `DATA_DIR/lifecycle/<agent_id>.yaml`.

Lifecycle states are:

- `offline`
- `booting`
- `idle`
- `waking`
- `working`
- `waiting`
- `sleeping`
- `error`
- `shutdown`

`LifecycleRuntime` exposes `boot`, `wake`, `sleep`, `shutdown`, `error`, `get`, and `list_all`. Every transition emits a specific event and `agent.lifecycle_changed`.

Lifecycle integrates with Presence but remains separate:

- boot sets presence to `idle`
- wake sets presence to `working`
- sleep sets presence to `idle`
- shutdown sets presence to `offline`
- error sets presence to `error`

AgentWorker and SchedulerRuntime use lifecycle for inbox work.

## Consequences

Lifecycle is now the place for future daemon and homelab operational management. The first version records transitions and counters but does not yet enforce a strict state transition graph, distributed locking, or historical lifecycle timeline.
