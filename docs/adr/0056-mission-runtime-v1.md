# ADR 0056: Mission Runtime v1

## Status

Accepted.

## Context

Synapse can process individual delegations, executions, retries, timeouts, DLQ
entries, and recovery decisions. Complex user requests and investigations often
need multiple related delegations, but there was no durable entity representing
the shared objective.

Without a Mission entity, future Mission Control, planner, and coordination
surfaces would need to infer grouping directly from individual delegations.

## Decision

Add `MissionRuntime` as a local-first, persistent grouping layer for
delegations. Missions are persisted under:

```text
DATA_DIR/missions/{mission_id}.yaml
DATA_DIR/missions/{mission_id}.delegations.yaml
```

`Mission` contains:

- mission id
- title
- description
- status
- priority
- optional owner agent id
- optional creator
- optional conversation id
- timestamps
- metadata

`MissionDelegationLink` stores only mission id, task id, and creation timestamp.
The mission does not duplicate delegation records.

`MissionSummary` is calculated on demand from linked delegation task state and
DLQ membership. It is not persisted in this stage.

## Runtime Surface

`MissionRuntime` exposes:

- `create_mission()`
- `get_mission()`
- `list_missions()`
- `update_mission()`
- `archive_mission()`
- `link_task()`
- `unlink_task()`
- `list_mission_tasks()`
- `summarize_mission()`

Commands:

- `/missions`
- `/mission <mission_id>`
- `/create-mission`
- `/link-mission-task <mission_id> <task_id>`
- `/mission-summary <mission_id>`

API:

- `GET /missions`
- `GET /missions/{mission_id}`
- `POST /missions`
- `POST /missions/{mission_id}/tasks`
- `GET /missions/{mission_id}/tasks`
- `GET /missions/{mission_id}/summary`

## Consequences

Synapse now has a durable objective-level grouping primitive without introducing
planning, workflow execution, task dependencies, DAGs, Mission Control, or UI.
Future coordination layers can build on missions instead of overloading
individual delegation records.

## Non-Goals

- Planner.
- Workflow engine.
- Mission Control UI.
- Delegation dependencies.
- DAGs.
- Kanban.
- Automation across agents.
