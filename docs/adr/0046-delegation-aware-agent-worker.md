# ADR 0046: Delegation-aware Agent Worker

## Status

Accepted.

## Context

Delegation tasks represent responsibility, but they were not yet operationalized by the worker. The worker needs to process assigned delegations without becoming a workflow engine or autonomous planner.

## Decision

Extend `AgentWorker` with:

- `process_delegations(agent_id, limit=1)`
- `process_next_delegation(agent_id)`

Processing is intentionally conservative:

- `pending` delegations are not auto-accepted under manual autonomy.
- `accepted` delegations move to `in_progress`.
- `in_progress` delegations call `AgentRuntime` with an optional `delegation_context`.
- If a conversation is linked, the worker creates a response message in that conversation.
- Delegations are not marked `completed` automatically from plain model text.

Scheduler support is added through job type:

```text
process_agent_delegations
```

## Consequences

- Delegations can be processed incrementally by background jobs, commands, or API.
- Responsibility state remains explicit and durable.
- The worker does not infer completion from unstructured text.
- No workflow engine, planner, or unrestricted automation is introduced.

## Non-Goals

- No UI or Mission Control.
- No workflow engine.
- No multi-agent planner.
- No automatic completion inference.
- No RAG, embeddings, or external providers.
