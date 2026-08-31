# Context Fusion Runtime

Status: **Implemented / Frozen**.

The runtime receives consumer-owned Conversation, Mission, Perception,
Multimodal, Memory and operational-status read ports. Thin adapters are built by
the composition root; the domain imports no concrete functional runtime or
store. See `docs/architecture/context-fusion-ports.md`.

`ContextFusionRuntime.build_context` accepts conversation, agent, current input,
mission, session, files, perception, options, and permission context. Mission and
perception enter through contracts rather than Chat importing their internals.

The result retains the legacy snapshot and adds provenance items, rendered
context, estimated token total, budget, omitted items, warnings, and trace ID.
Priority is explicit: mandatory current input, mission/task, summary/recent
conversation, relevant memory, perception, then files. Stable ordering and exact
normalized deduplication apply before budget.

Default budget is 4096 estimated tokens with `min(1024, 25%)` reserved for the
response. Mandatory overflow raises `context_budget_exceeded`; optional overflow
is returned in `omitted_items`. Low-confidence perception is excluded.

Memory authorization occurs before fusion. Perception is scoped to a requested
conversation or multimodal session; unscoped builds cannot import global signals.
Health/readiness are opt-in. Events expose source IDs/counts without content.

`ContextLoader` remains a compatibility adapter for identity/effective-policy
DTOs. Chat and workers invoke Context Fusion before this adapter.
