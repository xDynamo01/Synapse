# ADR 0050: Delegation Autonomy Policy

## Status

Accepted.

## Context

Delegation scheduling decides which assigned task is next. It does not decide whether an agent is allowed to accept, start, or reject a delegation automatically. That decision needs to be configurable, conservative, and auditable before higher-level coordination surfaces exist.

## Decision

Synapse adds `DelegationAutonomyPolicyRuntime`, backed by:

```text
DATA_DIR/config/delegation_autonomy_policy.yaml
```

The default policy is conservative:

- auto-accept is disabled
- manual autonomy blocks auto-accept
- auto-start for already accepted tasks is allowed to preserve existing worker behavior
- critical delegations require approval, but no approval request is created automatically in this stage

The runtime evaluates:

- `accept`
- `start`
- `reject`

Each evaluation returns a structured `DelegationAutonomyDecision` with allowed/blocked/requires_approval, reasons, risk level, and metadata.

## Runtime Integration

`AgentWorker` checks autonomy before:

- `pending -> accepted`
- `accepted -> in_progress`

Blocked or approval-required decisions leave the delegation in its current state and emit clear events.

`DecisionRuntime` supports the optional category `delegation_autonomy` for read-only evaluation.

## Commands and API

Commands:

- `/delegation-autonomy-policy`
- `/delegation-autonomy-check <task_id> <accept|start|reject>`

API:

- `GET /delegation-autonomy-policy`
- `POST /delegations/{task_id}/autonomy-check`

## Consequences

- Delegation transitions are now policy-driven instead of hardcoded in the worker.
- The default remains safe for manual agents.
- No workflow engine, planner, UI, or approval flow is introduced.
