# Sandbox Operational Admission Policy — Slice 3 audit

## Decision

**COMPLETE / APPROVED**

The canonical container now owns a deferred Sandbox runtime. Application construction
does not create its SQLite database. Required lifecycle startup builds it with the
canonical fail-closed policy; shutdown closes it. No execution port or adapter is enabled.

## Invariants

- materialization and supervision services remain unavailable;
- isolation driver and real execution remain unavailable;
- no admission-facts, policy-provider, approval, artifact, isolation or Skills adapter is
  configured;
- policy presence is not authorization, grants, materialization or executability;
- startup failure is required and triggers canonical lifecycle rollback;
- the inventory now records the required boundary as `global / authorized / active`.

## Current gates

- focused policy, Sandbox composition, global binding and lifecycle/architecture selection:
  **31 passed**;
- Ruff on bootstrap and changed tests: **passed**;
- Mypy on `backend/synapse/bootstrap`: **passed on 36 files**;
- no production data, process, network or secret was used.

## Next

Slice 4 adds a neutral Health projection that reports the operational policy boundary and
the separate absence of real execution.
