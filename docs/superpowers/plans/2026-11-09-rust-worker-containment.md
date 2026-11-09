# Rust worker containment experimental plan

> For agentic workers: use subagent-driven-development with an independent
> scoped review. This plan executes one testable experimental task, not product
> scaffolding or acceptance of the Core owner.

**Goal:** Eliminate the observed Windows blocked-worker orphan in the synthetic
Rust/Python integration experiment and prove descendant cleanup on host death.

**Architecture:** Compare fixture behavior before/after OS-owned kill-on-close
containment. Place the Python worker inside containment before it can execute;
the Rust host owns the only non-inheritable lifetime handle. EOF cooperation is
not the guarantee. Preserve the embedded comparator and original first-spike
evidence as historical observations.

**Tech stack:** measured Rust/MSVC and CPython from the first spike; exact locked
Windows API binding chosen from official sources; no JavaScript/TypeScript.

**Spec:** `docs/superpowers/plans/2026-11-09-rust-python-foundation-revalidation.md`

## Decision Charter Compliance

Charter: `docs/specs/2026-11-06-synapse-0.3-decision-charter.md`.
Binding IDs: CR-001, CR-004, MI-003, SE-005, PL-001, PL-004, PL-006, QA-001–003.

| Obligation | Evidence |
|---|---|
| Contain owned worker/descendants without relying on cooperative exit | hard Rust death with blocked Python and synthetic child |
| No PID-reuse termination or broad process kills | retained owned handles; exact process identities |
| Deny execution when containment cannot be established | denied assignment/creation fixture or explicit tested injectable setup failure |
| Strict bounded schema/cancel behavior retained | existing fixture regression |
| No product/platform acceptance inferred | Windows-only report, Linux/macOS NOT RUN |

No proposed deviations. Native UI, storage, durable cancellation/replay and
remote authority remain outside this focused task and mandatory for later gates.

## Task 1 — Contain the synthetic worker before execution

Files: create `experiments/rust-python-boundary/src/containment.rs`; modify
`src/main.rs`, `Cargo.toml`, `Cargo.lock`, `engine.py`, `probe.py` within that
experiment only as required. Create
`docs/evidence/foundation/rust-python-worker-containment.md`.

Consumes: first-spike private-pipe protocol and owned-handle test harness.
Produces: an owned worker/process-container abstraction with launch, terminate
and wait paths; returned worker cannot execute before containment assignment.

- [ ] Add a real failure fixture: launch blocked worker plus synthetic descendant,
      retain identity handles, kill Rust, require both to exit within 2 seconds.
      First show the pre-fix orphan; cleanup only through retained handles.
- [ ] Implement Windows Job Object kill-on-close ownership or an equivalent
      documented OS mechanism. Create the child suspended, assign before resume,
      fail closed on every setup error, and close non-inheritable handles using
      RAII. Do not use assign-after-start or a timing-based watchdog guarantee.
- [ ] Cover setup rejection without running worker code; native memory fault and
      nested-job restrictions must be recorded when not exercised.
- [ ] Repeat hard-death fixture at least 10 times, including worker busy/hung
      states; verify exact original identities disappear and no owned helper
      remains. Assert original schema/cancellation and embedding comparison
      behavior still hold; do not label embedded crash isolation solved.
- [ ] Record exact binaries/source hashes, actual OS/runtime, commands, output,
      limits and measured cleanup latency. Run formatting and relevant locked
      builds/probes; commit and independently review the exact artifact.

The 2-second bound and 10 repetitions are engineering experiment thresholds,
not a user SLA. R2 and Gate 00 remain blocked after this task until their other
requirements are proved.
