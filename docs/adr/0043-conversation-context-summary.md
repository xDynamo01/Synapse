# ADR 0043: Conversation Context Summary

## Status

Accepted.

## Context

Agent conversations are now persisted as first-class runtime records. Long-running conversations can grow indefinitely, and future agent collaboration needs a compact local context surface without introducing RAG, embeddings, global search, or UI.

## Decision

Add optional persistent summaries to `ConversationRuntime`.

Each conversation may store:

```text
DATA_DIR/conversations/{conversation_id}/SUMMARY.md
DATA_DIR/conversations/{conversation_id}/SUMMARY.yaml
```

`SUMMARY.md` is the human-readable projection. `SUMMARY.yaml` stores the structured `ConversationSummary` record with schema version, message count, last message id, timestamp, and metadata.

The runtime exposes:

- `get_conversation_summary()`
- `update_conversation_summary()`
- `generate_mock_summary()`
- `build_conversation_context()`

`generate_mock_summary()` is deterministic and offline. It uses participants, message count, and recent messages. It does not call a real model.

`build_conversation_context()` returns the existing summary, recent messages, participants, and conversation status. It does not replace the global `ContextLoader`.

## Consequences

- Long conversations can carry compact context without reading every message.
- Humans can inspect `SUMMARY.md`.
- Runtime clients can read structured metadata from `SUMMARY.yaml`.
- No RAG, embeddings, search index, UI, or provider integration is introduced.

## Non-Goals

- No global search.
- No embeddings.
- No LLM summarization.
- No ContextLoader replacement.
- No Mission Control or UI.
