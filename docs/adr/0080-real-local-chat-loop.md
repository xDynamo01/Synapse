# ADR 0080: Real Local Chat Loop

## Status

Accepted.

## Context

ADR 0079 introduced an optional LM Studio provider adapter. That validated the provider in isolation, but the core Synapse path still needed a real local LLM loop through Chat Runtime, Agent Runtime, Model Router, and durable conversation/session persistence.

## Decision

Add an optional local chat path to `ChatRuntime` that uses the existing Agent Runtime and Model Router with provider override `lmstudio_local`.

Policy lives in:

```text
DATA_DIR/config/local_chat_policy.yaml
```

Default policy is disabled:

```yaml
local_chat:
  enabled: false
  provider_id: lmstudio_local
  require_explicit_provider: true
  persist_conversations: true
  max_context_messages: 10
  include_conversation_summary: true
  include_multimodal_context: false
```

When enabled, the local chat flow is:

```text
user message
-> ChatRuntime.local_chat()
-> ContextLoader
-> AgentRuntime
-> ModelRouter provider override
-> LMStudioModelAdapter
-> LM Studio local API
-> chat session persistence
-> optional ConversationRuntime persistence
```

## Interfaces

Commands:

- `/local-chat "<message>"`
- `/local-chat-agent <agent_id> "<message>"`
- `/local-chat-conversation <conversation_id> "<message>"`

API:

- `POST /local-chat`
- `POST /agents/{agent_id}/local-chat`
- `POST /conversations/{conversation_id}/local-chat`

## Boundaries

This does not implement streaming, websockets, embeddings, RAG, UI, provider cloud calls, model downloads, LM Studio process management, automatic model selection, or real tool/function calling through LM Studio.

LM Studio remains optional. Bootstrap does not fail when it is disabled or offline.
