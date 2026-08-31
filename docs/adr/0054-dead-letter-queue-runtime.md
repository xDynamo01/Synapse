# ADR 0054: Dead Letter Queue Runtime

## Status

Accepted.

## Context

Synapse can now represent delegation tasks, execution attempts, retry decisions,
timeout candidates, inbox indexes, and worker processing. Failed or timed-out
delegations still needed an explicit operational destination so they would stop
reappearing in normal inbox and scheduling flows while waiting for manual review.

## Decision

Add a local-first Dead Letter Queue Runtime persisted under:

```text
DATA_DIR/dead_letter/{dlq_id}.yaml
```

Each entry records the delegation task, latest execution when available, reason,
status, priority, requester, assignee, optional conversation id, correlation
metadata, timestamp, and metadata.

Supported statuses are:

- `open`
- `reviewed`
- `restored`
- `closed`

Supported reasons are:

- `max_retries_exceeded`
- `timeout_exceeded`
- `manual_move`
- `repeated_failure`
- `execution_failure`
- `unknown`

Moving a delegation to DLQ is explicit. Retry and timeout policies do not move
tasks automatically in this stage. Tasks with non-restored DLQ entries are
filtered out of the delegation inbox and therefore out of normal worker and
scheduling flows. Restore is the only operation that returns a task to the
operational flow, and it does not create a retry or execution automatically.

## Runtime Surface

`DeadLetterRuntime` exposes:

- `create_entry()`
- `move_to_dead_letter()`
- `get_entry()`
- `list_entries()`
- `list_open_entries()`
- `review_entry()`
- `restore_entry()`
- `close_entry()`
- `review_scan()`

Commands:

- `/dead-letter`
- `/dead-letter <dlq_id>`
- `/move-to-dead-letter <task_id>`
- `/review-dead-letter <dlq_id>`
- `/restore-dead-letter <dlq_id>`
- `/close-dead-letter <dlq_id>`

API:

- `GET /dead-letter`
- `GET /dead-letter/{dlq_id}`
- `POST /dead-letter`
- `POST /dead-letter/{dlq_id}/review`
- `POST /dead-letter/{dlq_id}/restore`
- `POST /dead-letter/{dlq_id}/close`

## Consequences

This creates a safe stop point for problematic delegations without adding retry
automation, escalation, a workflow engine, Mission Control, or UI. Health and
readiness can report open DLQ entries, while operators can decide whether to
review, restore, or close them.

## Non-Goals

- Automatic retry.
- Automatic escalation.
- Dead letter recovery automation.
- Workflow engine behavior.
- Planner behavior.
- UI or dashboard.
