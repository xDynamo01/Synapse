# ADR 0002: Memory-First and Chat History Separation

## Status

Accepted.

## Context

Conversation history is useful context, but it is not durable memory. Treating chat logs as memory would make memory noisy, hard to audit, and hard to correct.

## Decision

Durable memory lives in markdown files under `DATA_DIR`:

- `memory/SYSTEM.md`
- `memory/USER.md`
- `memory/MEMORY.md`
- `agents/<agent_id>/MEMORY.md`

`ContextLoader` may include recent session history, but it returns that history in a separate `history` section and never merges it into memory.

## Consequences

- Brain and Runtime can read the same memory files.
- Users can inspect and edit durable memory.
- Session history can inform an interaction without becoming a fact.

