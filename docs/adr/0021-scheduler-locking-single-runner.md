# ADR 0021: Scheduler Locking / Single Runner Guard

Date: 2026-06-19

## Status

Accepted

## Context

Homelab mode may accidentally start multiple daemon or scheduler processes against the same `DATA_DIR`. Without a guard, those runners can execute the same pending or recurring jobs simultaneously.

## Decision

Add a local scheduler lock at:

```text
DATA_DIR/locks/scheduler.lock
```

`SchedulerLock` stores `owner_id` and `acquired_at`, supports `acquire()`, `release()`, `is_locked()`, stale lock detection, and stale recovery. Timeout is configured through `config/scheduler_policy.yaml`.

`SchedulerRuntime.run_next()`, `run_all_pending()`, and `enqueue_due_recurring_jobs()` acquire the lock before mutating scheduler state. `DaemonRunner` uses the SchedulerRuntime and therefore respects the guard indirectly.

## Consequences

The scheduler now has a single-runner guard for local processes sharing a `DATA_DIR`. This is intentionally not a distributed lock.

Known gaps:

- no Redis/database/distributed lock
- no OS-level advisory file lock
- no heartbeat renewal for long-running jobs
- no systemd or Windows service integration
