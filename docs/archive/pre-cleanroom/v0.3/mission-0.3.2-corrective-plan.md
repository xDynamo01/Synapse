# Swarm Verification Progress Guard Implementation Plan

**Goal:** Stop outer verification retries when verifier feedback produces no new
tool evidence, while preserving the multi-tool inner agent loop.

**Architecture:** `AgentRuntime` remains responsible for bounded multi-tool
execution. `WorkerRuntime` owns verifier continuation and must require observable
receipt progress before granting another outer round.

**Tech Stack:** Python 3.12, pytest, Synapse mission/worker runtimes.

**Spec:** `docs/v0.3/findings-and-operational-backlog.md` (`FND-031-001`).

## Global constraints

- Do not reduce the inner eight-round tool budget.
- Do not change Swarm size, tool permissions or verification criteria.
- Preserve approval continuation and previous receipt replay.
- No new dependency or external HTTP/product API change.

## Tasks

- [x] Change the existing acceptance scenario to require one feedback call per
  default ephemeral agent and fail against the current repeated-feedback path.
- [x] Add the minimal progress guard in `WorkerRuntime.execute_attempt()`.
- [x] Run the exact acceptance scenario, the complete project-tools acceptance
  file, bounded Swarm/worker tests and architecture suite.
- [x] Run the global Python suite and report every remaining failure without
  converting partial success into readiness.
- [x] Make concurrent registration of identical tool-input assets idempotent at
  the Intelligence Boundary after the first global run exposed the race.
- [x] Update Mission 0.3.2 evidence and findings, then review/commit/push the
  authorized branch.

## Review focus

- A successful new receipt must still permit the next verification attempt.
- Replayed receipts alone must not count as progress.
- Failed/blocked/approval receipts retain their existing handling.
- Multi-tool inner execution remains available for real project work.
- Failure remains explicit; the guard must not turn verification failure into
  completion.
