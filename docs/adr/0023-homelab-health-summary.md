# ADR 0023: Homelab Health Summary

## Status

Accepted

## Context

Synapse now has durable local projections for runner identity, daemon status, scheduler locks, jobs, recurring jobs, notifications, approvals, and agent presence. In homelab mode, operators need one read-only view that answers whether the local system is healthy without inspecting each file or runtime independently.

The health layer must not become a second owner of operational state. Runner, daemon, scheduler, notification, approval, and presence runtimes remain the source of truth for their domains.

## Decision

Add `HealthRuntime` as a local-first diagnostic aggregator.

It reads:

- runner identity and heartbeat
- daemon status
- scheduler lock status
- pending and failed jobs
- due recurring jobs
- unread critical notifications
- agents in `error` or `offline` presence
- pending approvals

It exposes:

- command `/health`
- API `GET /health`
- event `health.checked`

The returned `HomelabHealthSummary` is structured and suitable for future UI, CLI, and homelab monitors.

## Consequences

Operational health becomes visible through one runtime boundary without adding external dependencies or a database.

The first implementation is intentionally point-in-time. It does not provide historical health snapshots, alert routing, native OS health checks, or multi-node aggregation.

## Non-Goals

- UI dashboard
- Docker healthcheck integration
- systemd or Windows Service integration
- multi-node cluster health
- push/mobile notifications
- external monitoring providers
