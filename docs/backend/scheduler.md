# Scheduler Runtime

Scheduler jobs are persisted records, never serialized Python functions. Jobs
support one-shot, delayed and recurring schedules, idempotency keys, retry and
misfire policies, revision, pause, resume and cancel. The canonical
`mission_dispatch` job targets a mission ID and calls `MissionDispatcher`.

`SchedulerLock` enforces a single runner and supports stale-lock recovery.
Restart reloads pending and paused jobs without duplicating active
idempotency-key records.
