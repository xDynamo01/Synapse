# ADR 0037: Admin Approval Flow

## Status

Accepted.

## Context

`AdminPolicyRuntime` can decide whether administrative agent actions are allowed, blocked, or approval-required. Before this ADR, approval-required actions failed closed. That was safe, but it did not allow a human to approve and later apply sensitive actions such as archive, deactivate, restore, or activate.

## Decision

Add an admin action approval/apply flow inside `AgentAdminRuntime`.

Admin action requests are persisted in:

```text
DATA_DIR/agent_admin_requests/
```

Supported actions:

- `agent.activate`
- `agent.deactivate`
- `agent.archive`
- `agent.restore`

The flow is:

1. Request admin action.
2. Create linked `ApprovalRequest`.
3. Persist `AgentAdminActionRequest` as `awaiting_approval`.
4. Approve or reject the request.
5. Apply explicitly after approval.

Approval does not apply automatically. Duplicate application is blocked. Apply revalidates that the agent still exists and that policy is not blocked before executing the action.

## Consequences

- Sensitive administrative actions can now be reviewed and applied without UI-specific logic.
- Existing admin actions remain available when policy allows direct execution.
- `AgentAuditRuntime` records request, awaiting approval, approved, rejected, applied, and failed transitions.
- EventBus emits matching `agent.admin_action.*` events.

## Non-Goals

- No global RBAC.
- No login system.
- No physical agent deletion.
- No generic workflow engine.
- No UI.
