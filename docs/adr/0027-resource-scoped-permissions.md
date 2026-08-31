# ADR 0027: Resource-Scoped Permissions

Status: accepted

## Context

Synapse already checks permissions through `PermissionManager` and effective agent policy, but permission events did not carry a standard description of the resource being accessed. Future Library, Brain, Gallery, Voice, Mobile, Perception, and external integrations need a stable way to express "who is doing which action against which resource" without introducing a full resource registry yet.

## Decision

Add a minimal `backend/synapse/resources/` module with:

- `ResourceRef`: typed reference to a resource such as `file`, `approval`, `notification`, `communication_draft`, or `chat_session`.
- `ResourceAction`: constrained action name such as `read`, `update`, `approve`, `reject`, or `send_request`.
- `ResourceScope`: actor, action, resource, optional device, and optional correlation id.
- `check_resource_access()`: a small adapter that builds `ResourceScope`, attaches it to `PermissionContext`, and delegates authorization to the existing `PermissionManager`.

`ResourceScope` is intentionally optional. Existing permission checks continue to work when no resource is supplied.

## Consequences

- Permission decisions can now include `resource_type`, `resource_id` or `path`, `action`, `agent_id`, `device_id`, and `correlation_id`.
- Tool filesystem access is scoped at the `ToolRegistry` boundary before execution.
- Approval approve/reject, draft approve/reject, outbound authorization approve/reject, and notification read/delete can emit resource-aware permission decisions.
- No new parallel permission system is introduced.
- No resource registry, indexing, RAG, Library, Gallery, or global search is created in this phase.

## Follow-Ups

- Add richer resource policy rules to `EffectivePolicyRuntime`.
- Expand scoped checks to tasks, chat sessions, agent messages, and memory operations.
- Add resource migration/version coverage when durable resource records grow.
