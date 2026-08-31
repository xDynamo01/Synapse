# ADR 0035: Admin Permission Policy

## Status

Accepted.

## Context

Agent administration supports activation, deactivation, archive, restore, validation, provisioning, and audit timeline records. Before UI or mobile clients call these operations, the backend needs an explicit local policy that decides whether an administrative action is allowed, blocked, or approval-required.

## Decision

Add `AdminPolicyRuntime` backed by:

```text
DATA_DIR/config/admin_policy.yaml
```

The policy supports:

- user admin action enablement
- approval-required flags for archive, deactivate, and restore
- protected agents
- blocked admin actions
- action-specific required permissions

`AgentAdminRuntime` checks the policy before activate, deactivate, archive, restore, and administrative validation. Decisions are appended to the per-agent audit timeline with statuses such as `allowed`, `blocked`, and `requires_approval`.

In this foundation stage, approval-required admin actions fail closed with a clear error. A future dedicated admin approval/apply flow can reuse the existing Approval System without making this policy runtime responsible for applying actions.

## Consequences

- Admin operations no longer rely only on caller discipline.
- Future UI/mobile clients can call backend commands/API without duplicating admin authorization logic.
- Protected agents and blocked actions are enforced before state changes.
- Audit timeline records both successful state changes and denied decisions.

## Non-Goals

- No global RBAC system.
- No login/user database.
- No physical agent deletion.
- No UI.
- No mobile flow.
- No Resource Registry.
