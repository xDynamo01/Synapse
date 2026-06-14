# Synapse Foundation Architecture

## Runtime Boundary

The UI is a client. The API is an adapter. The runtime owns behavior.

```text
Client/UI
  -> API Layer
    -> RuntimeContainer
      -> Core: config, data dir, permissions, events, model routing
      -> Chat Runtime
      -> Memory System
      -> Context Loader
      -> Agent Runtime
      -> Model Adapters
      -> Task Runtime
      -> Tool System
      -> Command Runtime
      -> Device Registry
```

## DATA_DIR

All persistent local state lives under one root:

```text
data/
  config/
  memory/
  agents/
    <agent_id>/
      messages/
  projects/
  skills/
  tasks/
    active/
    completed/
    failed/
  logs/
  library/
  chats/
  devices/
    trusted/
    untrusted/
    revoked/
```

The runtime creates missing directories and seed files during bootstrap. New storage systems should be added inside `DATA_DIR`, not beside it.

## Permission Flow

Every tool has one required permission string. `ToolRegistry.execute()` checks the current `PermissionContext` before calling tool code.

```text
API request or runtime action
  -> PermissionContext
  -> ToolRegistry
  -> PermissionManager.require()
  -> Tool.run()
  -> EventBus.emit()
```

Direct service methods that can mutate state also call `PermissionManager`. This keeps the invariant intact even when a future scheduler or background worker bypasses HTTP.

## Context Loader

`ContextLoader` is the runtime-owned context composer. It returns a structured `LoadedContext`, not a prompt string.

The load order is fixed:

1. `memory/SYSTEM.md`
2. `memory/USER.md`
3. `memory/MEMORY.md`
4. `agents/<agent_id>/SOUL.md`
5. `agents/<agent_id>/MEMORY.md`
6. `agents/<agent_id>/SKILLS.md`
7. `projects/<project_id>/PROJECT.md`, when a project is provided
8. `projects/<project_id>/MEMORY.md`, when a project is provided
9. relevant tasks
10. recent session history

The returned object separates:

- `memory`: global, user, system, and agent memory
- `identity`: agent soul and skills
- `project`: project description and project memory
- `tasks`: relevant persisted task records
- `history`: recent session excerpts only, never memory

## Chat Runtime

`ChatRuntime` owns the real user-to-agent turn flow. The UI and API are clients.

```text
User message
  -> ChatRuntime
  -> ContextLoader
  -> AgentRuntime
  -> ModelRouter
  -> ModelAdapter
  -> ChatRuntime persists session
  -> EventBus
```

Chat sessions are persisted under:

```text
data/chats/sessions/<session_id>.json
```

Session history is passed to `ContextLoader` as `history`; it is never written to memory files.

If a chat message starts with `/`, `ChatRuntime` delegates to `CommandRuntime` and persists the command response in the same session. Non-command messages follow the normal agent/model flow.

Chat events:

- `chat.message_received`
- `chat.context_loaded`
- `chat.response_generated`
- `chat.session_persisted`

## Agent Runtime and Models

`AgentRuntime` receives:

- agent id
- structured loaded context
- user message
- allowed tool specs

It delegates response generation to `ModelRouter`. Tool calling is intentionally marked `not_implemented` at this stage; the runtime boundary is in place for future tool execution planning.

`ModelRouter` selects a route from agent `CONFIG.yaml` when `preferred_model` exists. Otherwise it uses system model config. Registered adapters:

- `MockModelAdapter`: deterministic, used for tests and dev/test fallback
- `OllamaModelAdapter`: simple local Ollama `/api/chat` adapter
- `OpenAICompatibleAdapter`: prepared boundary, not implemented yet

## Agent Files

Each agent is a persistent directory:

```text
data/agents/<agent_id>/
  SOUL.md
  MEMORY.md
  SKILLS.md
  CONFIG.yaml
  INBOX.md
  messages/
    <message_id>.yaml
```

The Brain/UI and runtime must read the same files. No separate shadow memory is allowed.

`INBOX.md` is a human-readable projection. Operational message state lives in structured YAML records under `messages/`.

Agent messages have:

- `id`
- `from_agent`
- `to_agent`
- `subject`
- `body`
- optional `task_id`
- `status`: `pending`, `read`, `processed`, or `failed`
- `created_at`
- `updated_at`

Every message creation or status change emits an event.

## Command Runtime

`CommandRuntime` is a runtime client boundary for text commands. It does not own business logic; it delegates to runtime services and tools.

Supported commands:

- `/help`
- `/agents`
- `/tasks`
- `/memory`
- `/call <agent> <message>`
- `/task <title> --agent <agent>`
- `/remember <text>`
- `/search <query>`

This runtime exists before UI so desktop, API, mobile, scheduler, and future voice input can share command behavior.

## Device Registry

`DeviceRegistry` prepares the remote access boundary without implementing login yet.

Devices are persisted under:

```text
data/devices/
  trusted/<device_id>.yaml
  untrusted/<device_id>.yaml
  revoked/<device_id>.yaml
```

Each record stores `device_id`, `trusted`, `revoked`, permissions, metadata, and timestamps. Device permissions are persisted but are not yet enforced by `PermissionManager`.

## Tool Contract

Tools are registered with:

- stable name
- description
- required permission
- Python callable implementation

This is intentionally close to OpenAPI tool server metadata without making OpenAPI the internal dependency.

## Events

Runtime actions append JSON lines to:

```text
data/logs/events.jsonl
```

Events are the base for Mission Control, audit views, background monitors, observability, and future mobile notifications.
