# ADR 0029: Agent Provisioning Runtime

Status: accepted

## Context

Agents were available through seed/bootstrap files and manual edits under `DATA_DIR/agents/`. Future UI-driven agent creation needs a backend-owned path that is runtime-first, validated, schema-aware, and agent-agnostic.

## Decision

Add `AgentProvisioningRuntime` in `backend/synapse/agents/provisioning.py`.

The runtime provides:

- `validate_create_request()`
- `create_agent()`
- `update_agent()`
- `validate_agent_files()`
- `get_agent_provisioning_status()`

New provisioned agents create:

- `CONFIG.yaml`
- `SOUL.md`
- `SKILLS.md`
- `MEMORY.md`
- `INBOX.md`

`CONFIG.yaml` includes `schema_version`, `record_type: agent_config`, `created_at`, and `updated_at`.

Capabilities are validated against `CapabilityRegistry`. Required permissions are derived only from explicitly allowed capabilities. New agents default to manual autonomy and do not receive dangerous tools or capabilities implicitly.

## Consequences

- `AgentRegistry` and `AgentIdentityRuntime` can load provisioned agents without special handling.
- `EffectivePolicyRuntime` and `CapabilityRuntime` work with provisioned agents using existing permission ceilings.
- Backend commands and API can create and validate agents before any UI exists.
- Existing seed/manual agents continue to load unchanged.

## Non-Goals

- No UI or visual editor.
- No LLM-generated personalities.
- No marketplace or plugin system.
- No full migration of older agent configs in this phase.
