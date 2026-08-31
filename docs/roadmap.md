# Synapse V3 Roadmap — historical baseline

> **Superseded as the operational roadmap.** Use
> [docs/roadmap/current.md](roadmap/current.md) for current backend status, the
> active bounded context and the next executable slice. This file is retained as
> historical evidence of the earlier V3 phase model; its phase statuses and gate
> counts are not current claims.

## Roadmap Rules

This roadmap is ordered by dependency and validation gates, not dates. A phase
starts automatically when its predecessor's exit criteria are met, but no phase
may bypass a failed safety or stability gate.

Status meanings follow [architecture.md](architecture.md). Historical V2 plans
and validation phase numbers do not override this V3 sequence.

## Current Baseline

| Area | Current evidence | Status |
| --- | --- | --- |
| Ruff | repository-wide pass | Implemented gate |
| Pytest | final zero-failure baseline | Implemented gate |
| Delegation | 105 direct tests passed | Implemented domain |
| Agent identity/registry | focused domains stabilized | Implemented foundation |
| Custom agent provisioning | focused domain green; global baseline still red | In development |
| React/Tauri client | removed from repository | Removed |
| Electron ADE | superseded by ADR 0119; implementation removed | Retired |
| Frontend | no active implementation | Not implemented |
| Swarm | specification only | Planned |

The detailed backend evidence remains in
`docs/validation/backend-freeze-baseline.md`.

## Phase 0: Canonical Specification

Status: **In development**

Deliverables:

- canonical README and domain specifications;
- explicit implemented/in-development/planned/legacy labels;
- one architecture target for backend and desktop;
- security, development, and contribution gates;
- replacement of obsolete roadmap assumptions.

Exit criteria:

- all canonical files linked from README exist;
- local links and terminology validate;
- target claims are distinguishable from current implementation;
- no implementation, commit, or remote publication is mixed into the phase.

## Phase 1: Backend Freeze Completion

Status: **Complete**

Objective completed: all backend failures were closed by domain, followed by
removal of obsolete visual contracts and their abandoned client consumers.

Priority groups:

1. agent identity and provisioning residuals;
2. conversations, summaries, and conversation-aware workers;
3. missions, mission control, context, and supervision;
4. workers, scheduler, lifecycle, presence, and dead letter;
5. effective policy, tools, and approval bridges;
6. speech pipeline, adapters, and multimodal context;
7. observability, health, daemon, readiness, and UI contracts.

Exit criteria:

- full pytest suite green;
- Ruff green repository-wide;
- no production validation weakened to satisfy fixtures;
- baseline records every domain correction;
- transient test artifacts are excluded from product state.

## Phase 2: Backend Contract Consolidation

Status: **Planned**

Objective: make stable backend domains safe for a new client without a backend
rewrite.

Deliverables:

- consistent error envelope and actor context;
- explicit idempotency and correlation contracts;
- truthful health/readiness by domain and provider;
- bounded pagination and event transport;
- persisted schema inventory and migration coverage;
- route decomposition only where justified by stable domain boundaries.

Exit criteria include API contract tests, migration compatibility tests, and no
regression in the green global suite.

## Phase 3: Retired Electron ADE Visual Foundation

Status: **Retired / superseded by ADR 0119**

Objective: prove the product reads as a multi-agent development environment.

Deliverables:

- removed `apps/electron-ade/` scaffold;
- static Activity Bar, Sidebar, Dockview workspace, Bottom Panel, and Status
  Bar;
- initial pane composition with isolated fake fixtures;
- responsive, keyboard-accessible visual validation.

No backend feature work or legacy UI migration belongs in this phase.

## Phase 4: Retired Desktop Runtime and API Integration

Status: **Retired / superseded by ADR 0119**

Deliverables:

- secure Electron main/preload/renderer boundary;
- backend sidecar lifecycle, handshake, health, retry, and shutdown;
- typed renderer API modules;
- real agents, models, console, context, events, and approval surfaces;
- versioned workspace persistence;
- desktop integration and packaging smoke tests.

Exit criteria forbid direct renderer Node access, component-level backend
`fetch`, hidden mock fallback, and secret persistence.

## Phase 5: Models and Tool Execution

Status: **Planned**, built on partial foundations

Deliverables:

- production-ready local model routing;
- complete OpenAI-compatible adapter only after secret handling is ready;
- streaming and cancellation contracts;
- normalized provider errors and usage;
- native tool-call normalization, approval, and result correlation;
- model management panes backed by truthful readiness.

## Phase 6: Memory and Context

Status: **Planned**, built on partial foundations

Deliverables:

- typed memory records and scopes;
- deterministic context ordering and token budgeting;
- provenance, sensitivity, retention, and deletion;
- retrieval and summarization evaluation;
- operator inspection and correction in the ADE.

No vector database is selected by this roadmap. A retrieval engine requires an
ADR and measured need.

## Phase 7: Voice and Multimodal

Status: **Planned**, built on partial foundations

Deliverables:

- green speech, adapter, and multimodal backend domains;
- truthful Faster Whisper and Piper readiness;
- desktop capture and playback with visible consent;
- correlated capture-to-conversation-to-speech loop;
- cancellation, privacy, retention, and failure UX;
- optional provider fallback only through explicit policy.

## Phase 8: Swarm Orchestration

Status: **Planned**

Deliverables follow [swarm.md](swarm.md): durable objective and task graph,
bounded coordinator, deterministic scheduling, scoped memory, versioned
artifacts, leases, recovery, budgets, approvals, and causal observability.

Swarm cannot begin until agent, delegation, mission, worker, policy, memory, and
event prerequisites are green.

## Phase 9: Release Hardening

Status: **Planned**

Deliverables:

- threat model closure and release-grade secret storage;
- local API authentication and desktop trust establishment;
- dependency, license, and supply-chain review;
- signed packaging and update policy;
- backup, migration, and rollback testing;
- performance, soak, accessibility, and platform validation;
- release runbook and support boundaries.

## Explicitly Deferred

- native email integration is removed, not deferred; any future operation of
  mail applications requires a new decision for generic application automation;
- unrestricted autonomous agent creation;
- cloud-first persistence;
- hidden cloud model or speech fallback;
- migration of React/Tauri workspace state into V3;
- mobile and multi-user remote hosting;
- plugin marketplace execution without signature and permission design.

Deferred work requires a new architectural decision and cannot be inferred from
existing experimental files.
