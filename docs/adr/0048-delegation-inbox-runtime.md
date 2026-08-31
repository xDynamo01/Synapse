# ADR 0048: Delegation Inbox Runtime

## Status

Accepted.

## Context

Delegations are persisted as durable task records under `DATA_DIR/delegation/`. Workers and future operational surfaces need to find tasks assigned to a specific agent without scanning every delegation file on each cycle.

## Decision

Synapse adds `DelegationInboxRuntime`, a derived per-agent index persisted under:

```text
DATA_DIR/delegation_inbox/{agent_id}.yaml
```

The inbox stores only lightweight references:

- task id
- status
- priority
- requester agent
- assignee agent
- timestamps
- optional conversation id

The source of truth remains `DATA_DIR/delegation/`. Inbox files can be deleted or rebuilt without losing delegation state.

## Runtime Surface

- `rebuild_agent_inbox(agent_id)`
- `rebuild_all_inboxes()`
- `get_agent_inbox(agent_id)`
- `get_pending_tasks(agent_id)`
- `get_active_tasks(agent_id)`
- `get_inbox_summary(agent_id)`

`DelegationRuntime` updates the inbox on task create and status transitions. `AgentWorker` uses the inbox when available and keeps the previous scan behavior as fallback.

## Operations

Commands:

- `/delegation-inbox <agent_id>`
- `/delegation-summary <agent_id>`
- `/rebuild-delegation-inbox <agent_id>`
- `/rebuild-all-delegation-inboxes`

API:

- `GET /delegation-inbox/{agent_id}`
- `GET /delegation-inbox/{agent_id}/summary`
- `POST /delegation-inbox/{agent_id}/rebuild`
- `POST /delegation-inbox/rebuild-all`

Scheduler job:

- `delegation_inbox_rebuild`

## Consequences

- Workers can locate agent-assigned delegations without scanning every task file.
- Corrupted inbox files are recoverable through rebuild.
- Health/readiness can surface inbox corruption or rebuild failures.
- This is not Mission Control, load balancing, analytics, or a workflow engine.
