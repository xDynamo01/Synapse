# ADR 0020: Scheduler Recurring Jobs

Date: 2026-06-19

## Status

Accepted

## Context

Synapse homelab mode needs local recurring jobs for maintenance and background routines such as notification cleanup, email checks, and inbox processing. This must work without UI, mobile, service managers, or external schedulers.

## Decision

Add recurring job definitions to `config/scheduler_policy.yaml` and persist runtime cadence state under `DATA_DIR/scheduler/recurring`.

`RecurringJobDefinition` includes:

- `id`
- `type`
- `payload`
- `interval_minutes`
- `enabled`
- `priority`
- `max_attempts`
- `last_run_at`
- `next_run_at`

Supported V1 job types:

- `notification_cleanup`
- `check_email`
- `process_agent_inbox`

`SchedulerRuntime.enqueue_due_recurring_jobs()` enqueues due jobs and advances cadence state. `DaemonRunner.run_once()` calls it before executing pending jobs.

## Consequences

Recurring jobs become local-first and file-backed. The runtime supports simple interval cadence without cron complexity.

Known gaps:

- no cron parser
- no timezone-specific scheduling
- no dependency graph between jobs
- no cross-process lock for multiple daemon instances
- no backoff policy for recurring failures
