# Implementation References

This document records patterns studied before implementing the Synapse foundation. The goal is to learn from working systems without copying their architecture or code.

## Open WebUI

Observed patterns:

- Self-hosted AI platform that works with Ollama and OpenAI-compatible APIs.
- UI, model providers, RAG, permissions, and extensibility are treated as platform concerns.
- Tools can be built in, workspace-local, MCP-based, MCPO-proxied, or OpenAPI-backed.

Synapse decisions:

- Keep model/provider routing behind Core.
- Keep tool execution behind `PermissionManager`.
- Treat OpenAPI/MCP as future tool gateway protocols, not as the internal runtime contract.

Sources:

- https://github.com/open-webui/open-webui
- https://docs.openwebui.com/features/extensibility/plugin/tools/
- https://docs.openwebui.com/features/extensibility/mcp/

## AnythingLLM

Observed patterns:

- Local-first desktop/server product with workspaces, documents, agents, memories, model routing, and scheduled jobs.
- Agent runs produce reviewable traces: thoughts, tool calls, produced files, and final output.
- RAG separates attached chat documents from embedded workspace documents.

Synapse decisions:

- Separate persistent memory from chat history.
- Make complex work a `Task` with status and event history.
- Keep future project/workspace document boundaries under `DATA_DIR/projects` and `DATA_DIR/library`.

Sources:

- https://github.com/Mintplex-Labs/anything-llm
- https://docs.anythingllm.com/chatting-with-documents/introduction
- https://docs.anythingllm.com/scheduled-jobs/overview
- https://docs.anythingllm.com/agent/usage/overview

## Open WebUI Pipelines

Observed patterns:

- UI-agnostic OpenAI-compatible plugin framework.
- Useful when heavy or custom logic should run outside the main UI process.
- Explicit warning that arbitrary pipeline code is a security boundary.

Synapse decisions:

- Runtime capabilities must not live in the UI.
- Future workflows should be isolated from the UI and permission-gated.
- Heavy or untrusted tool execution should move behind an external tool server or sandbox.

Source:

- https://github.com/open-webui/pipelines

## Hugging Face smolagents

Observed patterns:

- Agent/tool abstractions stay intentionally small.
- Supports code agents, JSON/text tool-calling agents, local/remote models, MCP, and multiple modalities.
- Sandboxing matters for code-executing agents.

Synapse decisions:

- Start with a small `Tool` protocol and explicit `ToolSpec`.
- Avoid framework lock-in in the internal agent runtime.
- Treat code execution as a future sandboxed subsystem, not a built-in unrestricted tool.

Sources:

- https://huggingface.co/docs/smolagents/en/index
- https://github.com/huggingface/smolagents

## FastAPI LangGraph Agent Template

Observed patterns:

- FastAPI routes are separated from services/core runtime.
- Production foundations include auth, rate limiting, long-term memory, tool calling, observability, migrations, and structured logging.
- Stateful agent work needs checkpoints and human-in-the-loop support.

Synapse decisions:

- Keep `backend/synapse/api` thin and put behavior in runtime services.
- Emit events for every important runtime action from day one.
- Leave clear extension points for auth, observability, queueing, and future graph/checkpoint engines.

Source:

- https://github.com/wassim249/fastapi-langgraph-agent-production-ready-template

## Open WebUI OpenAPI Servers

Observed patterns:

- OpenAPI provides a stable, widely supported interface for tool servers.
- MCP can be bridged to OpenAPI and OpenAPI can be bridged back to MCP.
- External tool servers reduce coupling and clarify security boundaries.

Synapse decisions:

- Internal tools use Python objects now, but specs should map cleanly to future OpenAPI exposure.
- Tool permissions stay internal to Synapse even if transport becomes OpenAPI/MCP.
- Bridges are integration adapters, not the core architecture.

Sources:

- https://github.com/open-webui/openapi-servers
- https://docs.openwebui.com/features/extensibility/plugin/tools/openapi-servers/

