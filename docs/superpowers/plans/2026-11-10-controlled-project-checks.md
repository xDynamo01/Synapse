# Controlled Project Checks Implementation Plan

> Agentic workers: subagent-driven-development; independent scoped review.
> Work directly in the canonical checkout, no new worktree. Start only after the
> integrated mission planner review passes; its immutable policy is the input.

**Goal:** Compile/test real supported Python/Rust candidate projects through the
existing Core inside an enforcing native Windows boundary, with durable receipts.

**Architecture:** A Core-owned asynchronous check validates an approved mission
and exact candidate set, prepares copied assets and a private LPAC, runs fixed
recipes under Job ownership, and publishes parent-observed results through the
same database/dispatcher. Missing isolation/tool assets fail closed.

**Tech Stack:** existing Rust/windows-sys0.61.2/SQLite, installed Python3.14 and
Rust/MSVC/SDK assets, native LPAC and Job Objects. No new VM, JS or downloads.

**Spec:** `docs/specs/2026-11-10-integrated-mission-execution.md`,
`docs/security/mission-runner-boundary.md`, existing authority/broker invariants.
Local feasibility inventory is `.superpowers/mission-runner-research/report.md`;
its source paths are observations, not strings to hardcode into product source.

## Global Constraints

- Model/project output never grants authority; Core is sole writer and publisher.
- Every check requires the current approved immutable mission's project_check
  action, exact artifact set, recipe and captured limits. Recheck stop before resume.
- Compile generated Rust and import/execute generated Python only inside verified
  LPAC. Never use unrestricted host execution as fallback.
- Do not alter global toolchain/repository/home ACLs or grant network capabilities.
- Actual token, filesystem and network enforcement must be tested alongside real
  successful and failing Python/Rust workloads; unavailable is not success.
- Windows loader/profile baseline and lack of a hard disk quota remain explicit.
- No new Synapse checkout, frontend, Swarm or model load/unload/settings changes.

## Review Focus

- Guest cannot read/write Core, host canaries, unrelated projects or runtime/receipts.
- Compiler/linker/test children remain in the same restricted boundary and die on stop.
- Cancellation works during preparation, suspended startup and running/flooded processes.
- Copied assets, fixed argv and input digests cannot be replaced by source metadata.
- Restart/profile-cleanup failures remain explicit, with no grant resurrection.

## Task 1 — Real Core check lifecycle, LPAC runner and verified tool closure

Files: focused `backend/core/src/runner/{mod,windows,assets}.rs` plus a shared
native process-lifecycle helper only where actual worker/runner reuse requires it;
contracts, store/Core, Windows dependency features and existing worker narrowly;
`backend/core/tests/project_check_cli.rs`; API docs. Keep security setup separate
from mission-state handling; no monolithic runner file.

Interfaces:

- Add `project_check_start {mission_id,check_index,artifacts:[{path,content}]}`,
  `project_check_get {check_id}`, `project_check_cancel {check_id}`. Initial check
  ID is the start request ID, durable/idempotent; ordinary retry changes conflict.
  Require policy-backed approved mission, exact unique planned artifact set,
  valid index and captured per-file/total limits. No executable/args/env fields.
- Persist candidate/check/tool digests and status before sensitive work. One
  active check initially; caller gets asynchronous running status. Core polls
  bounded channels; threads return data only and never write SQLite. Revoke or
  cancel persists and terminates owned activity, ignoring late success. Startup
  marks interrupted checks; cleanup state is separately visible.
- Private native entrypoint consumes validated candidate bytes, recipe and limits;
  produces a bounded parent-observed receipt with phase exit codes, input/tool
  digests, actual token/job observations, timing, output/error code and cleanup.
  stdout/stderr are untrusted diagnostics kept private/bounded, not effect receipts.
- Trusted tool locations come only from local owner configuration, using existing
  SYNAPSE_PYTHON_EXECUTABLE for the real Python executable and documented runner
  environment settings for real Rust sysroot, VC x64 libs, SDK um/ucrt x64 libs.
  Missing/unusable config is typed unavailable; no WindowsApps/rustup shim inside
  LPAC, source-supplied path or broad system scan. Do not hardcode user paths.

- [ ] RED actual-binary lifecycle fixture obtains a plan/proposal through real
      Core+test-local model endpoint, owner approves, then starts a check; old API
      rejects start. Use real native runner for GREEN, not a fake success backend.
- [ ] Validate/seal complete candidate batch and current mission policy before
      starting. Test unapproved/revoked/foreign/excess/missing/duplicate/altered
      payload and unknown fields; no project/sandbox execution on refusal.
- [ ] Implement a fresh owned profile/run intent, protected per-run copied runtime
      and project, readonly source/runtime and low-integrity output/temp. Bound
      preparation120000ms and assets2GiB. Skip user site/customization; use copied
      Python isolated/no-site mode and direct copied rustc/sysroot/bundled LLD plus
      copied selected VC/SDK libs. Never copy user Cargo config or run build scripts.
- [ ] Launch suspended LPAC with zero capabilities, exact handle list and atomic
      Job membership. Verify actual kernel LPAC/SID/low-integrity/capabilities/job
      before resume. Set memory512MiB/process8/output32768/execution30000ms limits
      from the approved spec. No breakaway. Cancellation must stop preparation and
      terminate the whole Job, including root-exited descendants and pipe holders.
- [ ] Implement fixed Python compile/unittest and Rust compile--test/test execution
      recipes with quoted fixed args and a sanitized explicit environment. Only
      approved flat entrypoints/data vary. Every generated executable stays inside
      verified LPAC. Bound and drain both pipes; exit output alone never approves QA.
- [ ] Actual positive/negative tests: real Python passing/failing unittest and Rust
      passing/failing test executable, stdlib/native DLL loading, process receipts,
      canary read/write/delete denial outside run, readonly runtime/receipt denial,
      known-live loopback IPv4/IPv6 traffic denied, child containment, runA/runB
      isolation, timeout/output flood/cancel, reparse/hardlink/ADS/export refusal.
      Inspect actual child tokens where processes persist long enough to observe.
- [ ] Cleanup only owned recorded profiles/run objects after Job exits; no-follow
      identity-checked cleanup. Crash/cleanup failure stays explicit; don't delete
      a colliding unknown profile. Do not silently pass if descendants survive.
      Use owned temporary roots/canaries; never touch the user's projects or disk E.
- [ ] Focused native/binary tests while iterating, full Rust suite once at end;
      preserve planner/conversation/learning/old broker tests. Report exact supported
      tool closure, capabilities/OS and real test evidence; no positive claims for
      unresolved probes. Self-review/commit, independent scoped review before the
      generation→QA→integration coordinator builds on this runner.

This supplies a real registered build/test consumer. It does not itself generate
source, accept semantic QA, integrate artifacts, run arbitrary Cargo/shell/Git,
fetch dependencies or declare the complete mission workflow finished.
