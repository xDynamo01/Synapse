# ADR 0052: Delegation Retry Policy

## Status

Accepted.

## Context

`DelegationExecution` tracks individual attempts. After a failed attempt, Synapse needs a clear policy for whether a delegation can be reopened for another attempt. This must happen before retry automation, timeouts, escalation, dead letter queues, Mission Control, or workflow logic.

## Decision

Synapse adds `DelegationRetryPolicyRuntime`, backed by:

```text
DATA_DIR/config/delegation_retry_policy.yaml
```

The policy evaluates a `DelegationTask` plus its executions and returns a structured `DelegationRetryDecision`:

- `allowed`
- `blocked`
- `requires_approval`
- attempt count
- max attempts
- reasons and blocked reasons
- risk level

`DelegationRuntime.request_retry()` uses this decision. If allowed, it reopens the task to the configured retry status, currently `accepted` by default. It does not create a new `DelegationExecution`; the worker creates the next execution when it processes the task again.

If retry requires approval, this stage returns `requires_approval` only. It does not create an `ApprovalRequest`.

## Runtime Surface

- `DelegationRetryPolicyRuntime.load_policy()`
- `DelegationRetryPolicyRuntime.evaluate_retry(task, executions)`
- `DelegationRetryPolicyRuntime.explain_retry(task_id, task, executions)`
- `DelegationRuntime.request_retry(task_id, requested_by_agent_id=None, reason=None)`

Commands:

- `/delegation-retry-policy`
- `/delegation-retry-check <task_id>`
- `/retry-delegation <task_id>`

API:

- `GET /delegation-retry-policy`
- `POST /delegations/{task_id}/retry-check`
- `POST /delegations/{task_id}/retry`

## Consequences

- Retry is explicit and policy-driven.
- Max attempts are enforced.
- Retry does not execute work directly.
- Approval integration can be added later without changing the retry decision contract.
- No retry scheduler, timeout engine, escalation, dead letter queue, planner, workflow engine, or UI is introduced.
