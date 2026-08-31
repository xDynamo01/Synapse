# ADR 0058: Mission Supervision Runtime

## Status

Accepted.

## Context

Mission Context can consolidate the state of a single mission, but future
operators and Mission Control surfaces also need an operational view across
missions: which missions are healthy, degraded, critical, or need attention.

Embedding this classification in UI, dashboards, commands, or automation would
duplicate supervision logic.

## Decision

Add `MissionSupervisionRuntime` as a read-only supervision layer. It consumes:

- `MissionRuntime`
- `MissionContextRuntime`
- `DelegationRecoveryRuntime`
- `DeadLetterRuntime`
- optional `HealthRuntime`
- optional `ReadinessRuntime`

It generates:

- `MissionSupervisionState`
- `MissionAttentionItem`
- `MissionSupervisionSummary`

Supervision is generated on demand and is not persisted.

## Rules

- `healthy`: no DLQ, no recovery candidates, no timeout candidates, no failed tasks.
- `warning`: recovery candidates, failed tasks, or timeout candidates.
- `critical`: DLQ present, critical recovery, or critical mission context.

Attention item types include:

- `timeout_detected`
- `recovery_required`
- `dead_letter_present`
- `failed_tasks`
- `mission_blocked`

## Runtime Surface

Commands:

- `/mission-supervision`
- `/mission-attention`
- `/mission-status <mission_id>`

API:

- `GET /mission-supervision`
- `GET /mission-attention`
- `GET /missions/{mission_id}/status`

Health includes mission warning and critical counts. Readiness can warn when
missions require attention.

## Consequences

Mission supervision becomes reusable by future Mission Control and operational
surfaces without creating workflow behavior. No recovery, escalation, planning,
or automation is executed by this runtime.

## Non-Goals

- Mission Control UI.
- Dashboard.
- Planner.
- Workflow engine.
- DAG.
- Task dependencies.
- Automatic recovery.
- Automatic escalation.
