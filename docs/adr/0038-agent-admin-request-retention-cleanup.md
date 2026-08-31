# ADR 0038: Agent Admin Request Retention Cleanup

## Status

Accepted.

## Context

Admin action requests are durable records stored under `DATA_DIR/agent_admin_requests/`. They are useful for review and audit, but a homelab system running continuously needs controlled cleanup to avoid unbounded operational growth.

## Decision

Add a local retention policy at:

```text
DATA_DIR/config/agent_admin_retention_policy.yaml
```

`AgentAdminRuntime` owns cleanup for admin action requests only. Cleanup is dry-run by default, preserves pending requests, preserves approved-not-applied requests by default, and deletes only eligible final-state records.

Supported controls:

- status-specific retention windows
- preserve awaiting approval
- preserve approved not applied
- max request cap
- dry-run default

Cleanup emits admin request cleanup events and returns a structured result.

## Consequences

- `agent_admin_requests/` can be maintained safely in long-running homelab deployments.
- Pending and approved-not-applied requests remain protected.
- Audit logs and agent records are not deleted.
- This does not create a global retention system.

## Non-Goals

- No UI.
- No global cleanup runtime.
- No deletion of agents.
- No deletion of audit logs.
- No RBAC changes.
