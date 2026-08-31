# ADR 0085: Agent Tool Discovery Bridge

## Status

Accepted.

## Context

Tool Runtime owns the model-agnostic tool catalog and Tool Permission Bridge owns execution decisions. Agent Runtime needs a formal view of that catalog before provider-specific function calling can be considered, but discovery must not execute handlers or create approval requests.

## Decision

Add `ToolDiscoveryRuntime` under `backend/synapse/tool_discovery/`.

Discovery evaluates each registered tool through `ToolPermissionBridge` with `dry_run=True`. This reuses Permission Manager, Capability Runtime, Effective Policy, Resource Scope rules, Decision Runtime, and approval policy without duplicating authorization logic.

Every tool remains visible. Each `AgentToolView` reports whether it is directly available, requires approval, or is unavailable with a reason. A failure evaluating one tool degrades only that item and does not invalidate the full catalog.

`AgentRuntime.available_tools(agent_id)` exposes `AgentToolCatalog`. It does not execute a tool and does not modify the model prompt or chat flow.

## Interfaces

Commands:

- `/agent-tools <agent_id>`
- `/tool-catalog`
- `/tool-explain <tool_id>`

API:

- `GET /agents/{agent_id}/tools`
- `GET /tools/catalog`
- `GET /tools/explain/{tool_id}`

Health and readiness expose `tool_discovery_runtime_available` and `tool_discovery.ready`.

## Consequences

Agents and clients can inspect a policy-aware tool catalog without hardcoded tool knowledge. Approval-required tools are discoverable but are not considered directly available.

No automatic execution, LM Studio/OpenAI function calling, MCP, planner, workflow engine, prompt injection, or new UI is introduced.
