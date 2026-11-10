# Explicit Conversation Context Implementation Plan

> Agentic workers: use subagent-driven-development and independent scoped review.
> This completes the existing approved memory-to-conversation integration.

**Goal:** Allow a conversation to use explicitly referenced canonical project
records through the same real Core, without automatically loading project memory.

**Architecture:** An optional bounded list of explicit references on
`conversation_start` selects exact project/key records. Rust resolves their latest
active revisions transactionally, constructs untrusted context data for the
existing worker and stores the selected revision identities with the source job.
Chat history and canonical memory remain distinct.

**Tech Stack:** existing Rust/SQLite Core and Python worker, API v1.

**Spec:** `docs/specs/2026-11-09-integrated-backend-design.md` and charter ME-001–005,
PX-001/002, SE-001/005, PL-006. User explicitly permits referring to a project's
memory from Presence or another conversation; references gate the read.

## Global Constraints

- All modules share one composition root, database writer and API contracts.
- No raw transcript copy to canonical records and no assistant-generated facts.
- No implicit reading of other project contexts.
- Model output is data, never authority.
- Memory and Skill guidance never grant tool or mission permissions.
- Rust/Python only; no old runtime source reuse.

## Review Focus

- A normal turn without references must not receive any canonical context.
- Referencing one project/key must not pull its other keys or chat history.
- Inactive/missing records must fail before appending a user turn.
- Selected revisions must remain pinned after memory changes and restart.
- All context text must count against existing request/message budgets.

## Task 1 — Explicit memory references in actual conversations

Files: focused `backend/core/src/context.rs`; extend contracts,
conversation/store/Core as needed; `backend/core/tests/ai_cli.rs` and API docs.

Interfaces: preserve existing guided/ordinary conversation requests. Add optional
`context` list (omitted when absent/empty), entries strictly `{scope,key}`.
Limit16 unique references total; validate project scope and bounded key with the
existing memory rules. Return durable selected context metadata from `job_get`
only when references are supplied: scope,key,revision,kind and content digest.

- [ ] RED actual-binary test creates canonical records in two projects, starts a
      turn with exactly one explicit reference, inspects the fixture provider
      request and verifies the selected content reached the model; unrelated
      keys/project chat text are absent. Normal turn has none of this context.
- [ ] Resolve each exact reference to the latest `active` revision in the same
      dispatcher transaction, using the existing explicit memory gate rather
      than bypassing scope validation. Cross-project reference is allowed only
      by the explicit list; it does not move/promote any record or change the
      source chat scope. Missing or non-active latest record is an explicit error.
- [ ] Persist selected revision identities and content hashes with the source
      job; actual worker messages receive the corresponding quoted data under
      fixed Core instructions. No prompt text can fabricate grants or cause a
      broader database read. Keep optional Skill pin behavior and all context
      inside the existing64message/48000byte serialized-message budget and
      32768UTF8-byte per-message worker limit, including wrappers/escaping.
- [ ] Reject duplicate references, unknown fields, >16 references, invalid scope,
      empty key and oversized combined prompt atomically. Verify no user message
      or running job is left by refusal. Do not silently truncate memory data.
- [ ] GREEN tests verify restart preserves selected revision metadata, subsequent
      manual revision does not change an existing job's selection, an injected
      record cannot approve a mission or execute a tool, cancelled/failed turns
      keep learning behavior, and automatic learning still sees only the latest
      human message rather than injected memory/Skill text.
- [ ] Run focused AI tests during iteration, full Core suite once before commit;
      preserve Python request schema if it already represents messages. fmt/diff
      check, self-review, exact report and independent scoped review. Controller
      later runs a real model recall example with explicit context separately.

Natural-language project-name resolution, searching all memory, conflict UI and
global promotion are subsequent work. This task exposes the explicit stable
contract for those callers and does not claim they are already implemented.
