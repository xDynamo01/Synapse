# ADR 0034: Agent Admin Audit Timeline

## Status

Accepted.

## Context

Agent administration supports provisioning, activation, deactivation, archive, and restore. These actions already emit events, but future admin surfaces need a durable per-agent history that is easier to query than the raw event log.

## Decision

Add `AgentAuditRuntime` as a focused audit timeline for administrative agent actions.

Records are appended to:

```text
DATA_DIR/agents/{agent_id}/AUDIT.jsonl
```

Each record stores:

- stable id
- timestamp
- agent id
- action
- actor metadata when known
- status
- reason/details
- correlation and causation ids when available

The timeline is integrated with:

- `AgentProvisioningRuntime`
- `AgentAdminRuntime`
- slash commands
- read-only API endpoints

## Consequences

- UI and admin clients can load agent history without reconstructing it from `events.jsonl`.
- EventBus remains the domain event stream; audit records do not replace events.
- Audit files are local-first and append-only for this foundation stage.
- A future retention policy or global audit runtime can be added without changing agent runtime behavior.

## Non-Goals

- No dashboard.
- No analytics engine.
- No global audit system for all resource types.
- No fine-grained admin permission model yet.
- No UI.
