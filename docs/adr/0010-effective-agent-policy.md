# ADR 0010: Effective Agent Policy

Date: 2026-06-14

## Status

Accepted

## Context

Synapse agents now have identity, runtime tool calling, permissions, approval gates, device records, and agent configuration. Without a single policy resolver, authorization decisions would spread across `AgentRuntime`, `ToolRouter`, `PermissionManager`, `ApprovalManager`, and future device/session layers.

That would make the system harder to audit and would create inconsistent behavior between normal chat execution, approval resume, commands, APIs, and future schedulers.

## Decision

Create `EffectivePolicyRuntime` and `AgentEffectivePolicy`.

The effective policy combines:

- global permissions and denies from `config/permissions.yaml`
- agent `CONFIG.yaml`
- structured `AgentIdentity`
- approval policy from `config/approval_policy.yaml`
- optional device context

Precedence:

1. explicit blocks always win
2. approval policy may require approval even if a tool is allowed
3. agent `CONFIG.yaml` can restrict or request permissions only inside the global ceiling
4. global permissions define the maximum permission ceiling
5. `AgentIdentity` defines preferences and behavior, not authorization by itself
6. device constraints can restrict the result further

`AgentRuntime`, `ToolRouter`, `ApprovalResumeRuntime`, `ContextLoader`, and `CommandRuntime` must use the resolved policy rather than rebuilding local permission logic.

## Consequences

Positive:

- agent authorization becomes inspectable through `/policy <agent_id>`
- approval resume revalidates the same policy as normal execution
- preferred tools no longer imply authorization
- device context can restrict tools without changing agent identity
- future UI/mobile/API surfaces can display one policy object

Tradeoffs:

- policy is currently coarse-grained by permission string and tool name
- resource-scoped rules for paths, projects, models, and devices still need a later design
- persisted policy inputs need schema versions and migration tooling
