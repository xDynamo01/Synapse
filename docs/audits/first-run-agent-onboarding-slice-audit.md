# First Run Agent Onboarding — slice audit

> Historical/superseded: the Electron ADE implementation and release artifacts were removed under ADR 0119 on 2026-08-21. This file is retained as historical evidence only, not active frontend architecture.

Date: 2026-08-21
Profile: `bounded-context-change` / Level B
Status: **FIRST RUN AGENT ONBOARDING READY**

## Scope

This slice changes only the Electron first-run gate, its typed IPC/preload boundary,
the isolated onboarding surface and focused tests. It does not change the primary
layout, Presence, Swarm, visualization, chat surfaces, audio, notifications, Insight,
command UX, backend contracts or release packaging.

## Cause

The Electron renderer previously restored and opened the normal workspace without first
querying the canonical Primary Agent state. A clean profile therefore reached actions
that require a Primary Agent while providing no path to create or select one.

## Implemented flow

- Startup queries `GET /api/primary-agent`, `GET /api/agents` and
  `GET /api/models/available` through a narrow main-process client.
- A configured Primary releases the normal workspace immediately.
- One existing usable persistent agent is canonically assigned as Primary; multiple
  candidates require explicit selection in onboarding.
- With no usable agent, onboarding permits only a name and a currently live,
  chat-usable model/provider. Creation uses canonical `POST /api/agents`, requires an
  applied result, then assigns it through `PUT /api/primary-agent`.
- The workspace remains blocked on failure. Empty model discovery is a recoverable state
  with retry. No frontend completion flag or duplicate agent store exists.
- A missing, archived or otherwise unusable prior Primary causes operational re-entry.

## Authority and persistence

All effects stay behind explicit allowlisted IPC operations. The main process validates
arguments and binds requests to the owning renderer. Electron sandbox,
`contextIsolation`, navigation/download/permission denial and the existing command
authority boundary remain unchanged. Durable agent and Primary state remains owned by
the backend's existing provisioning and Primary Agent runtimes.

## Gates

- `npm test`: **PASS**, 40/40.
- `npm run build`: **PASS**.
- `pytest -q tests/acceptance/test_primary_agent_initial_setup_e2e.py tests/acceptance/test_primary_agent_restart_e2e.py`: **PASS**, 2/2.
- Release packaging: **NOT RUN / OUT OF SCOPE**.

## Decision

The required no-agent, successful creation, configured restart, existing-agent,
creation-failure and no-model paths are covered. The slice is complete and no transition
to another slice is authorized.
