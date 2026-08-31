# Agents Specification

Primary and Persistent Agents have no egress bypass and may request scoped
approval. Ephemeral Agents inherit project/RFC/mission boundary and provider
constraints, cannot widen them and have `can_approve_egress=false`. Model and
Tool outputs preserve source classification and provenance.

Primary coordinates project/RFC clarification and status; Persistent Agents
may author/review within scope; Ephemeral Agents may analyze and produce
evidence but never approve permanently. Context carries bounded project/RFC
summaries with provenance rather than complete documents.

Skills Phase 1 keeps SOUL (identity), ROLE (operational function), SKILL
(shared workflow) and TOOL (executable authority) separate. Persistent agents
reference versioned packages by assignment; legacy `SKILLS.md` remains an
agent-specific compatibility file and package content is never copied.

## Canonical kinds and authorities

Agents declare `primary`, `persistent` or `ephemeral`; there is no fourth implicit
category. AgentProvisioning owns persistent identities and human-editable files.
PrimaryAgentRuntime binds one durable identity/conversation per workspace.
EphemeralAgentRuntime owns mission leases without agent folders or long-term
memory. The legacy Agent Creator adapter and contracts were removed.

## Definition

An agent is a durable runtime identity with configuration, human-readable
behavioral material, policy inputs, operational state, and optional provider
preferences. An agent is not a model instance and a role name does not grant
authority.

Status: identity, registry, provisioning, delegation, admin, audit,
presence, and lifecycle foundations are **Implemented**. Full agent execution,
conversation integration, and swarm coordination remain **In development** or
**Planned** as noted below.

## Canonical Identity

The canonical identifier is the folder name:

```text
DATA_DIR/agents/{agent_id}/
```

Rules:

- lowercase letters, numbers, hyphen, and underscore only;
- no path traversal or absolute path;
- a missing `CONFIG.yaml:id` may be inferred from the folder;
- an explicit config ID must match the folder;
- IDs are immutable after provisioning; rename is a migration, not an update.

## Agent Files

```text
CONFIG.yaml       structured configuration
SOUL.md           role narrative, system prompt, operating principles
SKILLS.md         human-readable skill description
MEMORY.md         agent-scoped durable memory source
INBOX.md          human-readable message projection
ADMIN.yaml        administrative state when initialized
AUDIT.jsonl       post-creation agent audit records
messages/         structured agent messages
```

Provisioning currently generates all five primary Markdown/config files.
Operational identity loading requires `CONFIG.yaml`; `SOUL.md` and `SKILLS.md`
are optional at load time and default to empty content.

## Minimum Operational Identity

| Field | Contract |
| --- | --- |
| `id` | required after folder inference |
| `name` | required after fallback to ID |
| `role` | non-empty free-form string |
| `can_delegate` | boolean, default false |

There is no role enum today. Introducing one requires migration analysis for
seed and user-created agents.

Optional identity/config fields include description, focus areas, preferred
and forbidden tools, model/provider preference, autonomy profile,
communication style, operational rules, capabilities, permissions, tags,
metadata, and schema timestamps.

## Registry And Identity Layers

`AgentRegistry` answers whether a configured agent exists and returns a compact
`AgentConfig`. It preserves compatibility with partial legacy configs.

`AgentIdentityRuntime` composes the operational identity and performs stricter
validation. Consumers that need role, delegation authority, tools, or identity
text use this runtime rather than registry output alone.

Invalid serialization, folder/config mismatch, missing operational fields, and
non-boolean `can_delegate` return structured validation errors.

## Capabilities, Permissions, And Tools

These concepts are distinct:

- **Skill**: descriptive competence; does not grant access.
- **Capability**: declared functional authority mapped to policy/permissions.
- **Permission**: low-level actor authorization.
- **Tool**: executable operation routed through tool policy.
- **Role**: semantic identity; never an authorization shortcut.

Effective authority is the intersection of global policy, agent config,
capability mapping, explicit denies, resource scope, actor/device context, and
approval status. Denies win over allows. Preferred tools are preferences only.

## Provisioning

All agents are created explicitly through `AgentProvisioningRuntime`. Synapse
does not provide prefabricated agents or an inheritance catalog.

Flow:

```text
request
  -> validate agent ID and fields
  -> validate capability references
  -> evaluate provisioning risk
  -> dry-run, direct create, or awaiting approval
  -> render files in staging
  -> validate staged Registry and Identity
  -> atomic rename / overwrite backup
  -> admin initialization
  -> events and audit
```

Dry-run returns deterministic preview data and performs no durable write or
approval creation. Sensitive configuration cannot use a local-owner bypass.
Approval is bound to the normalized configuration hash and apply remains a
separate operation. The complete contract is documented in
[backend/agent-provisioning.md](backend/agent-provisioning.md).

## Administrative State

Agent administration controls active/inactive/archive state separately from
identity. Archiving does not rewrite identity files. Sensitive admin actions
use admin policy and approval requests. Retention must preserve pending and
approved-not-applied requests according to policy.

## Presence And Lifecycle

Presence is a user-facing projection such as idle, working, speaking, waiting
for approval, offline, or error. Lifecycle describes runtime state such as
booting, waking, working, sleeping, shutdown, or failure.

Neither is stored in `CONFIG.yaml`. Identity is durable configuration;
presence/lifecycle are operational records.

## Agent-to-Agent Communication

Structured messages are stored under the recipient agent. Messages carry IDs,
sender/recipient, body, status, timestamps, and correlation metadata. `INBOX.md`
is a projection, not the source of truth.

Workers process durable messages and delegated work through policy and context
loading. A failed worker action must preserve the message/task and record a
structured failure.

## Delegation

Delegation is the implemented coordination primitive. `can_delegate` is an
explicit boolean; it does not imply permission by itself. Delegation policy,
capabilities, requester identity, assignee identity, scheduling, timeout,
retry, recovery, and execution states all remain authoritative.

Domain status: **Implemented and stabilized** at 105 direct tests in the
backend-freeze work.

## Audit And Events

Provisioning before agent creation writes audit under the provisioning domain
to avoid creating a partial agent directory. After creation, audit queries
combine pre-creation and agent-local records into one timestamp-ordered
timeline.

Important events include identity/config validation, provisioning requested,
approval required/approved/rejected/expired, provisioning started/completed/
failed/rolled back, agent created/updated, admin transitions, presence,
lifecycle, messages, delegation, and execution.

## Target Agent Runtime

Planned completion requirements:

- bounded context with explicit provenance;
- deterministic model/provider selection;
- tool-call loop with permission and approval checkpoints;
- cancellation and timeout propagation;
- resumable durable work;
- per-agent budgets and concurrency limits;
- versioned identity/config migration;
- UI authoring and review that never bypasses backend validation;
- swarm participation through delegation and scheduling, not direct mutation.

## Non-Goals

- role-based implicit superuser behavior;
- agents editing permissions or approval records directly;
- silent auto-provisioning from model output;
- runtime dependence on human-readable Markdown as the only source of truth;
- unrestricted agent spawning or recursive delegation.
