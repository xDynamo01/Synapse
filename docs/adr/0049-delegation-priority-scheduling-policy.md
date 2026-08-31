# ADR 0049: Delegation Priority and Scheduling Policy

## Status

Accepted.

## Context

Delegation inboxes let workers find tasks assigned to an agent without scanning every delegation file. The next issue is ordering: workers need a predictable, configurable way to choose which delegation to process first.

## Decision

Synapse adds `DelegationSchedulingPolicyRuntime` backed by:

```text
DATA_DIR/config/delegation_scheduling_policy.yaml
```

The policy scores active delegations using:

- task priority
- status order
- overdue `due_at`
- aging
- FIFO tie-breaking
- optional critical-first behavior

The worker orders active delegations through the policy before applying its per-cycle limit. If the policy is disabled or fails, the worker falls back to the existing inbox order and emits `delegation.scheduling.failed` on errors.

## Runtime Surface

- `load_policy()`
- `score_task(task)`
- `sort_tasks(tasks)`
- `select_next_task(agent_id, tasks)`
- `explain_task_order(agent_id, tasks)`

Commands:

- `/delegation-scheduling-policy`
- `/delegation-next <agent_id>`
- `/delegation-order <agent_id>`

API:

- `GET /delegation-scheduling-policy`
- `GET /delegation-inbox/{agent_id}/next`
- `GET /delegation-inbox/{agent_id}/order`

## Consequences

- Delegation processing order is explicit and locally configurable.
- The scheduler remains simple; this is not a planner, workflow engine, load balancer, or analytics system.
- Future Mission Control can explain why a delegation was selected without parsing worker internals.
