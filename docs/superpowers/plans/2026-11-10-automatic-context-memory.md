# Automatic Context Memory Implementation Plan

> Agentic workers: subagent-driven-development and independent scoped review.
> Automatic learning is already owner-approved; no extra user memory command.

**Goal:** Learn concise durable context after successful conversation turns,
inside the existing Core and canonical store, without treating chat as memory.

**Architecture:** Core queues a durable background extraction job for the latest
human message after a successful turn. The same supervised local worker proposes
bounded structured candidates; only Core validates and versions records. Chat
has priority, and all memory/model traffic remains local. The staging queue is
execution state, not a second memory system.

**Tech Stack:** existing Rust/SQLite writer and Python local provider;
static structured-output schema, no extra model runtime or weights.

**Spec:** approved integrated backend design and Charter ME-001–005,
PX-001, SE-001/002/005, MM-001/002, PL-001/006, QA-001–003.

## Global Constraints

- No raw transcript copy to canonical records and no assistant-generated facts.
- Scope is fixed by the source chat; candidates cannot provide scope, grants,
  commands, dependencies or tool actions. No global/cross-project promotion.
- Candidate content is an exact short clause quoted from the source user
  message, up to512UTF8 bytes; key is a stable bounded lowercase subject slug.
  Initial automatic kinds: fact, constraint, decision only. Provenance records
  actual source message/job IDs. Other existing explicit memory kinds unchanged.
- Model output is data, never authority. Parse strictly, cap8 candidates and
  reject malformed/extra fields, unsupported kinds and non-source quotations.
- No implicit reading of other project contexts. Reply generation does not
  automatically receive memory; existing explicit context references still gate
  reading. Learning may compare canonical metadata inside Core for versioning.
- No hidden generation-budget override; capture source model/endpoint/settings.
- All status/events are truthful; invalid extraction cannot be reported learned.

## Review Focus

- Duplicate/restart must not create duplicate records or revisions.
- Newer human/manual information must not be overwritten by stale extraction.
- Cancelled/failed turns or fabricated/assistant quotations cannot become memory.
- Malformed/prohibited candidates must not partially write a batch.
- Background learning cannot block the next foreground conversation.

## Task 1 — Integrated automatic learning pipeline

Files: focused `backend/core/src/learning.rs`; extend conversation/Core/store/
memory/contracts and Python worker/protocol/provider only as required; binary
and Python tests; v1 documentation and exact evidence report.

- [ ] Add actual-binary failing journey: conversation completes, automatic
      learning runs, explicit contextual memory read returns typed source-backed
      record; no memory_put or extract command issued by the client.
- [ ] Persist one queued learning job per successful source turn and captured
      model/endpoint/generation. Feed only latest human content plus fixed Core
      schema/instructions to classifier; use provider response_format JSON schema.
      Existing chat response remains ordinary text and successful independently.
- [ ] Add queryable learning status by source job ID. Queued/interrupted work
      resumes on dispatch/poll with bounded retries; results are published once
      atomically with status. Cancelled/failed conversation enqueues nothing.
- [ ] Foreground tasks preempt the owned learning worker and requeue its source,
      without late publication or starving chat. Reuse same worker supervision
      and one active model call; worker threads never write the database.
- [ ] Validate candidates entirely before writing. Deduplicate identical content;
      revisions retain prior versions and provenance. Kind conflicts are staged
      as conflicts, not silent reinterpretation. Compare source ordering before
      writes: stale job cannot overwrite newer manual/automatic source. Add a
      monotonic origin cursor to records if needed; manual writes use their own
      event cursor, automatic writes use the source-user event cursor. Keep
      latest-source precedence even if extraction completes out of order.
- [ ] Tests: second-version update, duplicate/restart, other chat/project absence,
      malformed batch/scope injection/nonquote/oversize/greeting no-facts,
      cancelled turn, foreground preemption and stale-source conflict. No raw
      candidate content in diagnostic events; only canonical data/history store.
- [ ] Preserve existing model/config/rollback tests. Bump internal worker version
      if purpose changes the request schema; public API remains v1. Reject unknown
      purposes and old workers rather than silently changing semantics.
- [ ] Commit/self-review with exact RED/GREEN commands/results; independent review.
      Then separate real local model smoke validates at least one extracted fact,
      source provenance, explicit retrieval and restart without a client write.

This initial verified-quote representation is a concise canonical fact selected
from a human statement, not free paraphrase. It does not prove universal semantic
classification accuracy; provenance/version history remain visible and reversible.
Unsupported structured output or too-small configured budgets fail learning
explicitly while preserving the already completed conversation.
