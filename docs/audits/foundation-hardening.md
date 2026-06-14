# Synapse V2 Foundation Hardening

Date: 2026-06-14

Scope: implementation pass after `docs/audits/foundation-audit.md`. This pass intentionally avoids UI, Voice, Avatar, Perception, and Communication integrations.

## Implemented

### ContextLoader

`ContextLoader` now composes a structured `LoadedContext` from `DATA_DIR`.

It loads in this order:

1. `memory/SYSTEM.md`
2. `memory/USER.md`
3. `memory/MEMORY.md`
4. `agents/{agent}/SOUL.md`
5. `agents/{agent}/MEMORY.md`
6. `agents/{agent}/SKILLS.md`
7. `projects/{project}/PROJECT.md`, when `project_id` exists
8. `projects/{project}/MEMORY.md`, when `project_id` exists
9. relevant tasks
10. recent session history

The result separates memory, identity, project, tasks, and history. Session history is explicitly returned under `history` and is never merged into memory.

### Structured Agent-to-Agent Messaging

Agent messages still append to `INBOX.md` for human reading. They now also persist to:

```text
data/agents/<agent_id>/messages/<message_id>.yaml
```

Each message has `id`, `from_agent`, `to_agent`, `subject`, `body`, optional `task_id`, `status`, `created_at`, and `updated_at`.

Supported state transitions:

- `pending`
- `read`
- `processed`
- `failed`

Every creation and state transition emits an event.

### Command Runtime

`CommandRuntime` handles slash commands independently of UI and delegates to runtime services/tools:

- `/help`
- `/agents`
- `/tasks`
- `/memory`
- `/call <agent> <message>`
- `/task <title> --agent <agent>`
- `/remember <text>`
- `/search <query>`

`/call` uses the existing `send_agent_message` tool. `/task` uses the existing `create_task` tool. `/search` uses `web_search`; while the tool remains unconfigured, the command returns `not_implemented`.

### Device Registry

`DeviceRegistry` now persists device records under:

```text
data/devices/trusted/
data/devices/untrusted/
data/devices/revoked/
```

Device records include `device_id`, `trusted`, `revoked`, permissions, metadata, `created_at`, and `updated_at`.

This prepares remote access and mobile approval flows without implementing login yet.

## Remaining Risks

- Device permissions are persisted but not enforced by `PermissionManager`.
- API requests still trust `x-actor-id`; no login/session validation exists yet.
- `CommandRuntime` is available in the runtime but not exposed through a dedicated API endpoint.
- Task writes and message writes are not atomic yet.
- Agent permissions in `CONFIG.yaml` are still not the source used by `PermissionManager`.
- No background scheduler or queue exists.

## Test Coverage Added

The hardening tests cover:

- exact `ContextLoader` section order
- chat history staying outside memory
- message creation as `pending`
- message status transitions to `read`, `processed`, and `failed`
- status transition events
- `/call` creating a real agent message
- `/task` creating a real task
- trusted and revoked device persistence
- device permission persistence

Latest command:

```powershell
py -m unittest discover -s tests
```

Latest result:

```text
Ran 17 tests
OK
```

## Recommended Next Foundation Step

Before adding UI or new runtimes, implement:

1. Runtime command/application service boundary for API, UI, scheduler, and mobile clients.
2. Device-aware `PermissionManager` checks.
3. Local auth/session layer for API calls.
4. Atomic writes for tasks, message records, memory appends, and device records.
5. Agent-config-driven permission loading, with clear separation between skill, permission, and autonomy.

