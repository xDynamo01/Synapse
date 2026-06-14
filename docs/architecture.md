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
      -> Agent Identity Runtime
      -> Effective Policy Runtime
      -> Context Loader
      -> Agent Runtime
      -> Model Adapters
      -> Task Runtime
      -> Tool System
      -> Tool Router
      -> Approval Manager
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

Every tool has one required permission string. For agent tools, authorization is resolved through `EffectivePolicyRuntime` before execution. `ToolRegistry.execute()` still checks the current `PermissionContext` before calling tool code as a final guard.

```text
Agent action
  -> AgentEffectivePolicy
  -> ToolRouter
  -> PermissionManager.require()
  -> ApprovalManager when required
  -> ToolRegistry.execute()
  -> Tool.run()
  -> EventBus.emit()
```

Direct service methods that can mutate state also call `PermissionManager`. This keeps the invariant intact even when a future scheduler or background worker bypasses HTTP.

## Effective Agent Policy

`EffectivePolicyRuntime` resolves the operational policy for each agent. The runtime should consult this policy instead of making scattered decisions about permissions, tools, autonomy, approval, or device constraints.

Inputs:

- global permissions from `data/config/permissions.yaml`
- explicit global denies from `data/config/permissions.yaml`
- agent `CONFIG.yaml`
- structured `AgentIdentity`
- approval policy from `data/config/approval_policy.yaml`
- optional device context from `PermissionContext.device_id`

Precedence:

1. explicit blocks always win
2. approval policy may require approval even when a tool is allowed
3. agent `CONFIG.yaml` can restrict or request permissions only inside the global ceiling
4. global permissions define the maximum permission ceiling
5. `AgentIdentity` provides behavior preferences, not authorization by itself
6. device constraints can restrict the result further

The resolved `AgentEffectivePolicy` includes:

- `allowed_tools`
- `forbidden_tools`
- `preferred_tools`
- `autonomy_profile`
- `approval_required_for`
- `can_delegate`
- `default_model`
- optional `risk_overrides`
- optional `device_constraints`

`ContextLoader` includes the policy as `agent_policy`. `AgentRuntime` uses the policy when exposing tool specs to models and when handling tool calls. `ToolRouter` validates the policy again when a policy is provided, so approval resume and direct router calls use the same gate.

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

- `agent_identity`: structured operational identity loaded from `SOUL.md`, `CONFIG.yaml`, and `SKILLS.md`
- `agent_policy`: effective policy resolved from global permissions, agent config, identity, approval policy, and device context
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
- structured `AgentEffectivePolicy`
- structured loaded context
- user message
- policy-filtered tool specs

It delegates response generation to `ModelRouter`. When a model response includes structured tool calls, `AgentRuntime` does not execute tools directly. It sends them to `ToolRouter`.

Before tool routing, `AgentRuntime` blocks tools explicitly forbidden by `AgentEffectivePolicy`. Other tool requests are sent to `ToolRouter`, which revalidates the policy and then calls `PermissionManager` and `ApprovalManager`.

## Agent Identity Runtime

`AgentIdentityRuntime` is responsible for loading and validating operational agent identity.

It reads:

- `agents/<agent_id>/SOUL.md`: identity narrative and operational rules
- `agents/<agent_id>/CONFIG.yaml`: operation, model, permissions, autonomy, structured identity fields
- `agents/<agent_id>/SKILLS.md`: capabilities

It does not read `MEMORY.md`; memory remains separate.

Structured identity fields:

- `id`
- `name`
- `role`
- `description`
- `can_delegate`
- `focus_areas`
- `preferred_tools`
- `forbidden_tools`
- `default_model`
- `autonomy_profile`
- `communication_style`
- `operational_rules`

Base agents:

- Artemis: orchestrator, can delegate, planning/coordination/briefings
- Researcher: research specialist, cannot delegate, forbids `write_file`
- Atlas: knowledge librarian, cannot delegate, forbids autonomous messaging and writes
- Hermes: communication specialist, cannot delegate, forbids future `send_email`
- Vigil: perception/security specialist, cannot delegate, forbids future `camera_control`

Tool calling flow:

```text
AgentRuntime
  -> EffectivePolicyRuntime
  -> ToolRouter
  -> PermissionManager
  -> ApprovalManager (when risk policy requires it)
  -> ToolRegistry.execute()
  -> Tool implementation
  -> EventBus
```

`ToolRouter` emits:

- `tool.requested`
- `tool.permission_checked`
- `tool.executed`
- `tool.failed`

Tool calls use the agent as the permission actor (`actor_type=agent`). This means a user chatting with an agent does not automatically grant that agent the user's permissions.

Each tool has a `risk_level`:

- `low`
- `medium`
- `high`
- `critical`

Default risk examples:

- `list_directory`: low
- `read_file`: low
- `create_task`: low
- `send_agent_message`: medium
- `write_file`: high

The approval policy lives in:

```text
data/config/approval_policy.yaml
```

Default policy requires approval for `high` and `critical` tools. Explicit tool permission does not bypass approval by default.

Approval requests are persisted under:

```text
data/approvals/<approval_id>.yaml
```

Approval statuses:

- `pending`
- `approved`
- `rejected`
- `expired`
- `resumed`

Approval events:

- `approval.requested`
- `approval.approved`
- `approval.rejected`
- `approval.expired`
- `approval.resumed`

When a tool requires approval, `ToolRouter` returns a `ToolCallResult` with `status="awaiting_approval"` and does not call `ToolRegistry.execute()`. If the same tool call is retried with an approved `approval_id`, `ToolRouter` validates the approval against agent, tool, risk level, and arguments before executing.

Approval requests retain enough data to resume execution:

- `agent_id`
- optional `session_id`
- `tool_name`
- `tool_args`
- `tool_call_id`
- optional `original_message_id`
- optional `project_id`

Resume flow:

```text
/approve or POST /approvals/{id}/approve
  -> ApprovalManager.approve()
  -> ApprovalResumeRuntime.resume()
  -> ToolRouter.execute_call()
  -> PermissionManager.require()
  -> ToolRegistry.execute()
  -> ApprovalManager.mark_resumed()
```

Approval resume resolves a fresh `AgentEffectivePolicy` and revalidates permissions immediately before execution. A resumed approval cannot execute a second time.

Current supported structured tool calls:

- `read_file`
- `list_directory`
- `create_task`
- `send_agent_message`

`web_search` remains registered but unconfigured by default.

`ModelRouter` selects a route from agent `CONFIG.yaml` when `preferred_model` exists. Otherwise it uses system model config. Registered adapters:

- `MockModelAdapter`: deterministic, used for tests and dev/test fallback
- `OllamaModelAdapter`: simple local Ollama `/api/chat` adapter
- `OpenAICompatibleAdapter`: prepared boundary, not implemented yet

`MockModelAdapter` supports deterministic tool-call tests with messages in this shape:

```text
tool:<tool_name> key=value key2="quoted value"
```

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
- `/agent <id>`
- `/policy <agent_id>`
- `/tasks`
- `/memory`
- `/call <agent> <message>`
- `/task <title> --agent <agent>`
- `/remember <text>`
- `/search <query>`
- `/approvals`
- `/approve <approval_id>`
- `/reject <approval_id>`

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

Each record stores `device_id`, `trusted`, `revoked`, permissions, metadata, and timestamps. `EffectivePolicyRuntime` can use device records as an additional ceiling for agent tools when `PermissionContext.device_id` is present.

Approval commands use device records when `PermissionContext.device_id` is present. A device must be trusted, not revoked, and have `approve_actions` or another configured approval permission.

Approval API endpoints:

- `GET /approvals/pending`
- `POST /approvals/{approval_id}/approve`
- `POST /approvals/{approval_id}/reject`

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
