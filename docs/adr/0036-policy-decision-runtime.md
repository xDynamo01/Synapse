# ADR 0036: Policy Decision Runtime

## Status

Accepted.

## Context

Synapse now has several focused policy and permission components:

- `PermissionManager`
- `EffectivePolicyRuntime`
- `CapabilityRuntime`
- `AgentProvisioningPolicyRuntime`
- `AdminPolicyRuntime`
- `ApprovalManager`

Each remains useful, but future clients should not need to know which runtime answers each kind of authorization question.

## Decision

Add `DecisionRuntime` as a convergence layer for policy decisions.

It returns a normalized `DecisionResult` for:

- capability checks
- tool execution checks
- agent provisioning checks
- administrative agent actions

`DecisionRuntime` does not replace existing runtimes. It delegates to them and standardizes the answer shape with:

- allowed
- blocked
- requires approval
- risk level
- reasons
- blocked reasons
- source policies
- evaluated components
- optional approval source

It emits:

- `decision.evaluated`
- `decision.blocked`
- `decision.requires_approval`

## Consequences

- UI, mobile, and future integrations can ask one backend surface for decisions.
- Existing permission, capability, provisioning, admin, and approval policies continue to own their domains.
- Approval is not executed by this runtime; it is only reported as required.
- Traceability improves because decision events carry correlation metadata when supplied.

## Non-Goals

- No new PermissionManager.
- No RBAC system.
- No login/user database.
- No UI.
- No provider integration.
- No Resource Registry.
- No policy replacement or mass refactor.
