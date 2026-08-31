# ADR 0044: Conversation-aware Agent Worker

## Status

Accepted.

## Context

Agent conversations are durable and can carry summaries plus recent message context. The worker still processed inbox messages mostly as isolated items. For agent collaboration, the worker needs to load conversation context when processing a conversation-backed message.

## Decision

Extend `AgentWorker` to detect conversation-backed inbox messages and load `ConversationRuntime.build_conversation_context()` before invoking `AgentRuntime`.

The loaded conversation context is passed through `ContextLoader.load(..., conversation_context=...)` into `LoadedContext.to_dict()`. This is an incremental extension and does not replace the global context loading order.

Replies sent by the worker stay in the same conversation when a conversation id exists. The reply preserves the original correlation id and sets causation to the original message id.

Events added:

- `worker.conversation_context_loaded`
- `worker.conversation_reply_sent`
- `worker.conversation_processing_failed`

## Consequences

- Agents can respond with awareness of conversation summary and recent messages.
- Existing legacy inbox messages without conversation records still process normally.
- Conversation message delivery status continues to follow worker transitions.
- The worker remains an inbox processor, not a workflow engine.

## Non-Goals

- No Mission Control.
- No visual workflow.
- No multi-agent planner.
- No RAG, embeddings, or global search.
- No automatic LLM summarization.
