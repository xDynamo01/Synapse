# Synapse V3 — Current-State Architectural Audit

Audit date: **2026-07-17**
Workspace: `E:\Projetos\Synapse`
Branch / HEAD: `backend-freeze-cleanup` / `8196eb1` (`feat: add scheduler recurring jobs`)
Verdict: **BACKEND NOT READY**

## 1. Executive Summary

The current working tree contains a substantial, integrated backend implementation. The official architecture and acceptance guardrails pass, the full regression suite reproduces the last documented green result, Ruff passes, and the governed import graph reproduces **72 bounded contexts / 261 edges / one 13-context SCC with 35 internal edges / zero exact-module SCCs**.

This does **not** make the backend ready or production-ready. The most important current-state finding is that almost the entire validated backend exists outside the committed baseline: the current tree has 454 production Python files while `HEAD` has 74; Git reports 1,048 porcelain entries, including 940 untracked files, 100 modified entries and 8 deletions, with nothing staged. A future audit or a second checkout cannot reconstruct the state that passed 1,208 tests. This is a P0 governance and reproducibility blocker before a new bounded context is started.

Confidence is **high** for the static graph, registered composition, test results and file inventory; **medium** for runtime security coverage because external providers, real secrets, real network transports, OS-specific integrations and production deployment were not exercised. No functional code, contract, configuration or test was changed by this audit.

Main findings:

- 1,208/1,210 global tests passed; the two skips are Windows symlink capability checks.
- All 113 architecture tests and all 96 acceptance tests passed independently.
- The historical graph headline is current, but one global 13-context SCC remains and contains nine direct bidirectional context pairs.
- Project Governance, Intelligence Trust Boundary, Skills Phase 1, Storage Primitives and orchestration contracts are present and testable.
- Private Evals Runtime itself is **NOT FOUND**. Only preparatory references and reusable frozen contracts exist.
- No Skills Phase 2, Sandbox, Repository Runtime or Coding Sessions implementation was found. Dockerfile/Compose are deployment scaffolding, not Deployment Runtime.
- The Intelligence Trust Boundary explicitly leaves UI-mediated Desktop Automation uploads unguarded.
- Direct subprocess execution exists in concrete Desktop, Speech and System Insight provider adapters. No `shell=True`, `os.system`, production `eval` or production `exec` was found, but no Sandbox Execution Boundary exists.
- Canonical documents drift: README and roadmap still say Swarm is planned, README advertises 923 tests, an older audit says Voice/Avatar/Perception are absent, and the current dependency-graph report contains a contradictory 247-edge sentence beneath a 261-edge headline.
- The workspace contains untracked runtime/test artifacts: 35 root logs (7.69 MiB), a WAV, 76 `data/` files, and two downloaded model files totaling about 210.5 MiB.

## 2. Audit Scope

### Analyzed

- `backend/synapse/**`: 454 Python files and 72 bounded-context packages (excluding the technical package root).
- `tests/**`: 189 Python files, including architecture and acceptance suites.
- `docs/**`: 290 files, including architecture, ADR, validation, audit, roadmap and module-status records.
- `data/**`: configuration, manifests, fixtures and runtime-like artifacts; sensitive contents were not reproduced.
- root build/config files: `pyproject.toml`, `uv.lock`, `.gitignore`, `.env.example`, `Dockerfile`, `docker-compose.yml`, README and roadmaps.
- `apps/`: present but empty.
- Git branch, HEAD, status, staged/unstaged/untracked state and recent commits.

### Environment

- Windows / PowerShell, timezone `America/Sao_Paulo`.
- Python 3.12.11 from `.venv`.
- pytest 9.1.1; Ruff from the same environment.
- Official configuration: `pyproject.toml`; `testpaths = ["tests"]`, `pythonpath = ["backend"]`.

### Limitations

- No network, real provider, credential, speech device, camera, Desktop Automation or deployment smoke was performed.
- No destructive Git command, checkout, reset, clean, stash, commit or publication occurred.
- No secret value was printed. The secret scan is path/pattern based, not a full entropy scanner or external secret-scanning service.
- Static import analysis cannot observe reflection, dynamic imports or calls through injected objects.
- Coverage percentage, mutation testing, flaky repetition and mypy were not official enforced gates in `pyproject.toml`; they were not used to overstate readiness.
- The first global pytest attempt was terminated by the audit executor's 120-second limit (exit 124); it was rerun unchanged with a sufficient timeout.

## 3. Repository Inventory

| Item | Current observation | Evidence |
| --- | ---: | --- |
| Production Python files | 454 | `rg --files backend/synapse -g '*.py'` |
| Python files at HEAD | 74 | `git ls-tree -r --name-only HEAD backend/synapse` |
| Apparent bounded contexts | 72 | direct packages under `backend/synapse`, excluding technical root |
| Test Python files | 189 | `rg --files tests -g '*.py'` |
| Documentation files | 290 | `rg --files docs` |
| API routers | 20 domain router modules plus registry/compatibility surface | `backend/synapse/api/routers/`, `api/router_registry.py` |
| Bootstrap | 12 feature builders, 7 composition adapters, container/lifecycle/application | `backend/synapse/bootstrap/` |
| CI | **NOT FOUND** | no `.github` directory |
| Frontend | **NOT FOUND** | `apps/` exists but contains zero files |
| Dependency lock | present | `uv.lock` |
| Migrations | two explicit mechanisms | `migrations/` and `storage/migrations.py` |
| Empty source/test/doc/data files | none found | zero-length scan excluding build artifacts |
| Empty build artifacts | six marker files | ignored `backend/dist/**`; not source defects |

The production packages include foundation/delivery (`core`, `bootstrap`, `api`, `commands`), agents and orchestration, tools/providers, persistence, multimodal/desktop domains, governance, Skills and Intelligence Boundary. The repository also contains ignored `backend/build`, `backend/dist`, caches and `__pycache__` directories. No named legacy/archive source directory was found; historical behavior is retained primarily in documents and Git, not a separate legacy package.

Marker scan found no production `NotImplementedError`, TODO, FIXME or HACK. Bare `pass` occurrences are chiefly exception class bodies and best-effort cleanup handlers. Their impact is low unless an exception is being swallowed; the global and architecture tests did not expose a failure. Examples requiring future review include cleanup `pass` blocks in `voice/runtime.py`, `context_fusion/runtime.py`, `model_hub/runtime.py` and `ephemeral_agents/runtime.py`.

## 4. Architectural Graph

### Method

The audit used the repository's executable method in `tests/architecture/support.py` and `test_audio_speech_boundary.py`:

1. parse `backend/synapse/**/*.py` with `ast`;
2. exclude `TYPE_CHECKING` imports from the runtime graph;
3. group `main.py` with API and `sidecar.py` with bootstrap;
4. exclude bootstrap edges and the three documented `core` compatibility adapters from the governed graph;
5. group `synapse.<context>` imports by the first package segment;
6. compute Tarjan SCCs for contexts and exact modules.

### Results

| Measure | Historical reference | Current | Difference |
| --- | ---: | ---: | --- |
| Production Python modules | 454 in latest report | 454 | none |
| Bounded contexts | 72 | 72 | none |
| Governed context edges | 261 | 261 | none |
| Non-trivial context SCCs | 1 | 1 | none |
| Global SCC | 13 contexts / 35 edges | 13 / 35 | none |
| Exact-module SCCs | 0 | 0 | none |

SCC members: `agents`, `approvals`, `avatar`, `context`, `conversations`, `decisions`, `delegation`, `embodiment`, `missions`, `models`, `policies`, `tools`, `voice`.

Direct bidirectional pairs inside it: `agents↔context`, `agents↔models`, `agents↔policies`, `agents↔tools`, `approvals↔policies`, `approvals↔tools`, `decisions↔tools`, `missions↔tools`, `policies↔tools`.

Highest degree contexts are `core` (63; expected foundation fan-in), `tools` (30; SCC hotspot), `observability` (28; sink-like), `agents` (27; SCC hotspot), `api` (16; delivery fan-out) and `policies` (15; SCC hotspot). Domain-to-bootstrap imports are rejected by architecture tests; bootstrap owns concrete construction. API and Commands have no incoming governed domain edges.

Interpretation: the headline baseline is valid. “Zero SCCs between Python modules” is true for exact modules but must not be read as “no architectural cycles”; aggregation exposes one significant bounded-context SCC. The guardrail in `test_domain_independence.py` prevents new/worsened cycles but explicitly tolerates the legacy component, so a green test does not close this debt.

## 5. Frozen Domains Status

Statuses use evidence from the current run, not names alone. “Verified” means implementation, real composition and relevant passing tests were found. Integration evidence centers on `bootstrap/application.py`, feature builders and `RuntimeContainer`.

| Domain | Official Status | Observed Status | Integration | Tests | Documentation | Drift | Evidence |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Bootstrap | Frozen | Implemented / Verified | canonical application builder | architecture + global pass | current | no code drift | `bootstrap/application.py::build_application/create_runtime`; `test_composition_boundaries.py` |
| Composition Root | Frozen | Implemented / Verified | 12 ordered feature builders, one container | 4 composition tests pass | mostly current | application docstring still says API/Commands are not decomposed | `bootstrap/application.py`, `bootstrap/container.py` |
| Lifecycle | Frozen | Implemented / Verified | resources registered then started/closed explicitly | 8 architecture lifecycle tests + unit/global pass | current | none observed | `bootstrap/lifecycle.py::LifecycleManager`; FastAPI lifespan test |
| Dependency Injection | Frozen | Implemented / Verified | constructor/feature dependency dataclasses; concrete adapters in bootstrap | dependency/composition tests pass | current | broad `Any` container surface remains debt | `bootstrap/features/*.py`, `RuntimeContainer` |
| API | Frozen | Implemented / Verified | application attached through FastAPI lifespan | routing/contract/global pass | stale README metrics | documentation drift | `main.py`, `api/routes.py`; 494/550/128 OpenAPI |
| Router Registry | Frozen | Implemented / Verified | single `DOMAIN_ROUTERS` registry | 7 API routing architecture tests pass | current | none observed | `api/router_registry.py` |
| Bounded Routers | Frozen | Implemented / Verified | 20 bounded router modules reachable | routing/global pass | current | none observed | `api/routers/*.py` |
| Commands Registry | Frozen | Implemented / Verified | handlers built once and registered once | command boundary/global pass | current baseline artifacts | none observed | `commands/registry.py`; `bootstrap/application.py::_build_commands` |
| Tool Execution Boundary | Frozen | Implemented / Verified, limited scope | one registry/executor; Desktop/MCP adapters | 5 architecture + functional/acceptance pass | documents state NOT READY | subprocess providers outside tool runtime need explicit exception model | `tools/runtime.py`; `bootstrap/features/integration.py`; `test_tool_execution_boundary.py` |
| Provider Taxonomy | Frozen | Implemented / Verified | one catalog, bootstrap projections | 4 architecture + focused/global pass | current | none observed | `providers/taxonomy.py`; `bootstrap/adapters/provider_taxonomy.py` |
| Storage Primitives | Frozen | Implemented / Verified pilot | adapters bind four pilot consumers | 5 architecture + storage tests pass; 2 symlink skips | correctly says four-store pilot | broader adoption intentionally incomplete | `storage/collection.py`, `storage/atomic.py`, `storage/locking.py` |
| Memory | Frozen | Implemented / Verified | platform builder and Context Fusion adapter | memory/context/global pass | current | none observed | `memory/store.py`, `memory/storage.py`; `test_memory_runtime.py` |
| Context Fusion | Frozen | Implemented / Verified | six consumer-owned readers bound in bootstrap | 8 boundary + functional/acceptance pass | current | none observed | `context_fusion/contracts.py`; `bootstrap/adapters/context_fusion.py` |
| Missions | Frozen | Implemented / Verified | mission feature builder; governance binding injected | mission, orchestration and acceptance pass | current | remains in global SCC with Tools | `missions/runtime.py`, `missions/dispatcher.py` |
| Workers | Frozen | Implemented / Verified | registry/scheduler/execution adapter in composition | worker/mission/global pass | current | broad coordinator, no SCC membership | `workers/runtime.py`, `workers/execution_adapter.py` |
| Swarm | Frozen | Implemented / Verified | Mission builder composes Swarm and strategies | 13 mission/swarm acceptance cases plus global pass | README/roadmap say Planned | documentation drift | `swarm/runtime.py`, `swarm/strategies.py`, `test_mission_swarm_e2e.py` |
| Agents | Frozen | Implemented / Verified | agent feature builder and platform registry | agent/provisioning/global pass | mixed status labels | participates in SCC | `agents/runtime.py`, `agents/registry.py`, `agents/provisioning.py` |
| Primary Agent | Frozen | Implemented / Verified | one primary runtime receives Skills/Project/Mission/Health/Loop views | primary initial/restart acceptance + global pass | current architecture doc | none observed | `primary_agent/runtime.py`; `test_primary_agent_*` |
| Persistent Agents | Frozen | Implemented / Verified | canonical provisioning/registry and assignments | provisioning, registry, project/skills acceptance pass | README says provisioning in development | documentation/status drift | `agents/provisioning.py`, `agents/identity.py` |
| Ephemeral Agents | Frozen | Implemented / Verified | Mission/Swarm owns bounded lifecycle; Skills leases injected | policy/resource/restart/swarm acceptance pass | current | none observed | `ephemeral_agents/runtime.py`; five named acceptance scenarios |
| Skills Runtime Phase 1 | Frozen | Implemented / Verified | storage + tool adapters, context and governance integrations | 5 architecture + functional + 7 acceptance paths pass | current and explicit exclusions | none observed | `skills/runtime.py`, `skills/package.py`, `bootstrap/features/skills.py` |
| Project Governance | Frozen | Implemented / Verified | storage/document/quality-gate adapters; Missions/Skills/Context consumers | 6 architecture + functional + 8 acceptance paths pass | current | none observed | `project_governance/runtime.py`, `contracts.py`, `models.py` |
| Intelligence Trust Boundary | Frozen | Implemented / Verified with known gap | egress gates injected into Model Router and Tool Runtime | 10 architecture + functional + 8 acceptance paths pass | gap is documented | UI-mediated upload path remains unguarded | `intelligence_boundary/runtime.py`; `test_intelligence_boundary_boundaries.py` |

No frozen domain was observed as Broken in the current suite. The important drifts are documentation/status drift and the explicitly tolerated global SCC, not a newly observed functional regression.

## 6. Test Results

| Command | Directory | Exit | Collected | Passed | Failed | Skipped | Xfail/Xpass | Errors | Warnings/notes | Duration |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | ---: |
| `.venv\Scripts\python.exe -m pytest tests/architecture -ra` | repo root | 0 | 113 | 113 | 0 | 0 | 0/0 | 0 | none reported | 41.12 s |
| `.venv\Scripts\python.exe -m pytest tests/acceptance -ra` | repo root | 0 | 96 | 96 | 0 | 0 | 0/0 | 0 | none reported | 46.48 s |
| `.venv\Scripts\python.exe -m pytest -ra` (first attempt) | repo root | 124 | NOT VERIFIED | — | — | — | — | — | audit executor timeout at 124 s; not a pytest failure | 124 s |
| `.venv\Scripts\python.exe -m pytest -ra` (unchanged rerun) | repo root | 0 | 1,210 | 1,208 | 0 | 2 | 0/0 | 0 | two Windows symlink capability skips | 722.01 s |
| `.venv\Scripts\python.exe -m ruff check .` | repo root | 0 | — | — | — | — | — | — | `All checks passed!` | 0.7 s wall |
| `git diff --check` | repo root | 0 | — | — | — | — | — | — | LF→CRLF working-copy warnings only | 0.3 s wall |

The two skips are `tests/test_data_maintenance.py:231` and `tests/test_storage_primitives.py:228`, both because symlink creation is unavailable on this Windows environment. No xfail/xpass markers were found. The baseline document reports 1,208 passed / 2 skipped in 851.42 s; current counts match and duration improved to 722.01 s without configuration changes.

## 7. Security Boundary Findings

### Tool Execution Boundary

- Verified: one descriptor registry and one executor are built in bootstrap; consumers do not import the concrete Desktop tool adapter; MCP and Desktop tool routes are covered by architecture tests.
- Verified: no production `shell=True`, `os.system`, `eval` or `exec` occurrence was found.
- Direct `subprocess.run`/`Popen` does exist in `desktop_automation/providers/*`, `speech_adapters/piper_tts.py` and `system_insight/providers/*`. Arguments are lists and timeouts are generally bounded; these are concrete technology adapters, not arbitrary shell strings.
- Risk: there is no Sandbox Execution Boundary. The architecture guardrail is narrower than “all subprocess must traverse ToolRuntime”; it allows these provider-owned execution paths. This is not proven exploitable, but the exception must be explicitly governed before Sandbox work or untrusted executable/model configuration is accepted.
- Auditability is strongest for ToolRuntime. Provider-local diagnostic/speech subprocesses do not share the same canonical execution ledger.

### Intelligence Trust Boundary

- Implemented controls include assets, classification, ownership, provider trust, purpose, minimization, redaction, manifests, approvals, derived provenance, ledger and operational profiles.
- Model generation is gated before `adapter.generate`; Tool/MCP processing is gated before handler invocation.
- Current Speech and Vision adapters contain no HTTP client markers and are treated as local.
- The project itself documents one known bypass family: UI-mediated Desktop Automation upload. The README and finalization report correctly do not claim full protection.
- Private eval assets are not yet owned by a runtime. `EvalReference` is metadata-only and private payload export is prohibited, which is a safe preparatory state.

### Secrets, external providers and artifacts

- No tracked/untracked `.env` was found; `.env.example` is present. No private key/certificate credential file was found outside ignored packaged CA material.
- Pattern hits in provider settings, tests and docs are mostly field names/redaction rules. No secret value is reported here.
- Local model tokenizer/vocabulary files produced false-positive token hits; they are not credentials.
- Risk: 76 untracked `data/` files, session/conversation records and 35 root logs may contain operational metadata or traces. Their contents were deliberately not reproduced. Current `.gitignore` does not cover every runtime family (for example conversations/audio/voice/vision/context-fusion artifacts).
- Two untracked model binaries total about 210.5 MiB. They create accidental-commit, repository-size and third-party-license risk.

## 8. Integration Findings

The canonical flow is `main.py` lifespan → `build_application()` → `create_runtime()` → 12 feature builders → `RuntimeContainer`. Concrete consumer-owned adapters for Context Fusion, Skills, Project Governance, Intelligence Boundary, Provider Taxonomy, Tool Execution and World State live under bootstrap. API uses one router registry; Commands uses one handler builder and registry. Lifecycle registers feature resources and starts/closes them deterministically.

Observed positive evidence:

- architecture tests prove a single full composition root and single tool registry/executor;
- every production Health contributor is registered;
- Skills, Governance and Intelligence Boundary are reachable from the real application;
- Model Router and Tool Runtime receive the live egress gate;
- Project Governance can receive evidence through `RFCEvidenceWritePort`/runtime and Missions receives an immutable implementation binding;
- Context Fusion consumes six bootstrap adapters rather than concrete domains.

Findings/debt:

- `RuntimeContainer` and some feature dependencies use broad `Any`, weakening static DI verification.
- `_build_commands` constructs services with `desktop/chat/world_state/attention/agent_loop=None`, then patches them after later composition. Tests prove the final graph works, but the partially initialized interval is structurally fragile.
- `MissionRuntime.dispatcher` is optional then injected later; it fails explicitly if unavailable, not silently.
- No proven port-without-adapter or adapter-without-consumer was found. Static absence alone was not treated as orphan proof because provider factories may construct adapters dynamically.
- Generic protocols in `synapse/contracts` overlap newer domain-owned ports; this is proven surface duplication but not proven safe-to-delete code.
- The 13-method `ToolExecutionPort` is broader than several consumers need and contributes to the global coupling hotspot.

## 9. Incomplete or Missing Capabilities

Evidence-backed gaps only:

- backend release readiness and reproducible committed baseline: missing;
- full Storage Primitives adoption beyond four pilots: partial;
- complete trust interception for UI-mediated uploads: missing;
- Sandbox Execution Boundary: missing;
- CI configuration: missing;
- active frontend/Electron ADE: missing (expected/planned);
- production service integration/health promotion/rollback orchestration: missing;
- full runtime artifact ignore/retention hygiene: partial;
- elimination of the 13-context bounded-context SCC: incomplete architecture debt;
- Private Evals, Skills Phase 2, Repository Runtime, Coding Sessions and Deployment Runtime: missing, as expected by official order.

## 10. Private Evals Readiness

### Existing and reusable

| Need | Current reusable evidence | Classification |
| --- | --- | --- |
| Evidence/acceptance/quality gates | `project_governance` models, runtime, ports and adapters | existing and reusable |
| Eval metadata reference | `project_governance.models.EvalReference` with dataset reference and private-only flag | preparatory contract only |
| Assets/classification/ownership | Intelligence Boundary asset/runtime contracts | existing and reusable |
| Provider restrictions/egress | trust profiles, gate, manifests, approvals, minimization/redaction | existing and reusable, with documented UI gap |
| Provenance/audit ledger | derived provenance and redacted immutable ledger | existing and reusable |
| Persistence primitives | atomic collection, locks, revisions, migrations, retention/recovery | existing and reusable pilot |
| Controlled execution | ToolExecutionPort, Missions, Workers, Swarm contracts | existing and reusable |
| Versioned Skills | discovery/resolution/loading/assignments/leases | existing, not an eval runtime |

### NOT FOUND

No production package/file implements eval suites, cases, private dataset custody, baseline snapshots, runs, scoring, verdicts, deterministic model snapshots, comparison, regression detection, evaluator provenance, reproducibility replay or eval-specific evidence emission. No `private_evals` bounded context, API, Commands, bootstrap feature, storage collection or tests exist.

### Risks and prerequisites

- Freeze/checkpoint the exact green working tree so a future eval baseline is reproducible.
- Define private dataset ownership and storage/egress handling using existing Intelligence Boundary contracts without embedding payloads in Governance documents/events.
- Decide how deterministic execution snapshots bind model/provider/config/tool versions; current contracts provide pieces, not a complete eval-run identity.
- Preserve one-way dependencies: Private Evals may consume Governance, Intelligence, Storage and orchestration ports; frozen domains must not import its concrete runtime.
- Treat the existing 13-context SCC as inherited debt; it is not an exact-module cycle and no test shows it blocks a new acyclic context, but new edges must not enter it unnecessarily.

Technical boundaries are sufficient to begin **inventory and architecture design** without changing frozen contracts. The current workspace is **not safely ready to start that phase until the P0 reproducibility/Git baseline is resolved**.

## 11. Premature Future-Domain Code

| Future domain | Observed code | Classification |
| --- | --- | --- |
| Private Evals Runtime | `EvalReference`, `private_eval_only`, dataset reference validation and no-export guard in Project Governance | preparatory frozen contract; belongs to Governance, not a runtime |
| Skills Runtime Phase 2 | no generation/mutation/promotion/evolution runtime; docs/tests prohibit it | NOT FOUND; no premature autoevolution |
| Sandbox Execution Boundary | direct provider subprocesses; Docker packaging; no generic sandbox port/backend | missing boundary; existing subprocess adapters require future analysis |
| Repository Runtime | no production Git/worktree/branch/commit/diff implementation | NOT FOUND |
| Coding Sessions | no production session/checkpoint/coding workflow package | NOT FOUND |
| Deployment Runtime | root Dockerfile and Compose only | Scaffold Only; no release/promotion/rollback/health/deployment runtime |

Disabled MCP seed names include GitHub and Docker, but their manifests are unconfigured placeholders; they are not Repository or Deployment runtimes.

## 12. Documentation Drift

| Document | Drift | Evidence |
| --- | --- | --- |
| `README.md` | says Swarm is Planned and latest validation is 923 tests | current code has `swarm/runtime.py`; 1,208 tests pass |
| `docs/roadmap.md` | says Swarm is specification-only and provisioning global baseline is red | Swarm acceptance passes; global suite is green |
| `docs/audits/project-state-for-new-chat.md` | says Voice, Avatar and Perception are not implemented | packages, bootstrap integration and tests now exist |
| `docs/audit/current-dependency-graph.md` | headline says 72/261, later validation bullet says 247 edges | executable graph is 261 |
| `docs/audit/current-scc-inventory.md` | retains 247-edge snapshot | predates Governance/Skills/Intelligence additions; should be labeled historical |
| `docs/audit/current-dependency-graph.json` | contains 69/249 historical snapshot while sibling Markdown claims current authority | JSON explicitly says historical, but filename is misleading |
| `bootstrap/application.py` module docstring | says Phase 1 does not decompose API/Commands | routers and handlers are decomposed and guarded |
| `docs/backend/module-status.md` | says Primary/ephemeral final global gate pending | current global and dedicated acceptance gates pass |

Correct/current authorities include `docs/validation/backend-freeze-baseline.md`, the three latest finalization reports, `docs/architecture.md` headline metrics and executable architecture tests. Historical documents are useful evidence but should not be read as current state without their dates/addenda.

## 13. Risk Register

| ID | Finding | Severity | Evidence | Impact | Recommended Next Step |
| --- | --- | --- | --- | --- | --- |
| R-01 | Validated backend is overwhelmingly uncommitted/untracked | High | 940 untracked, 100 modified, 8 deleted; HEAD has 74 vs current 454 Python files | baseline cannot be reproduced, reviewed or safely extended | review ownership, remove/ignore artifacts, establish an approved checkpoint before new domain work |
| R-02 | Runtime/test/model artifacts are untracked and incompletely ignored | High | 35 logs/7.69 MiB; 76 data files; ~210.5 MiB models; WAV | sensitive-data leak, accidental commit, repo bloat | inventory safely and update retention/ignore policy in a separately authorized change |
| R-03 | UI-mediated Desktop upload bypass remains | High | README and Intelligence finalization report | external egress may avoid classification/policy/ledger | block use for private eval assets or design a governed path before implementation |
| R-04 | One 13-context/35-edge SCC remains | Medium | executable graph and architecture test baseline | change amplification and ownership ambiguity | keep new domain outside SCC; plan evidence-driven reductions separately |
| R-05 | Direct provider subprocesses lack a unified sandbox/audit boundary | Medium | Desktop/Speech/System Insight provider modules | process isolation/audit varies by provider | make explicit inputs/trust model a prerequisite for Sandbox design |
| R-06 | Private Evals runtime capabilities are absent | Informational | no package/files; only `EvalReference` metadata | expected next-domain work remains | begin architecture only after R-01 |
| R-07 | Canonical docs contradict current implementation | Medium | README/roadmap/old audit/graph report | incorrect planning and freeze decisions | reconcile in a separately authorized documentation pass |
| R-08 | Storage adoption remains a four-store pilot | Medium | storage finalization docs and architecture tests | future eval volume/retention may exceed current adoption | define eval-specific storage needs using existing primitives |
| R-09 | DI has partially initialized/`Any` surfaces | Low | `RuntimeContainer`, `_build_commands`, optional dispatcher | integration errors may escape static checks | add targeted architecture assertions when extending composition; do not refactor frozen code now |
| R-10 | No CI configuration | Medium | `.github` NOT FOUND | green state depends on local manual execution | create CI only under a separate implementation authorization |
| R-11 | Windows symlink paths not exercised | Low | two pytest skips | symlink security/behavior remains unverified on this host | run the same tests in a symlink-capable controlled environment |
| R-12 | No secret value was found by pattern scan, but full secret scanning is NOT VERIFIED | Low | path-only scan; runtime artifacts not opened | residual credential risk | run an approved secret scanner before checkpoint/publication (project remains private) |

## 14. Recommended Next Actions

### P0 — blocks continuation

1. Establish an approved, reviewable and reproducible checkpoint for the exact 1,208-green state. The audit does not prescribe commit structure and did not stage/commit anything.
2. Before checkpointing, classify the 940 untracked files and prevent runtime logs, conversations/sessions, downloaded models and WAV artifacts from entering the source baseline. Do not delete them without explicit owner approval.

These P0 items block starting Private Evals safely in the present workspace. No P0 functional regression or exact-module architectural cycle was found.

### P1 — resolve before Private Evals freeze

1. Define eval asset/dataset custody through Intelligence Boundary assets and egress; explicitly exclude the known UI upload bypass.
2. Define reproducibility identity for run, suite/case/dataset versions, model/provider configuration, tools, Skills and code baseline.
3. Select eval-specific Storage Primitive usage, retention, redaction, recovery and pagination based on expected volume.
4. Add architecture/acceptance gates proving Private Evals remains outside the global SCC and frozen domains import contracts only.
5. Reconcile current canonical documents and graph snapshots.
6. Decide whether provider-local subprocess paths are explicit exceptions or future Sandbox consumers.

### P2 — proven debt

- reduce the 13-context SCC only through separate evidence-backed phases;
- narrow broad ports/`Any` views when a concrete consumer need demonstrates value;
- remove partially initialized composition states only with behavioral equivalence evidence;
- add CI and symlink-capable validation;
- complete Storage adoption where workload evidence justifies it.

### No Action

- bare `pass` in empty exception classes;
- disabled GitHub/Docker MCP seed manifests;
- Dockerfile/Compose as local packaging scaffolding;
- historical reports clearly dated as historical;
- two environment-driven symlink skips, provided they remain visible and are validated elsewhere before release.

## 15. Final Verdict

- **Really concluded and verified in the present tree:** Bootstrap/Composition/Lifecycle/DI; API routers and Commands registry; Provider Taxonomy; Tool Execution Boundary within its documented scope; Storage Primitives pilot; Memory; Context Fusion; Missions/Workers/Swarm; Agents/Primary/Persistent/Ephemeral; Skills Runtime Phase 1; Project Governance; Intelligence Trust Boundary within its documented scope.
- **Frozen with drift:** no frozen domain has a demonstrated functional regression, but API/Commands, Swarm, persistent-agent status and several overall status documents have documentation drift. The Tool/Intelligence boundaries retain documented scope gaps.
- **Partial:** broader storage adoption, complete egress interception, reproducible Git/governance baseline and process sandboxing.
- **Broken:** none demonstrated by the current suites. The uncommitted baseline is operationally unsafe, not a test failure.
- **Missing:** Private Evals Runtime, Skills Phase 2, Sandbox Execution Boundary, Repository Runtime, Coding Sessions, Deployment Runtime, CI and active frontend.
- **Architectural blocker before Private Evals:** no new exact-module cycle or frozen-domain regression; however, the non-reproducible dirty workspace is a P0 governance blocker. The inherited 13-context SCC is material debt but does not currently prevent an acyclic new context.
- **Ready to start Private Evals Phase 1:** **NO, not safely in the current workspace.** After the validated state is checkpointed and runtime artifacts are separated, the existing contracts are sufficient to begin inventory and architecture without speculative changes to frozen modules.
- **Backend status:** **NOT READY**.

Audit mutation statement: this audit created only this Markdown report. It changed no functional code, tests, configuration, contract, frozen module or Git state and made no commit.
