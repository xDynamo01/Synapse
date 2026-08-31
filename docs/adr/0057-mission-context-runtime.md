# ADR 0057: Mission Context Runtime

## Status

Accepted.

## Context

Mission Runtime introduced a durable objective-level grouping for delegations,
but operators and future Mission Control surfaces still needed a consolidated
view of the mission state. Reconstructing that view independently from
missions, delegations, executions, conversations, DLQ, and recovery decisions
would duplicate operational logic across clients.

## Decision

Add `MissionContextRuntime` as a read-only aggregation layer. It consumes:

- `MissionRuntime`
- `DelegationRuntime`
- `DelegationExecutionRuntime`
- `DeadLetterRuntime`
- `DelegationRecoveryRuntime`
- `ConversationRuntime`
- `DelegationTimeoutPolicyRuntime`

It builds `MissionContext` on demand with mission metadata, summary, execution
counts, timeout candidates, DLQ count, recovery candidates, linked
conversations, grouped task lists, and a generated timestamp.

It also returns `MissionContextSummary` with:

- status
- health: `healthy`, `warning`, or `critical`
- progress percentage
- key findings
- warnings
- recommendations

No context is persisted in this stage.

## Rules

- Progress is `completed_tasks / total_tasks`; missions with no tasks report 0%.
- No failures, timeout candidates, DLQ items, or recovery candidates means `healthy`.
- Failures, timeout candidates, or recovery candidates mean `warning`.
- DLQ plus recovery candidates means `critical`.

## Runtime Surface

Commands:

- `/mission-context <mission_id>`
- `/mission-health <mission_id>`
- `/mission-recovery <mission_id>`

API:

- `GET /missions/{mission_id}/context`
- `GET /missions/{mission_id}/health`
- `GET /missions/{mission_id}/recovery`

Health includes `missions_with_critical_context`. Readiness can warn when
critical mission context exists.

## Consequences

Future Mission Control, supervision, planner, and coordination layers can ask
one runtime for mission state instead of rebuilding it from lower-level
runtimes. This does not create automation, planning, workflow execution, DAGs,
or task dependencies.

## Non-Goals

- Mission Control UI.
- Planner.
- Workflow engine.
- DAG.
- Delegation dependencies.
- Analytics.
- Persistent mission context cache.
