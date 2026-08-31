# Global Composition Root Slice 6 Audit

Status: **COMPLETE / APPROVED**

## Findings

- `compose_private_evals()` eagerly opens five SQLite stores and may create/migrate the
  configured database; it cannot run during inert application construction.
- `PrivateEvalsRuntimeHandle.close()` is idempotent and closes all five stores.
- The local composition has no separate start phase; readiness distinguishes local,
  externally-bound, degraded, read-only and closed states.
- Every external dependency is already represented by a typed binding. Explicit
  `UnavailableExternalCapability` values preserve absence without fallback.

## Decision

Use a bootstrap-owned deferred lifecycle slot. It holds typed configuration and explicit
unavailable bindings during construction, composes once at lifecycle startup, exposes no
handle before startup, and closes the handle during shutdown. This preserves the frozen
Private Evals contract and keeps import/application construction free of SQLite I/O.

No architecture, product, security or data choice remains for this local-only binding.
Backend remains **NOT READY**.
