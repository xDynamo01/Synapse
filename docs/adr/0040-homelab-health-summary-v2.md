# ADR 0040: Homelab Health Summary v2

## Status

Accepted.

## Context

The original homelab health summary covered runner, daemon, scheduler, jobs, notifications, approvals, and agent presence. Since then, Synapse added migrations, capabilities, provisioning, admin action workflows, retention, and decision runtime.

## Decision

Expand `HealthRuntime` to include the newer foundational runtimes without turning it into a metrics platform.

The summary now includes:

- runner status
- daemon status
- scheduler lock status
- pending and failed jobs
- due recurring jobs
- unread critical notifications
- pending approvals
- agent presence attention
- pending agent provisioning requests
- pending admin action requests
- retention registry status
- migration status
- decision runtime availability
- capability count
- archived and inactive agent counts
- structured health check items with severities

Severity levels are:

- `ok`
- `info`
- `warning`
- `critical`

## Consequences

- Homelab operators get a more accurate local runtime summary.
- Existing `/health` command and `GET /health` endpoint remain the same entry points.
- No dashboard, metrics server, or historical metrics are introduced.

## Non-Goals

- No Prometheus/Grafana integration.
- No UI dashboard.
- No historical health snapshots.
- No Resource Registry.
- No provider integration.
