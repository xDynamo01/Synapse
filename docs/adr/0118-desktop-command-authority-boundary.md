# ADR 0118 — Desktop Command Authority Boundary

> Historical/superseded: the Electron ADE implementation and release artifacts were removed under ADR 0119 on 2026-08-21. This file is retained as historical evidence only, not active frontend architecture.

Status: **ACCEPTED / IMPLEMENTED** (2026-08-20).

## Decision

Desktop operational commands use a dedicated loopback-only boundary. The Electron main
process authenticates to its managed sidecar with the ephemeral launch credential and
obtains a short-lived, project-bound session. The renderer never receives either secret.

The boundary exposes typed operations rather than the generic `CommandRuntime`. Version 1
allows only `task.create`. Authorization is the intersection of the session capability and
the canonical runtime permission check. Every envelope carries a UUID command identity,
command type, project, session, timestamp and validated operation payload.

## Invariants

- Authentication does not imply authorization.
- A session is bound to exactly one existing project and one sidecar lifecycle.
- Unknown operations, wrong projects, stale sessions and malformed payloads fail before an
  effect.
- The renderer has no direct HTTP, token, filesystem, shell or arbitrary command authority.
- Durable command reservations are written before effects. Exact completed retries replay
  the result; conflicting or incomplete records require reconciliation and are never
  automatically re-executed.
- The command UUID is the correlation identity for task and operational facts.

## Rejected alternatives

- A generic `/execute` endpoint exposing slash commands.
- Trusting actor headers or loopback origin as authentication.
- Persisting the session credential in renderer or user preferences.
- In-memory-only duplicate detection.
