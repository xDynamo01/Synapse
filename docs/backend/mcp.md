# MCP Tool Provider

MCP IDs are `mcp:<server_id>:<tool_name>`. Discovery reads configured manifests without
executing code. A tool is enabled only when its server is enabled, installed, connected
and has an explicit transport executor. Every call passes through ToolRuntime schema,
permissions, risk and approval. Missing adapters remain honestly unavailable.

`MCPRegistry` is provider-local and never a second public catalog.
`MCPToolExecutorAdapter` is the only canonical handler allowed to invoke
`MCPRuntime.execute_tool`.
