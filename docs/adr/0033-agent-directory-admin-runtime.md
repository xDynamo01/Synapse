# ADR 0033: Agent Directory and Admin Runtime

Status: accepted

## Context

Synapse can create agents manually and from templates, but the backend needs an operational administration layer before any UI can manage agents. The UI must not invent its own logic for listing, activation, deactivation, or archival.

## Decision

Add `AgentAdminRuntime` in `backend/synapse/agents/admin.py`.

Administrative state is persisted in:

```text
DATA_DIR/agents/{agent_id}/ADMIN.yaml
```

This is intentionally separate from `CONFIG.yaml`, `SOUL.md`, `SKILLS.md`, and `MEMORY.md` so administrative state can change without modifying identity, skills, or memory. Agents without `ADMIN.yaml` default to active and unarchived for backward compatibility.

Archive is reversible and never deletes agent files.

## Consequences

- Agent directory entries include status, lifecycle, presence, schema timestamps, capability count, risk summary, seed/provisioned signal, and archive state.
- Deactivation and archival set lifecycle/presence offline when those runtimes exist.
- ChatRuntime and AgentWorker block archived or inactive agents.
- Scheduler paths that use AgentWorker inherit the worker block.
- Existing seed agents continue to load.

## Non-Goals

- No UI.
- No visual editor.
- No marketplace.
- No Resource Registry.
- No physical deletion of agents.
