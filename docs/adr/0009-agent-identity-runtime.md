# ADR 0009: Agent Identity Runtime

## Status

Accepted.

## Context

Agents must become operationally distinct entities, not only different names sharing the same prompt/runtime behavior. Identity, memory, skills, permissions, and autonomy need separate files and responsibilities so future UI, automation, and homelab operation can reason about agents safely.

## Decision

Synapse adds `AgentIdentityRuntime`.

It loads identity from:

- `SOUL.md`: identity narrative and operational rules
- `CONFIG.yaml`: operation, default model, permissions, autonomy profile, and structured identity fields
- `SKILLS.md`: capabilities

It does not load `MEMORY.md`; persistent memory remains under the Memory System.

Structured `AgentIdentity` contains:

- id
- name
- role
- description
- can delegate
- focus areas
- preferred tools
- forbidden tools
- default model
- autonomy profile
- communication style
- operational rules

`ContextLoader` includes `agent_identity` as a structured section. `AgentRuntime` loads the identity before model generation and blocks `forbidden_tools` before `ToolRouter`.

Base agents are seeded:

- Artemis
- Researcher
- Atlas
- Hermes
- Vigil

## Consequences

- Agents can behave differently through runtime data, not UI conditions.
- Tool availability can be shaped by identity before permissions and approvals.
- Brain/UI can inspect identity without reading memory.
- Identity files need future schema versioning and editing workflows.

