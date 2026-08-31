# Backend Specification

The required Intelligence Trust Boundary owns InformationAsset metadata,
provider trust, egress decisions/manifests, scoped consent and an immutable
redacted ledger. External processing fails closed when unavailable; explicitly
local processing may continue. It does not perform transport or claim control
over a provider after receipt.

The optional Project Governance runtime owns project identity, RFC lifecycle,
review, gate, plans, evidence and acceptance metadata. Human Markdown/YAML
remains editable; operational indexes use Storage Primitives. Its unavailability
does not stop unrelated backend work, but project coding governance is unavailable.

The optional Skills Runtime owns package validation, registry, discovery,
resolution, progressive loading, assignments and leases. Its unavailability is
degraded capability and does not prevent agents or backend startup.

## Administrative DataDir maintenance

Administrative inspection and cleanup are coordinated by the domain-neutral
`DataMaintenanceRuntime` and explicit owner contributors. Stored plans enforce
scope, checksum, revision, expiry, confirmation, policy and approval before an
owner may execute an action. Delivery accepts registered identifiers only and
exposes no absolute paths. See `architecture/data-maintenance.md`.

## Primary and ephemeral runtimes

`PrimaryAgentRuntime` and `EphemeralAgentRuntime` are composed once in bootstrap.
The first coordinates durable interaction state; the second owns leased identities
and cleanup. Neither duplicates Chat, Agent Loop, Voice, Worker, TaskAttempt,
ModelRouter or ToolExecutionPort. Legacy Agent Creator wiring no longer exists.

## Operational storage boundary

`synapse.storage` receives paths already resolved by DataDir and serves small,
bounded operational collections. It is internal infrastructure, not a public DTO
surface or ORM. Memory, Workers, Attempts and Notifications are the controlled
pilots; other stores retain their current owner and format.

## Provider discovery boundary

`RuntimeContainer.provider_catalog` is the internal transversal manifest catalog.
It lists and filters identity, domain, capabilities, availability, configuration
shape and lifecycle claims but cannot execute providers. Domain runtimes remain the
only operational authorities. No API or Command surface was added.

## HTTP API composition

HTTP delivery is organized into 13 domain routers under `synapse/api/routers`.
`synapse/api/router_registry.py` is the single registration point and
`synapse/api/routes.py` is an import-compatibility adapter. DTOs stay with their
owning router and handlers call the canonical `RuntimeContainer` facades. The
frozen contract remains 425 paths, 471 operations and 100 schemas. Routing rules
and retained findings are documented in `docs/architecture/api-routing.md`.

## Desktop Automation + Application Control

The generic desktop execution domain is Implemented / Frozen. It discovers
applications, windows, and semantic accessibility elements without knowing any
specific software. Every sequence is planned, previewable, dry-runnable,
policy/approval governed, verified step-by-step, audited, redacted, retry-safe,
and honestly rollback-aware. Technical contracts are in
`docs/backend/application-control.md`, `desktop-runtime.md`, `ui-automation.md`,
`window-runtime.md`, `input-runtime.md`, `verification-runtime.md`,
`clipboard.md`, `desktop-security.md`, and `desktop-providers.md`.

## Insight + System Runtime

The operational-awareness domain is Implemented / Frozen. It collects bounded,
sanitized platform evidence through isolated providers and exposes separate
system, hardware, disk, process, pressure, model-capability, and diagnostics
runtimes. It performs no control action. Canonical details are in
`docs/backend/insight.md`, `system-runtime.md`, `hardware.md`,
`resource-pressure.md`, `model-recommendations.md`, and `diagnostics.md`.

## World State, Attention, and Agent Loop

The continuous local-agent operating layer is implemented as four separate
runtimes. World State is a current projection over frozen sources; Attention
filters events; disposition Decision consults governance/autonomy; Agent Loop
coordinates bounded, idempotent canonical execution. See
`docs/backend/world-state.md`, `attention-engine.md`, `agent-loop.md`, and
`proactive-behavior.md`.

Persistent state lives under `DATA_DIR/world_state`, `attention`, and
`agent_loop`. No frontend, provider adapter, direct shell path, or second daemon
is part of this domain.

## Platform Governance

The transverse backend layer centralizes deterministic policy, correlation and
trace, real metrics, redaction, observability retention, structured health,
readiness, diagnostics, and foundation validation. Canonical contracts are in
`docs/backend/policy.md`, `docs/backend/observability.md`,
`docs/backend/health.md`, and `docs/backend/foundation-hardening.md`.

## Voice, Audio and Speech

This domain is Implemented / Frozen. See `docs/backend/voice.md`,
`docs/backend/audio.md`, `docs/backend/speech.md`, and
`docs/backend/voice-sessions.md` for contracts and limitations.

## Scope

The Synapse backend is a Python 3.12 local runtime exposed through FastAPI,
commands, scheduler jobs, and a client-neutral sidecar process. It is the sole owner
of business rules, durable state transitions, policy enforcement, and provider
orchestration.

Status: **Implemented / Frozen**. The final global baseline is green and visual
client contracts are outside the backend boundary.

## Composition

The canonical composition root is `backend/synapse/bootstrap/application.py`.
It coordinates typed bounded-context builders and constructs `RuntimeContainer`
through one production path. `backend/synapse/core/app.py` is compatibility
only. FastAPI builds, starts and closes through lifespan; see
`docs/architecture/bootstrap.md` and `docs/architecture/lifecycle.md`.

Primary infrastructure:

| Component | Responsibility | Status |
| --- | --- | --- |
| `DataDir` | Safe path resolution, directories, seed files | Implemented |
| serialization | YAML/JSON loading and structured dumping | Implemented |
| `EventBus` | Append-only operational event stream | Implemented |
| permissions/resources | Actor and resource authorization | Implemented foundation |
| approvals | Durable human authorization workflow | Implemented |
| migrations | Explicit record migration registry/history | Implemented foundation |
| health/readiness | Runtime diagnostics and capability readiness | Implemented / Frozen |
| observability | Correlation and trace projection | Implemented / Frozen |

## Domain Organization

Memory and Context Fusion are implemented and frozen. Structured memory uses an
independent storage port; Chat and workers enter through Context Fusion before
compatibility DTO adaptation.

Production packages under `backend/synapse/` are domain-oriented. A domain may
contain models, policy, persistence, runtime, and adapter modules. Cross-domain
dependencies must be explicit constructor dependencies.

Key groups:

- **Agents**: registry, identity, custom provisioning, admin, audit,
  presence, lifecycle, workers.
- **Conversation + Chat**: durable conversations/messages and a canonical turn
  service for local and agent communication.
- **Work**: tasks, delegation, execution, retry, timeout, recovery, dead letter,
  missions, scheduler.
- **Interaction**: chat, conversations, agent-to-agent communication, notifications.
- **Intelligence**: memory/context, models, model hub, providers, tools, MCP,
  execution router.
- **Multimodal**: audio, speech, voice, vision, perception and context fusion.

Frontend owns visualization and animation. Voice owns factual voice states and
events; Perception owns multimodal observations, features and inferences. No
Avatar or Embodiment Runtime exists in the backend target architecture.
- **Platform**: API, commands, daemon, sidecar, migrations, retention, health,
  readiness, observability, Insight/System Runtime, and generic Desktop Automation.

## Domain Runtime Contract

A runtime should:

1. accept typed input;
2. validate identifiers and state;
3. load required records through domain persistence helpers;
4. resolve policy and permissions before side effects;
5. perform an atomic or recoverable transition;
6. persist a versioned record;
7. emit domain events and audit when applicable;
8. return a typed result;
9. raise a `SynapseError` subtype for expected failures.

Runtimes must not return fabricated success, swallow parser/filesystem errors,
or use broad fallback behavior that changes authority.

## Persistence Layout

Representative `DATA_DIR` paths:

```text
config/                         runtime and policy configuration
agents/{agent_id}/              identity, config, inbox, audit
agent_provisioning/             approval-gated provisioning requests
memory/                         global/user memory sources
conversations/                  conversation records and summaries
delegation/                     delegated tasks
delegation_execution/           execution attempts
missions/                       mission records
approvals/                      approval requests
jobs/                           scheduler queue
logs/events.jsonl               event stream
migrations/                     migration status and history
audio/, voice/, vision/         multimodal artifacts and records
model_hub/, providers/          provider/model discovery and settings
```

`data/` in the repository is a development seed source. Runtime state belongs
in the configured `DATA_DIR`, which may be outside the repository.

## Context Fusion

Context Fusion coordinates read-only context through six consumer-owned ports.
Adapters are explicit in the composition root, source calls retain correlation
IDs and have a bounded technical timeout, and no owner store or runtime is
imported by the domain. Selection, ordering, budget and omission are unchanged.
See [Context Fusion](backend/context-fusion.md).

## Configuration

Configuration is local and explicit. Policy files include permissions,
approvals, provisioning, delegation, scheduler, communication, providers,
speech, and readiness. A missing optional policy may use a conservative
documented default. A malformed policy must fail validation; it cannot silently
be treated as permissive.

Secrets are not ordinary YAML configuration. See [Security](security.md).

## State Machines

Durable workflows use explicit statuses. Examples:

- approval: pending, approved, rejected, expired, resumed;
- provisioning: awaiting approval, approved, rejected, expired, applied,
  failed;
- delegation task: pending, accepted, in progress, completed, failed,
  rejected, cancelled;
- execution: pending, running, completed, failed, cancelled;
- scheduler job: pending, running, completed, failed, cancelled;
- lifecycle/presence: domain-specific operational states.

Transitions must reject terminal-state mutation and repeated side effects.
Idempotent reads are always safe; idempotent writes require a documented key or
request identifier.

## Atomicity And Rollback

Single-record writes use structured dump helpers. Multi-file operations use a
staging directory or a backup/rename sequence. Provisioning is the reference
pattern:

1. render files outside the final `agents/` path;
2. validate staged config through registry and identity;
3. rename into the final location;
4. restore backup if overwrite commit fails;
5. emit completed or rolled-back events.

Other multi-file domains should adopt equivalent behavior rather than copying
provisioning internals.

## Error Model

Base exceptions live in `synapse.core.exceptions`:

- `ValidationError` for invalid input/state;
- `NotFound` for absent resources;
- `PermissionDenied` for authorization failures;
- `ToolExecutionError` for controlled tool failures.

Domain exceptions may add stable `code` and structured `details`. Raw parser,
filesystem, provider, and subprocess exceptions must be mapped before crossing
an API or command boundary. Internal causes remain chained for diagnostics.

## Events And Audit

Events describe operational facts and may support correlation/tracing. Audit
records describe authorization and durable administrative changes.

Required event fields where supported:

- event ID and timestamp;
- type and actor;
- correlation, causation, parent, and source;
- target/resource identifiers;
- structured result or redacted error.

Never include API keys, access tokens, raw credentials, or unrestricted model
prompts in events.

## Background Execution

`DaemonRunner` executes deterministic cycles. Scheduler locking prevents two
local runners from processing the same queue concurrently. This is a local
single-runner mechanism, not a distributed consensus system.

Target background behavior:

- jobs are durable before execution;
- retries and max attempts are policy-controlled;
- heartbeat and lock ownership are inspectable;
- cancellation is explicit;
- process restarts recover pending durable work;
- no `sleep()`-based correctness in tests or runtimes.

## Provider Boundary

Tools, Execution, Approvals and MCP are implemented and frozen. Product consumers
submit calls to ToolRuntime; registries discover but never execute; MCP cannot bypass
schema, permissions, risk or approvals.

The canonical registry also contains hidden compatibility descriptors for historical
builtins and internal Desktop adapter identities. They preserve the public catalog
while ensuring Commands, API, Chat/Agents, Agent Loop, Missions/Workers, and MCP all
traverse the same execution authority. Global execution history belongs only to
ToolRuntime; provider-local technical records are not public execution histories.

Models + Providers is implemented and frozen. ModelRouter owns selection and
generation orchestration; adapters own external protocol translation; Model Hub
owns catalog/discovery; settings own endpoints and secrets.

Provider adapters implement external I/O. They must define:

- stable provider ID;
- configuration schema and secret references;
- health and discovery behavior;
- timeout and cancellation behavior;
- normalized errors;
- capability/model descriptors;
- whether network or local hardware is required.

Domains depend on provider interfaces, not SDK-specific response objects.

## API And Commands

FastAPI and `CommandRuntime` are sibling adapters. A capability exposed through
both must call the same runtime operation. Routes should be thin and use
`api_error()` or a domain-aware mapper. Commands should return structured
`CommandResult` data in addition to human-readable output.

Slash commands are registered once through `CommandRegistry`. New commands
belong to a bounded-context handler, require complete metadata and tests, and
must preserve policy/approval/revision/idempotency in the canonical runtime.
Handlers must not import stores, concrete providers, API or bootstrap; access
DataDir; instantiate runtimes; or execute subprocesses.

See [API](api.md).

## Health And Readiness

Bounded contexts expose read-only health contributors registered explicitly by
bootstrap. `HealthRuntime` aggregates canonical components and summary facts;
it must not import domain implementations. `ReadinessRuntime` consumes the
neutral health snapshot and applies the existing readiness policy. New health
surfaces require a contributor or an explicit `no health surface by design`
declaration.

## Testing Standard

- Unit/domain tests use temporary `DATA_DIR` roots.
- Factories generate contract-valid records and explicit invalid variants.
- Tests assert state, persisted files, events, audit, and error type/code.
- External providers use deterministic test adapters only in tests.
- A domain is complete only when its direct tests and related integration tests
  are green and the global failure count does not increase.

The final collected count and zero-failure result are recorded in
`docs/validation/backend-freeze-baseline.md`.

Perception, Vision, Capture, and Multimodal are offline-first backend services.
Visual providers are explicit protocol implementations; optional OCR/camera
absence is not global backend degradation. Production behavior never substitutes
fake detection output for an unavailable capability.

## Target Backend Completion Criteria

- all backend tests green;
- all durable records versioned or explicitly legacy-compatible;
- no production mock behavior presented as real capability;
- no raw parser/filesystem/provider errors across adapters;
- domain-level atomicity or recovery documented and tested;
- complete health/readiness for configured capabilities;
- OpenAPI and command contracts aligned;
- security review for secrets, approvals, plugins, and external providers.
