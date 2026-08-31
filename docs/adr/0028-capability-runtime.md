# ADR 0028: Capability Runtime

Status: accepted

## Context

Synapse had agent skills, tool permissions, effective policies, and autonomy profiles, but no explicit runtime concept for reusable functional capabilities. That made it harder to reason about future configurable agents without mixing conceptual skill, authorization, and autonomy.

## Decision

Add a minimal `backend/synapse/capabilities/` module:

- `Capability` describes a functional capability with category, risk, required permissions, allowed resource types, and optional approval level.
- `CapabilityRegistry` registers built-in capabilities in an agent-agnostic way.
- `CapabilityRuntime` lists capabilities, resolves agent capabilities, checks a capability, and explains a capability decision.

Agent `CONFIG.yaml` may optionally declare:

```yaml
capabilities:
  allow:
    - filesystem.read
  deny:
    - filesystem.write
```

The capability layer complements `EffectivePolicyRuntime` and `PermissionManager`; it does not replace them.

## Consequences

- `AgentEffectivePolicy` now includes `allowed_capabilities`, `denied_capabilities`, and `capability_decisions`.
- Agents without capability declarations continue to work through permission-based fallback.
- Tool calling can check mapped capabilities before executing selected tools.
- Capability checks emit `capability.checked` events with agent, capability, decision, reason, and optional resource scope.
- No UI, provider integration, Resource Registry, RAG, marketplace, or external service is introduced.

## Follow-Ups

- Expand resource-scoped capability decisions as Resource Registry matures.
- Add capability editing/inspection in future UI.
- Add migration/versioning for agent capability config if the schema evolves.
