# Synapse V2 Runtime Walkthrough

Date: 2026-06-14

Scope: validate whether the current Synapse foundation works as a system. No product feature was implemented for this validation.

Update: after the Chat Runtime and Model Adapter step, the previous "user talks to Artemis" architectural gap is partially closed. A real runtime flow now exists for:

```text
User -> ChatRuntime -> ContextLoader -> AgentIdentityRuntime -> EffectivePolicyRuntime -> AgentRuntime -> ModelRouter/ModelAdapter -> response -> events/logs/session
```

Remaining non-goals: no UI, no voice, no avatar, no communication integration, no perception runtime, no mobile approval UI, and no autonomous multi-step agent loop.

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
- `AgentIdentityRuntime`
- `EffectivePolicyRuntime`
- `SchedulerRuntime`
- `DaemonRunner`
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

Important limitation in the original validation: conversation could only be represented as session history. Current status: `ChatRuntime` now persists sessions under `chats/sessions/` and uses `ContextLoader` for non-command turns. Model responses can now request controlled tool calls through `ToolRouter`; high/critical risk calls create persisted approval requests before execution. Once approved, the runtime can resume and execute the saved tool call without the user resending it. Multi-step planning and streaming remain out of scope.

Agent identity status: agents now load structured operational identity through `AgentIdentityRuntime`. Artemis, Researcher, Atlas, Hermes, and Vigil exist as base agents in `DATA_DIR`, each with distinct roles, focus areas, preferred tools, forbidden tools, communication styles, and operational rules.

Effective policy status: `EffectivePolicyRuntime` now resolves the single policy object used by `AgentRuntime`, `ToolRouter`, `ApprovalResumeRuntime`, `ContextLoader`, and `/policy`. It combines global permissions, agent `CONFIG.yaml`, `AgentIdentity`, approval policy, and optional device constraints.

## Step-by-Step Walkthrough

### 1. User talks to Artemis

Status: executable at runtime level.

Components:

- `ChatRuntime`
- `ContextLoader`
- `AgentIdentityRuntime`
- `EffectivePolicyRuntime`
- `AgentRuntime`
- `ModelRouter`
- `MockModelAdapter` for deterministic tests, or configured model adapter
- `ToolRouter` when the model response requests a tool
- `ApprovalManager` when the tool risk policy requires approval
- `ApprovalResumeRuntime` when an approval is approved and resumed
- `EventBus`
- `DataDir`

Files read:

- `memory/SYSTEM.md`
- `memory/USER.md`
- `memory/MEMORY.md`
- `agents/artemis/SOUL.md`
- `agents/artemis/CONFIG.yaml`
- `agents/artemis/MEMORY.md`
- `agents/artemis/SKILLS.md`
- `config/permissions.yaml`
- `config/approval_policy.yaml`
- optional `devices/<state>/<device_id>.yaml`
- existing `chats/sessions/<session_id>.json` if the session already exists

Files written:

- `chats/sessions/<session_id>.json`
- `logs/events.jsonl`
- tool-specific files when requested, such as tasks or agent messages
- `approvals/<approval_id>.yaml` when a sensitive tool requires human approval

Events generated:

- `chat.message_received`
- `permission.decision`
- `context.loaded`
- `chat.context_loaded`
- `agent.run.started`
- forbidden tool blocking before `ToolRouter`, when applicable
- `tool.requested`, when applicable
- `tool.permission_checked`, when applicable
- `approval.requested`, when risk policy requires approval
- `approval.approved` or `approval.rejected`, when a human decision is made
- `approval.resumed`, when an approved request executes successfully
- `tool.executed` or `tool.failed`, when applicable
- `agent.run.completed`
- `chat.response_generated`
- `chat.session_persisted`

Risks:

- Chat history is persisted as session state, but it must remain separate from memory.
- Tool calling is controlled, permission-gated, and approval-gated for high/critical risk tools, but only supports simple single-pass execution.
- Agents now have distinct identities, but identity schema versioning and editing workflows are not implemented.
- Agent policy is centralized, but resource-scoped filesystem and per-project policy rules are still missing.
- Real model execution depends on configured adapters; deterministic tests use `MockModelAdapter`.

Architectural gap:

- Add streaming, multi-step tool planning, and stronger session schema/versioning before UI chat grows.

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
- Artemis now exists as a base bootstrap agent. Older `DATA_DIR` instances created before the identity runtime may need a bootstrap/migration pass.

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
- Agent permissions in `CONFIG.yaml` are combined with the global permission ceiling by `EffectivePolicyRuntime`.

Technical validation:

- A structured message was created with status `pending`.
- The human-readable `INBOX.md` projection was updated.

### 6. Researcher receives the message

Status: executable.

Components:

- `AgentWorker`
- `AgentCommunication`
- `ContextLoader`
- `AgentRuntime`
- `EffectivePolicyRuntime`
- `AgentRegistry`
- `PermissionManager`
- `EventBus`
- `DataDir`

Files read:

- `agents/researcher/messages/<message_id>.yaml`
- `agents/researcher/CONFIG.yaml`
- `agents/researcher/SOUL.md`
- `agents/researcher/MEMORY.md`
- `agents/researcher/SKILLS.md`
- `config/permissions.yaml`
- `config/approval_policy.yaml`

Files written:

- `agents/researcher/messages/<message_id>.yaml` when marked read
- `logs/events.jsonl`

Events generated:

- `permission.decision`
- `worker.inbox_checked`
- `worker.message_processing_started`
- `agent.message.status_changed` when message becomes `read`

Risks:

- Receiving is executable through `AgentWorker`, but still requires command/API invocation.
- No scheduler automatically reacts to pending messages yet.

Technical validation:

- `runtime.worker.process_inbox(..., "researcher")` lists pending messages and marks the message `read`.

### 7. Researcher responds

Status: executable.

Components:

- `AgentWorker`
- `AgentCommunication`
- `ContextLoader`
- `AgentRuntime`
- `EffectivePolicyRuntime`
- `AgentRegistry`
- `PermissionManager`
- `EventBus`
- `DataDir`

Files read:

- `agents/researcher/CONFIG.yaml`
- `agents/researcher/SOUL.md`
- `agents/researcher/MEMORY.md`
- `agents/researcher/SKILLS.md`
- `agents/artemis/CONFIG.yaml`
- `config/permissions.yaml`

Files written:

- `agents/artemis/INBOX.md`
- `agents/artemis/messages/<response_id>.yaml`
- `agents/researcher/messages/<request_id>.yaml` when request is marked processed
- `logs/events.jsonl`

Events generated:

- `permission.decision`
- `worker.message_processed`
- `agent.message.sent`
- `agent.message.status_changed` when the original request becomes `processed`

Risks:

- Response is produced by `AgentWorker` using `AgentRuntime`; invocation is explicit, not scheduled.
- The request/response relationship exists through shared `task_id`, not a formal conversation thread id.

Technical validation:

- Researcher can send a structured response to Artemis when effective policy allows autonomous messaging.
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
- `EffectivePolicyRuntime`
- `TaskRuntime`
- `PermissionManager`
- `EventBus`
- `DataDir`

Files read:

- `memory/SYSTEM.md`
- `memory/USER.md`
- `memory/MEMORY.md`
- `agents/artemis/SOUL.md`
- `agents/artemis/CONFIG.yaml`
- `agents/artemis/MEMORY.md`
- `agents/artemis/SKILLS.md`
- `config/permissions.yaml`
- `config/approval_policy.yaml`
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

The structured context also includes `agent_policy`, which is resolved outside the ordered memory/history sections.

Risks:

- Chat history is correctly separate from memory and persisted as session history, not memory.
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

1. Runtime starts and loads config, permissions, event bus, identities, agents, memory, tasks, tools, approvals, effective policy runtime, context loader, agent worker, scheduler runtime, daemon runner, command runtime, and device registry.
2. A chat turn with Artemis is persisted under `chats/sessions/` through `ChatRuntime`.
3. `ContextLoader` loads global memory, Artemis identity, Artemis effective policy, Artemis memory, skills, relevant tasks, and recent session history.
4. Artemis reads global and agent memory through runtime-owned services, not direct file access.
5. Artemis creates a persisted task through `TaskRuntime`.
6. Artemis sends a structured message to Researcher through `AgentCommunication`.
7. `DaemonRunner.run_once()` can trigger `SchedulerRuntime` to run a `process_agent_inbox` job, causing `AgentWorker` to list Researcher pending messages and mark the request as read.
8. `AgentWorker` loads Researcher context/policy, runs `AgentRuntime`, optionally sends a structured response to Artemis, and marks the request processed.
9. Artemis lists received messages and marks the response read.
10. Artemis completes the task through `TaskRuntime`.
11. `EventBus` records permission decisions, task events, message events, tool events, approval events, context load, chat events, and runtime starts.
12. `ContextLoader` reconstructs typed context from memory, identity, effective policy, relevant tasks, and session history.
13. Runtime is recreated against the same `DATA_DIR`.
14. Tasks, daemon status, jobs, messages, inbox projections, memory, identity files, chat sessions, approvals, and event log remain available.

With controlled tool calling, steps 4 and 5 can also be initiated by a model-produced `ToolCallRequest`. For low-risk tools, execution path is:

```text
AgentRuntime -> EffectivePolicyRuntime -> ToolRouter -> PermissionManager -> ToolRegistry -> Tool implementation
```

For high/critical tools, approval and resume path is:

```text
AgentRuntime -> EffectivePolicyRuntime -> ToolRouter -> PermissionManager -> ApprovalManager(pending)
/approve -> ApprovalResumeRuntime -> EffectivePolicyRuntime -> ToolRouter -> PermissionManager -> ToolRegistry -> ApprovalManager(resumed)
```

For scheduled inbox work:

```text
Command/API -> DaemonRunner -> SchedulerRuntime -> JobQueue(DATA_DIR/jobs) -> AgentWorker -> AgentRuntime
```

## Execution Diagram

```mermaid
sequenceDiagram
    participant User
    participant Artemis
    participant Runtime
    participant Daemon as "DaemonRunner"
    participant Identity as "AgentIdentityRuntime"
    participant Policy as "EffectivePolicyRuntime"
    participant Memory as "MemoryStore"
    participant Tasks as "TaskRuntime"
    participant A2A as "AgentCommunication"
    participant Scheduler as "SchedulerRuntime"
    participant Worker as "AgentWorker"
    participant Researcher
    participant Context as "ContextLoader"
    participant Events as "EventBus"
    participant Files as "DATA_DIR"

    User->>Runtime: "POST/chat or ChatRuntime.chat"
    Runtime->>Context: "load context for artemis"
    Context->>Identity: "load_identity(artemis)"
    Identity->>Files: "read SOUL.md, CONFIG.yaml, SKILLS.md"
    Context->>Policy: "resolve(artemis)"
    Policy->>Files: "read permissions, CONFIG.yaml, approval policy, device"
    Context->>Files: "read memory and recent session history"
    Runtime->>Artemis: "run with structured policy and context"
    Artemis->>Memory: "read_global(MEMORY.md)"
    Memory->>Events: "permission.decision"
    Memory->>Files: "read memory/MEMORY.md"
    Artemis->>Memory: "read_agent_memory(artemis)"
    Memory->>Files: "read agents/artemis/MEMORY.md"
    Artemis->>Tasks: "create_task"
    Tasks->>Files: "write tasks/active/<task>.json"
    Tasks->>Events: "task.created"
    Artemis->>Runtime: "model tool call request"
    Runtime->>Policy: "resolve effective policy"
    Runtime->>Events: "tool.requested"
    Runtime->>Events: "tool.permission_checked"
    Runtime->>Events: "approval.requested when high/critical"
    Runtime->>Runtime: "approval approved"
    Runtime->>Events: "approval.approved"
    Runtime->>Runtime: "resume approved tool call"
    Runtime->>Files: "tool writes through ToolRegistry"
    Runtime->>Events: "approval.resumed"
    Runtime->>Events: "tool.executed or tool.failed"
    Artemis->>A2A: "send_agent_message(to researcher)"
    A2A->>Files: "append researcher/INBOX.md"
    A2A->>Files: "write researcher/messages/<message>.yaml"
    A2A->>Events: "agent.message.sent"
    Runtime->>Scheduler: "enqueue process_agent_inbox"
    Scheduler->>Files: "write jobs/<job>.yaml"
    Runtime->>Daemon: "run_once"
    Daemon->>Events: "daemon.tick"
    Daemon->>Scheduler: "run_all_pending"
    Scheduler->>Events: "job.started"
    Scheduler->>Worker: "process_inbox(researcher)"
    Worker->>A2A: "list pending researcher messages + mark_read"
    A2A->>Events: "agent.message.status_changed"
    Worker->>Context: "load researcher context"
    Worker->>Policy: "resolve researcher policy"
    Worker->>Researcher: "AgentRuntime.run(message body)"
    Worker->>A2A: "optional response(to artemis)"
    A2A->>Files: "append artemis/INBOX.md"
    A2A->>Files: "write artemis/messages/<response>.yaml"
    A2A->>Events: "agent.message.sent"
    Worker->>A2A: "mark original processed or failed"
    Worker->>Events: "worker.message_processed or worker.message_failed"
    Scheduler->>Events: "job.completed or job.failed"
    Daemon->>Files: "write daemon/status.yaml"
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

1. Chat Runtime exists, but has no streaming or multi-step tool loop.
   User-to-agent turns are executable and persisted. Models can request simple structured tool calls, but there is no iterative observe/think/act cycle yet.

1A. Approval Gate exists, but has no UI/mobile approval surface.
    Approval can be managed through runtime commands and API endpoints only.

1B. Agent Identity Runtime exists, but has no schema version, editor, or migration workflow.
    SOUL, CONFIG, and SKILLS are loaded separately and exposed to runtime context, but identity records are still file-authored and manually maintained.

1C. Effective Agent Policy exists, but is still coarse-grained.
    It centralizes global permissions, agent config, identity preferences, approval policy, and device constraints. Resource-scoped filesystem/project/model rules and policy schema migrations are still missing.

2. Daemon Runner exists, but no production service wrapper exists.
   `run_once()` can execute pending jobs deterministically and `start_loop()` provides a basic loop boundary. There is no CLI/service wrapper, process supervision, lock manager, or backoff retry policy yet.

3. Persistent chat/session log exists, but is basic.
   Sessions persist under `data/chats/sessions/`, but there is no schema version, attachment model, retention policy, or search.

4. Logs are only event logs.
   `logs/events.jsonl` works, but there is no separate application diagnostic log or request correlation.

5. Message threading is incomplete.
   Request and response share `task_id`, but there is no formal thread/conversation id.

6. Agent inbox processing is queued and daemon-runnable, but still not supervised.
   Pending messages can be processed directly by `AgentWorker`, through `SchedulerRuntime` jobs, or by `DaemonRunner.run_once()`. There is no supervised 24/7 service yet.

7. Task and message writes are not atomic.
   Crashes during update can leave inconsistent state.

8. Base agents now exist, but older data directories may not have them.
   Artemis, Researcher, Atlas, Hermes, and Vigil are seeded for new `DATA_DIR` instances. Existing local directories created earlier need an explicit bootstrap or migration path.

9. Policy source is centralized, but not resource-scoped.
   `EffectivePolicyRuntime` combines agent config with global permissions, but rules are still permission-string based rather than scoped to paths, projects, models, or specific devices.

10. No persisted state migration/versioning exists.
    YAML message records, identity configs, chat sessions, approvals, and JSON task records have no schema version.

## Correction Priorities

Priority 1:

- Add message thread/conversation ids for agent-to-agent exchanges.
- Make task and message writes atomic.
- Add schema versioning for chat sessions, tasks, and messages.
- Add schema versioning and validation tooling for agent identity files.
- Add schema versioning and validation tooling for effective policy inputs.
- Add multi-step tool observation and final model follow-up.
- Add approval notifications, remote-safe approval workflows, and session message updates after resume.
- Add worker retry policy and queue/scheduler before homelab autonomous mode.
- Add daemon service wrapper, scheduler locks, backoff, and retention policies before homelab autonomous mode.

Priority 2:

- Add CLI/service packaging for the daemon runner.
- Add request/task/event correlation ids.
- Add schema version fields for structured persisted records.

Priority 3:

- Add resource-scoped policy rules for files, projects, tools, devices, and model access.
- Add a diagnostic application log separate from domain event log.
- Add identity editing and review workflows before allowing non-technical users to modify base agents.

Priority 4:

- Add real model integration and agent execution loop.
- Add API endpoints for session/chat and command runtime only after the runtime contracts are stable.
