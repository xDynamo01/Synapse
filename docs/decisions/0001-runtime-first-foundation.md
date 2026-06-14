# ADR 0001: Runtime-First Foundation

## Status

Accepted.

## Context

Synapse must become a local-first personal agent operating system, not a chatbot UI. The first implementation therefore needs to prove the runtime boundaries before any desktop interface, avatar, voice layer, or advanced agent graph is added.

## Decision

The first foundation implements:

- `RuntimeContainer` as the composition root.
- `DataDir` bootstrap for all local state.
- `PermissionManager` as a mandatory gate for tools and state mutation.
- `EventBus` as append-only JSONL audit trail.
- Persistent agents, memory, tasks, and messages.
- FastAPI as a thin adapter over the runtime.

## Consequences

- UI work can proceed without owning business logic.
- Background workers and schedulers can reuse the same services as HTTP.
- Tool execution is testable without a model.
- Early development is slower than a chat wrapper, but future modules have stable boundaries.

