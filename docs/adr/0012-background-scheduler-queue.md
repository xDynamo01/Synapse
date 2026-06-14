# ADR 0012: Background Scheduler Queue

Date: 2026-06-14

## Status

Accepted

## Context

Synapse needs a local-first background work layer before homelab 24/7 mode. Agent inbox processing exists, but running it only through direct commands/API calls does not provide durable queued work, retries, or a clear future boundary for a daemon.

The system must remain local-first and avoid external infrastructure at this stage.

## Decision

Create a persistent scheduler queue under `DATA_DIR/jobs`.

Modules:

- `backend/synapse/scheduler/jobs.py`
- `backend/synapse/scheduler/queue.py`
- `backend/synapse/scheduler/runtime.py`

Each job stores:

- id
- type
- payload
- status
- priority
- attempts
- max_attempts
- created/updated timestamps
- optional schedule, start, completion, failure, and correlation metadata

`SchedulerRuntime` supports enqueueing, listing, loading, cancelling, running next, running all pending, and retrying failed jobs.

The initial job type is `process_agent_inbox`, which calls `AgentWorker.process_inbox()`.

## Consequences

Positive:

- background work is durable across runtime restarts
- job execution produces auditable events
- inbox work can be queued without introducing a daemon yet
- future homelab runner can reuse the same runtime contract

Tradeoffs:

- no always-on loop is started by default
- no concurrency locking or distributed coordination exists
- retry is manual and has no backoff policy yet
- old job retention/cleanup is not implemented
