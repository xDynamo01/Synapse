# Synapse V2

Synapse is a local-first personal agent operating system. This repository starts with the runtime foundation: Core, Memory, Context Loader, Agent Runtime, Task Runtime, Tool System, Command Runtime, Permission Manager, Event Bus, Device Registry, and a FastAPI API layer.

## Principles

- Local first: the default `DATA_DIR` is local and no critical path depends on cloud services.
- Agent first: agents are persistent entities, not chat sessions.
- Runtime first: tools and state exist in the runtime before any UI uses them.
- Memory first: markdown memory files are persistent and separate from chat history.
- Permission first: every tool call passes through `PermissionManager`.
- Homelab ready: runtime state, logs, API, and future gateway boundaries are explicit.

## Layout

```text
backend/synapse/      Python runtime and API
data/                 Local DATA_DIR bootstrap
docs/                 Architecture notes and reference study
tests/                Core/runtime tests
```

## Quickstart

```powershell
cd E:\Projetos\Synapse
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m uvicorn synapse.main:app --reload --host 127.0.0.1 --port 8717
```

Then open `http://127.0.0.1:8717/docs`.

Run tests without installing runtime web dependencies:

```powershell
py -m unittest discover -s tests
```

## Current Scope

Implemented foundation:

- `DATA_DIR` bootstrap with config, memory, agents, tasks, logs, library, chats, and devices.
- Permission-gated tools: `read_file`, `write_file`, `list_directory`, `search_files`, `web_search`, `send_agent_message`, `create_task`, `update_task`.
- Persistent event log in `data/logs/events.jsonl`.
- Persistent task files under `data/tasks`.
- Persistent agent files under `data/agents/<agent_id>`.
- Structured agent-to-agent message records under `data/agents/<agent_id>/messages`.
- `ContextLoader` with ordered, typed context sections for memory, identity, project, tasks, and session history.
- `CommandRuntime` for slash commands over existing runtime services and tools.
- Initial `DeviceRegistry` for trusted, untrusted, and revoked devices.
- FastAPI endpoints over the runtime.

Not implemented yet:

- LLM execution and model routing beyond configuration shape.
- RAG indexing/vector storage.
- Desktop UI/Tauri.
- Voice, avatar, perception, communication integrations, remote gateway, and mobile companion.
- Full login/session handling and device permission enforcement.
