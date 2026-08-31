# Missions Runtime

`MissionRuntime` owns durable mission lifecycle, plan attachment, progress and
canonical dispatch. `PlannerRuntime` persists validated plans, while
`TaskGraph` provides deterministic DAG operations. `MissionDispatcher`
reserves compatible workers, creates immutable attempts and executes bounded
batches. Repeated dispatch is safe because active attempts and idempotency keys
prevent duplicate work.

Mission completion requires every plan task to be completed with a verified
result. Pipeline dependency outputs enter the next attempt through a persisted
snapshot containing provenance references. Pause, resume and cancel are
idempotent and survive runtime restart.

Plans are immutable versioned records. Replace creates a new plan ID/version,
requires the expected current version and preserves history. Task assignment,
reassignment, cancellation, verification and dependency edits require expected
revision where mutation occurs. Task delete and archive are not supported by
design because attempt and trace audit history must remain referentially valid.
