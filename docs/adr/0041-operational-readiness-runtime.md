# ADR 0041: Operational Readiness Runtime

## Status

Accepted.

## Context

`HealthRuntime` reports what is happening inside the local Synapse runtime. It includes structured checks and severities, but it does not answer whether the system should operate now in local or homelab mode.

Future CLI, daemon, service, and UI surfaces need a small operational interpretation layer without introducing dashboards, metrics servers, or historical observability.

## Decision

Add `ReadinessRuntime` as a thin interpreter over `HealthRuntime`.

Health remains responsible for collecting signals. Readiness consumes the health summary and policy from:

```text
DATA_DIR/config/readiness_policy.yaml
```

Readiness states are:

- `ready`
- `degraded`
- `action_required`
- `not_ready`

Initial rules interpret failed jobs, critical notifications, pending approvals, stale scheduler locks, migration availability, capability availability, template availability, and agent error states.

Readiness is exposed through:

- `/readiness`
- `/readiness-issues`
- `/readiness-actions`
- `GET /readiness`
- `GET /readiness/issues`
- `GET /readiness/actions`

## Consequences

- CLI/API clients get a direct answer to "can the system operate now?"
- Health and readiness stay separate: collection versus interpretation.
- Policy can adjust operational severity without changing health collection.

## Non-Goals

- No UI dashboard.
- No Prometheus/Grafana.
- No historical metrics.
- No service manager integration.
- No provider integration.
- No Resource Registry.
