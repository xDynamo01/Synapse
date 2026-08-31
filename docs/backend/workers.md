# Workers Runtime

`WorkerRegistry` persists availability, heartbeat, workload, current task and
attempt, capabilities, tools and permissions. `WorkerScheduler` deterministically
filters incompatible workers and explains every rejection.

`WorkerRuntime` validates assignment and mission state, transitions attempts,
loads Context Fusion data, delegates execution through
`WorkerExecutionAdapter`, verifies results and always releases workload. The
production adapter calls `ContextLoader` and `AgentRuntime`; models and tools
therefore remain behind ModelRouter and ToolRouter contracts.
