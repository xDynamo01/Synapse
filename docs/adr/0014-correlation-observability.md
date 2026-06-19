# ADR 0014: Correlation Observability

Date: 2026-06-14

## Status

Accepted

## Context

Synapse now has chat, agents, tools, approvals, worker processing, scheduler jobs, and daemon ticks. Without a shared correlation id, a single user-visible flow becomes hard to audit across `logs/events.jsonl`.

The observability layer must remain local-first and should not require an external tracing backend.

## Decision

Introduce `CorrelationContext` in `backend/synapse/observability/correlation.py`.

Events written by `EventBus` now include a correlation-aware envelope:

- `id`
- `type`
- `timestamp`
- `correlation_id`
- optional `causation_id`
- optional `parent_id`
- `source`
- `payload`

Runtime code uses context-local correlation scope so nested services can emit correlated events without threading a correlation id through every method signature.

Trace lookup is exposed through:

- `/trace <correlation_id>`
- `GET /trace/{correlation_id}`

Event loading remains backward-compatible with older JSONL entries that do not include correlation fields.

## Consequences

Positive:

- full flows can be traced across chat, tools, approvals, jobs, daemon, and workers
- no external observability dependency is required
- legacy event logs still load
- future UI/mission-control trace views have a stable data source

Tradeoffs:

- causation chains are still shallow
- not every persistent domain record stores its correlation id yet
- no external exporter or indexed trace store exists yet
