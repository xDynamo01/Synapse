# ADR 0004: Runtime-First UI Boundary

## Status

Accepted.

## Context

Synapse is an agent operating system, not a desktop UI with attached helpers. Features must continue to work when the UI is closed or replaced.

## Decision

The Runtime owns behavior. API, future desktop UI, mobile clients, voice input, and schedulers are clients of Runtime services.

FastAPI is an adapter over `RuntimeContainer`; it must not own persistence, tool execution, memory composition, or agent logic.

## Consequences

- Desktop UI can be built later without moving business logic.
- Background and homelab operation remain possible.
- A command/runtime application boundary should be preferred over UI-specific handlers.

