# Skill-Guided Conversation Implementation Plan

> Agentic workers: use subagent-driven-development and independent scoped review.
> This implements the already-approved integrated backend; no delivery-order change.

**Goal:** Make registered immutable Skill guidance actually participate in local
conversation generation, with a verifiable pinned version and no new authority.

**Architecture:** Extend the existing conversation command with an optional
Skill pin. Rust resolves the pin in the source chat's scope, validates its digest,
persists it with the job, and builds the existing supervised worker request.
Skill text is untrusted domain guidance, never a tool grant or owner instruction.

**Tech Stack:** existing Rust Core/SQLite, Python worker, API v1.

**Spec:** `docs/specs/2026-11-09-integrated-backend-design.md`, charter SK-001,
SK-003/004, ME-003/005, MI-003, SE-001/002/005, PL-006.

## Global Constraints

- Rust/Python only; no 0.2 runtime or experiment implementation copied into product.
- All modules share one composition root, database writer and API contracts.
- Model output never authorizes an effect; only explicit human CLI commands do.
- No network listener, external account operation or automatic weight download.
- The active Skill version is immutable during a mission.
- Skills provide domain expertise, not authority.
- No implicit reading of unrelated project context.
- Missing real providers/assets return typed unavailable, never fake success.

## Review Focus

- A mismatched scope or digest cannot expose another project's instructions.
- A retry after restart must retain the original pin, not silently use a newer Skill.
- Large Skill guidance must fail context bounds before appending a user message.
- Injected Skill instructions cannot execute tools, approve missions or write memory.
- No-Skill conversations and automatic learning retain their existing behavior.

## Task 1 — Pinned guidance in actual conversation execution

Files: create focused `backend/core/src/skills.rs`; extend contracts,
conversation/store/Core composition only as needed; update actual-binary
`backend/core/tests/ai_cli.rs`, `backend/contracts/v1/README.md`.

Interfaces: consume current `SkillPin { scope,id,version,digest }`, immutable
registry, `conversation::start` and existing `Launch`. Add optional `skill` to
`conversation_start` with absent serialized shape preserved. Produce durable
`job_get.skill` metadata for guided jobs; ordinary jobs retain compatibility.

- [ ] Write and run a failing actual-binary test: register a Skill, create a chat
      in its project, start a guided turn with the returned digest, inspect the
      test-local HTTP request and verify exact instructions and version reached
      the worker; successful assistant response persists through restart.
- [ ] Resolve exact scope/id/version/digest before appending the human message.
      Require chat scope equals Skill scope, full digest match and immutable
      version exists. Reuse registry validation instead of duplicating it.
- [ ] Persist the pin in the source job. Add fixed Core guidance describing Skill
      text as untrusted domain data; include delimited/serialized instructions
      without impersonating human approval. Do not include Skill permissions as
      worker authority. Keep canonical memory reads explicit and separate.
- [ ] Count Skill guidance inside existing message-count and UTF8 request budgets;
      reject oversized context atomically. Worker protocol changes only if its
      existing message schema cannot represent this; never silently accept old
      semantics. Background learning must still see only the human source.
- [ ] Add binary tests for wrong digest, foreign scope, missing version, large
      guidance atomic rollback, immutable pin after another version registration,
      duplicate request and restart. Use an instruction attempting file creation
      and memory/mission approval; assert there is no such effect/event and no
      authority-bearing data in the worker request. Do not claim prompt obedience
      proves security; the absence of an execution path enforces the boundary.
- [ ] Run the focused AI tests and Python worker tests if their request mapping
      changed; fmt/diff check, commit and report exact failing/passing results.
      Independent review before accepting. A later controller smoke uses the
      actual local model and reports its observable guidance behavior separately.

This task integrates guidance, not autonomous discovery, Skill evolution, planner
execution or arbitrary script tools. Those remain explicit subsequent backend
tasks and must not be marked operational by this change.
