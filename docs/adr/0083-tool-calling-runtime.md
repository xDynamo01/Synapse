# ADR 0083: Tool Calling Runtime

## Status

Accepted.

## Context

Synapse already had a legacy tool registry and `ToolRouter` used by controlled agent tool calls. That path is tied to permissions, approvals, capabilities, and Agent Runtime execution.

Before integrating provider-specific function calling, MCP, planners, or autonomous agent tool use, Synapse needs a generic runtime-owned tool surface that can register, inspect, execute, and log tools independently of any model provider.

## Decision

Add `ToolRuntime` as a separate runtime layer under `backend/synapse/tools/`.

This runtime owns:

- `ToolDefinition`
- `ToolExecutionRequest`
- `ToolExecutionResult`
- `ToolHealth`
- `RuntimeToolRegistry`
- synchronous `ToolRuntime.execute()`
- execution logging in `DATA_DIR/tools/execution_log.jsonl`

The existing legacy `ToolRegistry` remains in place for `ToolRouter` and controlled Agent Runtime tool calls. The new runtime is exposed as `runtime.tool_runtime` and is not called automatically by agents.

Seed runtime tools are read-only summary tools:

- `health.summary`
- `readiness.summary`
- `conversation.summary`
- `mission.summary`
- `agent.summary`
- `provider.summary`
- `tool.summary`

## API And Commands

Commands:

- `/tools`
- `/tool <tool_id>`
- `/tool-health`
- `/run-tool <tool_id> [key=value ...]`

API:

- `GET /tools`
- `GET /tools/{tool_id}`
- `GET /tools/health`
- `POST /tools/run`

The legacy `POST /tools/{tool_name}` endpoint remains available for the older registry path.

## Consequences

Synapse now has a model-agnostic tool execution surface with durable execution logs and health/readiness visibility.

No OpenAI Function Calling, LM Studio Function Calling, MCP, planner, workflow engine, or autonomous agent tool execution is implemented in this stage.

Future work can map model/provider tool-call payloads into `ToolExecutionRequest` without coupling the runtime to a specific model API.
