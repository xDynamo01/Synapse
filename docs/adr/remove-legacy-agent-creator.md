# ADR: Remove Legacy Agent Creator

Date: 2026-07-14. Decision: accepted.

## Context

The legacy Agent Creator was not an independent runtime. It was an API adapter that
translated two oversized HTTP DTOs into `AgentProvisioningRuntime`, performed
extra model/tool validation, orchestrated Embodiment/Wardrobe and read CONFIG
directly for a parallel profile. Health/Readiness exposed compatibility names.

## Decision

Delete the adapter and its exclusive tests, remove creator Health/Readiness facts,
and map the valid create/preview/update HTTP operations directly to canonical
Provisioning requests. Require explicit agent ID and `persistent` kind. Embodiment
remains an independently owned surface rather than a creation side effect.

Persistent creation is owned only by AgentProvisioning. Temporary creation is
owned only by EphemeralAgentRuntime under Mission/Swarm authority. Primary
assignment references a persistent agent and is not a third creation path.

No alias, facade, feature flag, template, compatibility DTO, storage or placeholder
for Agent Creator remains. The product was not released, so hypothetical client
compatibility does not justify retaining the abandoned path.

## Consequences

OpenAPI intentionally adds Primary and controlled ephemeral diagnostics and reduces
the agent creation schema. Commands add explicit Primary/ephemeral diagnostics.
Agent CONFIG/SOUL/SKILLS remain human-editable and outside Storage Primitives.
Unrelated cycles and DataDir maintenance are unchanged. Backend remains **NOT
READY**.
