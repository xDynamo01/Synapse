# Integrated Backend Rollback and Recovery Implementation Plan

> Agentic workers: use subagent-driven-development with an independent review.
> Product implementation and execution method are already owner-approved.

**Goal:** Complete the bounded file replacement/rollback/recovery path inside
the existing Rust Core, never a second writer or an independent subsystem.

**Architecture:** The Core persists an intent and verified backup before
mutation. Windows broker retains exclusive no-follow file identity handles;
replacement writes through the validated handle with readback/flush. SQLite and
filesystem are separate stores: crash ambiguity remains explicit and is resolved
only through verified recovery commands. No claim of a filesystem transaction.

**Tech Stack:** existing locked Rust/SQLite/Win32 product stack; current Python
worker is unaffected. Windows fixed NTFS first, other platforms unavailable.

**Spec:** `docs/specs/2026-11-09-integrated-backend-design.md`, Task3 of
`docs/superpowers/plans/2026-11-09-integrated-backend.md`.

## Global Constraints

- Charter: `docs/specs/2026-11-06-synapse-0.3-decision-charter.md`, CR-001/004,
  MI-001–007, SK-001–004, SE-005/006, PL-001/004/006, QA-001–003.
- Same Core/Store/API and sole writer; no old implementation copied.
- Exact approved action/resource/new digest and previous digest for replacement.
- Backup lives in protected runtime state, not logs/memory/Git or worker data.
- No unapproved overwrite/delete, no broad cleanup and no replacement on alias,
  reparse, hard link, changed identity or changed content.
- Stop/revocation blocks new filesystem writes, including recovery writes under
  the revoked mission. Inspection of journal metadata is safe; no renewed grant.
- Normal compiled product excludes all test-only fault hooks.

## Review Focus

- User modifies target after replacement: rollback must conflict, not clobber.
- Process dies after prepare or write: retry must never guess or repeat blindly.
- Backup corrupted or target exchanged: restore must refuse.
- Same request ID with altered recovery action: digest conflict after restart.
- Unapproved/revoked mission or forged Skill pin: no effect, including rollback.

## Task 1 — Verified replacement and operational recovery

Files: extend `backend/core/src/{contracts,core,store,tools,missions}.rs`;
create focused `backend/core/src/recovery.rs` if needed; update protocol README,
`docs/security/backend-tool-boundary.md`, and actual binary tests.

Interfaces: keep existing shapes compatible. Add optional defaulted
`artifact_previous_digests` to mission contract; new replacements require its
exact prior SHA plus the existing new-content SHA, approved action and explicit
verified-backup rollback policy. Publish typed recovery commands with intent ID,
mode and optional expected current hash. Names and wire examples are fixed in
the updated v1 contract report before the next task consumes them.

- [ ] Add actual-binary failing tests for approved replacement/readback,
      wrong old/new hash, foreign/revoked/Skill scope, existing hard links/state,
      rollback, replay and changed-file conflict.
- [ ] Prepare broker/target before mutation, retain identity and exclusive file
      handle (fail on concurrent access); commit bounded original bytes/hash and
      identity in protected state before any write. Write/flush/readback through
      the owned handle; no path reopen between authorization and mutation.
- [ ] Implement recovery inspect, verified finalize, verified restore and safe
      abandon/release for a prepared create with no effect. Mutating recovery
      requires still-valid original mission and rechecks identity/digests.
      Unknown identity/content returns recovery_required; never silently adopt.
- [ ] Rollback uses only the persisted verified backup and refuses if current
      target differs from the acknowledged replacement or supplied explicit
      expected snapshot. Restore itself has durable intent and receipt.
- [ ] Add opt-in fault points before/after mutation and before confirmation.
      Restart/readback/retry proves no blind repetition; corrupt backup and
      unexpected partial target refuse; safe abandoned no-effect request releases
      its reservation without granting new authority.
- [ ] Run default regressions, separate sequential feature-fault tests and
      Python regressions where affected; record exact commands/output, commits,
      environment and limitations. Independent scoped review before acceptance.

Bounded32KB UTF8 files initially. This is an exclusive-handle update with backup,
not atomic publication or a hostile-same-user sandbox. Arbitrary native/power
faults remain unproved; unexpected partial content needs explicit recovery and
must not be erased automatically. No production/user files used in tests.
