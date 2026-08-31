# Global Composition Root Slice 2 audit

Status: **COMPLETE / APPROVED**

Global status: **Backend NOT READY**

## Objective

Add the missing Deployment composition surface as explicit local construction without
global bootstrap activation.

## Result

`synapse.deployment_composition` owns typed config/dependencies, inert build, explicit
start/close, managed-resource rollback and factual health. SQLite persistence and
fencing are initialized only by `start()`. Apply, verification and rollback are wired
only when their entire dependency group is present; partial groups fail closed.

Deployment changed in the canonical inventory from `absent/unavailable` to
`local-opt-in/available`. Activation authority remains `not-authorized`, so the binding
continues to block global readiness.

## Governed edges

- `deployment_composition -> deployment`;
- `deployment_composition -> deployment_adapters`;
- `deployment_composition -> deployment_integrations`.

Runtime/source graph baselines changed from 298/333 to 301/336 with no new SCC.

## Gates executed now

- focused composition/inventory/freeze selection: **24 passed**;
- architecture suite: **265 passed**;
- Ruff global backend/tests: **passed**;
- focused Mypy: **passed**;
- authoritative Mypy: **761 source files, zero issues**;
- global regression: **not executed**; no domain/schema migration or global activation;
- diff integrity: pending final module-turn review.

## Decision

Slice 2 is approved. Slice 3 proceeds automatically with inert registration of the
Deployment runtime in the canonical container; lifecycle activation remains a later,
separately validated slice of the same module.
