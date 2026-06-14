# ADR 0008: Human Approval Gate for Sensitive Tools

## Status

Accepted.

## Context

Permission checks decide whether an actor may use a capability. They do not always decide whether an action should happen immediately. High-risk and critical actions need a human approval boundary even when an agent has the technical permission to request them.

Examples:

- writing files
- future deletion
- future email sending
- future camera access
- future home automation actions

## Decision

Each tool has a `risk_level`: `low`, `medium`, `high`, or `critical`.

`ToolRouter` now enforces this order:

```text
AgentRuntime
  -> ToolRouter
  -> PermissionManager
  -> ApprovalManager when policy requires it
  -> ToolRegistry.execute
  -> EventBus
```

Default policy requires approval for `high` and `critical` tools. Explicit permission does not bypass approval by default.

Approval requests are persisted in:

```text
DATA_DIR/approvals/<approval_id>.yaml
```

Approval commands exist in `CommandRuntime`:

- `/approvals`
- `/approve <approval_id>`
- `/reject <approval_id>`

When a `device_id` is present, approval requires a trusted, non-revoked device with the configured approval permission, currently `approve_actions`.

## Consequences

- Agents can request sensitive actions without executing them immediately.
- Approval state survives runtime restart.
- Future mobile and remote access workflows have a runtime contract to build on.
- UI is not required for approval logic.
- Multi-step agent planning still remains separate future work.

