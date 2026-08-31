# Synapse — operational backend roadmap

Status global: **Backend READY / Windows Release Candidate READY**.

Este é o único roadmap operacional atual. O [roadmap V3 anterior](../roadmap.md) é
histórico/superseded. Evidência detalhada permanece nas specifications e audits;
contagens históricas de testes, arquivos, edges ou SCCs não são gates atuais.

## Reconciled baseline

| Bounded context | Estado local | Evidence |
| --- | --- | --- |
| Private Evals | `IMPLEMENTED / OPERATIONALLY COMPLETE / FROZEN` — S1–S18 | [freeze audit](../audits/private-evals-final-freeze-audit.md) |
| Coding Sessions | `IMPLEMENTED / OPERATIONALLY COMPLETE / FROZEN` — S1–S20 | [freeze audit](../audits/coding-sessions-final-freeze-audit.md) |
| Skills Runtime Phase 2 | `IMPLEMENTED / OPERATIONALLY COMPLETE / FROZEN` | [architecture](../architecture/skills-runtime-phase-2.md) |
| Sandbox Execution Boundary | `IMPLEMENTED / OPERATIONALLY COMPLETE / FROZEN`, globally not activated | [architecture](../architecture/sandbox-execution-boundary.md) |
| Concrete Sandbox Driver Windows V1 | `IMPLEMENTED / OPERATIONALLY COMPLETE / FROZEN`, capability-limited | [freeze audit](../audits/concrete-sandbox-driver-final-freeze-audit.md) |
| Repository Runtime | `IMPLEMENTED / OPERATIONALLY COMPLETE / FROZEN` | [freeze audit](../audits/repository-runtime-final-freeze-audit.md) |
| Voice / Audio / Perception | `IMPLEMENTED / ARCHITECTURALLY COMPLETE / FROZEN`, with explicit external limitations | [freeze audit](../audits/voice-audio-perception-final-freeze-audit.md) |
| Search Runtime | `IMPLEMENTED / ARCHITECTURALLY COMPLETE / FROZEN`, live provider may be unconfigured | [freeze audit](../audits/search-runtime-final-freeze-audit.md) |
| Deployment Runtime | `IMPLEMENTED / OPERATIONALLY COMPLETE / FROZEN` — S2–S15 | [freeze audit](../audits/deployment-runtime-final-freeze-audit.md) |

Frozen means the bounded local contract is governed. It does not mean every
optional provider is configured, every external capability is available or the
backend is globally ready.

## Current product phase — Frontend V2 foundation

Status: **FRONTEND V2 RELEASE CANDIDATE READY**

Scope: clean rebuild planning for the local-first desktop frontend. The retired
Electron ADE frontend remains retired and is not a baseline for the new work.
This phase does not alter historical Backend Readiness. Frontend-specific gaps
are tracked as `FRONTEND REQUIREMENT GAP`.

Canonical frontend foundation documents:

- [Product specification](../frontend/PRODUCT_SPEC.md)
- [Frontend architecture](../frontend/ARCHITECTURE.md)
- [Backend contracts](../frontend/BACKEND_CONTRACTS.md)
- [Visual system](../frontend/VISUAL_SYSTEM.md)
- [ADR 0120 — Frontend V2 desktop stack](../adr/0120-frontend-v2-stack.md)
- [Frontend V2 Windows release plan](../frontend/RELEASE_PLAN.md)

Recommended stack for the initial rebuild: **Electron + React + TypeScript +
Vite + PixiJS**, with minimal state management and no heavy docking, global data
cache, 3D engine or design-system dependency until a later slice proves the need.

### Frontend V2 incremental rebuild roadmap

1. **Foundation and contract closure** — keep docs/ADR current, close or explicitly
   defer frontend requirement gaps for first-run, attachments, Presence projection,
   slash discovery and voice conversation/TTS. **Slice 1 complete:** first-run and
   text conversation boot are now exposed through the frontend-facing backend
   boundary under `/api/frontend/*`.
2. **Minimal desktop shell** — secure Electron shell, backend connectivity, typed
   client skeleton, degraded/offline state, no Presence animation beyond factual
   placeholder. **Slice 2 complete:** `apps/frontend-v2/` implements the minimal
   Electron/React shell, first-run onboarding, text Conversation Log, compact
   composer, typed client, custom window controls and root
   `F:\Projetos\Synapse\Synapse.exe` launcher.
3. **First-run + text conversation hardening** — no usable agent opens onboarding; providers
   and models are factual; valid creation sets Primary/default; text turn and
   streaming open the normal workspace. **Slice 3 complete:** conversation state,
   NDJSON stream handling, history reconciliation, disconnected stream recovery,
   double-submit prevention and Conversation Log runtime UX are implemented without
   changing the approved elevated panel structure.
   **Micro-slice 3.5 complete:** the official root icon is preserved as source,
   governed frontend icon derivatives are used by Electron/root launcher, and the
   composer supports `/` slash-command discovery from the existing tool catalog.
4. **Conversation Log** — persistent/minimizable log, message pagination, stream
   lifecycle, cancellation, summaries and attachment references. **Slice 4 complete:**
   bounded recent history, progressive older-page loading, deterministic page merge,
   read-only real summaries and frontend cancellation boundary are implemented.
   Attachment presentation remains deferred until frontend-safe attachment ingestion
   and staging are closed.
5. **Voice/transcription** — explicit recording/transcription and transcript
   insertion into the same conversation. **Slice 5 complete:** the composer mic
   performs explicit recording, sends audio through the frontend Voice
   transcription boundary, inserts editable STT text into the composer, and then
   uses the normal text conversation path when the user sends it. No full
   Conversation Mode claim is made until integrated TTS and interruption gates
   pass.
6. **Conversation Mode** — continuous voice turn loop with integrated TTS.
   **Slice 6 complete:** the second composer voice control runs a continuous
   frontend loop over real STT, same-conversation text response persistence,
   governed TTS synthesis and browser playback. Playback interruption is
   supported frontend-side; provider-level generation cancellation/full duplex
   remains limited by current backend/provider semantics.
7. **Presence** — PixiJS visual projection for idle/listening/transcribing/thinking/
   responding/speaking/degraded states, driven only by backend/application facts.
   **Slice 7 complete:** the central placeholder is replaced by a factual
   Presence adapter and PixiJS scene for `idle`, `listening`, `transcribing`,
   `processing`, `speaking`, `interrupted`, `failed`, and `disconnected`,
   including real audio amplitude for microphone/playback states, reduced-motion
   budget, unfocused throttling, resize handling and CSS fallback.
8. **Activity/Constellation** — project activity snapshot/events/SSE into an organic
   visual projection with cursor invalid/resync handling.
   **Slice 8 complete:** the sidebar Activity button now toggles the central
   surface between Presence and a factual PixiJS constellation backed by the
   existing Operational Projection snapshot/events/SSE contracts. The frontend
   adapter owns semantic color mapping, stable asymmetric layout, hover/selection,
   stale/cross-project rejection, resync/degraded/disconnected states,
   deterministic aggregation and reduced-motion/fallback behavior.
9. **Insight** — hardware, provider, diagnostics and model recommendation panel.
   **Slice 9 complete:** the sidebar Insight action opens a responsive elevated
   internal panel over the workspace, backed by the existing System Insight report
   and Model Hub facts. It shows hardware, GPU/VRAM, provider/model inventory,
   backend recommendation groups, diagnostics, loading/ready/degraded/unavailable/error
   states and manual refresh without renderer hardware discovery or generic IPC.
10. **Settings elevated surface** — real configuration as an on-demand panel.
   **Slice 10 complete:** the sidebar Settings action opens a responsive elevated
   internal panel over the workspace. It loads real Model Hub defaults/catalog/providers,
   Provider Settings and Voice settings/providers, exposes only owned settings, saves
   through typed backend contracts, persists the frontend-owned reduced-motion preference
   through the governed Frontend V2 preference key, and preserves Presence/Activity,
   Conversation Log, conversation and project state behind it.
   **Micro-slice 10.5 complete:** custom frameless window controls now use an
   explicit React → preload allowlist → Electron IPC → sender BrowserWindow path
   for minimize, maximize, restore and close. Maximize/restore state is synchronized
   from real BrowserWindow events, drag/no-drag regions are preserved and a real
   Electron smoke exercises the preload IPC path.
11. **Commands, panels, attachments and notifications** — safe command intents,
   governed file staging/registration, additional on-demand panels and factual
   notification actions.
   **Slice 11 notification subset complete:** the titlebar/header now exposes a
   discreet notification bell with real unread badge state and an elevated internal
   popover backed by existing `/api/notifications` records and read/delete routes.
   Loading, empty, degraded and error states are explicit. Approval notifications
   are shown factually without duplicating approval resolution.
   **Slice 12 command routing subset complete:** the single composer now keeps
   ordinary text on the conversation path and routes slash-prefixed input through
   a typed command registry. `/activity`, `/insight` and `/settings` execute only
   frontend-local UI surface actions. `/project <project_id>` validates a bounded
   argument, confirms the project through the backend project contract and reopens
   the conversation through the frontend boundary with project scope. Backend tool
   catalog entries remain factual discovery items but are not directly executable
   from the composer without a governed route.
12. **Integration hardening** — contract tests, stream/error recovery, no simulated
    operational state, IPC allowlist/security gates, degraded provider paths.
13. **Packaging/release** — Windows packaging, sidecar lifecycle, update/recovery and
    release readiness gates.

First completed implementation slice: **Frontend V2 Slice 1 — contract closure
for first-run and text conversation boot**.

**Slice 13 complete:** the composer `+` now uses an allowlisted Electron picker,
governed frontend staging, backend-owned checksum/storage refs, conversation-scoped
registration, removable composer chips and refs on the next text turn. Advanced file
browser, previews, remote uploads, multimodal processing, advanced panels and final
packaging remain out of scope.

**Slice 14 complete:** frontend hardening moved Presence and Activity/Constellation
behind lazy React chunks, isolated visual load failures behind a local fallback,
revalidated renderer cleanup/security gates, and reduced the initial renderer chunk
from 539.88 kB to 265.25 kB. The Vite >500 kB warning is no longer emitted in the
Slice 14 build. Packaging/release remains out of scope.

Current governed campaign result: **SYNAPSE v0.01 READY**.
The packaged first-run, text conversation, Voice/STT/TTS and runtime validation
gates are green. The retired installed E2E harness is documented only as
historical context in `docs/legacy/installed-e2e-harness.md`; current Activity,
Settings, theme and conversation validation must use the real local runtime and
normal component/integration tests. The v0.01 installer checksum is generated in
`apps/frontend-v2/release/checksums.txt` and the clean install/uninstall smoke
completed with no orphan sidecar processes.
The canonical release slice list, criteria, evidence ledger, produced artifacts
and limitations are tracked in
[Frontend V2 Windows release plan](../frontend/RELEASE_PLAN.md).

## Completed phase — Deployment Runtime

Status: **IMPLEMENTED / OPERATIONALLY COMPLETE / FROZEN**

Authority: [Deployment Runtime architecture](../architecture/deployment-runtime.md)

Completed slices:

1. Discovery.
2. Identities / Value Objects / Provider-neutral Contracts.
3. State Machines.
4. Operational Ports.
5. Append-only Persistence / Replay / Corruption Handling.
6. Governance Authorization / Evidence Binding.
7. Artifact Eligibility / Custody / Provenance.
8. Environment / Target / Slot / Revision Operational Contracts.
9. Deployment Generation / Fencing / Idempotency.
10. Local Preparation Adapter.
11. Local Apply / Factual Receipts.
12. Independent Observation / Verification.
13. Local Rollback Preparation / Apply / Observation / Verification.

Current structural journey:

`prepare → apply → observe → verify`

Local rollback also reaches independent observation and verification. Deployment
is frozen and is not globally composed.

## Completed current-phase audit

### Deployment Runtime Slice 14 — E2E Readiness Audit

Status: **COMPLETE / APPROVED FOR FINAL-FREEZE AUDIT**

Objective: reconcile Slices 2–13 through controlled end-to-end journeys and decide
whether Deployment is ready for a separate final-freeze slice.

Required scope:

- nominal local prepare/apply/observe/verify journey;
- explicit rollback prepare/apply/observe/verify journey;
- negative authorization, eligibility, fencing and correspondence cases;
- partial/unknown outcomes, restart, replay and reconciliation;
- public-surface, dependency-edge, privacy and bootstrap-absence audit;
- focused Deployment tests, architecture tests and risk-proportional global gates;
- current evidence recorded without converting historical metrics into results.

Evidence: [Slice 14 audit](../audits/deployment-runtime-e2e-readiness-audit.md).

Dependencies already available: Deployment Slices 2–13, Governance binding,
Repository Runtime, Coding Sessions, Sandbox boundary/driver and Private Evals
evidence semantics.

## Completed final-freeze slice

### Deployment Runtime Slice 15 — Final Audit and Freeze

Status: **COMPLETE / FROZEN**

Objective: inventory and freeze exactly the implemented Deployment V1 public surface,
schema/record formats, authority boundaries, local adapter/integration edges and
documented operational limitations.

Required gates:

- dedicated freeze guard for modules/public exports/schema and governed edges;
- complete Deployment focused and E2E suites;
- architecture suite and graph/SCC checks;
- repository-wide Ruff and authoritative Mypy;
- deterministic global regression with exact file coverage;
- diff integrity, residual review and zero staged files.

Evidence: [final freeze audit](../audits/deployment-runtime-final-freeze-audit.md).

## Completed phase — Global Composition Root

### Slice 1 — Canonical Binding Inventory and Readiness Contract

Status: **COMPLETE / APPROVED**

The canonical bootstrap now exposes an immutable factual inventory for the nine
frozen contexts relevant to global readiness. Requirement, availability, current
binding mode and activation authority are separate. No local Composition Root is
imported or activated, and every entry remains `not-authorized` for production
activation.

Evidence: [Slice 1 audit](../audits/global-composition-root-slice-1-audit.md).

### Slice 2 — Deployment composition surface

Status: **COMPLETE / APPROVED**

Six required bindings remain non-global: Private Evals, Coding Sessions, Skills
Runtime Phase 2, Sandbox Execution Boundary, Repository Runtime and Deployment
Runtime. Deployment is the only required entry whose composition surface is absent;
the others already have local or legacy construction paths.

Target: **Deployment Runtime composition surface**, implemented first as
explicit/inert local construction with typed configuration, lifecycle and factual
health, still without global startup activation.

Required outcomes:

- one explicit local construction authority outside the Deployment domain;
- typed configuration/dependencies and owned-resource lifecycle;
- factual health that preserves unavailable and reconciliation states;
- no provider discovery, hidden fallback, API, Commands or startup activation;
- focused composition, architecture, Ruff, Mypy and diff gates;
- inventory updated from `absent/unavailable` to the exact validated local state.

Do not batch-wire contexts or infer production activation authority from Slice 1.

Evidence: [Slice 2 audit](../audits/global-composition-root-slice-2-audit.md).

### Slice 3 — inert Deployment container registration

Status: **COMPLETE / APPROVED**

Register the constructed, non-started Deployment runtime in the canonical
`RuntimeContainer`. The slice must derive only local configuration, perform no
persistence initialization, add no lifecycle resource and keep startup behavior
unchanged. Update the binding inventory to `global` only when the canonical container
owns the runtime and architecture tests prove import direction, inert construction and
absence of I/O.

Evidence: [Slice 3 audit](../audits/global-composition-root-slice-3-audit.md).

### Slice 4 — governed Deployment lifecycle activation

Status: **COMPLETE / APPROVED**

Deployment is an explicitly authorized required lifecycle resource. Application
construction and module import remain inert; lifespan startup opens the owned SQLite
resources, and shutdown closes them through the canonical lifecycle manager. The
inventory records `global / authorized / active` without authorizing other bindings.

Evidence: [Slice 4 audit](../audits/global-composition-root-slice-4-audit.md).

### Slice 5 — factual Deployment health projection

Status: **COMPLETE / APPROVED**

Canonical Health registers one read-only Deployment contributor. It reports lifecycle,
persistence, fencing and reconciliation facts without importing the Deployment
Composition Root from Health, constructing runtimes or invoking mutating operations.

Evidence: [Slice 5 audit](../audits/global-composition-root-slice-5-audit.md).

### Slice 6 — Private Evals global-composition compatibility audit

Status: **COMPLETE / APPROVED**

Determine the smallest valid global binding for the already frozen Private Evals local
Composition Root. Reconcile its eager SQLite construction, explicit unavailable external
bindings, close semantics and absence of a separate start phase against the canonical
container/lifecycle contract. This slice is analysis and governance only: do not change
Private Evals frozen contracts or activate it. Persist an exact, testable next slice only
if no architecture, data or security decision remains.

The audit found no unresolved decision. The frozen composer opens five SQLite stores
eagerly, exposes idempotent `close()` and represents all four external capabilities
explicitly as available, disabled or unavailable. Therefore canonical application
construction must not call it. A bootstrap-owned deferred slot can preserve the frozen
contract, compose once during lifecycle startup with explicit unavailable bindings, and
close the handle during lifecycle shutdown.

Evidence: [Slice 6 audit](../audits/global-composition-root-slice-6-audit.md).

### Slice 7 — deferred Private Evals lifecycle binding

Status: **COMPLETE / APPROVED**

Add a typed bootstrap-owned deferred slot for `PrivateEvalsRuntimeHandle`. Construction
must be inert; required lifecycle startup composes exactly once at an owned SQLite path,
using explicit `not_configured` unavailable bindings for all four external capabilities;
shutdown closes the handle. Do not modify frozen Private Evals contracts, expose API or
Commands routes, execute eval cases, or infer external capability authority. Register the
slot in the canonical container and keep the inventory inert until lifecycle activation is
validated.

The canonical container now owns a typed deferred slot. Application construction does
not create the Private Evals database; required lifecycle startup composes the frozen
runtime with four explicit unavailable bindings and shutdown closes it. The inventory
records Private Evals as `global / authorized / active` without claiming external eval
execution capability.

Evidence: [Slice 7 audit](../audits/global-composition-root-slice-7-audit.md).

### Slice 8 — factual Private Evals health projection

Status: **COMPLETE / APPROVED**

Register a Health-owned, read-only contributor for the deferred Private Evals slot.
Project only lifecycle, persistence, read-only/commands/query availability, external
capability states and limitations through neutral immutable facts. Preserve degraded
status while required external capabilities are unavailable; do not import Private Evals
from Health, expose execution, or make Health a lifecycle authority.

Health now reports the deferred slot before startup and the frozen runtime readiness
after startup through neutral immutable facts. Local persistence is available while the
four external capabilities remain explicitly unavailable, so the required component is
factually degraded rather than promoted to ready.

Evidence: [Slice 8 audit](../audits/global-composition-root-slice-8-audit.md).

### Slice 9 — Coding Sessions global-composition compatibility audit

Status: **COMPLETE / APPROVED**

Determine the smallest valid global binding for the frozen
`coding_sessions_composition` surface. Reconcile construction I/O, lifecycle ownership,
required dependencies, factual health and existing bootstrap interactions. This slice is
analysis and governance only: do not change frozen Coding Sessions contracts or activate
the runtime. Persist an exact next slice when no architecture, data or security decision
remains.

The audit found eager SQLite migration in `CodingSessionsRuntimeBuilder.build()`, an
idempotent close, factual health, and optional reference-only integrations. Canonical
construction therefore must remain inert. A bootstrap-owned deferred slot can build once
during lifecycle startup with no integrations enabled and no managed external resources,
then close during shutdown. No unresolved decision remains.

Evidence: [Slice 9 audit](../audits/global-composition-root-slice-9-audit.md).

### Slice 10 — deferred Coding Sessions lifecycle binding

Status: **COMPLETE / APPROVED**

Add a typed bootstrap-owned deferred slot. Construction must perform no migration or
database I/O; lifecycle startup builds exactly one local runtime with explicit empty
integration authority and lifecycle shutdown closes it. Register the slot in the canonical
container and inventory. Do not enable Repository, Governance, Workers, Sandbox, Private
Evals or Deployment integrations and do not expose API, Commands or execution.

The canonical container now owns an inert deferred slot. Lifecycle startup performs the
SQLite migration and builds exactly one runtime; shutdown closes it. Persistence is
supported while every cross-context integration remains unavailable. The inventory
records `global / authorized / active` without granting integration authority.

### Slice 11 — factual Coding Sessions health projection

Status: **COMPLETE / APPROVED**

Register a Health-owned read-only contributor through neutral immutable facts. Report
slot lifecycle, persistence/schema health, managed-resource health and every integration
capability state. Preserve degraded status while required integrations are unavailable;
do not import Coding Sessions from Health or activate integrations.

Health now consumes neutral immutable facts from the deferred slot. Persistence and
schema are available after startup, while all cross-context integrations remain factual
and unavailable; the component is therefore degraded rather than falsely ready.

### Slice 12 — Skills Runtime Phase 2 global-composition compatibility audit

Status: **COMPLETE / APPROVED**

Audit the current Skills feature builder and `skills.composition` ownership to determine
whether the required Phase 2 binding is already globally constructed, which lifecycle
resources and Health contributor it owns, and what factual gap remains. Analysis and
governance only; do not change frozen Skills contracts, install/activate skills or execute
scripts.

The legacy `SkillsFeatureBuilder` is already globally constructed and owns its optional
legacy Health projection, but it is not the frozen Phase 2 composition. The canonical
`synapse.skills.composition` eagerly verifies/migrates SQLite and owns idempotent close.
It can coexist under a distinct typed container field with compatibility disabled; no
installation, activation or script execution occurs during construction.

### Slice 13 — deferred Skills Runtime Phase 2 lifecycle binding

Status: **COMPLETE / APPROVED**

Add a distinct bootstrap-owned deferred slot for `SkillsRuntimeComposition`. Construction
must be inert; lifecycle startup uses the owned SQLite path, migrate-if-needed, explicit
integrity policy, disabled legacy compatibility and a bounded query limit. Shutdown closes
the runtime. Do not replace the legacy Skills facade, install/activate skills, execute
scripts or expose delivery surfaces.

The canonical container now owns a distinct deferred Phase 2 slot. Lifecycle startup
migrates the owned SQLite database with compatibility disabled; shutdown closes it. The
legacy Skills facade remains intact and no execution/installation authority was added.

### Slice 14 — factual Skills Runtime Phase 2 health projection

Status: **COMPLETE / APPROVED**

Register a distinct Health-owned contributor for Phase 2 through neutral immutable
facts. Report lifecycle, schema/database reachability, migration, integrity/foreign-key
status and compatibility state. Do not conflate it with the existing optional legacy
Skills contributor, invoke integrity verification or activate compatibility.

Health now exposes `skills.phase2` separately from the optional legacy contributor.
Schema and database reachability make the component ready after startup while integrity
remains factually `not_checked` and compatibility remains disabled.

### Slice 15 — Sandbox Execution Boundary global-composition compatibility audit

Status: **COMPLETE / SECURITY DECISION PENDING**

Audit `sandbox_composition` and its relationship to the optional concrete driver. Identify
construction I/O, lifecycle, required injected ports, factual health/reconciliation and
whether a provider-neutral local binding can start without authorizing execution. Analysis
and governance only; do not start processes, materialize secrets, enable network access or
change frozen Sandbox contracts.

The local builder eagerly migrates SQLite and can remain completely non-executable with
all ports/features absent. However, it requires one concrete `SandboxAdmissionPolicy`.
The frozen architecture defines policy structure and decision semantics but no canonical
operational policy values. Bootstrap cannot choose approval requirements, accepted
capabilities/resources or minimum isolation profiles without security authority. No
Sandbox global activation was added. Independent module work continues.

Evidence: [Slice 15 audit](../audits/global-composition-root-slice-15-audit.md).

### Slice 16 — Repository Runtime global-composition compatibility audit

Status: **COMPLETE / APPROVED**

Audit `repository_runtime_composition` for construction I/O, lifecycle, required ports,
fencing/reconciliation health and safe provider-neutral local startup. Analysis and
governance only; do not mutate repositories, create restore points, execute Git, change
frozen contracts or activate mutation authority.

The builder eagerly migrates SQLite and probes the local adapter, but performs no
repository mutation without separately bound plans/materials. It supports an inert slot
using the configured project root, derived stable identities, an owned restore root,
no Coding Sessions adapter and no mutation/recovery artifacts. Staging, commit and push
remain explicitly unsupported.

### Slice 17 — deferred Repository Runtime lifecycle binding

Status: **COMPLETE / APPROVED**

Add a bootstrap-owned deferred slot for the provider-neutral local runtime. Construction
must perform no SQLite/Git I/O; lifecycle startup builds once against the configured
project root with no mutation/recovery plans or Coding Sessions adapter, and shutdown
closes it. Register container/inventory ownership without executing repository mutation.

The canonical container owns a deferred runtime bound to the configured project root.
Startup performs only persistence migration and allowlisted factual Git capability probes;
no mutation/recovery artifacts or Coding Sessions adapter are configured. Shutdown closes
the runtime.

### Slice 18 — factual Repository Runtime health projection

Status: **COMPLETE / APPROVED**

Register a Health-owned contributor through neutral immutable facts. Report lifecycle,
persistence/schema, adapter/Git availability, platform, supported/degraded/unsupported/
unavailable feature sets, Coding Sessions configuration and managed-resource health. Do
not expose mutation services or import Repository Runtime from Health.

Health now reports Repository Runtime through neutral facts. Local persistence, schema,
adapter and Git are ready; degraded and unsupported features remain visible, Coding
Sessions integration remains absent and Health exposes no mutation service.

### Slice 19 — optional binding classification audit

Status: **COMPLETE / APPROVED**

Audit Concrete Sandbox Driver, Voice / Audio / Perception and Search Runtime against the
canonical inventory. Prove their optional/capability-limited classification, current
construction mode, absence of hidden fallback and non-blocking readiness semantics.
Do not activate drivers/providers, add lifecycle resources or widen authority.

Voice / Audio / Perception is already constructed by the canonical interaction feature
and is recorded as active legacy-global. Concrete Sandbox Driver and Search remain local,
capability-limited and inert. No hidden fallback or new lifecycle resource was added; all
three remain intentionally optional and do not block readiness.

### Slice 20 — Global Composition Root final freeze audit

Status: **COMPLETE / APPROVED / FROZEN**

Reconcile the complete nine-binding inventory, lifecycle order, Health surface, import
graph, failure rollback and documentation. Classify the required Sandbox Execution
Boundary as locally available but not globally activated because no canonical operational
admission policy exists; retain it as an explicit Backend Readiness blocker. Execute full
architecture, bounded-context, global regression, Ruff, authoritative Mypy, SCC/diff and
security/forbidden-surface gates. Do not begin the Final Backend Readiness Campaign.

The nine-binding inventory is reconciled. Five required bindings are global and active:
Private Evals, Coding Sessions, Skills Runtime Phase 2, Repository Runtime and Deployment
Runtime. Voice / Audio / Perception is optional legacy-global and active. Concrete Sandbox
Driver and Search remain optional, capability-limited and local/inert. The required
Sandbox Execution Boundary remains locally available but not globally activated because
no canonical operational admission policy exists; it is the explicit readiness blocker.

Current final gates: focused 25 passed; architecture 265 passed; global regression 4,383
passed, 5 skipped and 4 subtests passed; global Ruff passed; authoritative Mypy passed on
772 source files; runtime/source graphs remained 301/336 edges with no new SCC; scoped
diff integrity passed with pre-existing line-ending warnings only.

Evidence: [final freeze audit](../audits/global-composition-root-final-freeze-audit.md).

Module status: **MODULE_COMPLETE — HUMAN_CHECKPOINT_FOR_PUBLICATION**

The required publication checkpoint is complete in the user-owned
`LinkedIn/Global Composition Root` package with five hash-verified final visuals (one cover
and four real-code views), post, prompts and publication notes. The earlier destination
visuals were replaced only after explicit user authorization; the new generated source was preserved.

No `NEXT` slice exists inside this module. The **Final Backend Readiness Campaign** is a
new module and requires an explicit human transition. Backend remains **NOT READY**.

After Global Composition Root is complete, the next macro phase remains the
**Final Backend Readiness Campaign**: inventory, static architecture, wiring, global
E2E journeys, real bootstrap, failure/recovery and an independent decision.

## Current phase — Final Backend Readiness Campaign

Transition authorization: **GRANTED BY USER**.

Campaign authority: validate and, only where an evidence-backed finding permits it,
apply the smallest corrective change under an existing task profile. The campaign does
not authorize production access, external credentials, destructive data operations,
dependency changes, frozen-contract changes or security-policy selection. Historical
results are context only; every readiness claim requires current evidence.

### Slice 1 — canonical readiness inventory and campaign contract

Status: **COMPLETE / APPROVED**

Reconcile the current module baseline, Backend READY gate and existing validation
surfaces into one bounded campaign. Define exact slice order, evidence ownership,
prohibitions and stopping conditions. Documentation and governance only; do not change
runtime behavior or convert historical gate results into current evidence.

Evidence: [Slice 1 audit](../audits/backend-readiness-campaign-slice-1-audit.md).

### Slice 2 — static architecture and frozen-surface reconciliation

Status: **COMPLETE / APPROVED**

Inventory the current backend packages, frozen-context public surfaces, architecture
allowlists, dependency graph and SCC baselines. Execute the current architecture suite,
freeze guards and graph tooling. Classify stale baselines, undeclared edges and frozen
surface drift without modifying frozen contracts. Persist exact findings and a governed
Slice 3 only when no architecture decision remains.

Required evidence:

- exact package and frozen-context inventory;
- architecture and freeze test results executed now;
- runtime/source graph counts and SCC comparison;
- residual/stale-baseline classification;
- scoped diff integrity and zero staging;
- explicit decision: `APPROVED`, `CORRECTIVE_SLICE_REQUIRED` or
  `HUMAN_DECISION_REQUIRED`.

Evidence: [Slice 2 audit](../audits/backend-readiness-campaign-slice-2-audit.md).

### Slice 3 — canonical bootstrap and required-binding audit

Status: **COMPLETE / APPROVED WITH EXPLICIT READINESS BLOCKER**

Audit real application construction, startup, shutdown, lifecycle rollback, Health
projection and all required/optional binding classifications. Exercise bootstrap using
isolated temporary data only. Sandbox remains inert unless a separately authorized
operational admission policy exists.

Evidence: [Slice 3 audit](../audits/backend-readiness-campaign-slice-3-audit.md).

### Slice 4 — global E2E journey campaign

Status: **COMPLETE / APPROVED**

Execute representative cross-context journeys through canonical boundaries, covering
success, denied/unavailable capabilities and factual handoffs. Tests must not contact
production, expose secrets or treat mock success as proof of an unavailable external
provider.

Evidence: [Slice 4 audit](../audits/backend-readiness-campaign-slice-4-audit.md).

### Slice 5 — failure, restart, replay and reconciliation campaign

Status: **COMPLETE / APPROVED**

Exercise durable contexts and lifecycle failure paths with isolated test state. Preserve
unknown/partial outcomes, exact identity and no-repeat semantics; replay never implies
external reexecution.

Evidence: [Slice 5 audit](../audits/backend-readiness-campaign-slice-5-audit.md).

### Slice 6 — security, egress, secrets and authority audit

Status: **COMPLETE / APPROVED WITH EXPLICIT SANDBOX BLOCKER**

Run repository-scoped safe checks for forbidden execution surfaces, credential leakage,
egress defaults, approval/authority bypass and fail-open behavior. Do not read secret
values, probe external systems or select the missing Sandbox admission policy.

Evidence: [Slice 6 audit](../audits/backend-readiness-campaign-slice-6-audit.md).

### Slice 7 — authoritative global quality gates

Status: **COMPLETE / APPROVED**

Run exact-scope global regression, architecture, Ruff, authoritative Mypy, graph/SCC and
diff/worktree-integrity gates. Partition deterministically only if required by the
execution window and prove exact coverage without duplicate test files.

Evidence: [Slice 7 audit](../audits/backend-readiness-campaign-slice-7-audit.md).

### Slice 8 — canonical documentation reconciliation and independent decision

Status: **COMPLETE / BACKEND NOT READY**

Reconcile all current campaign evidence and decide `Backend READY` or `Backend NOT READY`
without weakening any gate. A required unresolved Sandbox binding, unavailable critical
gate or material security/authority finding keeps the backend `NOT READY`. Complete the
module publication checkpoint only after this independent decision.

Independent decision: **Backend NOT READY**.

All current static, E2E, failure/recovery, security-test and global quality gates passed,
but the canonical inventory still contains one required readiness blocker: Sandbox
Execution Boundary is `available / local-opt-in / not-authorized / inert`. No canonical
operational admission policy defines approval requirements, accepted capabilities,
resource constraints or minimum isolation. The campaign cannot invent these security
values or classify a required inert binding as ready.

Evidence: [final decision audit](../audits/backend-readiness-campaign-final-decision.md).

Campaign status: **HUMAN_DECISION_REQUIRED**

Decision required: authorize and govern one concrete operational Sandbox admission
policy for the intended local backend environment, or explicitly change the product
requirement that makes the Sandbox Execution Boundary required. The first option is the
technical recommendation because it preserves the frozen readiness contract. Either
option is a security/product decision outside autonomous campaign authority.

No publication checkpoint was executed because the Backend READY gate is not satisfied.
After the decision and any separately authorized implementation, rerun the affected
bootstrap, security, E2E and authoritative global gates before reconsidering readiness.

## Current phase — Sandbox Operational Admission Policy

Transition authorization: **GRANTED BY USER** for the recommended security-governed path.

The module owns concrete local policy values and bootstrap activation only. It preserves
the frozen Sandbox domain contract, does not authorize production access, does not enable
external network/secrets, and does not claim driver capabilities that the Windows host
cannot enforce.

### Slice 1 — authority, contract and host-capability audit

Status: **COMPLETE / APPROVED**

Audit the frozen `SandboxAdmissionPolicy`, local composition requirements, Windows driver
capability classifications and readiness blocker. Select the narrowest fail-closed policy
baseline consistent with the user's authorization. Analysis and governance only; do not
start processes, change host security, access network/secrets or modify frozen contracts.

Evidence: [Slice 1 audit](../audits/sandbox-operational-policy-slice-1-audit.md).

### Slice 2 — canonical fail-closed policy factory

Status: **COMPLETE / APPROVED**

Add one bootstrap-owned factory for the authorized local admission policy. Require every
fact dimension to be complete; require fresh policy and approval facts; require exact
approval, external capability/resource grants and proven isolation support; allow only the
exact `python` capability; prohibit wildcards; select
`sandbox-profile:windows-job-contained-v1`; preserve closed outcome precedence. Add
focused deterministic tests for canonical identity, denial, staleness, incompleteness and
unavailable isolation. Do not compose the runtime or activate lifecycle in this slice.

Evidence: [Slice 2 audit](../audits/sandbox-operational-policy-slice-2-audit.md).

### Slice 3 — deferred global Sandbox runtime binding

Status: **COMPLETE / APPROVED**

Add a bootstrap-owned deferred slot using the canonical policy and owned SQLite path.
Construction remains inert; lifecycle startup builds once without materialization,
supervision, Skills handoff or concrete-driver ports; shutdown closes it. Update the
binding inventory only after lifecycle activation is proven.

Evidence: [Slice 3 audit](../audits/sandbox-operational-policy-slice-3-audit.md).

### Slice 4 — factual Sandbox Health projection

Status: **COMPLETE / APPROVED**

Register a neutral Health contributor for lifecycle, persistence, schema, policy identity,
configured adapters, execution-port availability and recovery findings. Health must expose
that execution is unavailable; it cannot authorize or activate execution.

Evidence: [Slice 4 audit](../audits/sandbox-operational-policy-slice-4-audit.md).

### Slice 5 — final security/freeze and readiness reconciliation

Status: **COMPLETE / APPROVED**

Run focused Sandbox/policy/bootstrap tests, architecture/freeze gates, security authority
checks, global regression, Ruff, authoritative Mypy, graph/SCC and integrity gates. Rerun
the affected Backend Readiness decision. Do not declare readiness if any required gate or
binding remains unsatisfied.

Evidence: [Slice 5 audit](../audits/sandbox-operational-policy-slice-5-audit.md).

Module status: **MODULE_COMPLETE — HUMAN_CHECKPOINT_FOR_PUBLICATION**

The required Sandbox Execution Boundary is now globally bound, authorized and active
through an inert-at-construction lifecycle slot and a canonical fail-closed policy. This
does not activate real workload execution: the Concrete Sandbox Driver remains
intentionally optional and capability-limited, and Health reports execution unavailable.

Independent readiness decision: **Backend READY**. The former required-binding blocker
is satisfied and every final gate listed below has current green evidence. Publication
remains a separate human checkpoint and does not alter runtime authority.

The publication checkpoint package is complete in the user-owned
`LinkedIn/Sandbox Operational Admission Policy` directory: five final visuals (one
conceptual cover and four real-code VS Code-like renders), the Portuguese post, prompts
and publication notes. Every source/destination copy was SHA-256 verified.

## Retired phase — Electron ADE Operational Foundation

Retirement status: **ELECTRON ADE REMOVED / FRONTEND NOT IMPLEMENTED** (2026-08-21).

The implementation, desktop packaging and release artifacts from this phase were removed
under [ADR 0119](../adr/0119-retire-electron-ade.md). The records below are retained as
historical evidence only. Backend-owned Operational Projection, Command Authority and
Voice capabilities remain reusable for a future clean frontend baseline.

Transition authorization: **GRANTED BY USER** for the frontend/backend integration phase.

The stabilized backend remains the factual baseline. Frontend presentation, layout,
particles, color, motion and GPU scene state do not enter backend domain contracts.

### Slice 1 — audit, architecture and dependency-free frontend state foundation

Status: **COMPLETE / APPROVED**

Inventory the removed/current frontend, canonical backend events, project identity,
resource APIs, Voice frontend events and transport gaps. Accept ADR 0117. Add only pure
TypeScript project activity consumption types, project-scoped application state, panel
lifecycle separation and a contextual slash-command registry. No dependency installation,
Electron shell, network transport, backend change, Dockview or GPU rendering.

Evidence: [Slice 1 validation](../validation/electron-ade-operational-foundation-slice-1.md).

### Slice 2 — backend operational projection contracts

Status: **COMPLETE / APPROVED**

Define a client-neutral, project-scoped read-model contract and deterministic reducer over
typed source facts. Require monotonic revisions, source references, safe metadata,
unknown/degraded state and cross-project rejection. Do not add transport, persistence,
bootstrap wiring or presentation concepts.

Evidence: [Slice 2 audit](../audits/electron-ade-operational-projection-slice-2-audit.md).

### Slice 3 — source normalization and minimization

Status: **COMPLETE / APPROVED**

Normalize already-authorized, explicitly project-scoped source records into projection
facts. Preserve source references, allowlist scalar metadata, reject missing project scope
and keep unmapped state unknown. No domain imports or composition wiring.

Evidence: [Slice 3 audit](../audits/electron-ade-operational-projection-slice-3-audit.md).

### Slice 4 — cursor, replay and resynchronization semantics

Status: **COMPLETE / APPROVED**

Define opaque versioned cursors, duplicate/stale/gap behavior, retained-event replay,
cross-project rejection and explicit snapshot resynchronization independently from
transport.

Evidence: [Slice 4 audit](../audits/electron-ade-operational-projection-slice-4-audit.md).

### Slice 5 — EventBus bridge and frontend transport

Status: **COMPLETE / APPROVED**

Compose a read-only bridge from redacted project-scoped EventBus facts, rebuild feeds from
durable events, expose HTTP snapshot/resume and validate SSE against actual lifecycle and
security requirements. Do not attach projectless legacy events to an inferred project.

Evidence: [Slice 5 audit](../audits/electron-ade-operational-projection-slice-5-audit.md).

### Governed sequence

### Slice 6 — Electron main/preload security foundation

Status: **COMPLETE / APPROVED**

Electron is pinned after dependency review. The main window uses context isolation,
sandboxing and disabled Node/webview integration; navigation, new windows, permissions and
downloads are denied. The preload exposes a narrow allowlisted bridge.

Evidence: [Slice 6 audit](../audits/electron-ade-slice-6-security-audit.md).
[Dependency review](../audits/electron-ade-dependency-review.md).

### Slice 7 — command-first shell and versioned project layout persistence

Status: **COMPLETE / APPROVED**

The shell opens factual project snapshots through a loopback-only main-process adapter.
Layout records are schema-versioned, validated and keyed by canonical project ID.

Evidence: [Slice 7 audit](../audits/electron-ade-slice-7-shell-audit.md).

### Slice 8 — modular Dockview panels and Inspector

Status: **COMPLETE / APPROVED**

Dockview hosts Activity, Inspector and contextual panels. Panel close/open state remains
presentation state and never implies an operational lifecycle transition.

Evidence: [Slice 8 audit](../audits/electron-ade-slice-8-panels-audit.md).

### Slice 9 — shared Presence/Swarm visualization adapter

Status: **COMPLETE / APPROVED**

A deterministic bounded adapter derives scene state from operational entities. Pixi renders
that state when available and preserves Activity as the factual accessible fallback.

Evidence: [Slice 9 audit](../audits/electron-ade-slice-9-visualization-audit.md).

### Slice 10 — Voice, accessibility and degradation

Status: **COMPLETE / APPROVED**

Voice presentation preserves factual backend state, reduced-motion is honored, GPU work is
budgeted and unavailable capabilities remain explicitly unavailable.

Evidence: [Slice 10 audit](../audits/electron-ade-slice-10-accessibility-audit.md).

### Slice 11 — packaging and frontend readiness campaign

Status: **COMPLETE / APPROVED**

The Electron shell builds, passes its focused/security tests, opens in smoke mode and
packages to a Windows unpacked artifact. Backend projection, architecture and global
regression gates are current. Backend readiness remains a separate decision.

Evidence: [Slice 11 audit](../audits/electron-ade-slice-11-readiness-audit.md).

Automatic transitions are allowed only within this frontend integration module when the
current slice is validated and the next slice has no unresolved architecture, security,
product or dependency decision. Backend domain restructuring and dependency installation
remain separately governed.

Frontend module status: **RETIRED / REMOVED**.

Current frontend status: **NOT IMPLEMENTED**.

## Backend READY gate

Backend may become `READY` only with current evidence for all of the following:

- Deployment frozen;
- global composition and bootstrap audited;
- every required binding classified as available, unavailable or intentionally
  optional without hidden fallback;
- global E2E journeys;
- failure, restart, replay and reconciliation campaign;
- current architecture and freeze gates;
- current global regression with exact scope;
- current global Ruff;
- current authoritative global Mypy;
- security, egress, secrets and authority audit;
- reconciled canonical documentation;
- independent readiness decision.

Any missing or failed critical requirement keeps the backend `NOT READY`.

## Operational workflow

`.agent/` owns persistent governance, profiles and gates.
`.agents/skills/` contains operational workflows such as `$continue-backend`.
The skill must select exactly the `NEXT` slice above, use a profile that exists in
`.agent/TASK_PROFILES.md`, persist current evidence here and continue
automatically through subsequent slices of the same bounded context when the
current slice is complete, validated and no architectural/product/security
decision is pending.

The skill must stop only when the bounded context reaches its final intended
state and is frozen, or on a genuine `HUMAN_DECISION_REQUIRED`.

## Retired Windows Release Candidate campaign

Status: **HISTORICAL / SUPERSEDED BY ELECTRON ADE REMOVAL** (2026-08-21).

Historical RC.1 result; superseded by the RC.2 closure below.

Backend readiness remains **READY**. The reproducible Windows installer, bundled sidecar,
clean install, restart, failure visibility and uninstall lifecycle were validated. Product
Release Candidate readiness is blocked by the absence of a governed authenticated desktop
command transport and by the absence of an approved application icon. No portable artifact
was produced and the technical installer is explicitly unsigned.

Evidence: [Windows Release Candidate campaign final audit](../audits/windows-release-candidate-campaign-final-audit.md).

### Retired Windows Release Candidate 0.1.0-rc.2 closure

Status: **HISTORICAL / SUPERSEDED BY ELECTRON ADE REMOVAL** (2026-08-21).

The Desktop Command Authority Boundary now provides sidecar-lifetime authentication,
explicit `task.create` authorization, project/session scoping, validation, durable
reserve-before-effect idempotency and command-to-projection correlation. The approved icon
is integrated into Windows application and installer surfaces. Clean installed command,
restart/restore and uninstall evidence passed. Distribution remains explicitly `UNSIGNED`
and is not a signed public distribution.

Evidence: [RC 0.1.0-rc.2 final audit](../audits/windows-release-candidate-rc2-final-audit.md).

### Retired Desktop UX 0.1.0-rc.3 campaign

Status: **HISTORICAL / SUPERSEDED BY ELECTRON ADE REMOVAL** (2026-08-21).

The root daily-use entry is now the real portable
`F:\Projetos\Synapse\Synapse.exe`; the NSIS installer remains separate. The Electron input
routes ordinary text through the canonical Primary Agent conversation and slash-prefixed
text through contextual command discovery. A frameless integrated title bar, minimal
window-control IPC and single-instance focus/restore are implemented and validated.

The clean packaged conversational E2E is blocked because no governed Primary Agent is
assigned in new user data. The desktop preserves that fact and does not choose one
implicitly. The campaign remains NOT READY until that independent assignment exists and
the installed conversational smoke passes. All other current gates pass, including 25
Electron tests, 268 architecture tests, global Ruff, authoritative Mypy on 788 files and
the full regression with 4,421 passed, 5 governed skips and 4 subtests.

Next: assign the intended Primary Agent through the existing governed flow, make its local
model provider available and rerun the packaged plain-message smoke.

Evidence: [Desktop UX 0.1.0-rc.3 final audit](../audits/desktop-ux-rc3-final-audit.md).

### Retired Shell Experience 0.1.0-rc.4 campaign

Status: **HISTORICAL / SUPERSEDED BY ELECTRON ADE REMOVAL** (2026-08-21).

The shell now has one composer, complete contextual slash discovery, on-demand bounded
Dockview panels, permanent Presence, factual Voice states, guarded Swarm/deep-work
activation, an in-app notification bell/popover, secure local attachment staging and a
simplified integrated header. Presence, panels and Swarm share the existing project
projection; panel lifecycle remains independent from operational lifecycle.

Current evidence: 33 Electron tests, TypeScript build, source and packaged visual smokes,
packaged application smoke, npm production audit, installer lifecycle and zero orphan
processes pass. The root portable is current and hash-matches its governed release artifact.

The campaign cannot declare READY while a clean profile has no governed Primary Agent:
plain text correctly reaches the canonical boundary but no agent may be selected implicitly.

Next: assign the intended Primary Agent, ensure its local provider is available and rerun
the clean packaged conversational smoke.

Evidence: [Shell Experience 0.1.0-rc.4 final audit](../audits/shell-experience-rc4-final-audit.md).

### Retired First Run Agent Onboarding

Status: **HISTORICAL / SUPERSEDED BY ELECTRON ADE REMOVAL** (2026-08-21).

Electron startup now gates the normal workspace on the canonical Primary Agent state.
When no usable agent exists, a bounded onboarding creates one only from a live chat-usable
model/provider and assigns it through the existing Primary Agent runtime. Existing agents
are reused, ambiguous choices remain explicit, failures stay inside onboarding and the
decision is re-evaluated from backend truth on every startup; no frontend completion flag
or duplicate Agent store was introduced.

Current evidence: 40 Electron tests, TypeScript build and the two canonical Primary Agent
initial-setup/restart acceptance tests pass. Packaging was not run because it is outside
this slice.

Evidence: [First Run Agent Onboarding slice audit](../audits/first-run-agent-onboarding-slice-audit.md).
