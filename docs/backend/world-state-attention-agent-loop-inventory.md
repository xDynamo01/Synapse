# World State, Attention, and Agent Loop inventory

Status: boundary review completed before implementation.

This inventory defines the ownership boundary for the World State + Attention
Engine + Agent Loop domain. Existing frozen domains remain authoritative for
their own records and execution. The new domain stores only references and
bounded summaries and must use canonical runtime contracts for side effects.

| Component | Current responsibility | State | Overlap | Consumers | Persistence | Risk | Destination |
|---|---|---|---|---|---|---|---|
| `core.events.EventBus` | Durable redacted event log and in-process listeners | Implemented / Frozen | Event ingestion and future client stream | All runtimes, observability | `logs/events.jsonl` | Recursive ingestion and sensitive payload propagation | Remains canonical event transport; the new domain consumes a strict allowlist and emits redacted lifecycle events |
| `perception.PerceptionRuntime` | Validated sensory signals, observations, confidence, provenance, expiry | Implemented / Frozen | Environment signals and transient facts | Multimodal, Context Fusion, API | `perception/` | Treating uncertain observations as durable facts | Remains source of observations; adapter emits TTL-bound summarized state updates and attention events |
| `context_fusion.ContextFusionRuntime` | Request-scoped context snapshots for conversations, missions, and sessions | Implemented / Frozen | `active_context` summaries | Chat, agents, missions | `context_fusion/snapshots/` | Duplicating its snapshots into World State | Remains context builder; World State keeps references and a bounded active summary only |
| `presence.PresenceRuntime` | Per-agent presence projection | Implemented / Frozen | Agent operational state | Lifecycle, workers, health | `presence/{agent}.yaml` | Confusing agent presence with user presence | Reconciliation source for `agents`; user presence stays evidence-based and low-confidence by default |
| `lifecycle.LifecycleRuntime` | Per-agent lifecycle transitions and wake/sleep | Implemented / Frozen | Loop lifecycle naming | Workers, scheduler, API | `lifecycle/{agent}.yaml` | New loop mutating agent lifecycle directly | Reconciliation/event source only; Agent Loop has its own independent state machine |
| `scheduler.SchedulerRuntime` | Persistent jobs, recurring schedules, single-runner lock | Implemented / Frozen | Recurring loop cycle and stale-lock recovery | Daemon, commands, API | `scheduler/` | A second scheduler or a busy loop | Canonical scheduling integration; new loop exposes one-shot bounded cycles |
| `daemon.DaemonRunner` | Incremental scheduler/maintenance runner | Implemented / Frozen | Continuous operation and shutdown | Process entrypoint, health | daemon status/identity stores | Blocking daemon or creating a parallel daemon | Hosts bounded Agent Loop cycles through minimal optional integration |
| `missions.MissionSupervisionRuntime` | Mission-specific operational attention recommendations | Implemented / Frozen | Uses the word attention | Mission Control, health, API | Derived from mission/DLQ stores | Replacing domain-specific diagnostics | Adapter converts eligible summaries into canonical `AttentionItem`; original remains authoritative |
| `mission_control.MissionControlRuntime` | Cross-mission operational dashboard | Implemented / Frozen | Operational snapshot and suggested actions | API, commands, health | Derived | Copying complete mission objects | Reconciliation source for mission references and summaries only |
| `health.HealthRuntime` | Cross-module health diagnostics | Implemented / Frozen | System health and alert candidates | Readiness, API, tools | Derived plus event log | Alert flapping and duplicated health logic | Source of summarized health updates; new domain adds its own bounded health report |
| `readiness.ReadinessRuntime` | Policy-based operational readiness | Implemented / Frozen | Startup gating | API, tools | `config/readiness_policy.yaml` | Making optional execution adapters globally required | Incorporates World State/policy/observability as required; action adapters remain disposition-specific |
| `agents.AgentRuntime` | Canonical reactive agent/model/tool orchestration | Implemented / Frozen | Response execution | Workers, chat/tool flows | Domain stores/events | Bypassing canonical Chat or manually constructing prompts | Not called directly by the loop; response uses `ChatRuntime` |
| `chat.ChatRuntime` | Canonical persisted chat turns and local model routing | Implemented / Frozen | `respond` disposition | API, commands | conversations and `chats/sessions/` | Duplicate messages after restart | Sole response executor; loop persists execution ledger before final commit and verifies persisted output |
| `tools.ToolRuntime` | Canonical governed tool execution and result ledger | Implemented / Frozen | Reversible action execution and verification | Tool calling, MCP bridge | `tools/execution_log.jsonl` | Arbitrary action injection or irreversible automation | Sole tool executor; selector accepts only policy-authorized registered tools within the risk ceiling |
| `missions.MissionRuntime` + `ResultVerifier` | Canonical mission creation/start and mission result verification | Implemented / Frozen | Long-running action routing | Mission Control, workers | `missions/` | Blocking cycles or duplicating a mission | Sole mission executor; loop stores mission reference and never waits for long work |
| `decisions.DecisionRuntime` | Frozen Platform Governance decision facade for capabilities/tools/admin/delegation | Implemented / Frozen | Name collision with disposition selection | Tools, capabilities, health | Policy records and event log | Replacing or weakening deny-by-default governance | Remains the governance engine; new `attention.DecisionRuntime` selects a disposition and delegates authorization to it |
| `policies.EffectivePolicyRuntime` | Effective permission, capability, tool, and approval policy | Implemented / Frozen | Autonomy and side-effect constraints | Agents, decisions, tools | `policies/`, agent config | Implicit allow when no rule exists | Canonical policy source; proactive policy adds stricter ceilings but never broadens existing permission |
| `notifications.NotificationRuntime` | Backend-local persistent notification inbox | Implemented / Frozen | Notification sink | API, health, event listener | notification provider store | Simulating frontend delivery or duplicate event notifications | Wrapped by a neutral `NotificationSink`; remains default inbox implementation |
| `memory.MemoryStore` | Canonical versioned scoped memory | Implemented / Frozen | Memory commit | Context, API, agents | `memory/records.json` | Saving every event or sensitive observation | Used only through an explicit `MemoryCommitPolicy`; skipped by default without durable value and policy |
| New `WorldStateRuntime` | Current-state projection, revisions, updates, TTL, snapshots, history, reconciliation | New owner | None after this boundary | Attention, Decision, Agent Loop, controlled API | `world_state/snapshot.json`, update ledger and history | Stale/incorrect facts and write conflicts | Owns state only; never selects or executes actions |
| New `AttentionRuntime` | Event relevance, deterministic scoring, deduplication, aggregation, suppression, escalation, queue | New owner | Mission/health diagnostic inputs only | Decision, Agent Loop, inbox API | `attention/items/`, ingestion ledger | Alert floods or hiding critical items | Owns canonical `AttentionItem`; never executes actions |
| New `attention.DecisionRuntime` | Selects one disposition after governance/autonomy/DND checks | New owner | Uses frozen governance result | Agent Loop, diagnostics | `agent_loop/decisions/` via loop store | Conflating selection and execution | Produces immutable `Decision`; never invokes Chat, Tool, Mission, approvals, or notifications |
| New `AgentLoopRuntime` | Bounded idempotent cycle, state machine, execution routing, verification, commit, traces | New owner | Daemon/scheduler host lifecycle | Daemon, scheduler, controlled API/commands | `agent_loop/state.json`, cycle and execution ledgers | Duplicate actions, busy loop, unsafe restart | Sole coordinator; all side effects go through canonical runtimes and explicit ports |

## Binding decisions

- World State is a projection, not a new source of truth. References replace
  copied conversations, missions, agents, devices, providers, and observations.
- Events and current state are separate. Events may create attention without
  becoming durable state; uncertain perception updates require TTL.
- Mission-specific attention remains in Missions. Canonical attention may ingest
  it but does not change mission supervision semantics.
- The frozen governance `synapse.decisions.DecisionRuntime` remains untouched.
  Disposition selection lives in `synapse.attention.decision` and must consult
  governance before returning any executable disposition.
- Agent Loop owns coordination only. It cannot call a provider, shell, or model
  adapter and cannot construct a model prompt. Chat, Tool, Mission, Approval,
  Notification, Observability, and Memory contracts remain authoritative.
- Proactive execution is opt-in. The default mode is `observe`; absence of an
  explicit allow or unavailable policy results in `record_only`, `defer`, or
  `require_approval`, never execution.
