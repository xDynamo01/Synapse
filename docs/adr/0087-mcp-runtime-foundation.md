# ADR 0087: MCP Runtime Foundation

## Status

Accepted.

## Context

Future integrations with IDEs, creative tools, browsers, source control, containers, and databases may use Model Context Protocol. Connecting external servers before defining a local boundary would couple transport and execution concerns to agents and internal tools.

## Decision

Add an isolated `MCPRuntime` and `MCPRegistry` under `backend/synapse/mcp/`.

Server manifests persist in `DATA_DIR/mcp/servers.yaml`; MCP tool references persist in `DATA_DIR/mcp/tool_registry.yaml`. Connection states are memory-only and always disconnected in this stage.

Seed placeholder manifests exist for local filesystem, GitHub, browser, Unreal Engine, Blender, and Docker. Every seed is disabled, not installed, and uses the `unconfigured` transport marker.

MCP Runtime does not import an MCP SDK, open sockets, start subprocesses, resolve transports, discover remote tools, or execute references. It has no integration with Tool Runtime, Tool Intent Runtime, Agent Runtime, Chat Runtime, or model providers.

## Interfaces

Commands: `/mcp-servers`, `/mcp-server <server_id>`, `/mcp-tools`, and `/mcp-summary`.

API: `GET /mcp/servers`, `GET /mcp/servers/{server_id}`, `GET /mcp/tools`, and `GET /mcp/summary`.

## Consequences

Synapse has a durable protocol catalog ready for later transport and discovery layers without weakening existing tool policy boundaries. No functional MCP connection, external dependency, automatic tool call, planner, workflow, or new UI exists.
