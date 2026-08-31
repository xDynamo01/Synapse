# ADR 0045: Agent Task Delegation Runtime

## Status

Accepted.

## Context

Agent-to-agent messages support communication, but a message does not represent responsibility. For durable collaboration, Synapse needs an explicit delegation entity that can be assigned, accepted, started, completed, failed, or cancelled.

## Decision

Add `DelegationRuntime` under `backend/synapse/delegation/`.

Delegation records are persisted as YAML:

```text
DATA_DIR/delegation/{task_id}.yaml
```

Delegation lifecycle states:

- `pending`
- `accepted`
- `rejected`
- `in_progress`
- `completed`
- `failed`
- `cancelled`

Priorities:

- `low`
- `normal`
- `high`
- `critical`

Creating a delegation requires the requester agent to have capability:

```text
agent.task.delegation
```

The runtime checks `AgentAdminRuntime` before assignment, so archived or inactive agents cannot receive delegations.

If a delegation is linked to a conversation, status updates may append lightweight conversation messages. This keeps the relationship traceable without creating a workflow engine.

## Consequences

- Delegation becomes a durable responsibility record, separate from chat/messages.
- Capabilities control which agents can delegate.
- Events and agent audit records capture lifecycle transitions.
- Conversations can reference delegation state without becoming a planner.

## Non-Goals

- No UI or Mission Control.
- No workflow engine.
- No multi-agent planner.
- No RAG, embeddings, or Resource Registry.
- No external provider integration.
