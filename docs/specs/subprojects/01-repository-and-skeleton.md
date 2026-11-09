# Plan 01 — Repository and cross-platform skeleton

Date: 2026-11-06. Execution handoff prepared: 2026-11-09.
Status: **SUPERSEDED / NOT EXECUTABLE — 2026-11-09 owner-approved PL-001/PL-006 amendment**.

This entire Electron/Node/TypeScript specification is preserved as history and
confers no implementation authority. Gate 00 is **BLOCKED / REOPENED**. Do not
execute its tasks, select Electron pins, or create product scaffolding. Native
Rust application/device integration with Python AI replaces its stack. A new
Plan 01 specification/plan may be written only after the
[Rust/Python foundation revalidation plan](../../superpowers/plans/2026-11-09-rust-python-foundation-revalidation.md)
passes with reviewed exact-commit evidence. All remaining text is historical.

## Purpose and scope

Produce a clean-room repository that installs, generates shared contracts,
builds and tests an inert headless Core bootstrap, CLI bootstrap and packaged
Electron/React bootstrap on the three selected platforms. The observable result
is a synthetic foundation status round trip, with a real packaged IPC boundary
test. It is not Assistant/Workspace UI, mission execution or an operational Core.
The architecture is `docs/specs/2026-11-06-synapse-0.3-clean-room-design.md`;
Gate 00 evidence is `docs/evidence/foundation/gate-00-report.md`.

## Selected foundation

- CPython 3.14.10, standard GIL; uv 0.13.7; Node.js 24.22.2; JavaScript pnpm
  11.25.0 under that Node; TypeScript 7.0.2. PowerShell 7.6+ runs foundation gates.
- gRPC over HTTP/2 with Protocol Buffers; package `synapse.foundation.v1`,
  contract version `1.0`. Preserve ADR 0002's `GetStatus`, `SubmitCommand`,
  `CancelCommand`, `SubscribeEvents` wire contract and evolution rules.
- SQLite WAL, `synchronous=FULL` per connection, linked SQLite >=3.51.3
  (Windows measured 3.53.1). Atomic immutable `(record_id, version)` append,
  snapshot reads, serialized writes and acknowledged-commit recovery follow
  ADR 0003. No product domain schema or database is created in this slice.
- Python gRPC 1.85.1 and Node @grpc/grpc-js 1.14.7 / @grpc/proto-loader 0.8.1
  are measured candidates; promote only the needed dependencies through the
  licence/provenance gate. Runtime/STT/TTS imports are not product approvals.
- Windows 11 x64, Ubuntu 24.04 x64/glibc and macOS 14+ arm64 are required lanes.
  Windows Server 2025 x64 is a separately labelled CI surrogate. macOS x64 is
  outside the selected native-package floor.

Electron and React were deliberately not selected by Gate 00. Task 1 selects
and locks exact supported versions from primary release/provenance sources,
records Electron's embedded Node separately, and proves compatibility with the
chosen gRPC adapter. This is an explicit acceptance gate, not permission to
silently substitute latest packages or change an accepted ADR.

## Deliverables and boundaries

Create `core/` as an installable Python modular-monolith package, `apps/cli/`
as a client bootstrap and `apps/desktop/` as Electron main/preload/React renderer.
Create `packages/contracts/` for versioned schema and generated clients, and
`tools/repository/` for deterministic policies/build orchestration. Dependencies
flow from clients through contracts; Core never imports Electron or client code.
Platform APIs have declared adapter boundaries; no working secure-store/audio/
service implementation is added here. Nothing imports archived runtime/state,
or experiment implementation code into product packages.

`python -m synapse_core --check` prints one allowlisted synthetic JSON status and
exits without opening sockets, reading accounts/projects or creating persistent
state. CLI `synapse --check` exposes that bootstrap result without conferring
authority. Product service lifecycle, identity/discovery, durable event journal
and reconnect/replay implementation belong to Plan 02.

The packaged smoke harness starts the selected transport's synthetic test server
outside product packages. Electron main owns its endpoint and public test-only
bearer; renderer sees only a named `foundation.getStatus()` API returning
`{ healthy: boolean, contractVersion: string }`. Main validates sender/frame,
method, payload and subscription ownership; context isolation and sandbox are
on, Node integration off, restrictive CSP/navigation/network policy on. Test
the real packaged app with its actual embedded Node and loopback socket.
Fixture credentials and server must never be present in a distributable product
artifact. The package tested here is explicitly a non-release smoke artifact.

## Security prerequisites and refusal behavior

Apply `docs/security/foundation-threat-model.md` and
`docs/security/authority-invariants.md` AI-01–AI-10. Plan 01 owns AI-04/05/09
design and synthetic denial/composition evidence, plus initial dependency and
state ownership boundaries. It does not claim product authentication is solved.
Before implementation, Task 1 documents local client identity, trusted bootstrap
launch ownership, packaged IPC and fixture-only credential handling. Product
credential issuance/storage/rotation, personal-data persistence, executable tool
boundaries and remote access remain blocked by E-02/E-05/E-04 respectively.
Unresolved questions may block a task; no placeholder secret store, plaintext
product bearer, prompt-only enforcement or new residual-risk acceptance is allowed.

Refuse missing/malformed/foreign-major bootstrap messages, unknown CLI actions,
wrong IPC sender/frame/method/payload, renderer access to endpoint/token/raw IPC,
non-numeric-loopback fixture configuration and attempts to enable remote mode.
Diagnostics use an allowlist. Private project-context preservation for authorized
local consumers (PC-01) remains a downstream model/memory requirement; this
slice must not mistake diagnostic redaction for erasure of canonical context.

## Acceptance and evidence

Frozen installs and reproducible generation must leave tracked sources/locks
unchanged. Run the selected foundation fixtures, policy negatives, bootstrap
tests and packaged smoke/attack tests on each lane. Missing runners or packages
produce BLOCKED/NOT RUN, never a passing empty matrix. Receipts identify exact
commit, tool/embedded-runtime versions, package hashes, OS/architecture, commands,
exit codes, negative cases and limitations. Windows physical development checks
are separate from Server CI. No platform reaches VALIDATED/OPERATIONAL here.
Independent QA reviews the exact proposed artifact; post-integration regression
is mandatory after authorized integration. Revert code/locks together and rebuild
the preceding artifact; disposable smoke state is removed. No shared merge,
push or publication is authorized by this specification.

## Decision Charter Compliance

**Charter:** `docs/specs/2026-11-06-synapse-0.3-decision-charter.md`

**Binding decisions:** CR-001, CR-002, CR-003, CR-004, MI-003, MI-004,
MI-006, MI-007, SE-001, SE-002, SE-004, SE-005, SE-006, PL-001, PL-002,
PL-003, PL-004, QA-001, QA-002, QA-003.

| Decision | Implementation obligation | Test/evidence owner |
|---|---|---|
| CR-001, CR-002, CR-003 | New source only; archive remains reference; isolated mission targeting 0.3 | Tasks 2/6 repository policy and reviewer |
| CR-004 | No secrets/private state in Git or diagnostic/artifact sinks | Tasks 2/5 canary and content-policy checks |
| MI-003, MI-004 | No owner approval or mission effects from bootstrap/client metadata; bounded inert checks | Tasks 3/5 refusal tests |
| MI-006, MI-007 | Isolated exact artifact, independent QA, regression and reversible integration | Task 6 reviewer/integration owner |
| SE-001, SE-002, SE-004 | Offline bootstrap; distrust renderer/input; synthetic bearer only; real credentials gated by E-02 | Tasks 1/3/5 security design and attack tests |
| SE-005, SE-006 | CLI has no authority; app-owned bootstrap only; no arbitrary tool broker; sensitive extensions precede implementation | Tasks 1/3 security prerequisites and CLI refusal |
| PL-001, PL-002, PL-003 | Headless modular package, separate clients, stable gRPC contracts, remote disabled | Tasks 2–5 import/contract/socket checks |
| PL-004 | Three required architecture-specific CI lanes, physical limits explicit | Tasks 4/6 platform receipts |
| QA-001, QA-002, QA-003 | RED/GREEN, real composition, packaged negatives, exact commit and scoped statuses | Every task; Task 6 clean clone and independent QA |

**Reviewed but not applicable:** PX-001–PX-006 (no product identity/experience
implementation); VO-001–VO-006 (no audio); ME-001–ME-005 (no memory/history or
personal state); MI-001/MI-002/MI-005 (no mission contract/effects implementation);
SK-001–SK-004 (no Skills); MM-001/MM-002 (no cognition/resource UI);
SW-001–SW-004 (no product Swarm); SE-003 (no browsing); PL-005 (no tray or
background-listening behavior). Their future requirements remain binding.

**Proposed deviations:** None.
