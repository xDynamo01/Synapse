# ADR 0013: Synapse Daemon Background Runner

Date: 2026-06-14

## Status

Accepted

## Context

Synapse now has a durable local job queue and an agent worker. Homelab mode needs a runtime boundary that can execute background cycles without requiring a UI request for each job.

This stage should not introduce process supervision, UI controls, mobile controls, or OS-specific service setup yet.

## Decision

Create `DaemonRunner` with:

- `run_once()` for deterministic single-cycle execution
- `start_loop(interval_seconds)` as a simple future CLI/service boundary
- `stop()`
- persisted `status()`

Persist daemon status under:

```text
DATA_DIR/daemon/status.yaml
```

Each cycle emits `daemon.tick`, calls `SchedulerRuntime.run_all_pending()`, persists the jobs run, and catches unexpected runtime errors as `daemon.error`.

Expose only safe runtime entry points for now:

- command `/daemon-status`
- command `/daemon-run-once`
- API `GET /daemon/status`
- API `POST /daemon/run-once`

Do not implement `/daemon-start` in the runtime command layer yet; a real long-lived process should be introduced through a CLI/service wrapper.

## Consequences

Positive:

- background cycles are now testable and deterministic
- daemon status survives runtime recreation
- queued work can be executed through a homelab-ready boundary
- future process wrappers can reuse the same runtime object

Tradeoffs:

- no OS service integration yet
- no locking for multiple daemon instances sharing one `DATA_DIR`
- no supervised 24/7 process lifecycle yet
- no backoff or advanced retry policy yet
