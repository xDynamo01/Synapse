# Mission candidate generation and separate review

> For implementation agents: use subagent-driven development and independent review.
> Use the canonical Synapse checkout.

**Goal:** Advance an approved mission from generation through native checks to a
separate review decision with durable evidence.

**Architecture:** Core alone owns mission state. Typed Python worker invocations
return bounded data. The existing native checker runs the exact staged candidate.
Review receives the original objective, candidate and observed phase results.

**Tech stack:** Rust Core, SQLite, Python inference worker, local LM Studio and
the existing Windows native check runner.

1. Add typed generation and review worker purposes with static schemas. Pin the
   model snapshots from the sealed mission and keep existing conversation,
   planner and learning wire behavior compatible. Test invalid output and exact
   artifact set/size enforcement.
2. Add a durable coordinator to start an approved mission, seal candidate bytes,
   run approved recipes sequentially and request review only after all pass.
   Persist phase IDs, digest and review decision. Stop on rejection, cancellation
   or interruption, without Workspace effects. Expose run status via the Core.
3. Test the real CLI against controlled provider fixtures for success, rejection,
   check failure and stop. Rerun worker and CLI regressions and exercise the
   available real local model with a small candidate. Review the diff independently.

This milestone ends at the pre-integration decision. Publication, readback,
postchecks and compensation are the following coordinator step.
