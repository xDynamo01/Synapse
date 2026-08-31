# Swarm Runtime

`SwarmRuntime` persists swarm lifecycle and executes four strategies:

- `leader_worker`: validates a distinct leader, dispatches worker attempts and
  deterministically consolidates verified outputs.
- `parallel`: dispatches bounded independent batches to distinct workers.
- `pipeline`: dispatches one dependency stage per tick and persists validated
  predecessor outputs in the next attempt snapshot.
- `review_loop`: creates producer and reviewer attempts, preserves rejected
  feedback and versions, and stops on approval or `max_iterations`.

Consolidated results contain outputs, evidence, conflicts, verification and
provenance. Private agent memory is not copied into shared snapshots.
