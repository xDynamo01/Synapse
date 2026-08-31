# ADR 0022: Runner Identity and Heartbeat

Date: 2026-06-19

## Status

Accepted

## Context

Synapse homelab mode needs stable runner identity and heartbeat diagnostics. Scheduler locking introduced owner ids, but generated owners are hard to diagnose and do not survive runtime recreation.

## Decision

Add `RunnerIdentityStore`, persisted at:

```text
DATA_DIR/daemon/runner.yaml
```

`RunnerIdentity` includes:

- `runner_id`
- `hostname`
- `process_id`
- `created_at`
- `last_seen_at`
- `role`
- `status`

Daemon updates heartbeat in `run_once()`, marks online during `run_once()`/`start_loop()`, marks offline in `stop()`, and marks error when `run_once()` catches a controlled failure.

`SchedulerLock` uses the stable runner id as `owner_id`.

## Consequences

Runner state is now diagnosable without UI or external service managers. This remains local-only and file-backed.

Known gaps:

- no systemd/Windows Service integration
- no Docker healthcheck
- no dashboard UI
- no multi-node registry
- no distributed lock
