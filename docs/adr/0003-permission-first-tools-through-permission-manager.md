# ADR 0003: Permission-First Tool Execution

## Status

Accepted.

## Context

Personal agents can affect files, tasks, messages, and future devices. Tool execution without a central permission gate would make remote access and autonomy unsafe.

## Decision

Every registered tool has a required permission. `ToolRegistry.execute()` must call `PermissionManager.require()` before tool code runs.

Runtime services that mutate state also call `PermissionManager` directly so schedulers or background workers cannot bypass the invariant by avoiding HTTP.

## Consequences

- Permission decisions are auditable through the event log.
- Tools can be exposed through API, command runtime, future UI, or schedulers without duplicating checks.
- Device and autonomy enforcement can be added to the same permission boundary.

