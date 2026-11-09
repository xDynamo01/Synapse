# Rust/Python foundation revalidation — Gate 00 reopened

Date: 2026-11-09. Status: **REQUIRED / NOT RUN**. Gate 00: **BLOCKED**.

The owner approved Rust native application/device integration and Python AI.
This plan replaces the execution authority of the Electron foundation/Plan 01
tasks; it does not select a UI crate, version, transport or binding by guess.
All executable probes stay in new `experiments/rust-python-*` directories and
`tools/foundation/`. No product source roots or scaffold until Gate 00 passes.
Preserve the original experiments and receipts as historical comparison only.

## Decision Charter Compliance

**Charter:** [Decision Charter](../../specs/2026-11-06-synapse-0.3-decision-charter.md).

**Binding decisions:** CR-001–CR-004, PX-002–PX-005, VO-001, VO-006,
MI-003, MI-004, SE-001–SE-006, PL-001–PL-006, QA-001–QA-003.

| Decisions | Obligation | Evidence owner |
|---|---|---|
| CR-001–CR-004, PL-006 | New Rust/Python experiments; no product JS/TS or archived imports | R1, R5 |
| PX-002–PX-005, VO-001/006, PL-004/005 | Portable native presentation, audio and lifecycle feasibility | R1 |
| PL-001–PL-003, MI-003/004 | Headless authority and versioned boundary; no UI ownership | R2, R3 |
| SE-001–SE-006 | Browser/device/credential trust boundaries before implementation | R1, R4 |
| QA-001–QA-003 | Exact artifact, negatives, budgets and truthful platform limits | Every gate; R5 |

**Reviewed but not applicable:** Voice identity/translation, canonical memory,
Skills evolution and MoM/Swarm execution remain required product behavior but
are not implemented by these synthetic foundation experiments.

**Proposed deviations:** None. Infeasible constraints produce BLOCKED.

## R1 — Rust toolchain and native presentation feasibility

- [ ] Read primary upstream support/licence/security sources. Compare at least
  two feasible native Rust UI approaches on the same small experiment; select
  exact compiler, crate and dependency pins/locks only from measured evidence.
- [ ] Demonstrate transparent Assistant surface, real audio-driven Presence
  animation, interruption, terminal/grid/rail layout, keyboard focus, text/input
  methods, scaling and accessibility with the actual native accessibility tree.
  Record startup/RSS, frame pacing, CPU/GPU and audio latency against explicit
  host-based budgets established before comparison; missing budget is BLOCKED.
- [ ] Probe microphone/output capture and native device/tray lifecycle, window
  close, locked-session policy and permission failure. Pre-wake audio remains
  ephemeral and raw audio is not stored. No model weights or personal accounts.
- [ ] Prove isolated internal browser feasibility without a web application UI
  or Synapse-authored JS bridge. Remote site JS stays untrusted within browser
  content; navigation/download/credential operations require broker boundaries.
  No candidate satisfying the constraint means BLOCKED, not a framework swap.
- [ ] Build/run available Windows/Linux/macOS lanes, document native system
  dependencies and packaging constraints; unavailable lanes are NOT RUN/BLOCKED.
  CI never establishes physical audio/device/platform operation under PL-004.
  Output a superseding runtime/native-UI ADR and exact reproducible evidence.

## R2 — Rust/Python boundary, lifecycle and packaging

- [ ] Compare an isolated Python worker/process contract with a feasible
  embedding alternative using the same synthetic job/status/event fixtures.
  Reassess Python runtime pins from ADR 0001 evidence; do not auto-promote them.
  gRPC/Protobuf remains a candidate, not a selected Rust transport.
- [ ] Test strict generated/schema validation and evolution; malformed/foreign
  major rejection, authentication/ownership, bounded messages/backpressure,
  command idempotency, cancellation, interruption and ordered reconnect/replay.
- [ ] Crash Rust and Python separately during queued/in-flight work; prove
  stop/revocation survives restart, descendants are reaped and no second Core
  or duplicate effect appears. Record startup/RSS and failure/recovery budgets.
- [ ] Package the real Rust executable with the chosen Python deployment model;
  test discovery, interpreter/native-library loading, offline start, shutdown,
  upgrade and rollback from a clean machine/clone. No system Node/pnpm runtime
  or JS/TS generated application dependency is allowed. Record per-platform
  runtime/library provenance and distribution licences in a superseding ADR.

## R3 — Authority and persistence ownership

- [ ] Name exactly one headless authoritative Core owner, the Rust/Python
  responsibility split, mission/effect enforcement points and sole storage
  writer; distinguish app/device ownership from AI inference capability.
- [ ] Reuse ADR 0003's semantics and Python results as evidence only. Validate
  actual chosen Rust or Python binding, linked SQLite version, transaction/ACK
  ownership, cancellation and cross-boundary crash ordering with the new stack.
- [ ] Rerun duplicate-version/concurrent-read negatives, at least 100 forced
  process deaths, zero acknowledged loss/partial visibility, integrity, migration
  refusal, backup/restore/reference readback and rollback within measured budgets.
  Update/supersede the storage ADR; no two independent authoritative stores.

## R4 — Updated threat model before product code

- [ ] Replace historical Electron/main/preload assumptions with the selected
  native Rust UI, Python worker/embedding, FFI/IPC, native libraries, device/audio,
  browser engine, credential, subprocess, packaging/update and storage owners.
- [ ] Preserve AI-01–AI-10 and PC-01–PC-04 intent; map every invariant to actual
  Rust/Python consumers and negative/allowed-path evidence. Update source anchors
  and document checks so stale renderer vocabulary cannot satisfy this review.
  Keep E-01–E-05 prerequisites and R-01–R-04 NOT ACCEPTED; synthetic checks do not
  authorize personal data, accounts, external effects or new residual risks.

## R5 — Fresh evidence, fail-closed gate and replacement Plan 01

- [ ] Produce exact-commit clean-clone receipts for R1–R4 with commands, lock
  and artifact hashes, actual output, budgets, OS/architecture and limitations.
  Historical Node/Python tests never count as new Rust/Python acceptance.
- [ ] Replace the aggregate's historical receipt contract in a reviewed change:
  bind receipts to the amended Charter and exact new ADR/stack identity; require
  actual Rust/Python suite evidence. Test missing/stale/legacy/forged receipts,
  missing platform lanes, changed hashes and forbidden product JS dependencies.
- [ ] Independent QA reviews the exact artifact and all required gates. Missing
  evidence keeps Gate 00 BLOCKED. Only a reviewed PASS report plus the new gate
  can authorize a newly written native Rust/Python Plan 01 specification/plan.
  Preserve superseded Electron Plan 01 files as history. Product scaffolding
  remains prohibited until that sequence is complete.

Rollback: revert experimental/policy changes together, preserving history and
receipts. Reverting evidence does not revoke the owner-approved language choice;
restoring Electron authority requires a new owner-approved Charter amendment.
