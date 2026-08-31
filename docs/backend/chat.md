# Chat

## Canonical Turn Service

`ChatRuntime.submit_turn()` is the canonical internal service for Local Chat,
Agent Chat, compatibility API routes, and chat commands.

Inputs are conversation, sender, content, target agent, model override,
attachments, idempotency key, and options. Agent Chat validates the target,
loads identity/policy/context/memory through existing ports, uses the agent
model or authorized override, executes tools through the existing guarded
runtime, and persists both sides of the turn in Conversation.

Local Chat has no agent identity. It uses the selected local provider and only
the user/system memory permitted by local-chat policy.

## Context

Conversation context enters through `ConversationRuntime.prepare_context()`.
Agent execution continues to use `ContextLoader` for identity, effective policy,
memory, project, and tool context. Memory and Context Fusion remain separate
domains; unavailable optional context does not authorize fallback or expand
scope.

## Models

Agent generation uses `ModelRouter`/`AgentRuntime`; Conversation never imports
LM Studio, Ollama, or OpenAI transports. Direct Local Chat retains the existing
LM Studio provider boundary until the general provider contract is complete.
Provider offline, invalid model, empty response, and transport failures surface
as errors and persist failure state where a message already exists.

Mocks are selected explicitly by tests. Production does not silently replace an
unavailable provider with a mock.

## Streaming and Cancellation

`stream_turn()` exposes NDJSON events: `turn_started`, `generation_started`,
`chunk_received`, and one terminal completed/failed event. Current non-streaming
providers return one real complete-response chunk labelled
`single_complete_chunk`; tokens are never fabricated.

Message cancellation is persisted and evented. Provider process interruption is
only promised when the adapter supports cancellation; otherwise cancellation
prevents further Synapse processing and preserves explicit terminal state.

## Tools

Tool proposals and results remain subject to tool schema, effective policy,
permission, approval, and loop limits in the existing agent/tool runtimes.
Conversation persists normalized tool results on the assistant message instead
of hiding them in response text.

## Compatibility Surfaces

`/chat`, `/local-chat`, agent local-chat, conversation local-chat, and related
commands delegate to `submit_turn`. They are transport compatibility aliases,
not independent implementations. New clients should use
`POST /conversations/{id}/turns` and its streaming variant.
