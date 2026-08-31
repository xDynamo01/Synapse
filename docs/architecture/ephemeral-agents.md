# Ephemeral Agents

`EphemeralAgentRuntime` is the sole temporary-identity authority. Only Mission or
Swarm may call creation; public API and Commands expose queries, cancel,
reconciliation and cleanup dry-run, never arbitrary spawn.

`EphemeralAgentSpec` is mission-specific and contains role/objective, capability
and model requirements, allowed/denied tools, bounded context/memory scope,
autonomy/risk ceilings, execution/retry/lease limits, creator, correlation and
redacted provenance. It is not a reusable template and has no personality files.

Lifecycle:

`planned → provisioning → ready → assigned → running/waiting → completed | failed | cancelled | expired → destroying → destroyed`

Every transition is explicit and revisioned. A lease is bounded by policy and
heartbeat cannot extend beyond maximum lifetime. Restart reconciliation cancels
incomplete provisioning, expires stale leases, inspects linked TaskAttempts and
continues cleanup without repeating completed work.

The runtime stores only operational instances, result/provenance and a temporary
redacted context record through Storage Primitives. Cleanup releases Worker
workload, removes temporary context/scratchpad references and is idempotent and
dry-run capable. It never writes `data/agents`, SOUL, SKILLS, CONFIG or durable
agent memory.

Tool scope is the intersection of the spec and the persistent parent's allowed
tools minus explicit denies. Autonomy cannot exceed the parent. Risk cannot exceed
system policy; critical/high behavior is not silently elevated. Model requirements
are resolved by Model Capability/Router with an explicit reason and no implicit
fallback. The runtime itself executes neither models nor tools.
