# ADR 0005: Structured Agent Messages and Human INBOX

## Status

Accepted.

## Context

Agent-to-agent communication must be real and auditable, but users also need a simple readable inbox for inspection.

## Decision

Each agent keeps `INBOX.md` as a human-readable projection. Operational message state is stored in structured YAML records under:

```text
data/agents/<agent_id>/messages/<message_id>.yaml
```

Each message stores id, sender, recipient, subject, body, optional task id, status, created timestamp, and updated timestamp.

## Consequences

- Agents and Mission Control can use structured state.
- Users can inspect messages in plain markdown.
- Status changes can be evented and audited.

