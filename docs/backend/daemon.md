# Daemon Runtime

Each daemon tick renews runner heartbeat, runs due scheduler jobs, dispatches
each running mission independently, scans timeout/stale state and persists a
structured tick status. A failure in one mission emits
`daemon.mission.error` and does not interrupt subsequent missions.

Dispatch work is bounded by mission `max_concurrency`; a tick does not execute
an entire DAG when dependencies require later stages. Scheduler locking
provides single-runner behavior.
