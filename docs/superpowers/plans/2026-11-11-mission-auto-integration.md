# Automatic integration of reviewed mission artifacts

> Implement directly in the canonical workspace with independent task review.

**Goal:** Publish only the QA-accepted bytes of an approved mission, validate
the actual Workspace files and compensate for a failed postcheck.

**Architecture:** Rust Core owns the durable run. A private integration
authorization is derived from its sealed candidate and current approval.
Existing broker path guards and tool intent journal own all filesystem writes.
The existing native checker supplies pre- and post-integration receipts.

**Tech stack:** Rust, SQLite, Windows native broker/LPAC and the existing
supervised Python worker.

1. Extend the broker with an identity-bound create receipt, actual readback and
   handle-based removal of owned matching files. Preserve legacy authorization
   and prove path conflict, hardlink, changed bytes/identity and delete refusal.
2. Advance a review-ready run after dispatch. Journal each effect before it
   occurs, recheck the approval and candidate at each write, and stop on
   ambiguous effects. Run postchecks from actual readback with the same pinned
   tool digests. Revalidate published files before completion. Roll back only
   verified owned unchanged files while approval remains active.
3. Test actual CLI publication, occupied targets, postcheck failure and rollback,
   cancel/revoke, crash ambiguity, and prior regressions. Use an empty test
   workspace for the real Qwen mission. Capture scoped independent review.
