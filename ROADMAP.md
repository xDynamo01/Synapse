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
- Correlation ID and event envelope hardening.
- Trace command/API for correlated runtime flows.
- Durable correlation metadata on tasks, messages, approvals, jobs, and chat sessions.
- Durable Presence Runtime for agent state projection.
- Presence commands `/presence` and `/presence <agent_id>`.
- Presence API endpoints.
- Durable Agent Lifecycle Runtime.
- Lifecycle commands `/lifecycle`, `/wake`, and `/sleep`.
- Lifecycle API endpoints.
- Communication Runtime V1 for mock email read/classify/summarize/draft.
- Communication tools, commands, API, scheduler job, and Hermes briefing.
- Notification Runtime with local provider, event integration, commands, and API.

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

## 5E. Correlation ID / Observability

Status: complete foundation.

- `CorrelationContext` based on context-local runtime scope.
- Event JSONL envelope includes `correlation_id`, `causation_id`, `parent_id`, and `source`.
- Chat, tool calls, approvals, jobs, daemon cycles, and worker flows are traceable through events.
- Durable records persist optional correlation metadata.
- Backward-compatible loading for legacy events without correlation fields.
- `/trace <correlation_id>` command and `GET /trace/{correlation_id}` API.

Pending:

- Full causation chain modeling between individual events.
- Structured trace summaries and timeline views.
- External observability exporters.

## 5F. Presence Runtime

Status: complete foundation.

- Durable agent presence records under `DATA_DIR/presence`.
- Runtime-owned states: `idle`, `listening`, `thinking`, `speaking`, `researching`, `working`, `waiting_approval`, `offline`, and `error`.
- Presence updates from Chat Runtime, Agent Runtime, approval/tool flow, AgentWorker, and SchedulerRuntime agent jobs.
- `presence.updated` events include correlation metadata when available.
- Commands `/presence` and `/presence <agent_id>`.
- API endpoints `GET /presence` and `GET /presence/{agent_id}`.

Pending:

- Historical presence timeline.
- Concurrent activity slots per agent.
- Rich emotion/avatar state mapping.
- Cross-process locking for homelab multi-runner scenarios.

## 5G. Agent Lifecycle Runtime

Status: complete foundation.

- Durable lifecycle records under `DATA_DIR/lifecycle`.
- Operational states: `offline`, `booting`, `idle`, `waking`, `working`, `waiting`, `sleeping`, `error`, and `shutdown`.
- Lifecycle counters for boot, wake, sleep, and error transitions.
- Presence integration for boot, wake, sleep, shutdown, and error.
- AgentWorker wakes agents with pending inbox work and returns them to idle.
- Scheduler wakes agents for `process_agent_inbox` jobs.
- Commands `/lifecycle`, `/lifecycle <agent_id>`, `/wake <agent_id>`, and `/sleep <agent_id>`.
- API endpoints for lifecycle list/detail/wake/sleep.

Pending:

- Explicit boot orchestration during daemon startup.
- Lifecycle transition guards/state machine validation.
- Historical lifecycle timeline.
- Cross-process locks for homelab multi-runner mode.

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

Status: complete V1 foundation.

- Runtime-owned email boundary.
- Offline `MockCommunicationProvider`.
- Prepared `GmailCommunicationProvider` boundary.
- Email classification categories: recruitment, project, personal, newsletter, system, unknown.
- Email summary and Hermes briefing generation.
- Draft creation and draft listing.
- Tools: `read_email`, `summarize_email`, `create_email_draft`, `list_email_drafts`.
- Commands: `/check-email`, `/email-summary`, `/email-drafts`, `/email-read <id>`.
- API: `/communication/messages`, `/communication/drafts`, `/communication/summary`.
- Scheduler job type `check_email`.
- Daemon can execute `check_email` through scheduler.
- Presence and lifecycle integration for Hermes.

Pending:

- Real Gmail OAuth/token storage.
- Real provider sync state and pagination.
- Send-email runtime with critical approval gate.
- Human review workflow for draft approval.
- Provider-specific rate limits and retries.
- Communication threads/conversations persistence beyond drafts.

## 6A. Notification Runtime

Status: complete foundation.

- Local-first `NotificationRuntime`.
- `LocalNotificationProvider` persists notifications under `DATA_DIR/notifications`.
- `ConsoleNotificationProvider` prepared for debug output.
- Notification severities: info, success, warning, critical.
- Notification categories: approval, communication, agent, scheduler, daemon, system, task, security, unknown.
- Event integration for approvals, communication briefings, job failures, daemon errors, agent errors, tool failures, and worker failures.
- Commands: `/notifications`, `/notifications unread`, `/read-notification <id>`.
- API: list, unread, detail, mark read, delete.
- Correlation metadata preserved on notifications.

Pending:

- Notification cleanup job execution.
- Notification retention policy.
- Real push/mobile/desktop providers.
- User preferences and routing rules.
- Deduplication and rate limiting.

## 7. Presence Runtime

Status: complete foundation.

- Durable agent presence state.
- Activity transitions.
- Runtime event feed through `presence.updated`.
- Background worker/scheduler presence integration.

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
