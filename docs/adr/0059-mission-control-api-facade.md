# ADR 0059: Mission Control API Facade

## Status

Accepted.

## Context

Mission data is spread across mission records, mission context, mission supervision, delegation inboxes, delegation records, recovery decisions, dead letter entries, health, and readiness. A future Mission Control UI should not reconstruct operational state by calling many endpoints and reimplementing classification rules.

## Decision

Add `MissionControlRuntime` as a read-only backend facade.

It exposes:

- `get_overview()`
- `get_mission_card(mission_id)`
- `get_attention_panel()`
- `get_work_queue(agent_id=None)`
- `get_agent_workload()`

The facade consumes existing runtimes and returns UI-oriented dataclasses. It does not persist cache, emit events for ordinary reads, create plans, execute workflows, automate recovery, or duplicate lower-level domain behavior.

## API

- `GET /mission-control/overview`
- `GET /mission-control/missions/{mission_id}`
- `GET /mission-control/attention`
- `GET /mission-control/work-queue`
- `GET /mission-control/agents/workload`

## Commands

- `/mission-control`
- `/mission-control-card <mission_id>`
- `/mission-control-attention`
- `/mission-control-work-queue [agent_id]`

## Consequences

The future UI gets one cohesive backend surface for mission state. Lower-level runtimes remain the source of truth. Planner, workflow engine, DAGs, analytics, and visual dashboard behavior remain out of scope.
