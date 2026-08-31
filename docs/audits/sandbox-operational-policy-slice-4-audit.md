# Sandbox Operational Admission Policy — Slice 4 audit

## Decision

**COMPLETE / APPROVED**

Canonical Health now reports the required Sandbox policy boundary through neutral facts.
It distinguishes a ready policy/persistence boundary from unavailable real execution and
does not acquire lifecycle or authorization authority.

## Projection

Before startup the component is degraded and reports lifecycle `constructed`. After
startup it is ready when persistence, schema, policy identity, managed resources and
recovery facts are healthy. Metadata separately reports empty adapters, unavailable
materialization/supervision ports, unavailable isolation driver and unavailable real
execution. The summary never claims secure execution.

## Current gates

- focused Health, binding, policy, lifecycle and Health architecture selection:
  **29 passed**;
- Ruff on changed Health/bootstrap/test files: **passed**;
- Mypy on Health plus bootstrap: **passed on 37 files**;
- Health component baseline updated with the governed `sandbox.runtime` row.

## Next

Slice 5 performs the module's final security/freeze gates and reruns the affected Backend
Readiness decision using current evidence.
