# Foundation Decision Gates Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce reproducible, reviewed decisions for the Synapse 0.3 runtime,
transport, persistence, hardware budget and foundation security boundary before
any product scaffold is created.

**Architecture:** All executable work in this plan lives under `experiments/` or
`tools/foundation/`; none becomes product runtime by accident. Identical
fixtures compare candidates, ADRs record evidence, and Gate 00 blocks the first
product plan until every decision passes.

**Tech Stack:** Markdown ADRs; PowerShell 7.6+ foundation checks; `uv` 0.10+ for
isolated Python 3.13/3.14 experiments; TypeScript clients run with the selected
Node/pnpm toolchain; Protocol Buffers/gRPC and HTTP/WebSocket are transport
candidates; SQLite WAL is the initial persistence candidate.

**Spec:** `docs/specs/2026-11-06-synapse-0.3-clean-room-design.md`

## Global Constraints

- Do not copy or import runtime code, build output, state or configuration from
  0.2 or the archived pre-clean-room attempt.
- Do not create `apps/`, `core/`, `packages/` or other product source roots in
  this plan.
- The current target is Windows 11 x64 on the owner's current machine.
- All runtime AI, voice, memory and RAG operations remain local.
- The future Core/client boundary must support authenticated remote transport
  without changing domain contracts.
- Shared choices must remain implementable and testable on Windows, Linux and
  macOS.
- No experiment result is `OPERATIONAL`; it is evidence for an ADR only.
- Every ADR names rejected alternatives, measured evidence and rollback cost.
- No secret, credential, raw audio, personal content or runtime state enters Git.

## Review Focus

- Missing GPU APIs or low VRAM must produce an explicit CPU/degraded capability
  result, not an empty or successful-looking inventory (Task 1).
- A stale or incompatible Python/Node dependency must fail the toolchain gate
  before scaffolding (Task 2).
- Core restart, client reconnect and event replay must not duplicate a command
  or lose the acknowledged event boundary (Task 3).
- Abrupt process termination during a write must recover the last committed
  record and reject corrupt or partial data (Task 4).
- A client, experiment process or future model must not gain authority merely by
  reaching the loopback endpoint (Task 5).

---

### Task 1: Reproducible host capability baseline

**Files:**
- Create: `tools/foundation/collect-host-capabilities.ps1`
- Create: `tools/foundation/test-host-capabilities.ps1`
- Create: `docs/evidence/foundation/host-capabilities.schema.json`
- Generate: `docs/evidence/foundation/host-capabilities.windows.json`
- Create: `docs/evidence/foundation/README.md`

**Interfaces:**
- Consumes: local read-only OS, CPU, RAM, GPU, disk, audio-device and installed
  tool information.
- Produces: `Get-SynapseHostCapabilities -OutputPath <path>` and a JSON document
  with `captured_at`, `os`, `cpu`, `memory`, `gpus`, `disks`, `audio`, `tools`
  and `limitations` keys.

- [ ] **Step 1: Write the failing schema/fixture check**

  `test-host-capabilities.ps1` must fail when a required key is absent, a byte
  quantity is negative, a GPU query returns no device and no limitation, or the
  document contains environment-variable values matching secret-like names.

- [ ] **Step 2: Run the check before the collector exists**

  Run: `pwsh -NoProfile -File tools/foundation/test-host-capabilities.ps1`

  Expected: non-zero exit naming the missing collector or fixture.

- [ ] **Step 3: Implement the read-only collector**

  Implement `Get-SynapseHostCapabilities -OutputPath <path>` without installing
  software, changing settings or emitting serial numbers, usernames, paths,
  tokens or raw device identifiers. Unsupported probes append a structured
  limitation instead of disappearing.

- [ ] **Step 4: Generate and validate the Windows fixture**

  Run:
  `pwsh -NoProfile -File tools/foundation/collect-host-capabilities.ps1 -OutputPath docs/evidence/foundation/host-capabilities.windows.json`

  Run: `pwsh -NoProfile -File tools/foundation/test-host-capabilities.ps1`

  Expected: exit 0 and a human-readable PASS summary.

- [ ] **Step 5: Commit the baseline**

  Commit: `chore(foundation): record clean-room host capabilities`

### Task 2: Core runtime and toolchain compatibility gate

**Files:**
- Create: `experiments/runtime-compatibility/README.md`
- Create: `experiments/runtime-compatibility/pyproject.toml`
- Create: `experiments/runtime-compatibility/tests/test_runtime_imports.py`
- Create: `experiments/runtime-compatibility/package.json`
- Create: `experiments/runtime-compatibility/tests/runtime-client.test.ts`
- Create: `docs/adr/0001-core-runtime-and-toolchain.md`
- Create: `docs/evidence/foundation/runtime-compatibility.md`

**Interfaces:**
- Consumes: Task 1 host/tool inventory and primary-source support matrices.
- Produces: one pinned Core Python minor, Node major, pnpm major and package
  policy; records whether Python 3.13 or 3.14 is the accepted Core baseline.

- [ ] **Step 1: Write failing compatibility tests**

  `test_runtime_imports.py` imports the candidate async, schema, local inference,
  STT, TTS, ONNX and SQLite libraries without loading a model. The TypeScript
  test proves ESM, generated types, child-process cancellation and clean exit.

- [ ] **Step 2: Run the tests in isolated 3.13 and 3.14 environments**

  Run: `uv run --python 3.13 --project experiments/runtime-compatibility pytest -q`

  Run: `uv run --python 3.14 --project experiments/runtime-compatibility pytest -q`

  Run: `pnpm --dir experiments/runtime-compatibility test`

  Expected before dependency declaration: FAIL with missing candidate packages.

- [ ] **Step 3: Add only the minimum compatibility dependencies**

  Pin exact versions and hashes in the experiment lockfiles. Use official
  documentation/release metadata and record source URL plus access date. Do not
  download model weights in this task.

- [ ] **Step 4: Repeat the matrix and record cold-start/RSS**

  Expected: at least one Python minor and one Node toolchain pass on the current
  host. Any unsupported candidate is recorded as rejected, not patched locally.

- [ ] **Step 5: Write ADR 0001 and validate it**

  ADR 0001 must state the selected versions, dependency policy, cross-platform
  CI floors, rejection evidence and upgrade rule. Run the experiment tests once
  more using only selected versions.

- [ ] **Step 6: Commit the runtime decision**

  Commit: `docs(adr): select Synapse core toolchain`

### Task 3: Versioned client/Core transport spike

**Files:**
- Create: `experiments/transport/proto/synapse/foundation/v1/lifecycle.proto`
- Create: `experiments/transport/server/`
- Create: `experiments/transport/client/`
- Create: `experiments/transport/tests/test_contract_semantics.py`
- Create: `experiments/transport/tests/reconnect.test.ts`
- Create: `docs/adr/0002-client-core-transport.md`
- Create: `docs/evidence/foundation/transport-spike.md`

**Interfaces:**
- Consumes: ADR 0001 toolchain.
- Produces: versioned `GetStatus`, `SubscribeEvents`, `SubmitCommand` and
  `CancelCommand` contract semantics, including `command_id`, `event_id`,
  `causation_id`, `contract_version` and structured error fields.

- [ ] **Step 1: Define transport-neutral failing fixtures**

  Tests must prove health, one acknowledged command, ordered event replay after
  reconnect, idempotent duplicate `command_id`, cancellation and rejection of
  an incompatible major contract version.

- [ ] **Step 2: Run fixtures with no server**

  Expected: FAIL because no candidate implements the lifecycle contract.

- [ ] **Step 3: Implement the smallest gRPC/Protocol Buffers candidate**

  Keep domain messages free of Electron and OS types. Bind to an ephemeral
  loopback port only and use a test-only authentication token.

- [ ] **Step 4: Implement the smallest HTTP/WebSocket candidate**

  Use the same fixture semantics, payload fields and failure cases so results
  compare the boundary rather than different behavior.

- [ ] **Step 5: Measure and fault-test both candidates**

  Record startup time, idle RSS, reconnect latency, generated-client ergonomics,
  cancellation, backpressure, Windows process restart and future TLS/pairing
  compatibility. Kill the server between acknowledged events and prove replay
  does not duplicate the submitted command.

- [ ] **Step 6: Write ADR 0002 and rerun only the selected path**

  ADR 0002 chooses one transport and specifies renderer isolation through the
  Electron main process. The selected path must pass every fixture on Windows;
  Linux/macOS CI requirements become Plan 01 gates.

- [ ] **Step 7: Commit the transport decision**

  Commit: `docs(adr): select versioned client core transport`

### Task 4: Persistence, crash recovery and backup spike

**Files:**
- Create: `experiments/persistence/`
- Create: `experiments/persistence/tests/test_atomic_write.py`
- Create: `experiments/persistence/tests/test_crash_recovery.py`
- Create: `experiments/persistence/tests/test_backup_restore.py`
- Create: `docs/adr/0003-foundation-persistence.md`
- Create: `docs/evidence/foundation/persistence-spike.md`

**Interfaces:**
- Consumes: ADR 0001 runtime.
- Produces: storage transaction semantics for canonical records, chats, mission
  metadata and event cursors; it does not define their later domain schemas.

- [ ] **Step 1: Write failing durability fixtures**

  Define `append_record(record_id, version, payload)`,
  `read_record(record_id, version)`, `checkpoint()` and
  `restore(backup_path)`. Tests cover concurrent readers, one writer, duplicate
  version rejection, process death before/after commit and restore validation.

- [ ] **Step 2: Run fixtures before an adapter exists**

  Expected: FAIL with missing storage adapter.

- [ ] **Step 3: Implement the SQLite WAL candidate in the experiment**

  Keep blobs and future vector indexes outside authoritative transaction rows;
  store hashes and references. Enable integrity checks and explicit migrations.

- [ ] **Step 4: Execute crash and recovery loops**

  Run at least 100 forced-termination iterations and a backup/restore into a new
  temporary directory. Expected: zero acknowledged-record loss, zero partial
  record visibility and successful integrity checks.

- [ ] **Step 5: Write ADR 0003**

  Accept SQLite WAL only if fixtures pass within the host budget. Otherwise
  record the failure and compare one local single-Core alternative using the
  same fixtures. State backup, migration, encryption-boundary and corruption
  recovery policy.

- [ ] **Step 6: Commit the persistence decision**

  Commit: `docs(adr): select recoverable foundation storage`

### Task 5: Foundation threat model and authority invariants

**Files:**
- Create: `docs/security/foundation-threat-model.md`
- Create: `docs/security/authority-invariants.md`
- Create: `tools/foundation/test-security-docs.ps1`
- Create: `docs/evidence/foundation/security-review.md`

**Interfaces:**
- Consumes: approved architecture plus ADRs 0001–0003.
- Produces: trust boundaries and non-negotiable controls consumed by Plan 01 and
  all later mission, tool, browser, Skill, model and remote-access plans.

- [ ] **Step 1: Write the failing security-document check**

  Require assets, trust boundaries, entry points, threats, mitigations,
  verification owners and residual risks. Require invariants for owner approval,
  Core enforcement stops, client authentication, loopback binding, secret
  handles, log redaction and denial-by-default.

- [ ] **Step 2: Run the check before the documents exist**

  Run: `pwsh -NoProfile -File tools/foundation/test-security-docs.ps1`

  Expected: non-zero exit listing missing sections.

- [ ] **Step 3: Model the foundation attack paths**

  Cover compromised renderer, forged local client, malicious model output,
  poisoned Skill, hostile web content, subprocess escape, replayed approval,
  event tampering and secret leakage. Mark browser, credential, self-evolution
  and remote pairing as later mandatory threat-model extensions.

- [ ] **Step 4: Validate and review residual risks**

  Run the document check. Expected: PASS. A human owner must explicitly accept
  any residual risk that would permit authority expansion or data egress.

- [ ] **Step 5: Commit the security baseline**

  Commit: `docs(security): define foundation trust boundaries`

### Task 6: Gate 00 synthesis and Plan 01 handoff

**Files:**
- Create: `docs/evidence/foundation/gate-00-report.md`
- Create: `tools/foundation/test-gate-00.ps1`
- Create: `docs/specs/subprojects/01-repository-and-skeleton.md`
- Create: `docs/superpowers/plans/YYYY-MM-DD-repository-and-cross-platform-skeleton.md`

**Interfaces:**
- Consumes: Tasks 1–5, their exact commits, ADRs and evidence.
- Produces: Gate 00 `PASS`, `FAIL` or `BLOCKED`, plus the focused specification
  and implementation plan for the first product vertical slice.

- [ ] **Step 1: Write the failing aggregate gate**

  The check requires complete host evidence; accepted ADRs 0001–0003; passing
  selected runtime, transport and persistence fixtures; security-document PASS;
  exact commit IDs; limitations; and no product source roots.

- [ ] **Step 2: Run Gate 00 before the report exists**

  Run: `pwsh -NoProfile -File tools/foundation/test-gate-00.ps1`

  Expected: non-zero exit identifying missing report or evidence.

- [ ] **Step 3: Write the Gate 00 report**

  Report measured budgets, decisions, rejected alternatives, unresolved limits,
  reproduction commands and whether the next slice is authorized to scaffold.
  `PASS` is forbidden if a selected experiment is failing.

- [ ] **Step 4: Run every foundation check from a clean clone**

  Execute host redaction, selected runtime, selected transport, persistence,
  security and aggregate checks. Expected: all PASS on the named commit and no
  untracked generated secrets or personal state.

- [ ] **Step 5: Write and review the focused Plan 01 documents**

  The new specification and plan must use the exact versions, transport names,
  persistence semantics and security invariants selected here. Do not implement
  Plan 01 during this task.

- [ ] **Step 6: Commit Gate 00**

  Commit: `docs(foundation): pass Synapse clean-room decision gate`

