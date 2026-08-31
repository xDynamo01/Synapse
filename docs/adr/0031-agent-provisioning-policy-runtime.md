# ADR 0031: Agent Provisioning Policy Runtime

Status: accepted

## Context

Agent provisioning already supports approval-gated sensitive creates and updates, but the risk logic was embedded in `AgentProvisioningRuntime`. Before UI, templates, or richer agents exist, provisioning risk rules need to be local-first, configurable, auditable, and testable.

## Decision

Add `AgentProvisioningPolicyRuntime` in `backend/synapse/agents/provisioning_policy.py` backed by:

```text
DATA_DIR/config/agent_provisioning_policy.yaml
```

The policy controls:

- default autonomy level
- maximum direct-create autonomy level
- whether high/critical capabilities require approval
- sensitive capabilities and tools
- blocked capabilities and tools
- whether sensitive preferred tools require explicit forbidden tools
- direct create/update allowance

Risk evaluation returns an `AgentProvisioningRiskDecision` with allowed, requires approval, risk level, reasons, blocked reasons, and detected sensitive capabilities/tools.

## Consequences

- Sensitive creates/updates still produce provisioning requests and approval requests.
- Blocked capabilities/tools fail before approval request creation.
- Pending provisioning requests persist the full risk decision.
- Future UI can display the policy and the exact decision without reimplementing risk logic.

## Non-Goals

- No UI.
- No templates.
- No LLM-generated agents.
- No Resource Registry.
- No external providers.
