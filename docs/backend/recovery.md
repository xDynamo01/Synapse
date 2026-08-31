# Mission Recovery

`MissionRecoveryRuntime` is the mission-level timeout and retry coordinator.
It scans mission deadlines, attempt deadlines and stale worker heartbeats.
Retry requires an idempotent task, remaining attempts and no irreversible side
effect. Every retry creates a new persisted `TaskAttempt` with provenance and
backoff.

Attempt DLQ records preserve mission, task, attempt, worker, agent,
correlation, redacted payload, recovery options and trace reference. Review,
close and archive preserve the original entry; no automatic restore occurs.

Recovery queries expose available decisions, history and supported actions.
Apply performs retry, worker/agent substitution, authorized model/provider
change, scope reduction, pause, intervention, replan or dead-letter. DLQ
restore creates one new attempt and records `restored_attempt_id`; repeated
restore returns the same attempt.
