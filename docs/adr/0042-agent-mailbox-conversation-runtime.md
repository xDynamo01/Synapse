# ADR 0042: Agent Mailbox & Conversation Runtime

## Status

Accepted.

## Context

Agent-to-agent communication existed through structured inbox messages and human-readable `INBOX.md` files. That was enough for early worker processing, but it did not model conversations, delivery state, or shared trace context as first-class runtime entities.

Before Mission Control, UI workflows, or richer multi-agent collaboration, Synapse needs a local-first conversation foundation.

## Decision

Add `ConversationRuntime` under `backend/synapse/conversations/`.

Conversation records are persisted under:

```text
DATA_DIR/conversations/{conversation_id}/CONVERSATION.yaml
DATA_DIR/conversations/{conversation_id}/messages.jsonl
```

Conversation lifecycle states:

- `active`
- `paused`
- `closed`
- `archived`

Message delivery states:

- `pending`
- `delivered`
- `acknowledged`
- `failed`

The existing `AgentCommunication` runtime remains compatible and now mirrors sent messages into `ConversationRuntime`. Existing inbox records under `agents/{agent}/messages/` and `INBOX.md` are preserved.

Admin runtime is consulted before delivery, so archived or inactive agents cannot receive new messages.

## Consequences

- Agent communication becomes queryable as conversations.
- Workers can keep using the existing inbox path while conversation message status tracks delivery progress.
- Correlation and causation IDs are preserved when available.
- No visual workflow, planner, Mission Control, or external provider is introduced.

## Non-Goals

- No UI.
- No Mission Control.
- No multi-agent planner.
- No RAG or Resource Registry.
- No external messaging provider.
