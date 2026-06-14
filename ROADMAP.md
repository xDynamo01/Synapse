# Synapse V2 Roadmap

This roadmap tracks technical phases only. Product UI, voice, avatar, perception, and communication features should not start until their runtime boundaries are ready.

## 1. Core Foundation

Status: complete.

- `DATA_DIR` bootstrap.
- Core configuration.
- Event bus.
- Permission manager.
- Agent registry.
- Model router placeholder.
- Tool registry.
- Task runtime.
- FastAPI adapter.

## 2. Foundation Hardening

Status: complete.

- Structured `ContextLoader`.
- Agent Identity Runtime / SOUL Runtime.
- Effective Agent Policy.
- Structured agent-to-agent messages.
- Human-readable `INBOX.md` projection.
- Initial device registry.
- Tests for permission, persistence, context loading, and command behavior.

## 3. Runtime Commands

Status: complete foundation, integrated with Chat Runtime.

- Slash command parser.
- Runtime-backed `/call`, `/task`, `/remember`, `/search`.
- Runtime-backed `/agent <id>` and `/agents detail`.
- Runtime-backed `/policy <agent_id>`.
- No duplicated command business logic in UI.

## 3A. Agent Identity Runtime

Status: complete foundation.

- Structured `AgentIdentity`.
- SOUL/CONFIG/SKILLS loading and validation.
- Identity exposed to `ContextLoader`.
- Agent Runtime respects `preferred_tools` and blocks `forbidden_tools`.
- Base agents: Artemis, Researcher, Atlas, Hermes, Vigil.

Pending:

- Rich identity editing workflow.
- Schema versioning for agent configs.
- Runtime validation for autonomy profiles beyond manual mode.
- Identity migration tooling.

## 3B. Effective Agent Policy

Status: complete foundation.

- `AgentEffectivePolicy` combines global permissions, agent `CONFIG.yaml`, `AgentIdentity`, approval policy, and optional device context.
- Explicit forbids and global denies win over agent allows.
- Preferred tools are exposed as preference only; they do not grant permission.
- `AgentRuntime`, `ToolRouter`, `ContextLoader`, `ApprovalResumeRuntime`, and `CommandRuntime` use the resolved policy.
- `/policy <agent_id>` exposes structured policy for inspection.

Pending:

- Resource-scoped policy rules.
- Policy schema versioning and migration.
- Rich policy audit/correlation records beyond existing events.
- UI/mobile inspection and approval surfaces.

## 4. Model Integration

Status: partial foundation complete.

- Mock provider adapter for deterministic tests.
- Ollama provider adapter with simple `/api/chat` support.
- OpenAI-compatible adapter boundary prepared.
- Model route selection per agent.
- Streaming response contract: pending.
- Model errors and retry policy: pending.

## 5. Tool Expansion

Status: partial foundation complete.

- Controlled tool-call contracts.
- Agent Runtime -> Effective Policy -> Tool Router -> Permission Manager -> ToolRegistry flow.
- Initial tool-call support for `read_file`, `list_directory`, `create_task`, and `send_agent_message`.
- Tool-call events for requested, permission checked, executed, and failed.
- Human Approval Gate for high/critical risk tools.
- Persisted approval requests.
- Approval commands `/approvals`, `/approve`, and `/reject`.
- Device-aware approval validation.
- Approval resume flow after approval.
- Approval API endpoints for pending, approve, and reject.
- Agent Worker inbox processing.
- Worker commands `/inbox`, `/process-inbox`, and `/worker-status`.
- Worker API endpoints for inbox processing and status.
- Local-first scheduler queue under `jobs/`.
- Scheduler commands `/jobs`, `/enqueue-inbox`, `/run-jobs`, and `/cancel-job`.
- Scheduler API endpoints for enqueue, list, run, and cancel.
- Initial Synapse Daemon / Background Runner.
- Daemon commands `/daemon-status` and `/daemon-run-once`.
- Daemon API endpoints for status and deterministic single-cycle execution.

Pending:

- Resource-scoped filesystem permissions.
- OpenAPI/MCP bridge adapters.
- Tool execution audit correlation beyond event type.
- Rich approval UI/mobile workflow and notifications.
- Sandbox strategy for risky tools.
- Multi-step tool planning and model follow-up after tool observations.
- Session message update after resumed tool execution.

## 5B. Agent Worker / Inbox Processing

Status: complete foundation.

- Runtime-owned pending inbox processing.
- Message status flow: `pending -> read -> processed` or `failed`.
- Worker uses `ContextLoader`, `AgentRuntime`, `EffectivePolicyRuntime`, and `AgentCommunication`.
- Optional replies are controlled by effective policy and delegation rules.
- Worker events for inbox checks, start, processed, and failed.

Pending:

- Background scheduler/queue.
- Backoff retry policy.
- Thread/conversation IDs for request-response chains.
- Worker concurrency controls.
- Rich worker observability and correlation IDs.

## 5C. Background Scheduler / Queue

Status: complete foundation.

- Persistent job model under `DATA_DIR/jobs`.
- Job lifecycle: `pending`, `running`, `completed`, `failed`, `cancelled`.
- Runtime operations for enqueue, list, get, cancel, run next, run all pending, and retry failed.
- Initial `process_agent_inbox` job type integrated with `AgentWorker`.
- Job events for enqueued, started, completed, failed, cancelled, and retried.

Pending:

- Always-on homelab runner process.
- Backoff and scheduled retry policy.
- Concurrent worker locks.
- Job dependency/chaining model.
- Retention/cleanup policy for old jobs.

## 5D. Synapse Daemon / Background Runner

Status: complete foundation.

- `DaemonRunner` with deterministic `run_once()`.
- Basic `start_loop(interval_seconds)` boundary for future CLI/service use.
- Persisted daemon status under `daemon/status.yaml`.
- Daemon events for tick and controlled errors.
- Commands and API for status and run-once.

Pending:

- Production CLI/service wrapper.
- Process supervision/systemd/Windows service integration.
- Graceful shutdown across process boundaries.
- Locking when multiple daemon instances target the same `DATA_DIR`.

## 5A. Chat Runtime

Status: complete foundation.

- Runtime-owned user-to-agent turn flow.
- ContextLoader integration.
- AgentRuntime integration.
- Session persistence under `chats/sessions`.
- Slash command delegation.
- Chat events.

Pending:

- Chat session API hardening.
- Streaming.
- Message attachments.
- Tool calling loop.

## 6. Communication Runtime

Status: pending.

- Email and chat integration boundary.
- Draft vs send permission separation.
- Message ingestion events.
- Agent review workflow.

## 7. Presence Runtime

Status: pending.

- Durable agent presence state.
- Activity transitions.
- Mission Control event feed contract.
- Background runtime status.

## 8. Voice Runtime

Status: pending.

- STT/TTS abstraction.
- Wake word boundary.
- Audio routing.
- Voice input mapped to runtime commands.

## 9. Avatar Runtime

Status: pending.

- Avatar state projection from agent events.
- Expression and animation state.
- Lip sync boundary.
- No agent logic inside avatar layer.

## 10. Perception Runtime

Status: pending.

- Camera/sensor registry.
- Hardware access through runtime only.
- Perception events for agents.
- Device/resource permission checks.

## 11. API Hardening

Status: pending.

- Local auth/session layer.
- Device-aware authorization.
- Remote-safe headers and audit trail.
- Rate limits and request correlation IDs.
- Health checks.

## 12. Desktop UI

Status: pending.

- Runtime client only.
- Chat/command surface.
- Agents, Brain, Mission Control, Library, Models.
- Persistent docking/split layouts.

## 13. Mobile Companion

Status: pending.

- Notifications.
- Approval flows.
- Agent chat.
- Briefings.
- Task and event monitoring.

## 14. Homelab Mode

Status: foundation in progress.

- Background worker: foundation complete.
- Scheduler/queue: foundation complete.
- Daemon runner: foundation complete.
- Watchers.
- Backup/restore.
- VPN/tunnel deployment guidance.
