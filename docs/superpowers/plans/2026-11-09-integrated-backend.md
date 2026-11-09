# Integrated Backend Implementation Plan

> Agentic workers: use subagent-driven-development; independent review after
> each task. Steps use checkboxes. Product implementation is explicitly approved
> by the owner; do not pause for another delivery-order approval.

**Goal:** Build the real Rust/Python backend as one coherent modular system,
then expose it to a future native frontend through the same versioned contracts.

**Architecture:** Rust Core is the sole authority/writer. SQLite persists domain
state, events and digest-bound receipts. Python workers provide local AI through
owned bounded pipes. A real JSON-lines CLI dispatches all registered commands.

**Tech Stack:** measured Rust 1.96.0/MSVC and Python 3.14.3 initially; locked Rust
dependencies; SQLite WAL/FULL; Python standard library where feasible. These
local baselines are implementation pins, not proof of all native dependencies.

**Spec:** `docs/specs/2026-11-09-integrated-backend-design.md`.

## Global Constraints

- Charter: `docs/specs/2026-11-06-synapse-0.3-decision-charter.md`, including the
  owner-approved integrated-backend-first amendment.
- Rust/Python only; no 0.2 runtime or experiment implementation copied into product.
- All modules share one composition root, database writer and API contracts.
- Model output never authorizes an effect; only explicit human CLI commands do.
- No network listener, external account operation or automatic weight download.
- Missing real providers/assets return typed unavailable, never fake success.
- Immutable mission scope, canonical contextual memory and separate MoM/Swarm.
- Test real binary/worker paths and restart; exact commit evidence/reviews.

## Review Focus

- Retried IDs with changed payloads must conflict, including after restart (T1).
- Context reference cannot retrieve unrelated project memory (T1/T2).
- Worker malformed output/crash/hang cannot grant authority or orphan children (T2).
- Revoke/stop must persist and prevent later effects after restart (T1/T3).
- Missing model/voice/browser cannot be reported as successful execution (T2/T4).

## Task 1 — Core contracts, durable domains and actual CLI

Files: root `Cargo.toml`, `.gitignore`; `backend/core/Cargo.toml`,
`backend/core/src/{lib,main,contracts,store,core,chats,memory,missions,registry}.rs`,
`backend/core/tests/core_cli.rs`, `backend/contracts/v1/README.md`.

Produces `Core::open(state_dir, workspace_root)` and
`Core::dispatch(Request)->Response`; binary `synapse-backend --state-dir PATH
--workspace PATH` consumes bounded JSON lines and emits exactly one response
per request. Both paths call the same dispatcher. Request envelope fixes
`version:1`, `request_id`, and tagged command; response fixes request ID,
success/error, event cursor and JSON result. Unknown fields/major rejected.

- [ ] RED actual-binary tests: init/health, strict bad input, chat creation/message
  readback, canonical memory revision/conflict/context lookup, immutable mission
  propose/approve/cancel/revoke and transition refusal.
- [ ] Implement focused domains with one SQLite writer, WAL/FULL transactions,
  migration version rejection, durable typed events and request-digest receipts.
  Persist receipt and resulting state atomically; altered retry conflicts.
- [ ] Include capability/model/Skill registries used by the same dispatcher.
  Missing external functions return explicit unavailable, no default echo model.
- [ ] GREEN: binary restart preserves messages, context records, terminal mission
  state, idempotent response and event replay. Capture malformed and foreign
  context denial. Commit and independent review.

Charter: CR-001/004, PX-001/002, ME-001–005, MI-001–004,
PL-001/003/006, QA-001–003. Voice/tools/orchestration execution belongs later tasks.

## Task 2 — Real supervised Python inference and conversation integration

Files: `backend/python/pyproject.toml`,
`backend/python/synapse_ai/{__init__,__main__,protocol,providers,worker}.py`,
`backend/python/tests/test_worker.py`; Rust
`backend/core/src/{worker,conversation}.rs` and focused platform child ownership
adapters; actual-binary tests and updated contract documentation.

Consumes T1 public dispatcher/store and publishes typed AI provider requests,
results and status. Production local provider accepts only configured numeric
loopback endpoints and explicitly selected/advertised models. No cloud fallback.

- [ ] RED worker handshake/version/schema/limits, missing provider, timeout,
  malformed output and actual child lifecycle tests. Keep any synthetic provider
  inside tests, never production default.
- [ ] Implement independent product worker supervision from documented OS APIs;
  apply experiment lessons without copying source. Python owns no database and
  receives no grants or secrets. Every request/response is bounded and matched.
- [ ] Register conversation command: persist user message, call real provider,
  persist assistant result only after success. Failures remain explicit events;
  retries do not generate duplicate acknowledged turns. Optional model-extracted
  canonical memory is validated and scoped before Rust writes it.
- [ ] GREEN through real CLI with test-local fixture endpoint, unavailable
  default and live local model if installed. Distinguish fixture integration
  from actual model operation. Commit/review.

Charter: PX-001, ME-001–005, MI-003, SE-001/002/005,
PL-001/004/006, QA-001–003. Secure remote pairing/voice/browser remain unproved.

## Task 3 — Approved mission tools and immutable Skills in the real Core

Files: `backend/core/src/{tools,skills,execution}.rs`, T1 contracts/dispatcher,
Rust integration tests and `backend/contracts/v1/README.md` updates.

Consumes T1 missions, events, store and T2 worker. Produces real tool receipts
and immutable Skill manifests consumed by mission execution and later routing.

- [ ] RED tests refuse unapproved/revoked/cancelled scope, path escape, symlinks,
  unauthorized overwrite/delete, mismatched Skill/tool permissions and altered
  contracts. Stop survives reopen.
- [ ] Implement bounded workspace list/read and approved artifact create/replace
  with exact target/digest and rollback policy. No arbitrary shell or browser
  side effect. File readback/hash and receipt required; claims are not receipts.
- [ ] Register immutable Skill versions, provenance/hash/declared tools and
  permissions. Run only approved Core tool implementations; instructions never
  grant authority. New version promotion cannot modify a running version.
- [ ] GREEN real binary creates an approved artifact, reads it back, repeats
  safely, cancels/reopens/refuses further effects and preserves evidence. Review.

Charter: MI-001–007, SK-001–004, SE-001–006, QA-001–003.
Full shell/git integration and audited browser Skill discovery need their own
actual containment/account gates and stay explicit unavailable until implemented.

## Task 4 — Integrated routing, temporary Swarm and capability boundaries

Files: `backend/core/src/{models,swarm,voice,capabilities}.rs`, composition root,
contracts and real CLI tests; Python adapters only when a real implementation
and installed compatible dependency are available.

- [ ] RED model routing respects capabilities/memory budget, explicit pin and
  missing models; Swarm refuses activation without accepted consent; temporary
  agents cannot approve or write canonical memory directly.
- [ ] Implement model registry/resource-aware selection and ordinary inference
  routing. Implement consent-gated temporary role lifecycle and bounded sequential
  execution through T2, preserving scoped evidence and cleanup on failure/stop.
  Multiple resident models/parallelism remain limited by measured capacity.
- [ ] Expose explicit voice/translation/browser/device capability status and
  versioned requests; run available real adapters only. Absent assets and native
  adapters are typed unavailable and must never produce placeholder success.
- [ ] GREEN end-to-end mission/routing/Skill/temporary-agent lifecycle, including
  worker failure and cleanup. Document exact functionality vs missing adapter
  operation. Review.

Charter: VO-001–006, MM-001/002, SW-001–004, PL-004, QA-001–003.

## Task 5 — Whole-backend integration, recovery and handoff

Files: `backend/README.md`, `docs/evidence/backend/2026-11-09-integration.md`,
`backend/core/tests/backend_journey.rs`, supported CI configuration.

- [ ] Run real backend journey: create chat, infer, explicitly reference project
  memory, propose/approve/execute mission, invoke Skill, request Swarm, revoke,
  restart/replay and read artifact/evidence. Inject missing dependencies and
  worker failures; no substitute results count as model/device operation.
- [ ] Verify clean-clone lock builds/tests and process cleanup; identify exact
  commit, OS and limitations. No runtime state, secrets or personal paths in Git.
- [ ] Independent whole-branch review. Fix actual defects and retain remaining
  capability gaps plainly. Publish frontend-ready contracts and commands without
  claiming backend completeness for adapters that have not run.

All tasks have their own RED/GREEN tests, commit and independent review.
These internal tasks deliver one system and do not revive the superseded
experiment-first delivery order.
