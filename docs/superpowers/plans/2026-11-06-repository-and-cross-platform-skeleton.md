# Repository and Cross-platform Skeleton Implementation Plan

Status: **SUPERSEDED / NOT EXECUTABLE — 2026-11-09 PL-001/PL-006 amendment**.

All tasks below are historical Electron/Node/TypeScript instructions. They must
not be dispatched or used to scaffold a product. The owner selected native Rust
application/device integration plus Python AI; Gate 00 is **BLOCKED / REOPENED**.
Complete the [foundation revalidation plan](2026-11-09-rust-python-foundation-revalidation.md)
before writing a replacement Plan 01. This notice overrides every execution
directive, technology choice and checkbox below; preserve them as history only.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a reproducible three-platform repository and inert Core/client
bootstrap with a separately labelled packaged synthetic IPC/transport smoke test.

**Architecture:** A Python modular-monolith package owns the future Core;
independent CLI and Electron/React packages consume generated versioned contracts.
The product bootstrap remains inert; a test-only gRPC fixture proves the packaged
renderer/preload/main boundary without promoting its bearer to product identity.

**Tech Stack:** CPython 3.14.10 standard GIL, uv 0.13.7, Node 24.22.2,
JS pnpm 11.25.0, TypeScript 7.0.2, gRPC/Protobuf, linked SQLite >=3.51.3;
Electron/React exact pins selected and recorded by Task 1 before use.

**Spec:** `docs/specs/subprojects/01-repository-and-skeleton.md`

## Global Constraints

- CPython 3.14.10, standard GIL; uv 0.13.7; Node.js 24.22.2; JavaScript pnpm
  11.25.0 under that Node; TypeScript 7.0.2. PowerShell 7.6+ runs foundation gates.
- gRPC over HTTP/2 with Protocol Buffers; package `synapse.foundation.v1`, contract version `1.0`.
- SQLite WAL, `synchronous=FULL` per connection, linked SQLite >=3.51.3 (Windows measured 3.53.1).
- Windows 11 x64, Ubuntu 24.04 x64/glibc and macOS 14+ arm64 are required lanes.
- Windows Server 2025 x64 is a separately labelled CI surrogate.
- No archived runtime/state or experiment implementation code enters product packages.
- No personal data, product credentials, arbitrary tools, remote listeners or mission effects.
- All AI remains local; no weights or inference are required in this plan.
- Product lifecycle/authentication, journal and reconnect/replay remain Plan 02 work.
- E-02/E-05/E-04 precede sensitive credential/tool/remote implementation; R-01–R-04 remain NOT ACCEPTED.
- No platform reaches VALIDATED/OPERATIONAL here; no shared merge/push/publication is authorized.

## Review Focus

- Wrong interpreter or stale locks must fail before bootstrap; Task 2 pins/probes both tools and frozen installs.
- Malformed or foreign-major status must be refused without private diagnostics; Task 3 tests strict parsing and canaries.
- A renderer/frame without ownership must fail even if it knows the IPC method; Task 5 tests the actual packaged boundary.
- A test bearer/server accidentally included in a release must block packaging; Task 5 inspects both smoke and normal artifacts.
- Missing platform runs must block three-platform acceptance; Task 6 tests a missing-lane receipt and reports NOT RUN explicitly.

## File structure and responsibilities

| Files | Responsibility |
|---|---|
| `docs/adr/0004-skeleton-dependencies.md`, `docs/security/skeleton-boundary.md` | Exact desktop/tool pins, licences/provenance and pre-implementation boundary design |
| `pyproject.toml`, `uv.lock`, `package.json`, `pnpm-workspace.yaml`, `pnpm-lock.yaml`, `.python-version`, `.node-version` | Workspace and exact tool/dependency locks |
| `core/pyproject.toml`, `core/src/synapse_core/{__init__,__main__,bootstrap}.py` | Installable inert Core package and strict allowlisted check |
| `apps/cli/package.json`, `apps/cli/src/{index,bootstrap}.ts` | Client-only bootstrap command and parser |
| `packages/contracts/{package.json,proto/synapse/foundation/v1/lifecycle.proto,tools/generate.mjs}` | Published v1 schema, locked generation and generated client packages |
| `apps/desktop/{package.json,src/main.ts,src/preload.ts,src/renderer.tsx,index.html}` | Packaged client isolation, typed narrow API and minimal status view |
| `tools/repository/{check-policy.mjs,test-policy.mjs,verify.mjs}`, `.github/workflows/skeleton.yml` | Policies, deterministic orchestration and architecture-specific CI |
| `tests/skeleton/{test_bootstrap.py,cli.test.ts,contract.test.ts,packaged.test.ts,fixture_server.py}` | Negative/real bootstrap and packaged synthetic composition |
| `docs/evidence/skeleton/{dependencies.md,platform-matrix.md,gate-01.md}`, `docs/development.md` | Exact receipts, reproduction, limits and handoff |

Generated clients live under `packages/contracts/generated/{python,typescript}`;
commit deterministic generated sources and verify regeneration produces no diff.
Core's Python distribution imports generated Python messages, never Node types.
The desktop transport adapter remains in main; preload never imports gRPC.

---

### Task 1: Resolve desktop pins and security prerequisites

**Files:** Create `docs/adr/0004-skeleton-dependencies.md`,
`docs/security/skeleton-boundary.md`, `docs/evidence/skeleton/dependencies.md`.

**Interfaces:** Consumes ADRs 0001–0003 and AI-01–AI-10. Produces exact Electron,
React, React DOM, builder and packaged-test-runner pins plus primary source,
licence, embedded Node version and supported OS/architecture evidence for each;
defines normal versus smoke artifact build mode and fixture principal lifetime.

- [ ] **Step 1:** Add a document acceptance checklist to `dependencies.md`:
  every chosen dependency has exact version/hash/source/licence, embedded Node
  is identified separately, all three target artifacts exist, no R-01–R-04 risk
  is accepted, and production credentials remain gated by E-02.
- [ ] **Step 2:** Review the absent ADR/model against the checklist; record RED
  for missing pins, missing boundary owners and missing artifact evidence.
- [ ] **Step 3:** Query only primary upstream release/package documentation,
  select the smallest supported desktop/build/test set, document distribution
  constraints and exact pins in ADR 0004. Do not silently change ADRs 0001–0003.
  Model trusted app-owned bootstrap versus arbitrary tool execution, fixture
  process cleanup, endpoint ownership, sender/frame checks, token disposal and
  non-release package separation before any corresponding code is written.
- [ ] **Step 4:** Recheck every acceptance row; unresolved architecture or
  required artifact means BLOCKED. Have the independent task reviewer verify
  the model/pins before Task 2; checklist PASS is documentation evidence only.
- [ ] **Step 5:** Commit `docs(skeleton): pin desktop build and isolation prerequisites`.

### Task 2: Establish locked workspaces and deterministic policy gates

**Files:** Create root manifests/locks/version files, `core/pyproject.toml`,
`apps/{cli,desktop}/package.json`, `packages/contracts/package.json`,
`tools/repository/{check-policy,test-policy}.mjs`; modify `.gitignore`.

**Interfaces:** `checkRepository(root: string): Promise<string[]>` returns
stable policy error codes, no private source values. `node tools/repository/test-policy.mjs`
is the permanent policy-negative entry point. No product process runs yet.

- [ ] **Step 1:** Write tests using disposable fixture trees: archived/runtime
  import => `ARCHIVE_IMPORT`; `.env`/database/raw-audio/private canary tracked
  => `PRIVATE_ARTIFACT`; Core importing client => `DEPENDENCY_DIRECTION`;
  unpinned direct dependency => `UNPINNED_DEPENDENCY`; changed lock with frozen
  install => nonzero; wrong Python/Node/pnpm patches => `TOOLCHAIN_VERSION`.
  An allowed new-source fixture returns `[]` and canary values never appear in
  diagnostics. Inspect actual import/configuration edges, not prose matches.

  ```ts
  assert.deepEqual(await checkRepository(allowedFixtureRoot), []);
  assert.deepEqual(await checkRepository(archiveImportFixtureRoot), ['ARCHIVE_IMPORT']);
  ```
- [ ] **Step 2:** Run `node tools/repository/test-policy.mjs`; expect missing
  implementation failure and record RED.
- [ ] **Step 3:** Implement `checkRepository` and exact workspaces from Task 1.
  Root Python workspace includes `core`; pnpm includes `apps/*` and
  `packages/*`. Install hooks/source builds stay disabled. Keep only needed
  gRPC/codegen/test dependencies; do not copy the entire inference experiment.
- [ ] **Step 4:** Run the policy tests, `uv sync --locked --no-build --python
  3.14.10` and `pnpm install --frozen-lockfile --ignore-scripts` under selected
  tools; expected zero exit and unchanged locks. Explicitly audited Electron
  binary acquisition is a separate hashed Task 1 operation, not an arbitrary
  lifecycle-script exemption. Run the foundation selected runtime fixture too.
- [ ] **Step 5:** Commit `chore(skeleton): add locked clean-room workspaces and policies`.

### Task 3: Generate contracts and implement inert Core/CLI bootstrap

**Files:** Create contract schema/generator/generated outputs,
`core/src/synapse_core/{__init__,__main__,bootstrap}.py`,
`apps/cli/src/{index,bootstrap}.ts`, `tests/skeleton/{test_bootstrap.py,cli.test.ts,contract.test.ts}`.

**Interfaces:** Python `check() -> dict[str, object]` returns exactly
`{"healthy": True, "contractVersion": "1.0"}`. Module `--check` prints that
JSON and exits 0. TypeScript `parseStatus(input: unknown): FoundationStatus`
returns `{ healthy: boolean; contractVersion: string }`, accepting only those
keys, true health and implemented major 1; otherwise throws `INVALID_STATUS`.
CLI `synapse --check` invokes the owned installed Core command, parses it and
prints the same allowlisted object. Unknown actions exit 2 with `UNKNOWN_ACTION`.

- [ ] **Step 1:** Add assertions for exact allowed status, foreign major `2.0`,
  unknown field containing a private canary, malformed JSON, failed child and
  unknown CLI action. Denials must not echo canaries. Require no state/socket
  creation by Core check; generated types reject wrong identifier/cursor types.
  Compare schema field numbers/names/service signatures to ADR 0002; deletions
  must reserve tags/names and breaking change must require a new major.

  ```python
  assert check() == {"healthy": True, "contractVersion": "1.0"}
  ```

  ```ts
  assert.deepEqual(parseStatus({ healthy: true, contractVersion: '1.0' }),
    { healthy: true, contractVersion: '1.0' });
  assert.throws(() => parseStatus({ healthy: true, contractVersion: '2.0' }), /INVALID_STATUS/);
  ```
- [ ] **Step 2:** Run `uv run --locked pytest tests/skeleton/test_bootstrap.py -q`
  and `pnpm test:skeleton:contracts`; expect missing bootstrap/parser/generation RED.
- [ ] **Step 3:** Implement the exact interfaces. Publish the approved schema
  through a fresh generator; no experiment server/client implementation imports.
  Resolve the Core executable from the installation, without a shell or renderer
  path input; bound child lifetime and reap it. Keep transport server, persistence
  state, owner approvals and arbitrary execution absent from product bootstrap.
- [ ] **Step 4:** Repeat both commands; run `python -m synapse_core --check` from
  the installed locked environment and `pnpm --filter @synapse/cli check`.
  Expect the exact JSON; generate twice and require `git diff --exit-code --
  packages/contracts/generated`. Run selected gRPC contract and persistence
  foundation suites, preserving 120 confirmed kills and zero acknowledged loss.
- [ ] **Step 5:** Commit `feat(skeleton): add generated contracts and inert bootstrap`.

### Task 4: Build a strict three-platform verification lane

**Files:** Create `tools/repository/verify.mjs`, `.github/workflows/skeleton.yml`,
`docs/evidence/skeleton/platform-matrix.md`, `docs/development.md`.

**Interfaces:** `node tools/repository/verify.mjs --lane <windows-x64|linux-x64|macos-arm64>`
validates actual OS/architecture, tool versions, frozen installs, policies,
generation, build, tests and selected foundation checks; exits nonzero on any
failure and emits allowlisted JSON receipts with commit/commands/exit codes.
Receipts use `.local/skeleton/<lane>/receipt.json`, with `commit`, `lane`,
`os`, `architecture`, `tools`, `artifact_sha256`, `checks` (command/exit/log hash)
and `limitations`; never include credentials or private absolute paths.
Packaged tests are added to the same verifier by Task 5, not silently omitted.

- [ ] **Step 1:** Add verifier tests in `tools/repository/test-policy.mjs` for
  wrong architecture, failed subprocess and missing required suite receipt;
  assert nonzero/no PASS. Require Windows Server versus Windows 11 identity
  to remain distinct. A successful fake receipt is orchestration-only evidence.
- [ ] **Step 2:** Run policy tests; expect verifier-missing RED.
- [ ] **Step 3:** Implement the verifier and workflow: Windows Server 2025 x64,
  Ubuntu 24.04 x64 and a verified macOS 14+ arm64 runner. Pin actions by audited
  commit and tool downloads by version/hash. Read-only repository permissions;
  never run untrusted PR content with secrets. Upload only allowlisted receipts
  and synthetic smoke artifacts. Add Windows 11 physical development receipt.
- [ ] **Step 4:** Run local matching lane and inspect workflow validation;
  expected zero exit locally. Dispatch other lanes only when authorized; their
  absence is BLOCKED/NOT RUN for acceptance. Never claim static YAML is CI proof.
- [ ] **Step 5:** Commit `ci(skeleton): verify selected foundation across platform lanes`.

### Task 5: Prove packaged renderer isolation against a real synthetic service

**Files:** Create desktop source/index, `tests/skeleton/{packaged.test.ts,fixture_server.py}`;
modify desktop build scripts and `tools/repository/verify.mjs`.

**Interfaces:** `window.foundation.getStatus(): Promise<FoundationStatus>` is
the only renderer capability. Main uses the generated contract and selected gRPC
adapter to a test-harness-owned ephemeral numeric-loopback service; credentials,
endpoint and raw IPC stay in main. Fixture implements v1 health only and returns
structured denial for unsupported commands; no durable product journal exists.
The harness owns PID/readiness/timeout/reaping. Normal artifact contains neither
fixture server nor test credential/injection switch; smoke artifact is labelled
non-release, synthetic and separate from the normal package.

- [ ] **Step 1:** Write packaged tests: allowed named status round trip succeeds
  through real renderer/preload/main/gRPC; forged sender/frame/unknown method,
  extra payload, raw IPC/token/endpoint exposure, direct renderer network and
  nonlocal binding fail. Navigation/destruction tears down owned subscriptions
  or requests and owned fixture processes. Inspect actual BrowserWindow settings
  and network activity; assert sandbox/context isolation on and Node off.
  Assert normal artifact excludes fixture/bearer; smoke build cannot publish.
- [ ] **Step 2:** Run `pnpm test:skeleton:packaged`; expect missing packaged app
  RED. No browser-only or standalone Node substitution counts as packaged proof.
- [ ] **Step 3:** Implement minimal React status surface, isolated preload and
  main sender/frame/method/payload ownership checks per Task 1 model. Validate
  inputs again at fixture server; no generic IPC/send/arbitrary command API.
  Configure restrictive CSP/navigation/network and teardown; expose no remote
  enablement. Record embedded Node and native dependency behavior at runtime.
- [ ] **Step 4:** Build with `pnpm build:skeleton:smoke`, run packaged tests and
  normal-artifact inspection on every applicable lane. Expected PASS with actual
  artifact hashes; missing display/runner/native binary is BLOCKED. Delete only
  harness-owned temporary state and prove child exit; do not call this product auth.
- [ ] **Step 5:** Commit `feat(skeleton): prove packaged synthetic IPC boundary`.

### Task 6: Exact-artifact acceptance and Plan 02 handoff

**Files:** Create `docs/evidence/skeleton/gate-01.md`; update platform matrix
and development guide. Add receipt negatives to `tools/repository/test-policy.mjs`.

**Interfaces:** Gate 01 consumes exact commit/artifact and all three lane
receipts plus Windows 11 receipt; produces PASS/FAIL/BLOCKED and an explicit
Plan 02 prerequisite list, never product-operation or sensitive-boundary approval.
`node tools/repository/verify.mjs --gate --receipts .local/skeleton` reads the
required lane subdirectories and Windows 11 receipt, checks they identify the
current exact HEAD, and exits nonzero for missing/failed/stale evidence.

- [ ] **Step 1:** Add negative assertions: one missing lane, wrong commit,
  altered artifact hash, missing packaged test, skipped selected suite or
  credential/personal-data placeholder => gate rejects; intact receipts pass.
- [ ] **Step 2:** Run `node tools/repository/test-policy.mjs`; expect missing
  acceptance checks RED.
- [ ] **Step 3:** Add the minimal acceptance checks to `verify.mjs`; document
  limits and exact interface handoff. Plan 02 must resolve product local identity,
  issuance/discovery and owner policy under E-02 before product integration,
  then implement durable lifecycle/replay with ADR 0003 semantics. Carry forward
  AI-01–AI-10, PC-01–PC-04 and E-01–E-05 without risk acceptance.
- [ ] **Step 4:** Clone the proposed committed artifact cleanly, run each selected
  suite and matching packaged lane; collect actual other-platform receipts.
  No missing lane may be marked PASS. Obtain independent exact-artifact QA;
  after separately authorized integration repeat regression on integrated HEAD.
  Revert code/locks together and rebuild prior artifact to prove rollback.
- [ ] **Step 5:** Commit `docs(skeleton): record exact-artifact build and isolation gate`.

## Decision Charter Compliance

**Charter:** `docs/specs/2026-11-06-synapse-0.3-decision-charter.md`

**Binding decisions:** CR-001, CR-002, CR-003, CR-004, MI-003, MI-004,
MI-006, MI-007, SE-001, SE-002, SE-004, SE-005, SE-006, PL-001, PL-002,
PL-003, PL-004, QA-001, QA-002, QA-003.

| Decision | Implementation obligation | Test/evidence owner |
|---|---|---|
| CR-001, CR-002, CR-003 | No historical source/state; isolated mission and shared 0.3 source | Task 2 policies; Task 6 independent QA |
| CR-004 | No private/secret/raw-audio state in Git/artifacts/diagnostics | Tasks 2/3 canaries; Task 5 artifact inspection |
| MI-003, MI-004 | Inert bootstrap cannot grant approval or execute effects | Task 3 unknown-action/side-effect negatives |
| MI-006, MI-007 | Independent exact-artifact QA, authorized regression and rollback | Task 6 |
| SE-001, SE-002, SE-004 | Local-only checks, opaque future credentials, untrusted renderer; no real credential implementation | Tasks 1/3/5 model and denial evidence |
| SE-005, SE-006 | Client-only CLI, app-owned bootstrap, formal sensitive-boundary prerequisites | Tasks 1/3; E-02/E-05 stay blocked |
| PL-001, PL-002, PL-003 | Independent client/Core packages; stable v1 contracts; no remote or microservices | Tasks 2/3/5 |
| PL-004 | Required platform lanes with truthful physical limits | Tasks 4/6 |
| QA-001, QA-002, QA-003 | Named artifact, RED/GREEN, real packaged composition, limitations | Every task and Task 6 acceptance |

**Reviewed but not applicable:** PX-001–PX-006 (no experience implementation),
VO-001–VO-006 (no audio), ME-001–ME-005 (no memory/personal persistence),
MI-001/MI-002/MI-005 (no mission contract/effects), SK-001–SK-004 (no Skills),
MM-001/MM-002 (no cognition/resource UI), SW-001–SW-004 (no product Swarm),
SE-003 (no browsing), PL-005 (no background host). No requirement is waived.

**Proposed deviations:** None.

## Self-review and execution handoff

Spec coverage: pins/security Task 1, repository Task 2, contracts/bootstrap Task 3,
platform verification Task 4, packaged IPC Task 5, evidence/rollback Task 6.
All five Review Focus conditions have named owning tests. Types and command
entry points above are the published handoff; there is no product implementation
in Gate 00. This plan awaits review and a separate implementation instruction.
