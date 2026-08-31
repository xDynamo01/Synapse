# ADR 0030: Agent Provisioning Approval Flow

Status: accepted

## Context

The backend can provision custom agents, but sensitive capabilities must not be granted silently before the future UI exists. Agent creation and update need the same permission-first and approval-first discipline used by tools and outbound communication.

## Decision

Extend `AgentProvisioningRuntime` with persisted provisioning requests under:

```text
DATA_DIR/agent_provisioning/
```

Sensitive creates or updates produce an `AgentProvisioningRequest` with status `awaiting_approval` and create an `ApprovalRequest`. Approval and application are separate:

1. Create/update request is validated.
2. Sensitive request is persisted.
3. Approval request is created.
4. Human approval changes provisioning request to `approved`.
5. Explicit apply writes the final agent files or config changes.

Sensitive criteria include high/critical capabilities, non-manual autonomy, selected sensitive capabilities such as `filesystem.write`, `communication.request_send`, `scheduler.run`, and `approval.review`, and sensitive preferred tools without explicit forbidden tools.

## Consequences

- Simple agents can still be created directly.
- Sensitive agents cannot appear in `DATA_DIR/agents/` until approved and explicitly applied.
- Re-applying an already applied request is blocked.
- Rejected requests cannot be applied.
- The future UI can use backend endpoints without implementing its own approval logic.

## Non-Goals

- No UI.
- No rich templates.
- No LLM-generated agent personalities.
- No marketplace.
- No external providers.
