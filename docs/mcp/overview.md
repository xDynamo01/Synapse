# MCP In Synapse

## Role

Model Context Protocol is the planned interoperability boundary for external systems such as IDEs, browsers, creative tools, source-control services, container platforms, and databases.

The current MCP Runtime is a local-first catalog only. It records server manifests and tool references so future transports and discovery can be added behind a stable boundary.

## Tool Runtime Versus MCP

Tool Runtime is Synapse's internal execution bus. It owns internal tool definitions, explicit execution, permission decisions, approval gating, health, and execution logs.

MCP Runtime describes external MCP servers and their referenced tools. In v1 it cannot connect or execute anything.

They remain separate because an external protocol reference is not automatically a trusted Synapse tool. A future bridge must preserve Permission Manager, Capability Runtime, Resource Scope, Decision Runtime, Approval Runtime, and audit requirements.

## Planned Coexistence

```text
MCP server manifest
-> transport connection
-> remote tool discovery
-> explicit Tool Runtime bridge
-> Synapse permission and approval decision
-> explicit execution
```

The catalog and structural Tool Runtime projection exist today. `MCPToolBridgeRuntime` can create disabled internal definitions for MCP references so they appear in unified discovery. There is still no transport, connection, remote discovery, external execution, Agent Runtime integration, or automatic execution.

Projected tools use deterministic `mcp.<server_id>.<tool_name>` ids, category `mcp`, high risk, and mandatory approval metadata. They remain disabled and return a controlled not-implemented error if execution is attempted.
