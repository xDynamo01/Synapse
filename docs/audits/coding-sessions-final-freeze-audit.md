# Coding Sessions — final freeze audit

Date: 2026-08-10

Decision: **IMPLEMENTED / OPERATIONALLY COMPLETE / FROZEN**

Global backend: **NOT READY**

This audit reconciles Coding Sessions Slices 1–20 and freezes the local bounded
context, its SQLite V1 persistence, reference-only integrations and opt-in local
Composition Root. It does not activate global bootstrap or add an external
authority, execution driver, API, CLI or deployment runtime.

## Production inventory and public surface

All **22 production modules** have a concrete producer/consumer role. The union
aliases represent deliberate closed request/fact alternatives consumed by typed
services; they are not deprecated compatibility aliases. No provisional model,
duplicate export, mutable registry or generic execution facade remains.

| Package | Modules | Public exports | Responsibility |
| --- | ---: | ---: | --- |
| `coding_sessions` | 15 | 198 | identities, contracts, lifecycle, coordination, factual control/recovery and persistence |
| `coding_sessions_integrations` | 6 | 88 | deterministic reference translation and receipt projection |
| `coding_sessions_composition` | 1 | 14 | typed opt-in wiring, health and resource lifecycle |

The frozen SHA-256 fingerprints of sorted newline-delimited exports are:

| Facade | Fingerprint |
| --- | --- |
| domain | `ec9c1c05f5083aec93f485cd154cf67f5b3be03e1124241b5fd2c44a4588c1d0` |
| integrations | `d46c54eba637c2bd8c48b4f8f645010032195c40fba41e6c09a916efed33bbf8` |
| composition | `a85bcc1a3a47183a15d89ec478527695fc6680ac0584ebba6937e73593bf7c23` |

The public groups are justified consumers: immutable identities/references feed
every artifact; contracts and assessments feed session orchestration; lifecycle,
lease, intent, journal, control, restart and recovery facts feed persistence and
callers; consumer-owned ports and SQLite stores feed the Composition Root;
integration DTOs bind external receipts without importing foreign objects into
the domain; runtime config, health, builder and handle provide explicit opt-in
wiring.

## Frozen V1 contracts

- Canonical format: `coding-sessions-json-v1`.
- Record format: `coding-session-record-v1`.
- SQLite schema: V1.
- Migration V1 checksum:
  `sha256:23e6daf70fb93da199ea758fd5bd726f603f75b1a8d12388effb19295ef43f40`.
- Lifecycle states: unknown, planned, prepared, active, suspended and terminal.
- Eleven independent state dimensions remain explicit.
- Seven persistence streams remain separated by responsibility.
- Capability states remain supported, degraded and unavailable; Deployment
  references are degraded/reference-only and concrete Sandbox execution plus a
  real Deployment Runtime are unavailable.

## Authority boundary

Coding Sessions owns session identity, contract/bindings, lifecycle,
coordination/leases, outbound intents, receipt bindings, journal/checkpoints,
pause/resume/cancellation semantics, restart/reconciliation, session recovery
coordination, completion prerequisites and deployment-candidate handoff
references.

It does not own Git/filesystem facts or mutation, approval/authorization, worker
selection or scheduling, Mission ownership, Sandbox admission/isolation/process
execution, Private Eval scoring/baselines, or deployment/release/promotion.

The frozen distinctions are: lease is not authorization; intent is not execution;
receipt is not lifecycle transition; authorization is not application;
Repository application is not verification; worker completion is not session
completion; process exit is not verified execution; termination proof is not the
session cancellation decision; accepted evaluation is not session completion;
recovery completion does not resume automatically; deployment handoff is not
deployment.

## Persistence, restart and recovery

SQLite records are append-only and versioned. Idempotent repeats do not duplicate
records; divergent identity/idempotency payloads, causal revision conflicts,
lineage gaps, unsupported versions, checksum mismatch and corruption fail
explicitly. Reads identify an exact identity/fingerprint or explicit causal
range—never latest/current. Checkpoint structural completeness, durable-ready,
persisted evidence and resumability remain distinct.

Replay and restart preserve unknown, pending, partial, late, rollback-failed and
manual-intervention facts without inventing progress. Duplicate restart/resume
does not create a transition. Recovery plans and results coordinate session
state only: they execute no repository, worker, Sandbox, evaluation or deployment
side effect, and recovered does not imply active or resumed.

## Composition and E2E reconciliation

The builder validates typed configuration, verifies the migration, opens managed
resources deterministically and closes them in reverse order after partial
failure. `close()` is idempotent and use-after-close fails. Health reports real
availability without upgrading degraded or unavailable capabilities.

E2E tests use real temporary SQLite databases and cover all seven streams,
idempotency, exact reads, causal replay, crash/restart, incompatible write leases,
shared reads, distinct worktrees, stale resume prerequisites, duplicate resume,
late external facts and all reference adapters. Existing focused suites preserve
cancellation races, orphan/late workers, corruption, migration mismatch,
unavailable authorities, partial recovery and manual intervention.

## Architecture and freeze gate

The only Coding Sessions edges are composition to domain/integrations and the
documented integration adapter dependencies. The pure domain has no context edge,
none of the three packages belongs to an SCC, reverse dependencies are absent and
global bootstrap imports none of them.

`tests/architecture/test_coding_sessions_freeze.py` freezes the exact 22-module
inventory, 300 public exports and their fingerprints, V1 constants, state/stream/
capability taxonomies, permitted graph edges, SCC isolation and prohibited
authority surface.

## Final quality baseline

| Gate | Frozen result |
| --- | --- |
| freeze + boundary | 14 passed |
| Coding Sessions including E2E/restart/failure paths | 210 passed |
| architecture | 197 passed |
| global regression (4 deterministic partitions) | 3166 passed, 4 skipped, 4 subtests passed |
| Ruff | clean |
| Mypy local | 25 source files, zero errors |
| Mypy global | 680 source files, zero errors |
| runtime import graph | 79 contexts, 282 edges, one pre-existing SCC; no Coding Sessions package in it |
| source import graph | 83 contexts, 317 edges, two pre-existing SCCs; no Coding Sessions package in them |
| diff/bootstrap integrity | clean; zero global bootstrap references |

These are local bounded-context freeze results. The existing SCC and skipped
tests are not Coding Sessions exemptions. The repository governance still marks
the backend globally **NOT READY**. A future frozen-contract change must rerun the
gate and issue a new explicit architectural decision.
