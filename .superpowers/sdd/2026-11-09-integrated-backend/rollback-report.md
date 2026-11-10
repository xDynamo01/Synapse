# Task 3b — replacement and recovery evidence

Status: implementation and local tests complete; independent scoped review is
still required before acceptance. Binding charter: `docs/specs/2026-11-06-synapse-0.3-decision-charter.md`,
CR-001/004, MI-001–007, SK-001–004, SE-005/006, PL-001/004/006, QA-001–003.
No production files were used for tests. Base: `f36ca5a` (which includes Task 3a `830fa9d`).

## Interfaces and implementation

Protocol examples and exact names are in `backend/contracts/v1/README.md`.
The compatible optional `artifact_previous_digests` map binds an exact resource
to the previous lowercase SHA-256. Replace additionally requires new SHA,
`artifact_replace`, and the exact policy `verified backup`. SQLite schema 4
retains backup bytes, old hash, target identity, request digest and operation in
Core state before writing. A no-follow handle denies sharing while the same
handle is used for snapshot, mutation, flush and readback. Persisted backup is
read back and verified before mutation. Only the existing Core owns the writer.

`tool_recovery` has `intent_id`, `mode` (`inspect`, `finalize`, `restore`,
`safe_abandon`) and optional `expected_current_hash` for restore. Inspect is
journal-only; other modes recheck the original approved mission and Skill.
Finalize verifies replacement identity, backup and new digest. Restore commits
its own request-bound intent and verifies target and backup before writing.
An interrupted restore can be reconciled only with verified old content; a
verified no-effect restore can be abandoned by its recovery request ID. An
absent prepared create can be safely abandoned. Reused IDs with changed
payloads conflict. Ambiguous or partial data stays `recovery_required`.

## Red/green and validation (Windows, local fixed NTFS, temporary roots)

1. `cargo test -p synapse-core --test core_cli mission_previous_digests_are_optional_and_validate_resources_and_sha256 -- --exact`: RED, 0 passed / 1 failed, unknown field; after contract change GREEN, 1 passed.
2. `cargo test -p synapse-core --test core_cli approved_replace_is_verified_and_replays_after_restart -- --exact`: RED, 0 passed / 1 failed, `capability_unavailable`; after implementation GREEN, 1 passed. The test subsequently gained restore, changed-target and replay assertions.
3. `cargo fmt --all -- --check`: exit 0.
4. `cargo test -p synapse-core`: exit 0; AI CLI 7 passed, Core CLI 21 passed, no failures; unit/doc targets contain 0 tests.
5. Separately, `cargo test -p synapse-core --features test-fault-injection`: exit 0; AI CLI 7 passed, Core CLI 24 passed, no failures; unit/doc targets contain 0 tests.
6. `git diff --check`: exit 0, only Git line-ending warnings.
7. After adding the missing event on verified recovery of an interrupted restore,
   `cargo test -p synapse-core --features test-fault-injection --test core_cli restore_crash_never_repeats_write_blindly -- --exact`
   passed 1 test, and `cargo test -p synapse-core --test core_cli` passed 21 tests.
   `cargo fmt --all -- --check` also passed.

The compiled-binary tests exercise replacement, old/new digest rejection,
readback, restart/replay, altered ID, user-changed and identity-exchanged
target, hardlink, corrupt backup, revocation, safe create release, simulated
unexpected partial content, and before/after replace and restore and before
confirmation process exits. Existing tests exercise state paths, Skill scope,
pinning and stopped missions. Fault hooks are compiled only with the opt-in
feature; the normal binary has no hooks. Python was unchanged and its suite was
not rerun. The existing generic Skill tests do not independently exercise a
forged Skill specifically on replacement or restore.

## Limitations and review

This is in-place update with durable journal, not atomic publication or a
hostile-same-user sandbox. Crash hooks model selected process exits, not power
loss or arbitrary native/filesystem failure. Unexpected partial content needs
explicit intervention and is not automatically overwritten. Older prepared
create intents from schema 3 have no persisted operation and cannot be safely
released automatically. The operator-supplied expected snapshot on restore is
an explicit authorization to restore over exactly that hash. No delete, shell,
network, or production-data exercise is included. Independent review and
additional adversarial/real-power-failure evidence remain outstanding.
