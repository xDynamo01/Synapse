# Local self-change, isolation and deterministic evals

Date: 2026-11-22. Scope: current Windows Core, local logged-in OS owner.

Binding charter: `docs/specs/2026-11-06-synapse-0.3-decision-charter.md`.
Decisions: MI-002/003/005/006/007, ME-003/005, SE-002/004/005/006,
PL-001/003/004/006 and QA-001/002/003. No charter deviation.
Voice/device decisions are not applicable to this gate. This document does not
close all readiness checklist items or certify a released package.

## Authority and threat boundary

Core is the only SQLite writer. A proposal's authenticated principal comes from
the Core process Windows token SID, not JSON, an environment username, a chat
profile, an agent name, a Skill or a model response. Local pipe ACLs constrain
access to the owning OS principal and reject remote clients. CLI stdin belongs
to its launching local OS process. No multi-user server authentication or
network identity is implemented by this feature.

Agent labels are explicitly untrusted attribution. They cannot grant review or
approval. Independent code review is performed by the local human in a native
confirmation displaying exact before/after content, target, base version and
digests, with findings supplied in the request. The full content is paginated
into bounded native confirmations to avoid truncating a long diff; refusing any
page cancels the operation. A second native confirmation
approves the exact change and review digest. A test result is never a substitute
for code review. The reviewer/approver may be the same local owner; they are
independent of the untrusted proposing agent. The executor is the Core process
under the recorded owner SID.

This is a single-user product boundary. Programs or administrators already
running with the owner's OS authority can change files or automate ordinary
desktop controls; this gate is not a defense against a compromised owner OS
session. A production approval test must involve the actual human; the automated
positive test seam is private to `cfg(test)` and absent from production dispatch.

Threats handled: generic mission authority escalation into Synapse sources or
distribution; forged roles/approval booleans; changed base bytes; replaced
directory/file identities; cross-conversation/project/mission/Swarm lookup;
partial publication and diagnostics leaking proposal contents. A versioned
self-change digest binds all proposal fields, including the complete scope tuple
and new content. The original bytes and stable root/file identities are captured
at proposal time and verified again before preparation/publication.

## Dedicated flow

The `self_change` Core command carries `action` and `payload`. `propose` payload:

```json
{"id":"change-1","context":{"conversation":"chat-a","project":"project-a","mission":"mission-a","swarm":null},"proposer_agent":"agent-a","root":"C:\\absolute\\fixture","path":"module.rs","base_version":"0.1.0","base_digest":"SHA256_OF_CURRENT_BYTES","content":"replacement text"}
```

Every later action carries exactly `id`, the same `context`, and
`change_digest` returned by `propose`; `review` also carries nonempty `review`
findings. No action accepts a caller-supplied principal, authority role or
approval boolean. `get` returns metadata and role principals without source
contents. The context tuple must match on every action.

Sequence: `propose` → `review` → `approve` → `prepare` → `publish`.
Each arrow is a separate committed Core request. `prepare` durably records
verified before/after bytes and file identities before publication is permitted.
The current implementation replaces one existing UTF-8 file (each version at
most 32 KiB), through the existing guarded Windows broker. It refuses aliases,
hard links, reparse points, protected state, changed ownership identities and
unexpected content. It is not an atomic multi-file updater or binary installer;
replacing an executing executable may be refused by Windows. Source paths and
the executing binary's distribution directory are denied to generic workspace
registration and mission effects, including ancestor roots. Tests use disposable
fixtures only.

`revoke` removes authority before publication. `rollback` restores verified
previous bytes after a complete publication while preserving the file identity.
`recover` repairs a persisted prepared/published journal after an interrupted
result transaction. If current bytes match neither before nor after, recovery
requires a fresh native human confirmation showing current and restoration
digests. This prevents the prepared journal being treated as automatic authority
to overwrite an unrelated operator edit. A changed file identity is refused even
with recovery consent. Never remove the state database to clear an uncertainty.

## Interrupted publication runbook

1. Stop the affected self-change flow; retain the state directory and journal.
2. Query `get` with the exact change digest and context. Compare the recorded
   base/change digests and the actual file. A `prepared` state may mean the file
   effect completed but the result transaction did not commit.
3. Use dedicated `recover`. Exact before/after bytes are recognized; an unknown
   partial file prompts for a human decision. Inspect it before accepting.
4. If identity changed, preserve both files and investigate. Do not redirect a
   recorded journal at a replacement inode or directory. Propose a new change
   against the new base when appropriate.
5. Verify restored bytes and `rolled_back` state. Retain metadata and the
   protected journal as recovery evidence. This test is process/transaction
   interruption evidence, not physical power-loss or reboot certification.

## Secret retention and diagnostics

Events and `get` export IDs, states and digests; proposal content, review text,
paths, prompts, credentials and broker diagnostics are not copied into these
events. Review findings are retained in the protected database to recompute the
review digest. SQLite deliberately retains original/proposed bytes for rollback and
therefore must receive the same owner-only state-directory/backups protection
as the rest of Core state. This module does not add encryption or an independent
ACL/backup retention subsystem. Do not submit real credentials as source fixtures.
The synthetic canary tests prove their specified consumers; they do not certify
all prompt, temporary-file, backup or log consumers across the product.

## Reproducible deterministic evals

`tools/readiness/evals-v1.json` fixes 16 labeled positive, negative and ambiguous
cases across routing, memory, tools, validation and continuation/replanning
boundaries. The runner executes the real CLI with separate disposable state per
case and no model, provider or network access:

```powershell
cargo test -p synapse-core --lib self_change::tests -- --test-threads=1
cargo build -p synapse-core --bin synapse-backend
py -3.14 tools/readiness/run_evals.py --binary target/debug/synapse-backend.exe --output docs/evidence/backend/readiness-evals-v1.json
```

The report identifies dataset and binary hashes, configuration, actual observed
decisions, per-class FP/FN and denominators. A false positive is a decision
observed true when its fixed binary label is false; a false negative is observed
false for a true label. Undefined rates use null. All five classes require zero
FP/FN; rejected secret-bearing boundary responses require zero canary leaks.
The fixed baseline expects all 16 cases to pass. Positive memory retrieval is
allowed to return its deliberately selected canary; only disallowed consumers
are counted as leaks. Raw response contents are never exported to the report.

These are deterministic policy/continuation evals, not real-model semantic
quality, diverse real project acceptance, full replanning execution, Windows
package acceptance, multi-user server certification, or measured reboot/power
failure evidence. Those remain separate gates. Dataset changes require a new
version/baseline and must not silently make the current baseline easier.
