# Implementation Plans

An `ImplementationPlan` translates one approved RFC revision into controlled
execution scope. It binds `project_id`, `rfc_id`, RFC revision/checksum, allowed
domains/references, forbidden changes, tasks, dependencies, Skills, Tools,
quality gates, eval references, criteria and rollback.

Plan states are `draft`, `validated`, `approved`, `executing`, `paused`,
`completed`, `failed`, `cancelled` and `stale`. An RFC content revision marks
older plans stale. A Mission binding carries immutable project/RFC/plan IDs,
revisions and checksums; Mission refuses to start if the gate reports stale or
incomplete state.

Implementation Plans remain separate from Mission DAGs. A plan may produce a
Mission, but Missions continue to own Tasks, Workers and Attempts. Restart
recovers partial metadata and never starts work or repeats a completed Mission.
