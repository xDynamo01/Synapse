# Synapse 0.3 full-system inventory

Status date: 2026-11-05. Profile: `analysis-only`. This inventory describes
the preserved implementation at `3966f84` and does not declare the runtime
operational.

## Evidence boundary

- Canonical composition root: `backend/synapse/bootstrap/application.py`.
- One `RuntimeContainer` construction point and 12 feature builders.
- 112 fields exposed by the canonical runtime container.
- 95 material top-level Python contexts, excluding `__pycache__`.
- 98 nodes and 352 directed edges in the architecture-test import graph.
- 568 unique HTTP method/path registrations across 23 domain routers.
- 58 distinct `/api/` path literals in the Electron shared client.
- Temporary-data composition produced 26 capabilities, 9 seed runtime tools,
  8 provider manifests, 25 provider-catalog entries and 6 real speech adapters.
- Architecture suite: 274 passed with one Starlette/httpx deprecation warning.
- No capability below is classified `OPERATIONAL`; no real end-to-end startup,
  device, provider, recovery or reboot proof was executed in this mission.

## Capability catalogue

The status is the highest claim supported by this inventory. `INTEGRATED` means
the canonical composition root wires the capability; it does not mean its real
providers or failure recovery were exercised.

| ID | Capability and owner | Principal surfaces | Status | Limitation |
|---|---|---|---|---|
| CAP-001 | Foundation and operational kernel | config, data directory, event journal, storage, health, readiness, migrations, retention, maintenance | `INTEGRATED` | Health/readiness are composition-tested, not validated against the user's live runtime. |
| CAP-002 | Agent identity and governance | agents, provisioning, admin, auth, policies, presence, lifecycle, notifications | `INTEGRATED` | Several contexts have only indirect acceptance/architecture coverage. |
| CAP-003 | Conversation and command interaction | chat, conversations, command registry, context loading | `INTEGRATED` | Local model/provider availability remains environment-dependent. |
| CAP-004 | Delegation and worker execution | delegation policies, inbox, execution, recovery, dead letter, workers | `INTEGRATED` | Part of the main 24-context SCC; recovery is not operationally replayed here. |
| CAP-005 | Missions and Swarm | mission plans, attempts, Swarm, ephemeral agents, mission control | `TESTED` in Mission 0.3.2 | Bounded verification and concurrent tool-input registration pass; real two- and four-agent project execution remains operationally unproved. |
| CAP-006 | Scheduler and decisions | scheduler, daemon, jobs/tasks, approvals and decision policy | `INTEGRATED` | Daemon/reboot and recurring execution were not run. |
| CAP-007 | Models and MoM | provider settings, model hub, provider plugins, MoM, system insight | `INTEGRATED` | Catalogue presence does not prove installed/loaded model inference. |
| CAP-008 | Tools and MCP | tool runtime, discovery, intents, execution router, MCP bridge, desktop commands | `INTEGRATED` | Default temporary composition exposes only nine seed tools; project-file tools are policy/configuration dependent. |
| CAP-009 | Knowledge and trust boundary | memory, project knowledge, search, context fusion, intelligence egress gate | `INTEGRATED` except search `IMPLEMENTED`/opt-in | Search is intentionally inert without opt-in configuration; learned embeddings are environment-gated. |
| CAP-010 | Voice and multimodal perception | audio, voice, speech adapters/pipeline, vision, perception, multimodal fusion | `INTEGRATED_WITH_GAP` | Conversational voice returns a TTS placeholder; device/provider operation is unproved. |
| CAP-011 | Desktop automation | application/window discovery, UI tree, plan, preview, execute, verify | `INTEGRATED` | Real desktop authority and active Windows behavior were not exercised. |
| CAP-012 | World and proactive loop | world state, attention, agent loop and agent event stream | `INTEGRATED` | Background lifecycle and long-running behavior were not observed. |
| CAP-013 | Product skills runtime | assignments, leases, installations, governed tool-backed execution | `INTEGRATED` | The product runtime and Codex engineering skills are separate systems. |
| CAP-014 | Engineering governance runtimes | project governance, coding sessions, repository, sandbox, deployment, private evals | `INTEGRATED` | Concrete sandbox driver is opt-in; persistence/recovery need operational validation. |
| CAP-015 | HTTP delivery and composition | FastAPI routers, bootstrap features/adapters, lifecycle | `INTEGRATED` | Public API is much wider than the current Electron client surface. |
| CAP-016 | Electron product shell | main/preload/renderer, sidecar, client, settings and activity UI | `TESTED` in Mission 0.3.0 | Renderer and stylesheet are large monoliths; no live visual/E2E proof in this inventory mission. |

## Complete backend context ownership map

Every material directory under `backend/synapse` is classified below. Adapter,
composition and integration directories remain with the capability that owns
their contract; they are not independent product capabilities.

| Capability | Classified top-level contexts |
|---|---|
| CAP-001 | `core`, `storage`, `contracts`, `observability`, `operational_projection`, `health`, `readiness`, `migrations`, `retention`, `maintenance`, `resources`, `capabilities` |
| CAP-002 | `agents`, `admin_policy`, `auth`, `policies`, `presence`, `lifecycle`, `notifications`, `primary_agent` |
| CAP-003 | `chat`, `conversations`, `commands`, `context` |
| CAP-004 | `delegation`, `delegation_execution`, `delegation_inbox`, `delegation_recovery`, `dead_letter`, `workers` |
| CAP-005 | `missions`, `mission_control`, `swarm`, `ephemeral_agents` |
| CAP-006 | `scheduler`, `daemon`, `tasks`, `decision`, `decisions`, `approvals` |
| CAP-007 | `models`, `model_providers`, `model_hub`, `providers`, `provider_plugins`, `mom`, `system_insight` |
| CAP-008 | `tools`, `tool_discovery`, `tool_intents`, `agent_tool_calling`, `execution_router`, `mcp`, `mcp_bridge`, `desktop_commands` |
| CAP-009 | `memory`, `project_knowledge`, `search`, `search_adapters`, `search_composition`, `search_integrations`, `context_fusion`, `intelligence_boundary` |
| CAP-010 | `audio`, `voice`, `voice_composition`, `speech_adapters`, `speech_pipeline`, `vision`, `perception`, `multimodal` |
| CAP-011 | `desktop_automation` |
| CAP-012 | `world_state`, `attention`, `agent_loop` |
| CAP-013 | `skills` |
| CAP-014 | `project_governance`, `coding_sessions`, `coding_sessions_composition`, `coding_sessions_integrations`, `repository_runtime`, `repository_runtime_composition`, `repository_runtime_integrations`, `sandbox`, `sandbox_composition`, `sandbox_driver_composition`, `sandbox_drivers`, `sandbox_integrations`, `deployment`, `deployment_adapters`, `deployment_composition`, `deployment_integrations`, `private_evals` |
| CAP-015 | `api`, `bootstrap` |

## Composition and initialization map

`create_app()` constructs only the FastAPI shell. Its lifespan constructs and
starts the application, then closes it on shutdown. `create_runtime()` builds in
this order:

1. foundation;
2. models and providers;
3. platform;
4. multimodal interaction;
5. agents and delegation;
6. missions and Swarm;
7. automation;
8. execution and observability;
9. product skills;
10. project governance;
11. intelligence trust boundary;
12. world state and agent loop.

Seven lifecycle resources are registered: agent loop, deployment, private
evals, coding sessions, skills phase 2, sandbox and repository runtime. Search
and a concrete sandbox driver remain local opt-in bindings. Voice/audio/
perception is an active legacy-global optional binding.

## Runtime registries observed with temporary data

- Capabilities: 26, including filesystem read/write, memory read/write,
  scheduling, notifications, audio, vision and speech.
- Seed runtime tools: 9 summary/transcription tools. Desktop and memory adapters
  are registered through composition; filesystem tools require the applicable
  project policy/configuration path.
- Execution providers: 8 manifests in the temporary composition.
- Provider taxonomy: 25 entries, including local, network, desktop, vision and
  speech projections. Taxonomy presence is discovery metadata, not health.
- Speech adapters: Faster Whisper, Kokoro, Piper, ChatTTS, VoiceStudio and local
  acoustic analysis. Mock adapters are filtered outside explicit development
  mode.

## Dependency graph findings

- Main SCC: 24 contexts and 80 internal edges across agents, tools, missions,
  models, conversations, approvals, voice, worker execution and related bridges.
- Secondary SCC: `audio`, `multimodal`, `perception` with four internal edges.
- Highest outgoing dependency counts: API 20, tools 17, agents 14, missions 14,
  commands 13, chat 12 and workers 12.
- `core` is the dominant incoming neutral dependency and remains protected by
  architecture tests.

Passing architecture tests prove compliance with today's allowlists and frozen
rules. They do not prove that the two SCCs are desirable or that every public
surface has one owner.

## Product shell inventory

- Electron main process owns sidecar launch, window/tray lifecycle, native file
  selection and window IPC.
- Preload exposes a narrow `window.synapse` bridge for backend location,
  bootstrap reporting, file selection and window controls.
- `frontendClient.ts` owns 58 direct API path literals spanning conversation,
  Swarm, MoM, projects, activity, models, voice and notifications.
- The renderer is concentrated in `main.tsx` (5,126 lines) and `styles.css`
  (3,540 lines), with smaller extracted components for Presence, workspace,
  MoM, Swarm confirmation and activity constellation.

## Unknowns requiring operational evidence

- Which of the 568 routes are intended product API, compatibility API or
  internal/admin-only API.
- Which provider/model/device combinations are healthy on the active machine.
- Whether lifecycle start/stop, crash recovery and reboot restore every active
  global binding.
- Whether every tool advertised through discovery has an executable adapter
  under the user's actual policy.
- Whether the Electron shell reaches each backend flow in the packaged root
  executable rather than only in tests/build output.
