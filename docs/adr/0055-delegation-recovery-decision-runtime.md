# ADR 0055: Delegation Recovery Decision Runtime

## Status

Accepted.

## Context

Synapse can now track delegation tasks, execution attempts, retry eligibility,
timeout candidates, and dead letter queue entries. These subsystems identify
signals, but they do not answer a single operational question: what should an
operator or future Mission Control surface do with this delegation now?

Duplicating that reasoning in commands, API clients, health, future UI, or
future automation would fragment recovery behavior.

## Decision

Add `DelegationRecoveryRuntime` as a passive decision layer. It consumes:

- `DelegationRuntime`
- `DelegationExecutionRuntime`
- `DelegationRetryPolicyRuntime`
- `DelegationTimeoutPolicyRuntime`
- `DeadLetterRuntime`

It generates `RecoveryDecision` records on demand with:

- task id
- recommendation
- risk level
- reasons
- recommended actions
- execution counts
- timeout/DLQ/retry signals
- generation timestamp
- metadata

Initial recommendations:

- `continue_processing`
- `retry_task`
- `manual_review`
- `move_to_dead_letter`
- `restore_from_dead_letter`
- `cancel_task`
- `unknown`

The runtime emits `recovery.decision.generated` and
`recovery.decision.failed`, but decisions are not persisted in this stage.

## Rules

- Healthy pending/accepted/in-progress tasks recommend `continue_processing`.
- Failed tasks with retry allowed recommend `retry_task`.
- Failed tasks with retry blocked and no DLQ recommend `move_to_dead_letter`.
- Open/closed DLQ entries recommend `manual_review`.
- Reviewed DLQ entries recommend `restore_from_dead_letter`.
- Critical timeout candidates recommend `manual_review`.

## Consequences

Recovery reasoning is now centralized and reusable by commands, API, health,
readiness, and future Mission Control. The runtime does not perform actions,
create retries, restore DLQ entries, cancel tasks, escalate, or schedule work.

## Non-Goals

- Automatic recovery.
- Automatic retry.
- Automatic escalation.
- Workflow engine behavior.
- Planner behavior.
- UI or Mission Control.
- Persistent recovery decision history.
