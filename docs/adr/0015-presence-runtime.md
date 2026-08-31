# ADR 0015: Presence Runtime

Date: 2026-06-19

## Status

Accepted

## Context

Synapse needs a durable, observable way to represent what each agent is currently doing. Chat, workers, scheduler jobs, Voice, and future UI clients should not infer state by scraping logs or duplicating runtime logic.

## Decision

Create `synapse.presence` as a runtime-owned layer with:

- `AgentPresence` records persisted at `DATA_DIR/presence/<agent_id>.yaml`
- `PresenceRuntime.get()`, `set_state()`, `clear()`, and `list_all()`
- `presence.updated` events for every transition
- optional correlation metadata from the active `CorrelationContext`

Initial integrations update presence from Chat Runtime, Agent Runtime, ToolRouter approval waits, AgentWorker, and SchedulerRuntime agent jobs.

## Consequences

Presence is a projection, not a source of authorization. Permission, approval, and policy decisions remain in their existing runtimes.

The current implementation is intentionally single-record-per-agent and local-first. It does not yet track historical presence timelines, concurrent activities per agent, distributed locks, or richer emotional state.
