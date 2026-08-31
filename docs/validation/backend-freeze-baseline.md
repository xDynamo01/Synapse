# Backend Freeze Baseline

## Intelligence Trust Boundary addendum (2026-07-15)

Intelligence Trust Boundary is implemented outside the global SCC with
canonical assets, classification/ownership, provider trust, purpose,
minimization/redaction, manifests, scoped approvals, derived provenance and an
immutable redacted ledger. Model and declared Tool/MCP external paths are
gated; current Speech/Vision providers remain local. OpenAPI intentionally
advances to 494 paths / 550 operations / 128 schemas; Commands to 410 canonical
/ 434 names; Health to 35 components. Eight acceptance scenarios pass. Final
global pytest is 1,208 passed / 2 skipped in 851.42 s, as recorded in
`intelligence-trust-boundary-finalization.md`; Ruff and `git diff --check` are
green (the latter reports working-copy LF/CRLF warnings only). Backend remains
NOT READY.

## Project Governance + RFC addendum (2026-07-15)

Project Governance is implemented outside the global SCC with project
manifests, human-editable RFC revisions/checksums, structured reviews, gate,
plans, evidence/criteria, restart and controlled API/Commands/Health. OpenAPI
intentionally advances to 479 paths / 532 operations / 121 schemas; Commands
to 394 canonical / 418 names; Health to 34 components. Architecture is 103/103
and the eight required acceptance scenarios pass. Global pytest is 1,177
passed / 2 skipped in 821.28 s; Ruff and `git diff --check` are green (the
latter reports working-copy LF/CRLF warnings only). Backend remains NOT READY.

## Skills Runtime Phase 1 addendum (2026-07-15)

Skills Runtime is implemented outside the global SCC with versioned packages,
metadata discovery, deterministic resolution, progressive loading,
assignments/leases, storage adapters, Tool Execution Boundary, optional health,
controlled API/Commands and a Researcher migration pilot. OpenAPI intentionally
advances from 443/490/107 to 460 paths / 508 operations / 110 schemas. Phase 2,
SDK, frontend, Workspace and Repository runtimes remain unimplemented.
Final gates: architecture 97 passed; integrated affected-domain regression 144
passed; seven named Skills acceptance scenarios passed; global 1,155 passed /
2 skipped; ruff passed; `git diff --check` passed
with pre-existing line-ending warnings. Commands are 372 canonical / 396 names;
Health has 33 components including optional `skills`.

## Attention/World State boundary removal addendum (2026-07-15)

The concrete return dependency `world_state -> attention` has been removed.
Attention now reads the current snapshot through the one-method
`WorldStateReadPort`; `WorldStateReadAdapter` and the existing runtime event
projector are owned and bound exclusively by bootstrap. World State imports no
Attention runtime or model, while Agent Loop retains its existing coordination
of both runtimes.

The governed graph changed only from 248 to 247 edges and from two to one
non-trivial SCC. The former `attention/world_state` 2/2 SCC disappeared; the
remaining global SCC is unchanged at 13/35 and the exact-module graph remains
acyclic. Architecture tests are 92 passed. The global suite is 1,136 passed / 2
skipped, ruff and `git diff --check` pass, and OpenAPI remains frozen at 443
paths, 490 operations/unique operation IDs and 107 schemas. Detailed evidence
is in `architecture-stabilization-attention-world-state-boundary.md`.

## Audio/Speech concrete-boundary removal addendum (2026-07-15)

`AudioRuntime` no longer imports or annotates the concrete
`SpeechAdapterRuntime`. Audio owns the two-method `SpeechExecutionPort` and the
existing `SpeechAdapterRuntime` satisfies it structurally; the sole production
binding remains `bootstrap/features/interaction.py`. No adapter was added.

The governed graph changed only from 249 to 248 edges and from three to two
non-trivial SCCs. The former `audio/speech_adapters` 2/2 SCC disappeared;
SCC-01 remains 13/35 and `attention/world_state` remains 2/2. The exact-module
graph remains acyclic.

OpenAPI is byte-for-byte structurally identical under canonical JSON:
443 paths, 490 operations, 107 schemas, zero duplicate operation IDs, schema
SHA-256 `94a03c0c8ce5a829e0af5f3754f626bbcf83d442a4050ff76dffe241360f1a34`
and operation matrix SHA-256
`7537ec22d3406f73ceb7792c454d51fc6c2271e768e15029b15a6d66648b93a1`.
Global pytest collected 1,128 tests: 1,126 passed and 2 skipped in 1,131.59 s.
Ruff and `git diff --check` pass. Voice, Speech Pipeline, Conversation Mode,
Voice Message, Providers, Health, Readiness, Commands, API, Context Fusion,
Tools, Missions, Storage, Primary/Ephemeral Agents, Swarm and Model Router were
not changed. The backend remains **NOT READY**.

## Agent kinds addendum (2026-07-14)

Agent Creator was removed and replaced by no alias. AgentProvisioning remains the
only persistent creation authority; Primary binding and Mission/Swarm-owned
ephemeral lifecycle are explicit. OpenAPI changes only for the authorized Primary
and ephemeral diagnostic surfaces. DataDir maintenance, unrelated cycles and
broader Storage adoption remain unchanged. Backend remains **NOT READY**.

## Operational storage addendum (2026-07-14)

The persistence inventory covers 48 store families. A neutral file primitive was
adopted only by MemoryStorage, WorkerRegistry, TaskAttemptRuntime and local
Notifications, with exact public/file field-shape compatibility. Human-editable
files, DataDir maintenance, growing SQLite candidates and unrelated SCCs were not
migrated. Frozen API/Commands/Health/Readiness/Context Fusion/Tools/Providers remain
unchanged; backend status remains **NOT READY**.

## Provider taxonomy addendum (2026-07-14)

One internal discovery-only catalog now projects 20 real providers on the measured
Windows composition. Legacy public lists, IDs, settings, Model Hub, Speech, Vision,
Desktop, Insight, API, Commands, Health/Readiness, Context Fusion, Tool Execution
and OpenAPI remain frozen. The 25/76 provider-related SCC and unrelated 4/6 and 2/2
SCCs are unchanged. Broader store adoption, Agent Creator and DataDir remain blockers; backend
status is **NOT READY**.

## Context Fusion read-port inversion addendum (2026-07-14)

Context Fusion now consumes six small read ports through six bootstrap adapters;
concrete functional-domain imports are 9→0. Its SCC is 26 contexts/79 internal
edges → singleton 1/0; the remaining related SCC is 25/75 and unrelated cycles
are unchanged. API, Commands, Health and Readiness hashes are unchanged; OpenAPI
remains exactly 425/471/100. Architecture is 47/47, reader integrations are
196/196, acceptance is 64/64, and global pytest is 1,040 passed plus 4 subtests
in 528.93 s. Ruff and `git diff --check` pass. The backend remains NOT READY.

## Health contributor inversion addendum (2026-07-14)

`health/runtime.py` is now a neutral 229-line collector over one registry and
ten bounded-context contributors. All 32 component IDs and 82 summary fields are
preserved; Readiness consumes a neutral snapshot protocol. Exceptions, timeout,
invalid results, duplicates and optional absence are isolated. OpenAPI remains
exactly 425/471/100 with the frozen SHA-256. Architecture is 39/39 in 16.70 s;
Health/Readiness/contributor isolation is 37/37 in 49.59 s; contributor domains
are 337 passed plus 4 subtests in 188.73 s; acceptance is 64/64 in 26.69 s;
global pytest is 1,018 passed plus 4 subtests in 790.35 s. Ruff and
`git diff --check` pass. The backend remains NOT READY.

## Command bounded-context decomposition addendum (2026-07-14)

`commands/runtime.py` is now a 98-line facade/dispatcher over one explicit
registry and 14 bounded-context handlers. The frozen 339-branch, 363-name and
24-alias surface is structurally equivalent with zero conflicts. 73 command
exercise files passed 828 tests plus 4 subtests in 467.14 s. OpenAPI remains
exactly equal at 425/471/100 with SHA-256
`bc0b2a3cab01aa9377bc80b50193089d288edd71901a9f650e3bd02ad48ea72f`.
Architecture is 32/32 in 13.03 s; acceptance is 64/64 in 26.34 s; global pytest
is 1,004 passed plus 4 subtests in 513.32 s; Ruff and `git diff --check` pass.
The backend remains NOT READY; Health, cycles, Tools, Providers and Storage
remain out of scope.

## API bounded-context decomposition addendum (2026-07-14)

The 6,371-line central API module is now an eight-line compatibility adapter.
All 471 operations live in 13 bounded-context routers with one registry. The
normalized before/after OpenAPI SHA-256 is identical; the contract remains 425
paths, 471 unique operations and 100 schemas. Architecture is 25/25, API
regression is 814 passed plus 4 subtests, acceptance is 64/64, global pytest is
997/997 in 507.28 s, and Ruff passes. Commands, Health, Tools, Providers and
Storage were not decomposed. The backend remains NOT READY; full evidence is in
`architecture-stabilization-api-decomposition.md`.

## Architecture Stabilization Phase 1 addendum (2026-07-14)

The canonical composition root moved from `core/app.py` to bounded builders
under `bootstrap/features`; `core/app.py` is compatibility-only. OpenAPI is 425
paths / 471 unique operations / 100 schemas. Architecture is 18/18, acceptance
is 64/64, global pytest is 990/990 in 527.93 s, and global Ruff passes. Detailed
evidence and SCC baselines are in
`docs/validation/architecture-stabilization-phase-1.md`. This does not change
the architecture status to READY.

## Desktop Automation + Application Control finalization (2026-07-13)

- Generic separated runtimes cover application/window discovery, accessibility,
  fallback input/screen, clipboard custody, planning, risk, execution, and
  mandatory verification.
- Native Windows UI Automation, Linux AT-SPI, and macOS Accessibility providers
  are isolated from OCR and Vision fallbacks; input is element-relative and last.
- Policy, Approval, Audit, Redaction, Agent Loop, Mission, Vision, Perception,
  Insight, Health, and Readiness integrations use public ports only.
- Plans persist no typed/clipboard text, raw OCR, captures, full trees,
  credentials, private executable paths, or environment data.
- Mandatory acceptance: `20 passed`; complete exclusive domain/provider/API/
  security suite: `34 passed`.
- Focused domain plus frozen integrations: `107 passed` in `63.51s`.
- Global: `972 passed`, `0 failed`, `0 skipped`, plus `4 subtests passed`, in
  `506.61s`. The `938 -> 972` increase is exactly the 34 new domain tests.
- Real Windows smoke: 15 windows discovered, an accessibility tree collected,
  and clipboard readability confirmed without emitting clipboard content.
- OpenAPI: `425` paths and `471` operations, with no duplicate path/method or
  operation ID.
- Ruff: repository-wide green.
- `git diff --check`: green; existing LF-to-CRLF working-copy warnings only.
- Coupling audit: zero forbidden application names, production mocks,
  placeholders, fixed coordinates, or frontend/Electron changes.
- No frontend, Electron, application-specific behavior, commit, push, or pull
  request was created.

## Insight + System Runtime finalization (2026-07-13)

- Seven separated read-only runtimes and isolated Windows, Linux, and macOS
  providers are implemented; production contains no mock provider.
- All hardware collection is provider-owned. Agent Loop consumes InsightRuntime,
  Mission consumes ResourcePressureRuntime, and Model Router consumes
  ModelCapabilityRuntime.
- Recommendations use only registered model/provider capability snapshots and
  measured free resources; diagnostics contain evidence for every finding.
- Privacy audit: no serials, MAC addresses, environment variables, credentials,
  tokens, command lines, executable/private paths, or real host/user names in
  Insight output; full processes are not persisted.
- Mandatory acceptance: 8 tests cover all 9 required scenarios and pass.
- Focused provider/domain/integration regression: `153 passed` in `245.17s`.
- Global: `938 passed`, `0 failed`, `0 skipped`, plus `4 subtests passed`, in
  `700.81s`. The `927 -> 938` increase is the 11 net new tests for this domain.
- OpenAPI: `414` paths and `460` operations, with no duplicate path/method or
  operation ID.
- Ruff: repository-wide green.
- `git diff --check`: green; existing LF-to-CRLF working-copy warnings only.
- No frontend, Electron, commit, push, pull request, or later domain was created.

## Native email post-removal regression audit (2026-07-13)

- Shared-removal classification: mail-specific notification projections,
  scheduler jobs, tools, resource types, policies, providers, and protocol
  adapters are category A; `send_request` without a remaining consumer is B;
  retained generic runtimes are C; the removed provider-oriented communication
  namespace is D because Conversation, Delegation, Mission/Swarm, Event Stream,
  and NotificationSink are canonical.
- Added four regression tests only: the Agent Loop notification sink lifecycle,
  canonical A-to-B delegation result return, delayed scheduling, and the
  scheduler-driven Agent Loop cycle.
- Focused post-removal matrix: `279 passed` in `121.05s`.
- Final global: `927 collected`, `927 passed`, `0 failed`, `0 skipped` in
  `477.45s`.
- Count change after the removal baseline: `923 -> 927`, entirely from the four
  new regression tests. The documented removal count remains `988 -> 923`.
- OpenAPI remains `403` paths and `449` operations, with zero occurrences of
  `email`, `mail`, `gmail`, `outlook`, `smtp`, `imap`, or `drafts`.
- Active runtime/config/tool/policy/health residue audit: zero matches. The only
  test references assert that the two removed Python namespaces cannot resolve.
- No generic responsibility required restoration or relocation. No Outlook,
  desktop automation, new permission, frontend, commit, push, or pull request
  was introduced.

## Native email domain removal (2026-07-13)

- Architectural decision: the backend no longer contains a native email domain;
  future generic application automation is outside this change.
- Focused affected regression: `109 passed` in `54.08s`.
- Final global: `923 collected`, `923 passed`, `0 failed`, `0 skipped` in
  `476.08s`.
- Count change: `988 -> 923`. Sixty-five tests for removed runtimes, providers,
  OAuth/protocol adapters, internal drafts, routes, commands, tools, scheduler
  behavior, and notification projections were removed with the functionality.
- Ruff: repository-wide green.
- OpenAPI: `403` paths, `449` operations, with zero occurrences of `email`,
  `mail`, `gmail`, `outlook`, `smtp`, `imap`, or `drafts`.
- Generic approvals, audit, redaction, attachments, tool execution, policy,
  notifications, agent-to-agent communication, and external-action confirmation
  remain available and domain-neutral.
- No Outlook/application automation, compatibility endpoint, placeholder,
  feature flag, commit, push, or pull request was created.

## World State + Attention Engine + Agent Loop closure (2026-07-13)

- Required acceptance: `8 passed` in `1.66s`.
- Focused domain suite: `14 passed` in `2.32s`.
- Final global: `988 passed`, `0 failed`, `0 skipped` in `495.13s`.
- Baseline preservation: the previous 974 tests remain green; 14 domain tests
  were added.
- Ruff: repository-wide green.
- `git diff --check`: green; existing LF/CRLF warnings only.
- OpenAPI: `430` paths, `480` unique operations, zero duplicate path/method or
  operation ID, and no arbitrary execution surface.
- World State + Attention Engine + Agent Loop: **Implemented / Frozen**.
- Default proactive mode is `observe`; execution remains explicit,
  deny-by-default, policy-bound, approval-aware, local-first, and restart-safe.
- No frontend, later domain, commit, push, PR, or GitHub mutation was performed.

## Perception + Multimodal + Vision closure (2026-07-13)

- Required acceptance: `6 passed` in `2.54s`.
- Focused domain/provider suite: `43 passed` in `21.96s`.
- Final bridge/domain regression: `51 passed` in `28.44s`.
- Global: `974 passed`, `0 failed`, `0 skipped`, `4 subtests passed` in
  `493.71s`.
- Ruff: repository-wide green.
- `git diff --check`: green; existing LF/CRLF conversion warnings only.
- OpenAPI: `409` paths, `458` operations, unique operation IDs, zero mock
  paths/operations.
- Perception + Multimodal + Vision: **Implemented / Frozen**.
- No frontend, World State, Agent Loop, Insight, later domain, commit, push, PR, or
  GitHub mutation was performed.

## Backend Freeze final closure (2026-07-13)

- UI Contracts/App Shell focused suite: `45 passed` in `51.69s`.
- Frozen-domain regression: `715 passed`, `259 deselected`, `4 subtests passed`
  in `369.36s`.
- Global: `974 collected`, `974 passed`, `0 failed`, `0 skipped`, `4 subtests
  passed`, no warnings reported, in `479.01s`.
- Count change: `991 -> 974`. Twenty-one obsolete UI/App Shell/desktop tests
  were removed with their functionality; four cleanup invariants were added.
- OpenAPI: `389` paths, unique operation IDs, no old UI/App Shell path and no
  mock path.
- Old React/Tauri roots, visual contracts, visual health/readiness flags,
  Tauri-specific CORS/configuration and public mock surfaces are absent.
- Frontend-agnostic DTOs/protocols remain in `backend/synapse/contracts/`.
- Backend Freeze: **Complete**.

## Platform governance definitive closure (2026-07-13)

- Transverse suite: `115 passed` in `71.14s`.
- Frozen domains: `613 passed`, `4 subtests passed` in `304.49s`.
- Global: `987 passed`, `4 failed`, `4 subtests passed` in `508.50s`.
- Remaining failures: four external UI Contract fixture cases only. Policy,
  observability, health, readiness, and foundation failures are zero.
- OpenAPI: `403` paths, unique operation IDs, no duplicate warning.
- Platform Governance + Policy + Observability + Health + Foundation
  Hardening: **Implemented / Frozen**.

Date: 2026-07-09
Branch: `backend-freeze-cleanup`

## Purpose

Record the baseline before any backend consolidation work. This baseline is
used as the reference point for later refactors and for verifying that runtime
changes do not regress the current behavior.

## Environment Notes

- `python -m unittest` is not available through the default `python` alias in
  this environment.
- The project interpreter was executed through `uv`.
- `pytest` is present in the project environment via `uv`, but not on the
  bare interpreter path.

## Commands Run

- `python -m unittest`
- `uv run python -m unittest`
- `uv run --extra dev ruff check .`
- `uv run --extra dev pytest --collect-only -q`
- `uv run --extra dev pytest`
- `uv run --extra dev pytest tests/test_delegation_retry_policy.py -q`
- `uv run --extra dev pytest`
- `uv run --extra dev ruff check .`

## Results

### unittest

- Direct `python -m unittest` failed because `python` is not on the active PATH.
- `uv run python -m unittest` completed with:
  - `Ran 0 tests in 0.000s`
  - `NO TESTS RAN`

### ruff

- `uv run --extra dev ruff check .` failed with one lint error:
  - `backend/synapse/commands/runtime.py:4854`
  - `ValidationError` is undefined in that file.

### Correction Applied

- Added the missing import in `backend/synapse/commands/runtime.py`:
  - `from synapse.core.exceptions import ValidationError`
- This is a minimal lint fix only.
- No new router, no new contracts, and no broad refactor were introduced for
  this stabilization step.

### pytest

- `uv run --extra dev pytest --collect-only -q` discovered `869` tests.
- `uv run --extra dev pytest` completed with:
  - `613 passed`
  - `256 failed`
  - total runtime: about `7 minutes`

### New Baseline After Fix

- `uv run --extra dev ruff check .` now passes with no errors.
- `uv run --extra dev pytest` now completes with:
  - `669 passed`
  - `209 failed`
  - total runtime: about `6 minutes 59 seconds`

### Main failing areas in pytest

- mission runtime / mission supervision / mission context / mission control
- observability / correlation trace coverage
- presence and lifecycle integration
- scheduler job execution and job transitions
- speech adapters and speech pipeline
- UI contract endpoints and DTOs
- tool intent persistence flow
- a smaller number of health and readiness checks
- `delegation_inbox` is now passing and no longer part of the failure set.
- `delegation_completion_signal` is now passing and no longer part of the
  failure set.
- `delegation_autonomy_policy` is now passing and no longer part of the
  failure set.

### Remaining Failures by Module

- `delegation_completion_signal`: 11
- `conversation_runtime`: 10
- `delegation_recovery_runtime`: 10
- `delegation_execution_runtime`: 10
- `delegation_timeout_policy`: 9
- `speech_pipeline_runtime`: 9
- `delegation_retry_policy`: 9
- `mission_control_runtime`: 9
- `agent_multimodal_context_bridge`: 9
- `dead_letter_runtime`: 9
- `agent_worker`: 9
- `observability`: 9
- `effective_policy`: 9
- `mission_context_runtime`: 8
- `mission_supervision_runtime`: 8
- `delegation_runtime`: 8
- `delegation_aware_worker`: 7
- `conversation_summary`: 7
- `agent_identity`: 7
- `delegation_scheduling_policy`: 7
- `agent_tool_calling`: 5
- `conversation_aware_worker`: 5
- `scheduler`: 5
- `speech_adapters`: 5
- `mission_runtime`: 5
- `presence_runtime`: 4
- `health_runtime`: 4
- `ui_contracts`: 4
- `daemon`: 3
- `lifecycle_runtime`: 2
- `tool_intents`: 1

## Models + Providers + Model Routing Finalization

Date: 2026-07-11

### Previous Result

- Global suite: `917 collected`, `814 passed`, `103 failed`.
- Ruff: passing repository-wide.
- Models + Providers: in development with 121 initial focused tests passing.

### Root Causes

- OpenAI-compatible generation raised `NotImplementedError`.
- ModelRouter silently replaced non-mock routes in dev/test mode.
- Provider descriptors, usage, streaming and selection provenance were incomplete.
- Ollama transport and Model Hub probes duplicated endpoint knowledge.
- Model Hub deduplicated by incidental entry ID rather than provider+model.
- Local Chat direct mode invoked LM Studio completion outside ModelRouter.

### Corrections Applied

- Added canonical provider-neutral descriptors, selection, request/result, usage,
  stream chunk, capability and structured error contracts.
- Implemented OpenAI-compatible model listing, generation, SSE, tools, structured
  output, optional auth/headers, timeout and normalized HTTP/JSON errors.
- Normalized Ollama listing, generation, JSONL streaming and real usage without
  automatic pull; extended LM Studio streaming/capability/empty-response behavior.
- Removed environment-driven mock fallback. Fallback now requires explicit policy
  and returns reason/warnings.
- Routed direct Local Chat generation through ModelRouter and added safe selection/
  generation events without prompts or secrets.
- Changed Model Hub identity to provider+model and used configured Ollama endpoint.
- Added routing, validation and capability API/command surfaces and richer health.

### New Result

- Expanded Models + Providers suite: `153 passed`.
- Global suite: `925 collected`, `822 passed`, `103 failed` in `491.39s`.
- Models + Providers failures globally: `0`.
- Frozen upstream domains remain green.
- Ruff: passing repository-wide.
- `git diff --check`: passing; only LF/CRLF normalization warnings.
- OpenAPI: no duplicate operation IDs or duplicate method/path pairs.
- Net change: eight new tests, eight more passes and no additional failures.

### Remaining Failures by Module

- `agent_worker`: 9
- `dead_letter_runtime`: 9
- `effective_policy`: 9
- `mission_control_runtime`: 9
- `observability`: 9
- `speech_pipeline_runtime`: 9
- `mission_context_runtime`: 8
- `mission_supervision_runtime`: 8
- `mission_runtime`: 5
- `scheduler`: 5
- `speech_adapters`: 5
- `presence_runtime`: 4
- `ui_contracts`: 4
- `daemon`: 3
- `health_runtime`: 3
- `lifecycle_runtime`: 2
- `foundation_hardening`: 1

## Architecture stabilization: tool execution boundary — 2026-07-14

The frozen public tool identities and transport surfaces now route through one public
registry and one operational executor. Builtin, MCP, and Desktop integrations are
explicit adapters. Timeout, active cancellation, restart-safe idempotency, redacted
history, and structured verification are coordinated centrally. Final counts and
surface hashes are recorded in
`docs/validation/tool-execution-boundary-after-metrics.json`.

This addendum does not mark the backend ready. General provider taxonomy, Storage,
remaining SCCs, Agent Creator, and DataDir maintenance findings remain open.

## Voice, Audio and Speech Checkpoint

Date: 2026-07-12

### Previous Result

- Focused domain suite: `39 passed`, `14 failed`.
- Global suite: `914 passed`, `40 failed` (`954 collected`).
- Ruff: passing repository-wide.

### Root Causes and Correction

- Nine `speech_pipeline_runtime` failures came from an incomplete fixture that
  created Voice and Avatar sessions for `artemis` without registering the
  minimum agent identity. The fixture now seeds an explicit identity through
  the shared agent factory.
- Five `speech_adapters` failures encoded obsolete implicit-mock selection.
  Tests now use an explicit mock provider when testing deterministic doubles,
  disable every STT candidate when testing no-selection behavior, and expect
  the real provider priority on generic resolution surfaces.
- No production validation was weakened and no frozen-domain runtime was
  changed.

### New Result

- Focused domain suite: `53 passed` in `27.56s`.
- Global suite: `928 passed`, `26 failed` in `528.62s` (`954 collected`).
- Ruff: passing repository-wide.
- The global failure count decreased by 14, exactly matching the focused
  failures removed. No failures were added.

### Remaining Failures by Module

- `effective_policy`: 9
- `observability`: 9
- `ui_contracts`: 4
- `health_runtime`: 3
- `foundation_hardening`: 1

The domain remains **In development**. The complete inventory and unresolved
production architecture work are tracked in
`docs/validation/voice-audio-speech-finalization.md`; focused green tests alone
do not satisfy the Voice/Audio/Speech Definition of Done.

### Voice Operational Checkpoint

Date: 2026-07-12

- Global suite: `944 passed`, `26 failed`, `4 subtests passed` in `463.24s`.
- Ruff: passing repository-wide.
- `git diff --check`: no whitespace errors; only existing LF/CRLF warnings.
- Remaining failures: `effective_policy` 9, `observability` 9,
  `ui_contracts` 4, `health_runtime` 3, `foundation_hardening` 1.
- Voice/Audio/Speech, device and VAD tests are green in the global run.
- No global failures were added by the operational Voice changes.

### Voice Conversation Closure Checkpoint

Date: 2026-07-12

- First global run after conversation/API closure: `947 passed`, `27 failed`,
  `4 subtests passed` in `462.29s`.
- The sole new failure was `avatar_runtime::test_api`, caused by a misplaced
  `conversation_id` argument in route wiring. The route was corrected.
- Post-fix integrated Avatar + Voice/Audio/Speech regression: `84 passed`, `4
  subtests passed`.
- Ruff: passing repository-wide.
- Expected remaining global failures return to the existing 26 external
  failures; a second full global run has not yet been recorded after the
  targeted route correction.

## Voice, Audio and Speech Final Freeze

Date: 2026-07-12

- Collection: `980 tests`.
- Acceptance: `6 passed` in `3.59s`.
- Integrated Voice/Audio/Speech/Avatar: `90 passed`, `4 subtests passed`.
- Global: `954 passed`, `26 failed`, `4 subtests passed` in `473.88s`.
- Ruff: passing repository-wide.
- `git diff --check`: no whitespace errors; line-ending warnings only.
- Remaining failures are external: `effective_policy` 9, `observability` 9,
  `ui_contracts` 4, `health_runtime` 3, `foundation_hardening` 1.
- No remaining failure belongs to this domain or its Avatar integration.
- Domain status: **Implemented / Frozen**.

### Voice/Audio/Speech definitive closure refresh (2026-07-13)

- Acceptance: `9 passed` in `5.98s`, covering Voice Message, two-turn
  Conversation Mode, barge-in, four restart states, retention, and the neutral
  Perception bridge.
- Integrated Voice/Audio/Speech/Avatar: `93 passed`, `4 subtests passed` in
  `43.01s`.
- Global collection: `983 tests`.
- Global result: `957 passed`, `26 failed`, `4 subtests passed` in `476.69s`.
- The unchanged failures remain external: effective policy 9, observability 9,
  UI contracts 4, health 3, and foundation hardening 1. No failure belongs to
  Voice, Audio, Speech, Avatar integration, VAD, devices, providers, retention,
  or the Perception bridge.
- Ruff global: green. `git diff --check`: no whitespace errors; Git reports only
  the existing LF-to-CRLF worktree warnings.
- OpenAPI: 384 paths, 41 Voice/Audio/Speech paths, zero domain mock paths, and
  unique operation IDs. The pre-existing FastAPI duplicate warning names the
  external `agent_multimodal_policy` function.
- Domain status: **Implemented / Frozen**.

## Missions Operational Baseline Stabilization

Date: 2026-07-11

### Previous Result

- Global suite: `825 passed`, `102 failed` (`927 collected`).
- Ruff: passing repository-wide.
- The mission, mission-control, worker, scheduler, daemon, presence,
  lifecycle, and dead-letter suites contained 62 failures caused primarily by
  incomplete bootstrapped agent identities.

### Root Causes

| Scope | Failures | Root cause | Classification |
| --- | ---: | --- | --- |
| Missions and Mission Control | 30 | Test fixtures retained bootstrapped agents without the required `role` and delegation identity fields | Fixture |
| Workers, Scheduler, Daemon, Lifecycle, Presence, Dead Letter | 31 | Test fixtures either did not seed agents or retained partial identities | Fixture |
| Chat approval presence | 1 | A tool approval updated requester presence but did not persist `waiting_approval` for the agent executing the chat turn | Runtime integration bug |

### Correction Applied

- Migrated the ten affected test modules to
  `tests/factories/agents.py::seed_delegation_pair` and explicitly seeded the
  additional `atlas` worker where required.
- Preserved each scenario's permissions, capabilities, preferred tools, and
  forbidden tools; no identity or delegation validation was weakened.
- Updated the chat-to-presence bridge to persist the executing agent's
  approval state, session ID, and approval ID when tool execution is awaiting
  approval.
- Kept mission, delegation, worker, scheduler, daemon, and dead-letter public
  contracts unchanged.

### New Result

- Focused mission and operational domain suite: `119 passed`.
- Presence regression suite: `9 passed`.
- Global suite: `887 passed`, `40 failed` in `530.11s` (`927 collected`).
- Ruff: passing repository-wide.
- Global failures decreased by 62; no new global failures were introduced.

### Remaining Failures by Module

- `effective_policy`: 9
- `observability`: 9
- `speech_pipeline_runtime`: 9
- `speech_adapters`: 5
- `ui_contracts`: 4
- `health_runtime`: 3
- `foundation_hardening`: 1

### Domain Freeze Status

The existing Missions/Mission Control operational baseline is green, but the
domain is **not frozen**. Inventory confirmed that the current runtime still
aggregates delegation tasks and does not yet provide the production planner,
validated task DAG, canonical `run_mission` execution flow, worker registry,
or SwarmRuntime required by the domain Definition of Done.

### Structural Increment (2026-07-12)

PlannerRuntime, persisted task DAGs, WorkerRegistry, deterministic worker
selection, ResultVerifier, canonical mission dispatch, and a persisted
SwarmRuntime foundation were added. The focused regression increased from
`119 passed` to `126 passed` and remained green. The domain remains in
development because worker attempt execution, strategy-specific swarm
semantics, mission-native recovery, commands, and trace closure are pending.

Validation after the structural increment:

- Focused domain suite: `126 passed`.
- Global suite: `894 passed`, `40 failed` (`934 collected`) in `520.57s`.
- Ruff: passing repository-wide.
- The same 40 previously documented failures remain; no new failure was
  introduced.

Execution/recovery increment validation on 2026-07-12:

- Focused domain suite: `132 passed`.
- Global suite: `898 passed`, `40 failed` (`938 collected`) in `464.97s`.
- Ruff: passing repository-wide.
- Attempts, worker execution, timeout/retry, swarm strategies, commands and
  mission trace added four tests without changing the existing failure set.

Closure attempt validation on 2026-07-12:

- Focused domain suite: `135 passed`.
- Global suite: `901 passed`, `40 failed` (`941 collected`) in `451.66s`.
- Ruff and `git diff --check`: passing.
- OpenAPI: no duplicate method/path or operation ID.
- The 40 remaining failures are unchanged from the classified baseline; no
  mission/worker/scheduler/daemon/DLQ focused test is failing.

End-to-end strategy validation on 2026-07-12:

- Acceptance and focused domain suite: `143 passed`.
- Global suite: `909 passed`, `40 failed` (`949 collected`) in `501.77s`.
- Ruff, diff check and OpenAPI uniqueness gates passed.
- The same 40 external/consumer failures remain; the domain introduced no new
  global failure.

Operational closure validation on 2026-07-12:

- Focused domain suite: `147 passed`.
- Global suite: `913 passed`, `40 failed` (`953 collected`) in `483.67s`.
- OpenAPI: 417 routes, no duplicates.
- Ruff and diff check pass.
- No focused mission, worker, swarm, scheduler, daemon, recovery or DLQ test
  fails globally.

Formal domain freeze on 2026-07-12:

- Focused domain suite: `148 passed`.
- Global suite: `914 passed`, `40 failed` (`954 collected`) in `462.97s`.
- Ruff, diff check and OpenAPI uniqueness gates passed.
- Missions + Mission Control + Workers + Swarm + Recovery is now
  `Implemented / Frozen`.

## Tools + Execution + Approvals + MCP Finalization

Date: 2026-07-11

### Previous Result

- Global: `925 collected`, `822 passed`, `103 failed`.
- Ruff: passing repository-wide.
- Focused tools baseline: `101 passed`, `1 failed` from an incomplete fixture.

### Root Causes

- ToolRuntime allowed execution when PermissionBridge was unavailable.
- Registry and execution lacked strict schema/conflict/lifecycle contracts.
- Approval IDs created by policy could not be supplied and consumed by ToolRuntime.
- MCP bridge projected disabled placeholders and had no executable transport adapter.
- A mock critical tool was seeded in production and an API route bypassed ToolRuntime.

### Corrections Applied

- Added final tool/preview/result/status contracts and structured ToolError.
- Added schema validation, normalized preview, dry-run isolation, config hashes,
  idempotency, history, status, cancel, restricted retry and truthful rollback.
- Changed missing PermissionBridge to deny-by-default and fixed approval validation,
  argument binding, call ID and one-time consumption.
- Removed production mock tools; test fixture exists only under explicit test mode.
- Added executable MCP adapters with `mcp:<server>:<tool>` namespacing through the
  same canonical executor and redirected the legacy API bypass.
- Corrected incomplete fixtures and added schema/idempotency/MCP regression tests.

### New Result

- Integrated focused/frozen suite: `168 passed`.
- Global: `927 collected`, `825 passed`, `102 failed` in `833.77s`.
- Tools domain failures globally: `0`.
- Ruff and `git diff --check`: passing.
- OpenAPI: no duplicate operation IDs or method/path pairs.
- Net change: two tests added, three more passes, one fewer failure.

### Remaining Failures by Module

- `agent_worker`: 9
- `dead_letter_runtime`: 9
- `effective_policy`: 9
- `mission_control_runtime`: 9
- `observability`: 9
- `speech_pipeline_runtime`: 9
- `mission_context_runtime`: 8
- `mission_supervision_runtime`: 8
- `mission_runtime`: 5
- `scheduler`: 5
- `speech_adapters`: 5
- `presence_runtime`: 4
- `ui_contracts`: 4
- `daemon`: 3
- `health_runtime`: 3
- `lifecycle_runtime`: 2
- `foundation_hardening`: 1

All 102 remaining failures are outside Tools + Execution + Approvals + MCP.
- `tool_intents`: 1

All 103 remaining failures are outside Models + Providers.
- `agent_audit`: 1
- `foundation_hardening`: 1

## Memory + Context Fusion Finalization

Date: 2026-07-11

### Previous Result

- Global suite: `908 collected`, `796 passed`, `112 failed`.
- Ruff: passing repository-wide.
- Memory + Context Fusion: foundations present, not finalized.

### Root Causes

- Markdown append storage lacked record lifecycle, revision, isolation, and a
  runtime-compatible storage contract.
- ContextLoader and Context Fusion were parallel paths; Fusion lacked memory,
  provenance, deterministic priority, and budget.
- Local Chat promoted phrases to memory through unsafe regex heuristics.
- Perception builds without a scope could collect unrelated global signals.
- Nine bridge tests used incomplete agent identity fixtures.

### Corrections Applied

- Added scoped memory records, independent storage protocol, atomic/versioned file
  adapter, explicit corruption errors, optimistic concurrency, deduplication,
  working-memory expiry/limits, retrieval, import/export, deletion, and isolation.
- Removed all heuristic automatic Chat memory writes.
- Added canonical structured Context Fusion with priority, estimated token budget,
  response reserve, provenance, omissions, stable ordering, conflict visibility,
  and trace IDs.
- Routed Chat, workers, commands, and API through canonical runtimes while preserving
  frozen Conversation DTOs and explicit legacy fallback behavior.
- Scoped perception and made health/readiness optional context sources.
- Corrected bridge fixtures with the existing test-only agent factory.

### New Result

- Expanded Memory + Context Fusion domain suite: `126 passed`.
- Global suite: `917 collected`, `814 passed`, `103 failed` in `470.62s`.
- Memory + Context Fusion failures globally: `0`.
- Conversation + Chat remains green.
- Ruff: passing repository-wide.
- `git diff --check`: passing; only LF/CRLF normalization warnings.
- OpenAPI: no duplicate operation IDs or duplicate method/path pairs.
- Net change: nine new tests, 18 more passing tests, and nine fewer failures.

### Remaining Failures by Module

- `agent_worker`: 9
- `dead_letter_runtime`: 9
- `effective_policy`: 9
- `mission_control_runtime`: 9
- `observability`: 9
- `speech_pipeline_runtime`: 9
- `mission_context_runtime`: 8
- `mission_supervision_runtime`: 8
- `mission_runtime`: 5
- `scheduler`: 5
- `speech_adapters`: 5
- `presence_runtime`: 4
- `ui_contracts`: 4
- `daemon`: 3
- `health_runtime`: 3
- `lifecycle_runtime`: 2
- `foundation_hardening`: 1
- `tool_intents`: 1

These 103 failures are outside Memory + Context Fusion. Pytest cache retained one
older `agent_provisioning` and one older `conversation_summary` failure that passed
in the definitive run; they are excluded from this grouping.

## Conversation + Chat Finalization

Date: 2026-07-10

### Previous Result

- Global suite: `901 collected`, `762 passed`, `139 failed`.
- Focused inventory: `27 failed`, `51 passed`.
- Ruff: passing repository-wide.

### Root Causes

- Incomplete test fixtures still assumed removed prefabricated agents.
- Chat and Conversation used parallel turn paths and duplicated persistence.
- Conversation records lacked revision, pagination, idempotency, typed content,
  participant metadata, attachment metadata, and generation lifecycle state.
- Summary generation used a production mock heuristic rather than a configured
  model.
- Streaming, cancellation, structured domain errors, and explicit destructive
  confirmation were absent.

### Corrections Applied

- Added explicit test-only agent fixtures without restoring runtime seed data.
- Introduced the canonical `ChatRuntime.submit_turn` path for local and agent
  chat while preserving provider-neutral model routing and tool integration.
- Extended backward-compatible Conversation and Message persistence with atomic
  writes, revisions, pagination, idempotency, participants, content parts,
  attachments, model/tool/error metadata, and lifecycle states.
- Replaced heuristic summary generation with configured-model generation and
  persisted source messages, revision, model, and provider provenance.
- Added NDJSON lifecycle streaming without fabricated tokens, cancellation,
  structured errors, explicit delete confirmation, and full attachment
  size/SHA-256 validation.
- Added regression coverage for each identified contract.

### New Result

- Focused Conversation + Chat set: `97 passed`.
- Global suite: `908 collected`, `796 passed`, `112 failed` in `475.85s`.
- Conversation + Chat failures in global suite: `0`.
- Ruff: passing repository-wide.
- Net change from the previous baseline: 34 more passing tests, 27 fewer
  failures, and seven additional regression tests collected.

### Remaining Failures by Module

- `agent_multimodal_context_bridge`: 9
- `agent_worker`: 9
- `dead_letter_runtime`: 9
- `effective_policy`: 9
- `mission_control_runtime`: 9
- `observability`: 9
- `speech_pipeline_runtime`: 9
- `mission_context_runtime`: 8
- `mission_supervision_runtime`: 8
- `mission_runtime`: 5
- `scheduler`: 5
- `speech_adapters`: 5
- `presence_runtime`: 4
- `ui_contracts`: 4
- `daemon`: 3
- `health_runtime`: 3
- `lifecycle_runtime`: 2
- `foundation_hardening`: 1
- `tool_intents`: 1

These 112 failures are outside Conversation + Chat. The pytest cache also
retained one earlier `agent_provisioning` and one earlier
`conversation_summary` failure; both passed in the definitive run and are not
included above.

## Prefabricated Agent Domain Removal

Date: 2026-07-10

### Previous Result

- Global suite: `915 collected`, `775 passed`, `140 failed`.
- Ruff: passing repository-wide.
- Custom provisioning and the prefabricated-agent catalog were coupled through
  runtime composition, API, commands, health/readiness, metadata, approval
  behavior, tests, seeds, events, and documentation.

### Inventory and Classification

- **A: retained for provisioning**: request validation, risk policy, preview,
  dry-run, staging, atomic rename, overwrite backup, rollback, Registry and
  Identity validation, structured errors, approvals, audit, and lifecycle.
- **B: removed as catalog-only**: runtime/models, three seed manifests,
  bootstrap directory/files, catalog/validation/merge logic, API routes,
  commands, lifecycle events, health/readiness counts, exclusive tests, ADR,
  and validation report.
- **C: reviewed general changes**: `ApprovalManager`, agent audit, admin policy,
  API composition, command composition, capability policy, DataDir bootstrap,
  health models, and readiness policy. Only catalog coupling was removed.

### Root Cause and Architectural Decision

The catalog contradicted the product requirement that users explicitly control
agent identity, role, personality, model, memory, tools, permissions,
delegation, and lifecycle. The product has not been released, so compatibility
stubs or deprecation routes had no value. ADR 0116 records complete removal.

### Correction Applied

- Removed the catalog runtime, source manifest entries, seeds, bootstrap,
  endpoints, commands, events, tests, health/readiness fields, and active docs.
- Custom provisioning now evaluates actual configuration risk for every
  requester; local-owner context no longer bypasses sensitive configuration.
- Durable requests store a SHA-256 configuration hash. Approval binds request,
  agent, hash, requester, permissions, tools, capabilities, action, and risk.
- Identical active requests are idempotent by agent, requester, action, and
  hash. Changed configuration produces a distinct request and approval.
- Manual creation accepts explicit SOUL/SKILLS content and permissions.
- Preview reports normalized config, files, permissions, tools, capabilities,
  risk, approval requirement, conflicts, validations, and destination.
- Permanent delete is separate from archive and requires inactive state,
  literal confirmation, dependency checks, explicit force, staging, rollback,
  event, and surviving audit.

### New Result

- Provisioning, admin, approval, policy, identity, registry, API-router, and
  contract integration: `129 passed`.
- Core provisioning, admin, audit, and approval subset: `87 passed`.
- Global suite: `901 collected`, `762 passed`, `139 failed` in `7:13`.
- Ruff: passing repository-wide.
- Failure count decreased by one. No global failure was added.
- Collected/pass totals decreased because the exclusive catalog test module was
  deleted; new provisioning and deletion regressions remain collected.

### Remaining Failures by Module

- `conversation_runtime`: 10
- `agent_multimodal_context_bridge`: 9
- `agent_worker`: 9
- `dead_letter_runtime`: 9
- `effective_policy`: 9
- `mission_control_runtime`: 9
- `observability`: 9
- `speech_pipeline_runtime`: 9
- `mission_context_runtime`: 8
- `mission_supervision_runtime`: 8
- `conversation_summary`: 7
- `agent_tool_calling`: 5
- `conversation_aware_worker`: 5
- `mission_runtime`: 5
- `scheduler`: 5
- `speech_adapters`: 5
- `presence_runtime`: 4
- `ui_contracts`: 4
- `daemon`: 3
- `health_runtime`: 3
- `lifecycle_runtime`: 2
- `foundation_hardening`: 1
- `tool_intents`: 1
## Agent Identity Stabilization

Date: 2026-07-10

### Previous Result

- `tests/test_agent_identity.py`: `1 passed`, `7 failed`.
- Global suite: `731 passed`, `149 failed` across 880 tests.
- Ruff: passing repository-wide.

### Root Causes

- The identity test fixture created a temporary runtime but did not seed the
  `artemis` and `researcher` config or identity files. Seven tests failed
  before reaching their target behavior.
- Registry and identity runtime accepted a config `id` that differed from the
  containing folder name.
- Invalid YAML/JSON could leak a parser exception instead of a structured
  `ValidationError`.
- Non-boolean `can_delegate` values were coerced through Python truthiness.

### Contract Confirmed

- Folder id is canonical. A missing config `id` is inferred from the folder;
  an explicit mismatch is rejected.
- Operational identity requires a non-empty `id`, `name`, and `role`.
- Missing `name` falls back to the canonical id.
- Missing `can_delegate` defaults explicitly to `False`; a supplied value must
  be boolean.
- Registry lookup remains compatible with partial configs. Full identity
  validation occurs in `AgentIdentityRuntime`.
- `SOUL.md` and `SKILLS.md` are optional and load as empty strings.
- Status/admin state, model, capabilities, tools, permissions, memory,
  description, system prompt, schema version, and record version are optional
  for identity loading.
- Role is currently a non-empty free-form value; the runtime has no role enum.

### Correction Applied

- Added shared config normalization and structured config loading in
  `backend/synapse/agents/models.py`.
- Updated `AgentRegistry` and `AgentIdentityRuntime` to use the shared folder-id
  and parsing rules.
- Added the additive `can_delegate` field to `AgentConfig`, defaulting to
  `False`.
- Extended `tests/factories/agents.py` with invalid-config and optional
  identity-file helpers.
- Corrected the identity fixture and added registry/identity regressions for
  valid and invalid cases.
- No provisioning, mission, frontend, router, or public endpoint
  implementation changed.

### New Result

- `tests/test_agent_identity.py`: `11 passed`.
- `tests/test_agent_registry.py`: `9 passed`.
- Provisioning, capabilities, agent admin, and delegation remained green.
- Global suite: `750 passed`, `142 failed` across 892 tests in about
  `7 minutes 27 seconds`.
- Net global change: 7 fewer failures and 19 more passes.
- Ruff: passing repository-wide.

### Remaining Failures by Module

- `conversation_runtime`: 10
- `mission_control_runtime`: 9
- `effective_policy`: 9
- `dead_letter_runtime`: 9
- `observability`: 9
- `agent_multimodal_context_bridge`: 9
- `speech_pipeline_runtime`: 9
- `agent_worker`: 9
- `mission_context_runtime`: 8
- `mission_supervision_runtime`: 8
- `conversation_summary`: 7
- `agent_tool_calling`: 5
- `conversation_aware_worker`: 5
- `speech_adapters`: 5
- `scheduler`: 5
- `mission_runtime`: 5
- `presence_runtime`: 4
- `health_runtime`: 4
- `ui_contracts`: 4
- `daemon`: 3
- `lifecycle_runtime`: 2
- `tool_intents`: 1
- `agent_audit`: 1
- `foundation_hardening`: 1

### Retry Policy Stabilization

- Previous result for `delegation_retry_policy`:
  - `9 failed`
  - `1 passed`
- Correction applied:
  - Seeded the retry-policy test fixture with the minimal identity fields required by runtime validation for `artemis` and `researcher`.
  - Added a regression test to verify the fixture now loads a complete identity shape.
- New result:
  - `uv run --extra dev pytest tests/test_delegation_retry_policy.py -q` now passes with:
    - `11 passed`
  - `uv run --extra dev pytest` now completes with:
    - `679 passed`
    - `200 failed`
  - `uv run --extra dev ruff check .` still passes.
- Remaining failures by module after this stabilization:
  - `delegation_completion_signal`: 11
  - `delegation_recovery_runtime`: 10
  - `delegation_execution_runtime`: 10
  - `conversation_runtime`: 10
  - `delegation_timeout_policy`: 9
  - `speech_pipeline_runtime`: 9
  - `mission_control_runtime`: 9
  - `agent_multimodal_context_bridge`: 9
  - `dead_letter_runtime`: 9
  - `agent_worker`: 9
  - `observability`: 9
  - `effective_policy`: 9
  - `mission_context_runtime`: 8
  - `mission_supervision_runtime`: 8
  - `delegation_runtime`: 8
  - `delegation_aware_worker`: 7
  - `conversation_summary`: 7
  - `agent_identity`: 7
  - `delegation_scheduling_policy`: 7
  - `agent_tool_calling`: 5
  - `conversation_aware_worker`: 5
  - `scheduler`: 5
  - `speech_adapters`: 5
  - `mission_runtime`: 5
  - `presence_runtime`: 4
  - `health_runtime`: 4
  - `ui_contracts`: 4
  - `daemon`: 3
  - `lifecycle_runtime`: 2
  - `tool_intents`: 1
  - `agent_audit`: 1
  - `foundation_hardening`: 1

### Timeout Policy Stabilization

- Previous result for `delegation_timeout_policy`:
  - `9 failed`
  - `1 passed`
- Cause root:
  - The timeout-policy fixture was creating `artemis` and `researcher` without the minimal identity fields required by runtime validation.
  - The failure surfaced before timeout logic executed, so this was a fixture gap rather than a policy bug.
- Correction applied:
  - Seeded the fixture with the minimal identity shape for `artemis` and `researcher`.
  - Added a regression test that asserts the loaded `artemis` identity has `id`, `name`, `role`, and `can_delegate`.
- New result:
  - `uv run --extra dev pytest tests/test_delegation_timeout_policy.py -q` now passes with:
    - `11 passed`
  - `uv run --extra dev pytest` now completes with:
    - `689 passed`
    - `191 failed`
  - `uv run --extra dev ruff check .` still passes.
- Remaining failures by module after this stabilization:
  - `delegation_recovery_runtime`: 10
  - `conversation_runtime`: 10
  - `delegation_execution_runtime`: 10
  - `mission_control_runtime`: 9
  - `effective_policy`: 9
  - `dead_letter_runtime`: 9
  - `observability`: 9
  - `agent_multimodal_context_bridge`: 9
  - `speech_pipeline_runtime`: 9
  - `agent_worker`: 9
  - `mission_context_runtime`: 8
  - `mission_supervision_runtime`: 8
  - `delegation_runtime`: 8
  - `agent_identity`: 7
  - `conversation_summary`: 7
  - `delegation_aware_worker`: 7
  - `delegation_scheduling_policy`: 7
  - `agent_tool_calling`: 5
  - `conversation_aware_worker`: 5
  - `speech_adapters`: 5
  - `scheduler`: 5
  - `mission_runtime`: 5
  - `presence_runtime`: 4
  - `health_runtime`: 4
  - `ui_contracts`: 4
  - `daemon`: 3
  - `lifecycle_runtime`: 2
  - `tool_intents`: 1
  - `agent_audit`: 1
  - `foundation_hardening`: 1

## Baseline Summary

- The backend is test-rich, but the current suite still has a large failure
  surface in orchestration, speech, observability, and UI-contract layers.
- Lint no longer reports the command-runtime defect after the minimal import
  fix.
- `delegation_inbox` has been stabilized and now passes in isolation.
- `delegation_completion_signal` has been stabilized and now passes in
  isolation.
- `delegation_autonomy_policy` has been stabilized and now passes in
  isolation.
- The baseline is documented and ready to serve as the freeze reference for
  backend consolidation work.

## Delegation Block Stabilization

Date: 2026-07-10

### Previous Result

- Delegation suite: `63 passed`, `42 failed`.
- Global suite: `689 passed`, `191 failed`.
- Ruff: passing repository-wide.

### Failure Inventory

| Test module | Failures | Root cause | Classification | Dependencies |
| --- | ---: | --- | --- | --- |
| `delegation_aware_worker` | 7 | Missing minimum `artemis` identity | Fixture | agent identity, capability policy |
| `delegation_execution_runtime` | 10 | Missing minimum `artemis` identity | Fixture | delegation runtime, execution runtime |
| `delegation_recovery_runtime` | 10 | Missing minimum `artemis` identity | Fixture | retry, timeout, dead letter |
| `delegation_runtime` | 8 | Missing minimum `artemis` identity | Fixture | agent identity, capability policy |
| `delegation_scheduling_policy` | 7 | Missing minimum `artemis` identity | Fixture | delegation runtime, scheduling policy |

All 42 failures stopped at `AgentIdentityRuntime.validate()` because `role`
was absent. Policy, execution, recovery, workload, ordering, timestamps, and
persistence code had not run yet.

### Correction Applied

- Added `tests/factories/agents.py` with explicit helpers for minimum valid
  agent config, individual agent seeding, and delegation-pair seeding.
- Migrated the repeated agent setup in all 10 `test_delegation*.py` modules to
  the shared factory.
- The factory preserves scenario-specific overrides and existing bootstrapped
  config while requiring `id`, `name`, `role`, and `can_delegate`.
- Existing identity regression tests now exercise the shared factory.
- No production runtime, public API, router, contract, or validation changed.

### New Result

- `delegation_scheduling_policy`: `8 passed`.
- `delegation_execution_runtime`: `10 passed`.
- `delegation_recovery_runtime`: `10 passed`.
- All `tests/test_delegation*.py`: `105 passed`.
- `tests/test_contracts.py`: `4 passed`.
- `tests/test_agent_identity.py`: `1 passed`, `7 failed`; these are existing
  fixture failures caused by missing agent config files and are outside this
  delegation-only correction.
- Global suite: `731 passed`, `149 failed` in about `7 minutes 40 seconds`.
- Ruff: passing repository-wide.

The global failure count decreased by 42, exactly matching the delegation
failures removed. No failures were added.

### Remaining Failures by Module

- `conversation_runtime`: 10
- `mission_control_runtime`: 9
- `effective_policy`: 9
- `dead_letter_runtime`: 9
- `observability`: 9
- `agent_multimodal_context_bridge`: 9
- `speech_pipeline_runtime`: 9
- `agent_worker`: 9
- `mission_context_runtime`: 8
- `mission_supervision_runtime`: 8
- `agent_identity`: 7
- `conversation_summary`: 7
- `agent_tool_calling`: 5
- `conversation_aware_worker`: 5
- `speech_adapters`: 5
- `scheduler`: 5
- `mission_runtime`: 5
- `presence_runtime`: 4
- `health_runtime`: 4
- `ui_contracts`: 4
- `daemon`: 3
- `lifecycle_runtime`: 2
- `tool_intents`: 1
- `agent_audit`: 1
- `foundation_hardening`: 1
### Administrative DataDir maintenance addendum — 2026-07-14

One domain-neutral runtime and four owner contributors replace direct
administrative DataDir access from API/Commands. The generic destructive
Foundation/Retention delivery surface was removed. The intentional public delta
is 443 OpenAPI paths, 490 unique operations and 107 schemas; Commands contain
356 canonical entries and 380 registered names including 24 aliases. Stored
plans are path-free, checksummed, revisioned, expiring, confirmation/policy
gated and approval-bound for high risk. Restart never auto-runs cleanup.

The status remains **NOT READY**. No global backup/restore or storage migration
capability is claimed.

Final gate: 1,125 collected; 1,123 passed; 2 skipped; zero failed; 4 subtests
passed in 623.03 seconds. Architecture 83/83, acceptance 73/73,
repository-wide Ruff and `git diff --check` are green.
