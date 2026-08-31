# ADR 0088: MCP Tool Bridge

## Status

Accepted.

## Context

MCP Runtime catalogs external server manifests and tool references, while Tool Runtime provides Synapse's unified internal tool catalog and policy boundary. MCP references need a safe representation in the internal catalog before transports or external execution exist.

## Decision

Add `MCPToolBridgeRuntime` under `backend/synapse/mcp_bridge/`.

Explicit synchronization projects each MCP tool reference into a deterministic Tool Runtime definition using `mcp.<server_id>.<tool_name>`. Projected definitions use category `mcp`, high risk, mandatory approval metadata, and remain disabled while MCP execution is unavailable.

The bridge is derived from MCP Registry state and has no separate persistence. It records server installation, enablement, and connection snapshots in metadata. Tool Discovery sees projected definitions and reports them unavailable while retaining approval/risk information.

Executing a projected definition fails before permission evaluation or handler invocation with `MCP execution is not implemented in this stage`. No operational ApprovalRequest is created for an unavailable MCP tool.

## Interfaces

Commands: `/mcp-bridge`, `/mcp-bridge-sync`, and `/mcp-bridge-tool <bridge_tool_id>`.

API: `GET /mcp/bridge`, `POST /mcp/bridge/sync`, and `GET /mcp/bridge/tools/{bridge_tool_id}`.

## Consequences

Internal and MCP tools share one discovery surface without treating external references as executable or trusted. A future execution bridge must add transport handling and revalidate all Synapse permission, capability, resource, decision, approval, and audit controls.

No MCP connection, transport, external execution, Agent Runtime integration, LLM tool calling, planner, workflow, or new UI is introduced.
