# ADR 0051: Delegation Execution Runtime

## Status

Accepted.

## Context

`DelegationTask` represents responsibility: who requested work, who owns it, and its lifecycle. It should not also carry every execution attempt. Future retries, timeout policies, escalation, dead letter handling, Mission Control, and analytics require an explicit attempt entity.

## Decision

Synapse adds `DelegationExecutionRuntime`, persisted under:

```text
DATA_DIR/delegation_execution/{execution_id}.yaml
```

`DelegationExecution` represents a single attempt to execute a delegation task. It includes attempt number, status, timestamps, assignee, correlation metadata, result summary, error message, and metadata.

Statuses:

- `pending`
- `running`
- `completed`
- `failed`
- `cancelled`

`DelegationTask` remains the source of truth for responsibility. The delegation inbox continues to point at tasks, not executions.

## Worker Integration

When the worker runs an `in_progress` delegation, it creates an execution and marks it `running`. If the agent runtime raises an error, the execution becomes `failed`.

Successful free-form responses do not complete the execution automatically because task completion must still come from an explicit completion signal.

## Completion Signal Integration

When a completion signal is applied:

- `completed` marks the latest active execution as `completed`
- `failed` marks the latest active execution as `failed`
- `needs_followup` keeps the execution running

Keeping `needs_followup` running is the safer option for this stage because no timeout or retry engine exists yet.

## Runtime Surface

- `create_execution(task_id)`
- `get_execution(execution_id)`
- `list_task_executions(task_id)`
- `start_execution(execution_id)`
- `complete_execution(execution_id)`
- `fail_execution(execution_id)`
- `cancel_execution(execution_id)`
- `latest_execution(task_id)`

Commands:

- `/delegation-executions <task_id>`
- `/delegation-execution <execution_id>`

API:

- `GET /delegations/{task_id}/executions`
- `GET /delegation-executions/{execution_id}`

## Consequences

- Attempts can be tracked independently from responsibility.
- Retry, timeout, escalation, and dead letter behavior can be added later without overloading `DelegationTask`.
- This stage does not implement retry automation, timeout automation, escalation, Mission Control, or a workflow engine.
