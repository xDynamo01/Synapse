# Agent Provisioning

## Status and Authority

`AgentProvisioningRuntime` is the only creation and update authority for custom
agents. Synapse has no prefabricated agent catalog. A user request and an
authorized programmatic request use the same validation, risk, approval,
persistence, registry, identity, event, and audit path.

The domain is **implemented and under stabilization**. Focused provisioning,
approval, audit, policy, and administration tests are green; the repository-wide
backend baseline remains red.

## Creation Contract

`AgentCreateRequest` accepts:

- `agent_id`, `display_name`, `role`, and `can_delegate`;
- description, focus areas, communication style, and autonomy;
- model/provider preference and system prompt;
- explicit SOUL and SKILLS content;
- allowed and denied capabilities;
- preferred and forbidden tools;
- explicit permissions, operational rules, and tags;
- initial memory and metadata;
- `dry_run` and overwrite intent.

The transport API also accepts `name` as a display-name alias and resolves
allowed tools and model identifiers before constructing the domain request.
Requester identity comes from authenticated actor context, not request JSON.

## Validation

Before persistence, provisioning validates identifier syntax and traversal,
required identity fields, autonomy, boolean delegation state, capability IDs,
duplicate agents, model/tool references at the API boundary, and the complete
staged identity through `AgentRegistry` and `AgentIdentityRuntime`.

Errors use structured codes such as `invalid_agent_id`, `invalid_request`,
`duplicate_agent_id`, `approval_required`, `approval_mismatch`,
`approval_expired`, `identity_validation_failed`, and `provisioning_failed`.

## Preview and Dry-run

`POST /api/agents/preview` and `/preview-agent` normalize the same creation
request used by create. The result includes configuration, destination, files,
permissions, tools, capabilities, risk decision, approval requirement,
conflicts, and validation details.

Dry-run does not create an agent directory, mutate registry state, create an
approval, write per-agent audit, or leave staging data. It emits only the
preview event.

## Risk and Approval

Risk is calculated from actual requested capabilities, tools, explicit
permissions, autonomy, and delegation authority. Blocked content fails before
approval. Sensitive content creates a durable provisioning request and approval
even when requested by the local owner.

The approval is bound to:

- provisioning request and agent ID;
- SHA-256 of normalized configuration;
- requester;
- action;
- requested capabilities, permissions, and tools;
- risk level, reasons, and decision.

Equivalent pending requests from the same requester reuse the same request and
approval. Any configuration change produces a different hash and cannot reuse
the prior approval. Approval and application are separate operations.

## Atomic Creation

Provisioning writes the complete agent tree below an operation-specific staging
root. Registry and identity validation run against staging. Commit uses an
atomic directory rename. Overwrite moves the prior directory to a backup first.
On commit or validation failure, the previous directory is restored and a
rollback event is emitted. Staging is cleaned in every path.

Created files are `CONFIG.yaml`, `SOUL.md`, `SKILLS.md`, `MEMORY.md`, and
`INBOX.md`. Explicit SOUL/SKILLS content is preserved; otherwise provisioning
renders deterministic content from the request.

## Lifecycle

| Operation | Meaning |
| --- | --- |
| create | persist a new validated custom identity |
| read/list | resolve through registry/admin directory |
| validate | run file, registry, identity, and capability checks |
| update | change allowed configuration through provisioning policy |
| activate | permit runtime work after validation |
| deactivate | stop runtime work while preserving data |
| archive | reversible inactive administrative state |
| restore | return an archived agent to active state |
| delete | permanently remove an inactive agent after strong confirmation |

Delete requires the literal confirmation `DELETE <agent_id>`. Associated
conversation, task, or delegation records block deletion unless force is
explicit. The agent directory is moved to deletion staging before removal and
restored if removal fails. Archive never deletes identity files.

## API

```text
POST   /api/agents
POST   /api/agents/preview
PATCH  /api/agents/{agent_id}
POST   /api/agents/{agent_id}/validate
POST   /api/agents/{agent_id}/activate
POST   /api/agents/{agent_id}/deactivate
POST   /api/agents/{agent_id}/archive
POST   /api/agents/{agent_id}/restore
DELETE /api/agents/{agent_id}
GET    /api/agent-provisioning/status
GET    /api/agent-provisioning/policy
GET    /api/agent-provisioning/requests
GET    /api/agent-provisioning/requests/{request_id}
POST   /api/agent-provisioning/requests/{request_id}/approve
POST   /api/agent-provisioning/requests/{request_id}/reject
POST   /api/agent-provisioning/requests/{request_id}/apply
```

## Commands

Creation and administration commands include `/create-agent`,
`/preview-agent`, `/validate-agent`, `/activate-agent`, `/deactivate-agent`,
`/archive-agent`, `/restore-agent`, and `/delete-agent`. Provisioning request
inspection, approval, rejection, and application use the corresponding
`/agent-provisioning-*` commands.

## Events and Audit

Core events are `agent.provisioning.validated`, `.previewed`, `.requested`,
`.awaiting_approval`, `.approved`, `.rejected`, `.started`, `.completed`,
`.failed`, `.rolled_back`, plus `agent.created`, `agent.updated`,
`agent.activated`, `agent.deactivated`, `agent.archived`, `agent.restored`, and
`agent.deleted`.

Audit records identify action, status, actor, reason, correlation, approval,
and relevant result metadata. Permanent deletion writes its surviving audit
record outside the removed agent directory.
