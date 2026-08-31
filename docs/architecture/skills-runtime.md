# Skills Runtime

Skill manifests may restrict allowed classifications, external processing,
consumed categories, provider trust requirements, telemetry retention and
output classification. A Skill can only narrow project/RFC policy. Scripts do
not receive external authority by installation and remain behind Tool and
Egress boundaries.

Skills Phase 1 separates four concepts: **SOUL** is identity/personality,
**ROLE** is an operational function, **SKILL** is a reusable versioned workflow,
and **TOOL** is an executable capability governed by `ToolExecutionPort`.

The `synapse.skills` bounded context owns manifests, packages, registry,
metadata discovery, deterministic resolution, progressive loading, assignments,
leases, validation, resources, version state and structured errors. It never
imports Agents, Primary Agent, Ephemeral Agents, Missions, Swarm, API or
Commands. Consumers use neutral ports and bootstrap owns every adapter.

Phase 1 contains no skill generation, mutation, evaluation, promotion,
autoediting, swarm evolution, Workspace Runtime, Repository Runtime or SDK.
