# ADR 0053: Delegation Timeout Policy

## Status

Accepted.

## Context

Delegation executions can remain `running`, and delegation tasks can remain `in_progress`. Before retry automation, escalation, dead letter queues, Mission Control, or workflow runtime, Synapse needs a safe way to detect stale execution state.

## Decision

Synapse adds `DelegationTimeoutPolicyRuntime`, backed by:

```text
DATA_DIR/config/delegation_timeout_policy.yaml
```

The runtime can:

- find timeout candidates
- evaluate a single task/execution pair
- apply a timeout to a single task
- run a timeout scan

Timeout scans are dry-run by default. Applying a timeout is explicit. Depending on policy, apply may mark the latest running execution as `failed` and optionally mark the task as `failed`.

Critical delegations can require human review; when enabled, apply skips them instead of mutating state.

## Runtime Surface

- `load_policy()`
- `find_timeout_candidates()`
- `evaluate_timeout(task, latest_execution)`
- `apply_timeout(task_id, dry_run=True)`
- `run_timeout_scan(dry_run=True)`

Commands:

- `/delegation-timeout-policy`
- `/delegation-timeout-scan`
- `/delegation-timeout-scan --apply`
- `/delegation-timeout-check <task_id>`
- `/apply-delegation-timeout <task_id>`

API:

- `GET /delegation-timeout-policy`
- `POST /delegations/timeout-scan`
- `POST /delegations/{task_id}/timeout-check`
- `POST /delegations/{task_id}/timeout-apply`

Scheduler job:

- `delegation_timeout_scan`

## Consequences

- Timeout detection is auditable and local-first.
- Timeout application is explicit and conservative.
- No retry automation, escalation, dead letter queue, workflow engine, Mission Control, or UI is introduced.
