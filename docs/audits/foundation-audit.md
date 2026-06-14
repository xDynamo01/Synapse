# Synapse V2 Foundation Audit

Date: 2026-06-14

Scope: current implementation under `E:\Projetos\Synapse`. This audit reviews the foundation against the stated principles: local-first, permission-first, runtime-first, memory-first, agent-first, and homelab-ready.

## Executive Summary

The current foundation is directionally correct. It is not a chatbot wrapper: the first implementation centers a runtime container, local `DATA_DIR`, permission-gated tools, persistent agents, persistent tasks, an event log, and a thin FastAPI layer over runtime services.

The main gaps are architectural hardening, not feature volume. The most important missing pieces before UI work are a formal context loader, a stronger message/state model for agent-to-agent communication, a real auth/session boundary for API callers, and explicit extension contracts for future Voice, Avatar, Perception, Communication, and Remote Access runtimes.

## Principle Check

### Local-First

Correct:

- Default state lives under local `data/`.
- No required cloud service exists in the runtime path.
- Model routing defaults to local Ollama-compatible configuration.
- Docker Compose mounts `./data:/data` and keeps local state outside the container image.

Fragile:

- `web_search` is registered as a tool but intentionally returns `unconfigured`. This is acceptable for now, but it should stay disabled or provider-configured explicitly.
- `FastAPI`, `uvicorn`, `pydantic`, and `pyyaml` are required runtime dependencies even when testing core behavior. This is not excessive, but the API dependency is already visible in tests through a Starlette TestClient deprecation warning.

Missing:

- No local service supervisor, queue, scheduler, or long-running worker yet.
- No backup/export/import policy for `DATA_DIR`.

### Permission-First

Correct:

- `ToolRegistry.execute()` checks `PermissionManager.require()` before calling any tool implementation.
- Mutating runtime services such as task creation/update, memory append, and agent messaging also call `PermissionManager.require()` directly.
- Permission decisions are emitted to the event log.
- Path access goes through `DataDir.resolve()`, which blocks escaping `DATA_DIR`.

Fragile:

- Permission config is loaded once at runtime startup. Changes to `data/config/permissions.yaml` require recreating the runtime.
- Device permissions exist only as directory shape, not as enforced policy.
- There is no authentication. `x-actor-id` headers are trusted as identity.
- `PermissionContext.autonomy` exists but is not enforced.

Missing:

- No distinction yet between skill, permission, and autonomy beyond data fields.
- No deny rules, scoped resource grants, or approval workflow.
- No audit correlation ID tying permission decisions to a user request/task/tool call.

### Runtime-First

Correct:

- `RuntimeContainer` composes Core, Memory, Agents, Tasks, Tools, Model Router, Event Bus, and Permission Manager.
- FastAPI obtains `request.app.state.runtime` and delegates to runtime services.
- No UI code owns runtime behavior.

Fragile:

- API routes sometimes call services directly (`runtime.tasks.create_task`, `runtime.communication.send_agent_message`) instead of consistently using a command/application service layer. This is still runtime-owned logic, but the API already knows too much about service topology.
- `RuntimeContainer` is a simple composition root. There is no lifecycle management for background workers, shutdown, or health of subsystems.

Missing:

- No command bus or runtime application service boundary for future UI, scheduler, mobile, and remote clients.
- No background runtime yet.

### Memory-First

Correct:

- Global memory files are `data/memory/USER.md`, `MEMORY.md`, and `SYSTEM.md`.
- Agent memory files are under `data/agents/<agent_id>/MEMORY.md`.
- `MemoryStore` reads and appends the same files that a future Brain UI would display.
- Chat history is not used as memory.

Fragile:

- There is no formal Context Loader. Current tests verify `MemoryStore` reads the correct files, but model/agent context composition is not a named component yet.
- Memory appends are raw markdown writes with no record schema, provenance, conflict handling, or compaction policy.

Missing:

- No memory retrieval policy.
- No distinction between facts, preferences, summaries, task memory, project memory, and episodic memory.
- No migration/versioning strategy for memory files.

### Agent-First

Correct:

- Agents are persistent directories with `SOUL.md`, `MEMORY.md`, `SKILLS.md`, `CONFIG.yaml`, and `INBOX.md`.
- `AgentRegistry` lists and loads agents from `DATA_DIR`.
- Agent-to-agent messaging writes to the target agent inbox and emits an event.

Fragile:

- Agents are still mostly static records. There is no execution loop, planner, model invocation, tool selection, or autonomy enforcement.
- Agent skills and permissions are stored in config, but runtime permission enforcement still comes from global `permissions.yaml`, not from the agent config.

Missing:

- No agent runtime execution state beyond basic presence store.
- No inbox processing.
- No agent outbox, conversation thread, acknowledgement, retry, or delivery status.

### Homelab-Ready

Correct:

- Dockerfile and Compose are simple and do not complicate local development.
- API binds to configurable host/port.
- `DATA_DIR` is volume-mounted in Docker Compose.
- Event log and persistent task files are useful foundations for Mission Control and continuous operation.

Fragile:

- No auth, TLS, reverse proxy guidance, VPN/tunnel assumptions, or remote gateway boundary.
- No process health beyond `/api/health`.
- No structured logging outside JSONL runtime events.

Missing:

- No scheduler, queue, watcher, notification system, or service supervision.
- No device registry enforcement.
- No backup/restore procedure.

## Specific Findings

### 1. DATA_DIR as Single Source of Persistence

Mostly correct.

Runtime persistence goes to `data/`:

- config: `data/config`
- memory: `data/memory`
- agents: `data/agents`
- tasks: `data/tasks`
- events/presence: `data/logs`

Fragility: `ConfigStore`, `EventBus`, and `PermissionManager` accept raw `Path` roots instead of `DataDir`. They still point inside `DATA_DIR`, but this weakens the "single persistence gateway" invariant. Future services should prefer receiving `DataDir` or a narrow storage interface.

### 2. Brain/Runtime Memory Files

Partially correct.

Runtime uses the exact markdown files specified for global and agent memory. There is no Brain UI yet, so shared Brain/Runtime behavior cannot be fully proven. The correct next step is to make Brain read through the same `MemoryStore` or a dedicated `ContextLoader`, not by implementing a separate file reader.

### 3. Tool File Access and Permission Manager

Correct at the execution boundary.

All registered tools are invoked through `ToolRegistry.execute()`, which checks permissions before `tool.run()`. File tools then resolve paths through `DataDir.resolve()`.

Fragility: Direct construction and calling of tool instances could bypass `ToolRegistry`. That is not used today, but should be prevented later by convention, tests, or by making the registry the only exposed executor.

### 4. Core Components Decoupling

Partially correct.

- `ModelRouter` is decoupled from agents, permissions, and tools.
- `AgentRegistry` depends only on `DataDir`.
- `EventBus` is simple and independent.
- `PermissionManager` depends on `EventBus` to audit decisions.

Fragility: `RuntimeContainer` wires concrete classes directly. This is fine for the current size, but future background/runtime plugins should depend on protocols or narrow interfaces.

### 5. Agent-to-Agent Reality

Partially correct.

Agent-to-agent communication is real in that it persists a message into `INBOX.md` and emits `agent.message.sent`. It is not merely an in-memory mock.

Missing: there is no message state, delivery state, read state, retry, or processing loop. It does not yet model a real mailbox lifecycle.

### 6. `send_agent_message`: Message, Event, Log, State

Partially correct.

Generated:

- message object: yes
- persisted message: yes, appended to `INBOX.md`
- event/log: yes, via `EventBus` JSONL event
- state: no durable message state beyond the inbox entry

Recommendation: before building UI, add a message ledger under `data/agents/<agent_id>/messages/` or `data/logs/messages.jsonl`, with delivery/read status. Keep `INBOX.md` as human-readable projection if desired.

### 7. Task System

Correct for the foundation.

Tasks are created under `data/tasks/active`, updates can move them to `completed` or `failed`, and events are emitted. Tests now verify file persistence and movement between status directories.

Fragile:

- Updates delete the old file and then write the new one without atomic replacement. A crash could lose a task.
- No task event history file exists beyond global events and metadata notes.

### 8. FastAPI as Runtime Client

Mostly correct.

FastAPI delegates to `runtime` from `app.state`. It does not duplicate task or message persistence logic.

Fragility: API routes know concrete service names. A runtime application service or command bus should be introduced before more clients are added.

### 9. Dependencies

Mostly appropriate.

Runtime dependencies are modest: FastAPI, Pydantic, PyYAML, Uvicorn. No agent framework, vector database, frontend framework, LangGraph, or LLM SDK was added prematurely.

Fragility: PyYAML is used only through a fallback loader; config files currently contain JSON in `.yaml` files. Prefer real YAML or rename them later.

### 10. Docker

Correct.

Docker was added without complicating local flow. Compose keeps state in `./data`, exposes only the API port, and uses `restart: unless-stopped`, which is appropriate for early homelab readiness.

Missing: no healthcheck, non-root user, or production hardening yet.

### 11. Tests

Improved.

The original tests covered real behavior but were broad. The current tests cover:

- permission denial for unauthorized tool execution
- `read_file` blocking relative and absolute escapes outside `DATA_DIR`
- `send_agent_message` persisting inbox content and emitting event
- `create_task` persisting task file and emitting event
- task status update moving files between directories
- `MemoryStore` reading global and agent memory from `DATA_DIR`
- FastAPI task endpoint delegating to runtime instead of duplicating logic

Remaining gaps:

- No API auth tests because auth does not exist.
- No device permission tests because device policy does not exist.
- No autonomy tests because autonomy is not enforced.

### 12. Future Runtime Risks

Voice:

- Risk: implementing STT/TTS in UI would violate runtime-first. Add a `VoiceRuntime` service boundary before UI voice controls.

Avatar:

- Risk: avatar logic could become agent logic. Keep avatar as projection of agent state and events only.

Perception:

- Risk: agents accessing cameras/sensors directly. Hardware access must go through `PerceptionRuntime`, emit events, and require device/resource permissions.

Communication:

- Risk: email/chat integrations sending messages without approval. Draft/send permissions must be separate.

Remote Access:

- Risk: trusting `x-actor-id` over network. Add auth/session/device registry before exposing beyond localhost or VPN.

## Priority Recommendations

1. Add a runtime command/application service boundary so API, UI, scheduler, and mobile call the same runtime commands.
2. Add a formal `ContextLoader` that composes `USER.md`, `SYSTEM.md`, global memory, agent `SOUL.md`, agent `MEMORY.md`, skills, and task/project context from the same `DATA_DIR` files.
3. Extend agent messaging with durable message state, not just `INBOX.md` projection.
4. Enforce device identity, actor authentication, and session authorization before remote access work.
5. Connect agent `CONFIG.yaml` permissions/autonomy to `PermissionManager` instead of duplicating permission facts in two places.
6. Add atomic writes for tasks, memory appends, presence, and future message ledgers.
7. Define explicit runtime interfaces for Voice, Avatar, Perception, Communication, and Remote Access before implementing them.
8. Add a healthcheck to Docker Compose after the API health endpoint stabilizes.

## Next Steps Before UI or New Features

1. Introduce `ContextLoader` and tests for exact memory/context composition.
2. Introduce a `RuntimeCommands` or application service layer and move API endpoints to it.
3. Define message state storage for agent-to-agent communication.
4. Add auth/session/device enforcement for all API requests, even if the first provider is local-only.
5. Normalize config format: real YAML or JSON file extension.
6. Add crash-safe writes for task and state files.
7. Add tests for permission reload behavior, device denial, autonomy denial, and API auth once those policies exist.

