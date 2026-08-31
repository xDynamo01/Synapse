# ADR 0084: Tool Permission And Approval Bridge

## Status

Accepted.

## Context

`ToolRuntime` provides explicit, model-agnostic tool execution, while Synapse already has permission, capability, resource scope, decision, and approval runtimes. Executing runtime tools without joining those controls would create a second, weaker authorization path.

## Decision

Add `ToolPermissionBridge` as the mandatory policy boundary used by container-managed `ToolRuntime` executions.

Each tool may declare a required capability, required permission, resource-scope requirement, approval requirement, and risk level. Each request identifies its caller type, optional agent and resource, correlation metadata, and dry-run mode.

Before invoking a handler, the bridge:

1. builds the permission and optional resource context;
2. delegates the unified decision to `DecisionRuntime`;
3. blocks denied requests;
4. creates a durable `ApprovalRequest` when approval is required;
5. returns without executing the handler while approval is pending.

Approval does not resume or execute a runtime tool in this stage. A future explicit resume contract must revalidate permission and policy before execution.

`danger.mock` is a critical-risk test tool. It has no dangerous side effect and exists only to validate the approval boundary.

## Interfaces

Commands:

- `/run-tool <tool_id> [--agent <agent_id>] [--dry-run] [--resource <type:id>]`
- `/tool-decision <tool_id> [options]`

API:

- `POST /tools/run`
- `POST /tools/decision`

Execution logs include the decision, approval id, caller type, and agent id.

## Consequences

Runtime tool execution is fail-closed and uses existing Synapse controls rather than a parallel permission system. Dry-run can inspect decisions without creating approvals or invoking tools.

No model-driven tool selection, automatic execution, approval resume, MCP, planner, workflow engine, or new UI is introduced.
