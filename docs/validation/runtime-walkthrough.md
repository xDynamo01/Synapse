# Synapse V2 Runtime Walkthrough

Date: 2026-06-14

Scope: validate whether the current Synapse foundation works as a system. No product feature was implemented for this validation.

Update: after the Chat Runtime and Model Adapter step, the previous "user talks to Artemis" architectural gap is partially closed. A real runtime flow now exists for:

```text
User -> ChatRuntime -> ContextLoader -> AgentRuntime -> ModelRouter/ModelAdapter -> response -> events/logs/session
```

Remaining non-goals: no UI, no voice, no avatar, no communication integration, no perception runtime, and no autonomous agent/tool-calling loop.

## Technical Execution

The scenario was executed against a temporary `DATA_DIR`, not the repository `data/` directory.

Temporary agents were seeded for validation:

- `artemis`
- `researcher`

The runtime services used were the existing services:

- `RuntimeContainer`
- `MemoryStore`
- `TaskRuntime`
- `AgentCommunication`
- `EventBus`
- `ContextLoader`
- `PermissionManager`

Technical result summary:

```json
{
  "global_memory_read": true,
  "artemis_memory_read": true,
  "request_initial_status": "pending",
  "researcher_message_count_after_restart": 1,
  "artemis_message_count_after_restart": 1,
  "task_status_before_restart": "completed",
  "task_status_after_restart": "completed",
  "history_count_after_restart": 2,
  "log_line_count_before_restart": 22,
  "events_log_exists_after_restart": true
}
```

Event types generated during the technical run:

```text
runtime.started
runtime.started
permission.decision
permission.decision
permission.decision
task.created
permission.decision
agent.message.sent
permission.decision
permission.decision
agent.message.status_changed
permission.decision
agent.message.sent
permission.decision
agent.message.status_changed
permission.decision
permission.decision
agent.message.status_changed
permission.decision
task.updated
permission.decision
context.loaded
```

Important limitation in the original validation: conversation could only be represented as session history. Current status: `ChatRuntime` now persists sessions under `chats/sessions/` and uses `ContextLoader` for non-command turns. The LLM execution loop is still limited to model adapter response generation; tool calling remains `not_implemented`.

## Step-by-Step Walkthrough

### 1. User talks to Artemis

Status: executable at runtime level.

Components:

- `ChatRuntime`
- `ContextLoader`
- `AgentRuntime`
- `ModelRouter`
- `MockModelAdapter` for deterministic tests, or configured model adapter
- `EventBus`
- `DataDir`

Files read:

- `memory/SYSTEM.md`
- `memory/USER.md`
- `memory/MEMORY.md`
- `agents/artemis/SOUL.md`
- `agents/artemis/MEMORY.md`
- `agents/artemis/SKILLS.md`
- existing `chats/sessions/<session_id>.json` if the session already exists

Files written:

- `chats/sessions/<session_id>.json`
- `logs/events.jsonl`

Events generated:

- `chat.message_received`
- `permission.decision`
- `context.loaded`
- `chat.context_loaded`
- `agent.run.started`
- `agent.run.completed`
- `chat.response_generated`
- `chat.session_persisted`

Risks:

- Chat history is persisted as session state, but it must remain separate from memory.
- Tool calling is not implemented yet.
- Real model execution depends on configured adapters; deterministic tests use `MockModelAdapter`.

Architectural gap:

- Add streaming, tool-calling loop, and stronger session schema/versioning before UI chat grows.

### 2. Artemis reads global memory

Status: executable.

Components:

- `MemoryStore`
- `PermissionManager`
- `EventBus`
- `DataDir`

Files read:

- `memory/MEMORY.md`

Files written:

- `logs/events.jsonl`

Events generated:

- `permission.decision`

Risks:

- Permission config is loaded at runtime startup, so changes require runtime recreation.
- Memory is raw markdown with no schema/provenance yet.

Technical validation:

- `runtime.memory.read_global(artemis, "MEMORY.md")` returned expected global memory content.

### 3. Artemis reads her own memory

Status: executable.

Components:

- `MemoryStore`
- `PermissionManager`
- `EventBus`
- `DataDir`

Files read:

- `agents/artemis/MEMORY.md`

Files written:

- `logs/events.jsonl`

Events generated:

- `permission.decision`

Risks:

- The runtime can read agent memory, but there is no higher-level memory policy for summarization, conflict resolution, or compaction.
- Artemis must already exist as an agent directory and config. The default repository currently bootstraps `orchestrator`, not Artemis.

Technical validation:

- `runtime.memory.read_agent_memory(artemis, "artemis")` returned expected Artemis memory content.

### 4. Artemis creates a task

Status: executable.

Components:

- `TaskRuntime`
- `PermissionManager`
- `EventBus`
- `DataDir`

Files read:

- `config/permissions.yaml`
- existing task directories when listing or later loading

Files written:

- `tasks/active/<task_id>.json`
- `logs/events.jsonl`

Events generated:

- `permission.decision`
- `task.created`

Risks:

- Task write is not atomic.
- Task metadata is free-form; there is no strict assignment/project schema yet.
- No task event history file exists besides global event log and metadata notes.

Technical validation:

- `runtime.tasks.create_task(...)` created a real JSON task file under `tasks/active`.

### 5. Artemis sends a message to Researcher

Status: executable.

Components:

- `AgentCommunication`
- `AgentRegistry`
- `PermissionManager`
- `EventBus`
- `DataDir`

Files read:

- `agents/artemis/CONFIG.yaml`
- `agents/researcher/CONFIG.yaml`
- `config/permissions.yaml`

Files written:

- `agents/researcher/INBOX.md`
- `agents/researcher/messages/<message_id>.yaml`
- `logs/events.jsonl`

Events generated:

- `permission.decision`
- `agent.message.sent`

Risks:

- Message file write is not atomic.
- There is no delivery retry model.
- There is no separate outbox for Artemis.
- Agent permissions in `CONFIG.yaml` are not the source of truth for `PermissionManager`; permissions still come from `config/permissions.yaml`.

Technical validation:

- A structured message was created with status `pending`.
- The human-readable `INBOX.md` projection was updated.

### 6. Researcher receives the message

Status: executable.

Components:

- `AgentCommunication`
- `AgentRegistry`
- `PermissionManager`
- `EventBus`
- `DataDir`

Files read:

- `agents/researcher/messages/<message_id>.yaml`
- `agents/researcher/CONFIG.yaml`
- `config/permissions.yaml`

Files written:

- `agents/researcher/messages/<message_id>.yaml` when marked read
- `logs/events.jsonl`

Events generated:

- `permission.decision`
- `agent.message.status_changed` when message becomes `read`

Risks:

- Receiving means listing/reading message records; no background inbox processing exists.
- No agent loop automatically reacts to pending messages.

Technical validation:

- `runtime.communication.list_messages(researcher, "researcher")` returned the pending message.
- `mark_read(...)` changed status to `read` and emitted an event.

### 7. Researcher responds

Status: executable.

Components:

- `AgentCommunication`
- `AgentRegistry`
- `PermissionManager`
- `EventBus`
- `DataDir`

Files read:

- `agents/researcher/CONFIG.yaml`
- `agents/artemis/CONFIG.yaml`
- `config/permissions.yaml`

Files written:

- `agents/artemis/INBOX.md`
- `agents/artemis/messages/<response_id>.yaml`
- `agents/researcher/messages/<request_id>.yaml` when request is marked processed
- `logs/events.jsonl`

Events generated:

- `permission.decision`
- `agent.message.sent`
- `agent.message.status_changed` when the original request becomes `processed`

Risks:

- Response is manually invoked by runtime calls. There is no autonomous Researcher processing loop.
- The request/response relationship exists through shared `task_id`, not a formal conversation thread id.

Technical validation:

- Researcher sent a structured response to Artemis.
- The original Researcher message was marked `processed`.

### 8. Artemis receives the response

Status: executable.

Components:

- `AgentCommunication`
- `AgentRegistry`
- `PermissionManager`
- `EventBus`
- `DataDir`

Files read:

- `agents/artemis/messages/<response_id>.yaml`
- `agents/artemis/CONFIG.yaml`
- `config/permissions.yaml`

Files written:

- `agents/artemis/messages/<response_id>.yaml` when marked read
- `logs/events.jsonl`

Events generated:

- `permission.decision`
- `agent.message.status_changed`

Risks:

- Artemis does not automatically consume or reason over the response.
- No inbox notification or scheduler exists yet.

Technical validation:

- Artemis had one response message after restart.
- `mark_read(...)` updated its status and emitted an event.

### 9. Task is completed

Status: executable.

Components:

- `TaskRuntime`
- `PermissionManager`
- `EventBus`
- `DataDir`

Files read:

- `tasks/active/<task_id>.json`
- `config/permissions.yaml`

Files written:

- `tasks/completed/<task_id>.json`
- `logs/events.jsonl`

Files deleted/moved:

- `tasks/active/<task_id>.json` is deleted after the completed task record is written.

Events generated:

- `permission.decision`
- `task.updated`

Risks:

- Update is delete-then-write, not atomic.
- A crash between delete and write can lose the task.

Technical validation:

- The task status was `completed` before restart and remained `completed` after restart.

### 10. Events are registered

Status: executable.

Components:

- `EventBus`
- all runtime services that emit events

Files read:

- `logs/events.jsonl` when tailing events

Files written:

- `logs/events.jsonl`

Events generated:

- `runtime.started`
- `permission.decision`
- `task.created`
- `agent.message.sent`
- `agent.message.status_changed`
- `task.updated`
- `context.loaded`

Risks:

- Events are append-only JSONL with no rotation, indexing, or correlation id.
- Events are not written atomically as part of the same transaction as task/message changes.

Technical validation:

- 22 event log lines existed before the simulated restart.

### 11. Logs are registered

Status: partial.

Components:

- `EventBus`

Files read:

- `logs/events.jsonl`

Files written:

- `logs/events.jsonl`

Events generated:

- Same event types listed in step 10.

Risks:

- The only implemented log is the runtime event log.
- There is no separate application log, structured request log, tool trace log, or log retention policy.

Architectural gap:

- Add logging policy later: event log for domain events, application logs for runtime diagnostics, and request/task correlation ids.

### 12. Context is reconstructed correctly

Status: executable for current context scope.

Components:

- `ContextLoader`
- `AgentRegistry`
- `TaskRuntime`
- `PermissionManager`
- `EventBus`
- `DataDir`

Files read:

- `memory/SYSTEM.md`
- `memory/USER.md`
- `memory/MEMORY.md`
- `agents/artemis/SOUL.md`
- `agents/artemis/MEMORY.md`
- `agents/artemis/SKILLS.md`
- `tasks/completed/<task_id>.json`

Files written:

- `logs/events.jsonl`

Events generated:

- `permission.decision`
- `context.loaded`

Context source order observed:

```text
memory/SYSTEM.md
memory/USER.md
memory/MEMORY.md
agents/artemis/SOUL.md
agents/artemis/MEMORY.md
agents/artemis/SKILLS.md
tasks/completed/<task_id>.json
history item
history item
```

Risks:

- Chat history is correctly separate from memory, but there is no chat session persistence yet.
- Relevant tasks are detected through free-form metadata.
- Project context was not part of this specific walkthrough because no project was created.

Technical validation:

- Context before restart and after restart had the same source order.
- Two session history items were included as history, not memory.

### 13. System restarts

Status: executable as runtime recreation.

Components:

- `create_runtime`
- `RuntimeContainer`
- `DataDir`
- `ConfigStore`
- `PermissionManager`
- `EventBus`
- `AgentRegistry`
- `TaskRuntime`
- `AgentCommunication`
- `ContextLoader`

Files read:

- `config/system.yaml`
- `config/permissions.yaml`
- agent configs as needed after restart
- existing tasks/messages when queried after restart

Files written:

- `logs/events.jsonl`

Events generated:

- `runtime.started`

Risks:

- This validates service recreation, not a full process manager or graceful shutdown.
- There is no background worker lifecycle yet.

Technical validation:

- A new runtime was created against the same temporary `DATA_DIR`.

### 14. State is preserved

Status: executable.

Components:

- `TaskRuntime`
- `AgentCommunication`
- `ContextLoader`
- `EventBus`
- `DataDir`

Files read:

- `tasks/completed/<task_id>.json`
- `agents/researcher/messages/<request_id>.yaml`
- `agents/artemis/messages/<response_id>.yaml`
- `agents/researcher/INBOX.md`
- `agents/artemis/INBOX.md`
- `logs/events.jsonl`
- memory and agent files used by context reconstruction

Files written:

- `logs/events.jsonl` for runtime restart and context reload

Events generated:

- `runtime.started`
- `permission.decision`
- `context.loaded`

Risks:

- State is preserved because it is file-backed.
- There is no migration/versioning for persisted structured records yet.
- There is no consistency checker for orphaned task/message/event records.

Technical validation:

- Task status after restart: `completed`.
- Researcher message count after restart: `1`.
- Artemis message count after restart: `1`.
- Event log still existed after restart.

## Complete System Flow

1. Runtime starts and loads config, permissions, event bus, agents, memory, tasks, tools, context loader, command runtime, and device registry.
2. A session with Artemis can currently be represented as transient history, but not persisted as real chat.
3. Artemis reads global and agent memory through `MemoryStore`.
4. Artemis creates a persisted task through `TaskRuntime`.
5. Artemis sends a structured message to Researcher through `AgentCommunication`.
6. Researcher lists pending messages and marks the request as read.
7. Researcher sends a structured response to Artemis and marks the request processed.
8. Artemis lists received messages and marks the response read.
9. Artemis completes the task through `TaskRuntime`.
10. `EventBus` records permission decisions, task events, message events, context load, and runtime starts.
11. `ContextLoader` reconstructs typed context from memory, identity, relevant tasks, and transient history.
12. Runtime is recreated against the same `DATA_DIR`.
13. Tasks, messages, inbox projections, memory, and event log remain available.

## Execution Diagram

```mermaid
sequenceDiagram
    participant User
    participant Artemis
    participant Runtime
    participant Memory as "MemoryStore"
    participant Tasks as "TaskRuntime"
    participant A2A as "AgentCommunication"
    participant Researcher
    participant Context as "ContextLoader"
    participant Events as "EventBus"
    participant Files as "DATA_DIR"

    User->>Artemis: "Session history (no Chat Runtime yet)"
    Artemis->>Memory: "read_global(MEMORY.md)"
    Memory->>Events: "permission.decision"
    Memory->>Files: "read memory/MEMORY.md"
    Artemis->>Memory: "read_agent_memory(artemis)"
    Memory->>Files: "read agents/artemis/MEMORY.md"
    Artemis->>Tasks: "create_task"
    Tasks->>Files: "write tasks/active/<task>.json"
    Tasks->>Events: "task.created"
    Artemis->>A2A: "send_agent_message(to researcher)"
    A2A->>Files: "append researcher/INBOX.md"
    A2A->>Files: "write researcher/messages/<message>.yaml"
    A2A->>Events: "agent.message.sent"
    Researcher->>A2A: "list_messages + mark_read"
    A2A->>Events: "agent.message.status_changed"
    Researcher->>A2A: "send response(to artemis)"
    A2A->>Files: "append artemis/INBOX.md"
    A2A->>Files: "write artemis/messages/<response>.yaml"
    A2A->>Events: "agent.message.sent"
    Artemis->>A2A: "mark response read"
    A2A->>Events: "agent.message.status_changed"
    Artemis->>Tasks: "update_task(completed)"
    Tasks->>Files: "move active task to completed"
    Tasks->>Events: "task.updated"
    Artemis->>Context: "load(artemis, history)"
    Context->>Files: "read memory, identity, task"
    Context->>Events: "context.loaded"
    Runtime->>Runtime: "restart with same DATA_DIR"
    Runtime->>Files: "read persisted state"
```

## Gaps Found

1. Chat Runtime exists, but has no streaming/tool-calling loop.
   User-to-agent turns are executable and persisted, but agents do not yet plan or execute tools from model output.

2. No LLM/agent execution loop exists.
   Artemis and Researcher do not autonomously reason, call tools, or process inboxes.

3. Persistent chat/session log exists, but is basic.
   Sessions persist under `data/chats/sessions/`, but there is no schema version, attachment model, retention policy, or search.

4. Logs are only event logs.
   `logs/events.jsonl` works, but there is no separate application diagnostic log or request correlation.

5. Message threading is incomplete.
   Request and response share `task_id`, but there is no formal thread/conversation id.

6. Agent inbox processing is manual.
   Pending messages are not picked up by a scheduler or background worker.

7. Task and message writes are not atomic.
   Crashes during update can leave inconsistent state.

8. Artemis and Researcher are not bootstrap agents.
   The current repository ships only `orchestrator`. The validation had to seed Artemis and Researcher in a temporary `DATA_DIR`.

9. Permission source is split.
   Agent config declares permissions, but `PermissionManager` enforces permissions from `config/permissions.yaml`.

10. No persisted state migration/versioning exists.
    YAML message records and JSON task records have no schema version.

## Correction Priorities

Priority 1:

- Add message thread/conversation ids for agent-to-agent exchanges.
- Make task and message writes atomic.
- Add schema versioning for chat sessions, tasks, and messages.

Priority 2:

- Add a background inbox processor/scheduler for agent message handling.
- Add request/task/event correlation ids.
- Add schema version fields for structured persisted records.

Priority 3:

- Connect agent `CONFIG.yaml` permissions to `PermissionManager` or document the single source of truth more strictly.
- Add a diagnostic application log separate from domain event log.
- Add bootstrap agent templates for Artemis and Researcher only when product design requires them.

Priority 4:

- Add real model integration and agent execution loop.
- Add API endpoints for session/chat and command runtime only after the runtime contracts are stable.
