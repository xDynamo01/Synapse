# Synapse V2 Project State for New Chat

Date: 2026-06-19

Workspace: `E:\Projetos\Synapse`

## Executive Summary

Synapse V2 has a substantial local-first backend foundation implemented and covered by tests. The current committed baseline is behind the working tree: the last commit is `8196eb1 feat: add scheduler recurring jobs`, while several later stages are implemented but not committed.

Current state is backend-only. No UI, Voice, Avatar, Mobile, or Perception runtime has been started.

The implemented backend now includes agent identity, memory/context loading, chat/model flow, controlled tool calling, approvals and approval resume, worker/scheduler/daemon foundation, correlation observability, presence/lifecycle, communication/draft approval, outbound send authorization policy, notifications/cleanup, runner identity/heartbeat, scheduler locking, and homelab health summary.

## Git State

- Branch: `main`
- Last commit: `8196eb1 feat: add scheduler recurring jobs`
- Working tree: dirty

Modified tracked files:

- `ROADMAP.md`
- `backend/synapse/api/routes.py`
- `backend/synapse/commands/runtime.py`
- `backend/synapse/communication/__init__.py`
- `backend/synapse/communication/gmail_provider.py`
- `backend/synapse/communication/mock_provider.py`
- `backend/synapse/communication/models.py`
- `backend/synapse/communication/provider.py`
- `backend/synapse/communication/runtime.py`
- `backend/synapse/core/app.py`
- `backend/synapse/core/data_dir.py`
- `backend/synapse/core/events.py`
- `backend/synapse/daemon/runner.py`
- `backend/synapse/notifications/runtime.py`
- `backend/synapse/scheduler/runtime.py`
- `backend/synapse/tools/builtin.py`
- `docs/adr/0017-communication-runtime.md`
- `docs/architecture.md`
- `docs/validation/runtime-walkthrough.md`
- `tests/test_communication_runtime.py`

Untracked files/directories:

- `backend/synapse/communication/outbound.py`
- `backend/synapse/daemon/identity.py`
- `backend/synapse/health/`
- `backend/synapse/scheduler/lock.py`
- `docs/adr/0021-scheduler-locking-single-runner.md`
- `docs/adr/0022-runner-identity-heartbeat.md`
- `docs/adr/0023-homelab-health-summary.md`
- `docs/adr/0024-communication-draft-approval-flow.md`
- `docs/adr/0025-outbound-communication-policy.md`
- `docs/audits/agent-agnostic-audit.md`
- `docs/audits/project-state-for-new-chat.md`
- `tests/test_draft_approval_flow.py`
- `tests/test_health_runtime.py`
- `tests/test_outbound_communication.py`
- `tests/test_runner_identity.py`
- `tests/test_scheduler_lock.py`

Implemented stages still without commit:

- Scheduler Locking / Single Runner Guard
- Runner Identity / Heartbeat
- Homelab Health Summary
- Communication Draft Approval Flow
- Agent-agnostic communication default fix
- Outbound Communication Policy

There may also be uncommitted tracked changes from the Notification Runtime and Communication Runtime stages because the repository was already dirty before the latest work.

## Test State

Commands executed:

```powershell
py -m unittest discover -s tests
py -m ruff check .
```

Results:

- Unit tests: `Ran 219 tests in 34.806s`, `OK`
- Ruff: `All checks passed!`

Known warning:

- FastAPI/Starlette emits `StarletteDeprecationWarning: Using httpx with starlette.testclient is deprecated; install httpx2 instead.` This warning does not fail the suite.

## Implemented Architecture

### Core

- Runtime container in `backend/synapse/core/app.py`.
- Central bootstrapping of DataDir, ConfigStore, EventBus, PermissionManager, agents, memory, tasks, tools, policies, chat, API-facing runtimes, scheduler, daemon, health, and command runtime.
- Local-first structured file helpers in `core/serialization.py`.

### DATA_DIR

- `DATA_DIR` is the persistence root.
- Bootstraps required directories for config, memory, agents, projects, tasks, approvals, jobs, scheduler recurring state, daemon, presence, lifecycle, communication drafts/outbound, notifications, locks, logs, library, chats, and device records.
- Seeds base agents and policies.

### Config System

- `config/system.yaml`
- `config/permissions.yaml`
- `config/approval_policy.yaml`
- `config/notification_policy.yaml`
- `config/scheduler_policy.yaml`
- `config/communication_policy.yaml`
- `config/outbound_communication_policy.yaml`

### Memory System

- Global memory files under `memory/`.
- Agent memory under `agents/{agent}/MEMORY.md`.
- Chat history is persisted separately and is not memory.

### Context Loader

- Loads structured context in ordered sections: system memory, user memory, global memory, agent identity/soul/memory/skills, project context, relevant tasks, and session history.
- History is explicitly separated from memory.
- Includes `agent_identity` and effective policy in context.

### Chat Runtime

- `backend/synapse/chat/runtime.py`
- Flow: user message -> ContextLoader -> AgentRuntime -> ModelRouter/Adapter -> response -> session persistence.
- Persists sessions under `chats/sessions/`.
- Emits chat events.
- Routes slash commands through CommandRuntime.

### Agent Runtime

- Uses AgentIdentity and AgentEffectivePolicy.
- Calls ModelRouter.
- Detects structured tool calls.
- Blocks forbidden tools before ToolRouter.
- Keeps tool execution through ToolRouter/PermissionManager/ApprovalManager.

### Model Router

- Supports mock deterministic model adapter.
- Prepared adapter boundaries for Ollama and OpenAI-compatible providers.
- Chooses model based on agent config where available.

### Tool Calling

- Structured tool contracts exist: `ToolCallRequest`, `ToolCallResult`, and related routing.
- Supported tools include file read/list/write/search, task creation/update, agent messages, web search mock/unconfigured, email read/summarize/draft/list drafts.
- Tool execution is permission-gated and approval-gated where relevant.

### Permission Manager

- Central permission checks.
- Tools and mutating runtimes use PermissionContext.
- Filesystem tools resolve paths through DATA_DIR.

### Effective Agent Policy

- `backend/synapse/policies/effective.py`
- Combines global permissions, agent CONFIG.yaml, AgentIdentity, Approval Policy, and device constraints.
- Produces `AgentEffectivePolicy`.
- Used by AgentRuntime, ToolRouter, ContextLoader, and policy commands.

### Approval System

- Persistent ApprovalRequest records under `approvals/`.
- Risk levels: low, medium, high, critical.
- Approval policy controls required risk levels, bypass agents, device permissions, and expiration.
- Approve/reject/expire/list/get status functions.

### Approval Resume Flow

- Approved tool calls can resume execution without user resending the call.
- Resume revalidates permissions/policy before executing.
- Prevents double execution after resumed.

### Agent Identity Runtime

- `backend/synapse/agents/identity.py`
- Loads SOUL.md, CONFIG.yaml, SKILLS.md.
- Produces structured AgentIdentity with role, focus areas, preferred/forbidden tools, default model, autonomy, communication style, and operational rules.

### Agent-to-Agent

- Structured messages persisted under `agents/{agent}/messages/`.
- Human-readable `INBOX.md` maintained.
- Message statuses include pending/read/processed/failed.
- Functions exist for send, list, mark read/processed/failed.
- Emits message events.

### Agent Worker

- Processes pending inbox messages for an agent.
- Marks read, builds context, calls AgentRuntime, optionally replies, marks processed/failed.
- Respects effective policy and delegation constraints.
- Integrated with presence and lifecycle.

### Scheduler

- Local-first job queue under `jobs/`.
- Job model supports pending/running/completed/failed/cancelled, priority, attempts, schedule time, timestamps, correlation metadata.
- Supports enqueue, list, get, cancel, run_next, run_all_pending, retry_failed.
- Job types include `process_agent_inbox`, `check_email`, and `notification_cleanup`.

### Recurring Jobs

- Recurring policy in `config/scheduler_policy.yaml`.
- Supports `interval_minutes`, `last_run_at`, `next_run_at`, enabled flag, priority, max attempts.
- Supported recurring job types: `notification_cleanup`, `check_email`, `process_agent_inbox`.
- Commands/API can list and run due recurring jobs.

### Scheduler Locking

- Local lock file under `locks/scheduler.lock`.
- `SchedulerLock` supports owner id, acquire/release/is_locked, stale detection/recovery.
- Scheduler queue execution and recurring enqueue paths acquire the lock.
- No distributed lock.

### Daemon

- `DaemonRunner` supports deterministic `run_once()`, `start_loop(interval_seconds)`, `stop()`, and status.
- Persists status under `daemon/status.yaml`.
- Ticks run recurring enqueue then pending jobs.
- Emits daemon events.

### Runner Identity / Heartbeat

- `RunnerIdentityStore` persists stable runner identity in `daemon/runner.yaml`.
- Fields include runner id, hostname, process id, created/last seen, role, and status.
- Daemon updates heartbeat.
- Scheduler lock uses stable runner id as owner id.

### Observability / Correlation

- CorrelationContext implemented.
- Event envelopes include id, type, timestamp, correlation id, causation id, parent id, source, and payload.
- `/trace` command and `GET /trace/{id}` exist.
- Event log is JSONL under `logs/events.jsonl`.

### Durable Correlation Fields

- Tasks, agent messages, approvals, jobs, chat session messages, notifications, communication drafts, and outbound send requests carry correlation metadata where relevant.
- Trace records include durable records in addition to events.

### Presence Runtime

- Persists current agent presence under `presence/{agent_id}.yaml`.
- States include idle/listening/thinking/speaking/researching/working/waiting_approval/offline/error.
- Integrated with chat, agent runtime, approval flow, worker, scheduler agent jobs.

### Lifecycle Runtime

- Persists lifecycle state under `lifecycle/{agent_id}.yaml`.
- States include offline/booting/idle/waking/working/waiting/sleeping/error/shutdown.
- Tracks transition counts and errors.
- Integrated with presence, worker, scheduler.

### Communication Runtime

- Offline deterministic MockCommunicationProvider.
- Prepared Gmail provider boundary that is not configured.
- Supports listing/reading mock messages, classification, summaries, briefings, draft creation/list/get/update, and draft approval.
- Requires explicit communication `agent_id` or `communication.default_agent_id` from `config/communication_policy.yaml`.
- Default policy is null; no implicit Hermes default remains.

### Draft Approval Flow

- Draft states: draft, awaiting_approval, approved, rejected, cancelled, sent_future.
- `create_draft(..., requires_approval=True)` creates a draft and ApprovalRequest, links `approval_id`, and sets draft to awaiting_approval.
- Approve/reject draft uses ApprovalManager and updates draft status.
- No email send occurs.

### Outbound Communication Policy

- Implemented as `backend/synapse/communication/outbound.py`.
- Policy in `config/outbound_communication_policy.yaml`.
- Separates:
  - draft approved
  - send authorized
  - sent future
- `OutboundSendRequest` statuses: pending_authorization, authorized, rejected, cancelled, sent_future.
- Approved draft -> request_send_draft -> OutboundSendRequest -> ApprovalRequest critical -> authorized/rejected.
- No real send_email exists.

### Notification Runtime

- Local notification provider persists under `notifications/`.
- Event-driven notification creation for approvals, communication briefings, draft approval, send authorization, job failures, daemon errors, agent errors, tool failures, worker failures.
- Commands/API for list, unread, detail, mark read, delete.

### Notification Retention / Cleanup

- Policy in `config/notification_policy.yaml`.
- Cleanup deletes old read notifications and enforces max total while preserving unread/critical by default.
- Runnable by runtime, command, API, scheduler job, daemon cycle.

### Homelab Health Summary

- `backend/synapse/health/`
- Aggregates runner, daemon, scheduler lock, pending/failed jobs, due recurring jobs, unread critical notifications, agents in error/offline, pending approvals.
- Command `/health`.
- API `GET /health`.

### API Endpoints

Implemented API includes:

- Health: `GET /health`
- Agents/workers: `GET /agents`, `GET /agents/{agent}/inbox`, `POST /agents/{agent}/process-inbox`, `GET /workers/status`
- Presence/lifecycle: `GET /presence`, `GET /presence/{agent}`, `GET /lifecycle`, `GET /lifecycle/{agent}`, wake/sleep endpoints
- Communication: messages, drafts, draft approve/reject, request-send, outbound list/approve/reject, summary
- Notifications: list/unread/detail/read/delete/cleanup
- Daemon/runner: status, run-once, runner, heartbeat
- Events/trace
- Jobs/scheduler recurring/scheduler lock
- Tasks/tools/approvals
- Agent messages
- Chat: `POST /chat`

### Commands

Implemented slash commands include:

- `/help`, `/agents`, `/agent`, `/policy`
- `/tasks`, `/memory`, `/call`, `/task`, `/remember`, `/search`
- `/approvals`, `/approve`, `/reject`
- `/inbox`, `/process-inbox`, `/worker-status`
- `/jobs`, `/enqueue-inbox`, `/run-jobs`, `/cancel-job`
- `/daemon-status`, `/daemon-run-once`
- `/trace`
- `/presence`
- `/lifecycle`, `/wake`, `/sleep`
- `/check-email --agent <agent_id>`, `/email-summary --agent <agent_id>`, `/email-drafts`, `/email-read`
- `/drafts`, `/draft <id>`, `/approve-draft <id>`, `/reject-draft <id>`
- `/send-draft-request <draft_id>`, `/outbound-requests`, `/approve-send <request_id>`, `/reject-send <request_id>`
- `/notifications`, `/read-notification`
- `/recurring-jobs`, `/run-recurring`
- `/scheduler-lock`
- `/runner-status`, `/runner-heartbeat`
- `/health`

### ADRs

ADRs present:

- 0001 local-first DATA_DIR
- 0002 memory-first chat history is not memory
- 0003 permission-first tools through Permission Manager
- 0004 runtime-first UI is client
- 0005 structured agent messages and human inbox
- 0006 autonomy/skill/permission separation
- 0007 remote/homelab-ready foundation
- 0008 human approval gate
- 0009 agent identity runtime
- 0010 effective agent policy
- 0011 agent worker inbox processing
- 0012 background scheduler queue
- 0013 daemon background runner
- 0014 correlation observability
- 0015 presence runtime
- 0016 lifecycle runtime
- 0017 communication runtime
- 0018 notification runtime
- 0019 notification retention cleanup
- 0020 scheduler recurring jobs
- 0021 scheduler locking single runner
- 0022 runner identity heartbeat
- 0023 homelab health summary
- 0024 communication draft approval flow
- 0025 outbound communication policy

### Roadmap

`ROADMAP.md` is maintained and reflects completed foundation, hardening, communication/notification, scheduler, daemon, presence/lifecycle, and pending future runtime/UI phases.

## Agent-Agnostic Status

Search terms checked: `artemis`, `hermes`, `atlas`, `vigil`, `researcher`.

Classification:

- `backend/synapse/core/data_dir.py`: seed/bootstrap agents. OK seed/demo/test.
- `data/agents/*`, `data/config/permissions.yaml`, `data/config/system.yaml`: local DATA_DIR seed/config. OK seed/demo/test.
- Tests: many references used as fixtures. OK seed/demo/test.
- Docs/ADRs/walkthrough: examples and seeded scenario. OK documentation/example.
- Communication runtime/API/commands/scheduler: no current Hermes hardcoded runtime default. Previous risk was corrected.

Current verdict:

- No architectural error found.
- No current runtime dependency on Artemis/Hermes/Atlas/Vigil/Researcher outside seed bootstrap.
- Remaining risk is documentation tone: walkthrough is example-heavy around Artemis/Researcher/Hermes, but it is not runtime logic.

## Communication Runtime Details

- There is no implicit default to Hermes.
- `create_draft` requires `created_by_agent` or resolves `communication.default_agent_id`.
- `check_email` requires `agent_id` or resolves `communication.default_agent_id`.
- If no explicit/default communication agent exists, runtime returns a clear validation error.
- Draft approval is separate from send authorization:
  - draft approval approves content
  - outbound send authorization approves future sending
  - sent state is reserved as `sent_future`
- `send_email` real implementation does not exist.
- Gmail OAuth/token storage does not exist.
- Gmail provider is a prepared boundary only.

## Homelab Readiness

Implemented:

- Local scheduler queue.
- Recurring jobs with interval cadence.
- Scheduler lock with local lock file and stale recovery.
- Daemon runner with deterministic `run_once` and loop boundary.
- Runner identity and heartbeat.
- Homelab health summary.
- Notification cleanup.
- Jobs, daemon, runner, health, lock, recurring jobs available through commands/API.

Limitations for 24/7:

- No systemd service.
- No Windows Service.
- No Docker healthcheck integration.
- No external process supervisor.
- Local file lock only, not distributed.
- No lock heartbeat renewal for very long jobs.
- No historical health timeline.
- No schema migrations/versioned records.
- No production CLI wrapper.
- No multi-node runner registry.

## UI / Voice / Avatar / Mobile / Perception Status

- Desktop UI: not started.
- Mobile Companion: not started.
- Voice Runtime: not implemented.
- Avatar Runtime: not implemented.
- Perception Runtime: not implemented.
- Communication provider UI/review screens: not implemented.

## Remaining Technical Gaps

- Real Gmail integration.
- OAuth/token storage and rotation.
- Real `send_email` runtime/provider dispatch.
- Provider-specific rate limits, retries, pagination, sync cursors.
- Push/mobile/native notifications.
- Voice Runtime.
- Avatar Runtime.
- Perception Runtime.
- Desktop UI.
- Mobile Companion.
- systemd/Windows Service/Docker health integration.
- Distributed locks.
- Historical timeline for presence/lifecycle/health.
- Schema migrations and record versioning.
- Real CLI entrypoint.
- Admin/config editing surfaces.
- Custom agent creation/migration flow.
- Resource-scoped permissions and policy migrations.

## Recommended Next Step

The safest next architectural step is **checkpoint and commit the current backend foundation before adding any product surface**.

Reasoning:

- The working tree contains multiple completed stages beyond the last commit.
- Tests are green at 219 tests.
- The next functional work would increase risk if done without a clean baseline.

Recommended sequence:

1. Review and commit the current backend state in one or several logical commits.
2. Add a small CLI/service entrypoint for daemon and health operations, still without UI.
3. Add schema/version metadata and migration strategy before any long-lived homelab deployment.
4. Only after that, start Desktop UI as a Runtime client, not as owner of logic.

Avoid repeating V1 mistakes by keeping UI, provider integrations, and real sending behind the runtime boundaries already created.
