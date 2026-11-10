# Mission Planning Implementation Plan

> Agentic workers: use subagent-driven-development with an independent scoped
> reviewer. Owner already authorized implementation of this workflow; proceed
> directly in F:\Projetos\Synapse under its AGENTS.md.

**Goal:** Turn a human objective into a strict, reviewable proposed mission using
the actual local worker, without executing or approving anything before consent.

**Architecture:** Add planner purpose to the existing supervised AI path and
persist its input/pinned execution policy in the sole Core store. Core validates
the entire plan and creates the existing immutable proposed mission. Its optional
execution policy binds later staging, fixed checks and QA; legacy contracts keep
their existing shape/digests.

**Tech Stack:** existing Rust/SQLite Core, Python worker, LM Studio structured JSON.

**Spec:** `docs/specs/2026-11-10-integrated-mission-execution.md`, existing charter
and `docs/specs/2026-11-09-integrated-backend-design.md`.

## Global Constraints

- Core is the sole authority and database writer; model output never grants effects.
- Before approval, no Workspace writes, project-code execution, secrets or network
  activity beyond the explicitly selected numeric-loopback inference endpoint.
- Reuse existing missions, request receipts, model registry, Skill pins and context
  gates; do not implement a separate coordinator or store.
- One permanent A.R.T.E.M.I.S.; planner/QA roles do not activate Swarm.
- Rust/Python product only; experiments remain reference, not copied source.
- Missing execution capabilities stay unavailable; a proposed plan is not success
  creating a project. Do not alter the loaded model or its server settings.

## Review Focus

- Planner text cannot approve, invoke tools or invent executable arguments.
- Malformed/unsupported paths, recipes or fields reject the entire proposal.
- Original objective and captured model/Skill/context identity survive restart.
- Cancel, crash, repeat and changed-request retries cannot publish a late/duplicate plan.
- Future candidate content must not be confused with an approved legacy digest.

## Task 1 — Integrated structured planning and execution-policy contract

Files: create focused `backend/core/src/planner.rs`; extend contracts, missions,
store, Core/worker/conversation only where their shared interfaces require it;
Python protocol/provider mapping; actual-binary `backend/core/tests/mission_cli.rs`
and Python tests; `backend/contracts/v1/README.md`.

Interfaces:

- Add `mission_plan_start` with `mission_id`, `scope`, `model_id`, `objective`,
  optional exact `skill`, optional `context` refs, required `review_model_id` and
  `review_generation` (existing Generation). `review_model_id` may equal primary
  model, but the explicitly supplied review generation must differ from primary
  effective generation. Capture both complete immutable model manifests/digests.
- Use existing `job_get/job_cancel` for asynchronous lifecycle. Add
  `mission_plan_get {mission_id}` returning job status and validated plan/proposed
  contract when ready; invalid/cancelled/interrupted work has no mission proposal.
- Planner result is strictly `{summary,artifacts,checks}`. Summary1..2048UTF8;
  artifacts1..16 entries `{path,purpose}`; purpose1..512UTF8; path1..128ASCII,
  single safe Windows component, no slash/backslash/colon/dot traversal, reserved
  devices, trailing space/dot or duplicates (case-insensitive). Allowed suffixes
  `.rs`, `.py`, `.md`, `.txt`, `.toml`. The actual broker remains authoritative.
- Checks1..8 unique entries `{kind,entrypoint}`; kind `python_unittest` or
  `rust_test`; entrypoint must be an exact artifact path with matching `.py`/`.rs`.
  Both JSON schema and Core validation enforce unknown-field refusal. No content,
  executable, argv, environment, grant, approval or Swarm fields are accepted.
- Optional `MissionContract.execution` holds immutable `MissionExecutionSpec`:
  `plan_id`, captured primary/reviewer manifests and their digests, explicit review
  generation, validated artifacts/checks and fixed limits. Fixed initial limits:
  per-file8192UTF8 bytes, total24576UTF8 bytes, check30000ms,512MiB job memory,
  8 owned processes,32768bytes combined check output, one generation attempt.
  Also preparation_timeout_ms120000 and max_tool_asset_bytes2147483648 cap trusted
  runtime copying/ACL preparation separately from the check's execution timer.
  Fields are strict typed data. Absent execution must serialize omitted, preserving
  all existing mission request/contract digests and behavior.
- Core derives contract actions `mission_generate`, `project_check`,
  `artifact_create`, `workspace_read`; resources are exactly artifact paths;
  rollback `owned verified removal`. Contract objective/scope are the original
  owner values, not a model rewrite. This policy cannot operate until later
  coordinator/runner gates; legacy tool execution stays unaffected.

- [ ] RED actual-binary fixture test: register primary/reviewer configuration,
      select a Skill/context, start planning; inspect actual provider request,
      finish plan; get proposed immutable mission; no Workspace file/effect,
      no approval and no canonical learning. Restart preserves proposal/pins.
- [ ] Implement planner in the existing one-active-worker lifecycle. Foreground
      planning preempts background learning like conversation; another foreground
      returns busy. Store planning rows and job linkage, not another writer.
      Unknown provider/version, malformed result and duplicate IDs fail explicitly.
- [ ] Reuse Skill resolution through an explicit project scope (factor existing
      helper narrowly), and exact context selection/budgets. Planner sees only
      objective, approved selected guidance/context and fixed instructions; never
      scans Workspace contents. Check64messages/48000serializedUTF8 and32768per
      message before inserting a running job. Capture generation from the primary
      registry manifest; do not silently increase its budget.
- [ ] Replace the internal Launch learning flag with a typed purpose if needed;
      bump worker protocol to4 for `mission_plan`. Existing conversation/learning
      semantics and wire APIv1 remain intact. Fixed provider response_format schema;
      no synthetic production fallback. Validate all results again in Rust.
- [ ] Seal the validated execution policy under its source plan in the same
      transaction that proposes the mission and completes the job. Public
      `mission_propose` with an execution policy must match that source mission,
      original objective/scope and sealed policy; forged/rebound policies fail.
      A plan has one mission ID; failed retry needs a new mission ID initially.
- [ ] GREEN negative binary tests: extra/approval/command fields, invalid paths,
      case collisions, device names, unsupported/mismatched checks, missing model,
      foreign Skill, forged policy, timeout/cancel/restart and late result. Test
      legacy digest/absent-field compatibility. No partial proposal/event on
      invalid output and no raw output in error events.
- [ ] Run focused tests while iterating; full Rust all-feature suite once after
      implementation, plus Python protocol tests and fmt/diff checks. Commit exact
      files, self-review/report, independent scoped review. Controller then uses
      the actual loaded model and real Core to obtain an unapproved plan.

Next implementation blocks from the binding design: an enforcing Windows runner
with positive/adversarial real tool tests, then generation/check/reviewer/
integration/recovery coordination and a real project journey. This task must not
claim those blocks operational or stop their later execution after its review.
