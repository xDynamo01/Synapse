# RFC Gate

`RFCGate` classifies a requested change by behavior and risk, not file count.
It verifies applicable RFC identity, approval state, revision/checksum,
domains/contracts, conflicts, acceptance criteria, eval references and plan
freshness. Results are explicit: allowed, allowed without RFC, or a structured
block for missing, unapproved, stale, out-of-scope, conflicting or incomplete
specification.

Mission and Skills consume `RFCGatePort`/governance contracts. Agents,
providers, tools and Commands cannot grant a bypass. Administrative exceptions
are not exposed by the Phase 1 API or Commands. Trivial and local
non-behavioral changes return `allowed_without_rfc`.

Every decision emits only IDs, revision/checksum, disposition and correlation
metadata. RFC bodies and private eval data are excluded from events.
