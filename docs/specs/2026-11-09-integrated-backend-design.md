# Synapse integrated backend — approved execution design

Date: 2026-11-09. Status: APPROVED by the owner's backend-first instruction.

## Intent and authority

Implement one real backend before native frontend development. This document
specializes the approved clean-room architecture and delivery amendment in
`2026-11-06-synapse-0.3-decision-charter.md`; it does not replace product features.

Rust owns the headless modular Core, domain state machines, versioned requests,
permissions, effects, events and sole SQLite writer. Supervised Python workers
provide local inference and audio/model adapters. They exchange bounded typed
messages and cannot open the Core database or authorize effects. The CLI is the
initial real client; the future native GUI uses the same Core commands.

## Approaches and selected direction

- Backend-first modular monolith, then native frontend: selected by the owner.
  All domains share one composition root and contracts from their first callers.
- Complete UI feasibility and isolated subsystems before product code: superseded
  as delivery order. Existing experimental results remain useful evidence.
- Independent domain services: rejected by PL-003 and by the need to prevent
  overlapping authorities and duplicated state.

## Product layout

`backend/core/` is one Rust library/binary with focused domain modules, storage,
worker supervision and a single dispatch root. `backend/python/` is the local AI
worker package. `backend/contracts/` contains the versioned wire schema/examples.
No frontend, Node, TypeScript, cloud inference or old runtime source is included.

## Boundary and trust model

Initial CLI transport is bounded JSON-lines over owned stdin/stdout, with an
explicit protocol major. There is no network listener or remote auth claim.
The local OS user invoking the CLI is the human owner; model/worker output is
data only and cannot fabricate an approval or invoke Core dispatch. A future
remote/API client needs a separate authenticated transport adapter, preserving
these domain commands. SQLite commits precede acknowledgement; request IDs bind
to payload digests, and retries cannot authorize altered requests.

Mission contracts declare scope, actions and resources before approval. Rust
checks every effect against the current immutable approved contract and checks
cancellation/revocation again immediately before effects. Terminal outcomes and
idempotency receipts survive restart. State transitions append replayable
events. Raw credentials/audio never enter evidence or canonical memory.

Project memory is typed/versioned contextual knowledge, separate from chats.
Explicit context references gate reads. Skills are immutable manifests with
audited provenance and declared tools; they do not grant authority. Swarm
requires accepted consent and creates temporary scoped roles; MoM routing is
separate and honors local hardware/model limits. Provider output cannot merge
work, publish, access arbitrary files or promote knowledge by itself.

## Completion and truthful capabilities

Backend tasks must provide real registered callers and persistent operations,
not disconnected interfaces or success stubs. Capability inventory distinguishes
implemented/integrated/tested/operational. Missing local models, voice assets,
browser engines, secure storage or hardware return typed unavailable responses.
Synthetic test providers are explicitly test-only and never selected by normal
production startup. No download of weights or external account access is implied.

## Verification

Test the actual binary: strict malformed/version rejection, restart/readback,
digest conflict, mission approval and revocation, cross-context memory denial,
worker failure/timeout, and no orphaned owned processes. Use temporary roots.
Every task is independently reviewed. Windows is the live target; Linux/macOS
execution is reported truthfully. Frontend/device validation is a later gate,
not a prerequisite to writing backend code.

## Decision Charter Compliance

Binding IDs: CR-001–004, PX-001/002/006, VO-001–006, ME-001–005,
MI-001–007, SK-001–004, MM-001/002, SW-001–004, SE-001–006, PL-001–006,
QA-001–003. Each implementation task maps its subset to concrete tests.
PX-003–005 visual execution is deferred to the native frontend; policy/events
are backend responsibilities. No proposed product-behavior deviations.
