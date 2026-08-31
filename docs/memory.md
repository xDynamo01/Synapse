# Memory And Context Fusion

Memory is durable, attributable information. Context is the bounded,
policy-filtered input for one execution. History, identity, audit, and memory are
distinct records.

The V3 backend implements scoped memory with atomic storage, working-memory
expiry, revision conflicts, deterministic retrieval, import/export, isolation,
and audited deletion. Context Fusion is the canonical selection port and returns
provenance, stable ordering, budget estimates, omissions, warnings, and trace ID.

See [Memory Runtime](backend/memory.md) and
[Context Fusion Runtime](backend/context-fusion.md).
