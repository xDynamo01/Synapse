# Global Composition Root Slice 1 audit

Status: **COMPLETE / APPROVED**

Profile: `bounded-context-change`

Authority: explicit user authorization for Global Composition Root Slice 1

Global status: **Backend NOT READY**

## Objective

Create the canonical binding inventory and readiness contract discovered by the
preceding analysis-only slice, without production activation or changes to frozen
bounded-context behavior.

## Delivered contract

`synapse.bootstrap.bindings` defines immutable typed declarations for the nine frozen
backend contexts relevant to global readiness. Requirement, availability, current
binding mode, composition reference and activation authority remain separate facts.

The canonical application publishes the tuple as inert bootstrap metadata. It does
not import a local composition package, add a lifecycle resource, perform I/O, select
a provider or authorize execution.

| Binding | Requirement | Availability | Current mode |
| --- | --- | --- | --- |
| Private Evals | required | available | local opt-in |
| Coding Sessions | required | available | local opt-in |
| Skills Runtime Phase 2 | required | available | legacy global only |
| Sandbox Execution Boundary | required | available | local opt-in |
| Concrete Sandbox Driver | intentionally optional | capability-limited | local opt-in |
| Repository Runtime | required | available | local opt-in |
| Voice / Audio / Perception | intentionally optional | capability-limited | legacy global only |
| Search Runtime | intentionally optional | capability-limited | local opt-in |
| Deployment Runtime | required | unavailable | absent |

All entries retain `activation_authority=not-authorized`. Six required entries remain
global-readiness blockers because none has a canonical `global` binding in this slice.

## Preserved invariants

- inventory is not activation;
- local composition is not global composition;
- legacy global runtime is not the frozen replacement composition;
- capability-limited is not available-with-hidden-fallback;
- required binding absence blocks readiness;
- optional binding limitation does not become a global readiness claim;
- Backend remains NOT READY.

## Gates executed now

- focused Global Binding Inventory tests: **4 passed**;
- focused inventory, composition and lifecycle selection: **16 passed**;
- Voice freeze regressions after declarative-reference correction: **6 passed**;
- architecture suite: **262 passed**;
- repository backend/tests Ruff: **passed**;
- focused source Mypy: **passed**;
- authoritative Mypy on `backend/synapse`: **759 source files, zero issues**;
- test-only Mypy selection: **failed** on the pre-existing unannotated
  `tests/architecture/support.py:adjacency`; no source suppression or baseline change
  was applied;
- global regression: **not executed** because this is a structural metadata contract,
  not a critical schema/persistence/security change;
- diff integrity: executed separately after documentation finalization.

## Decision

Slice 1 is approved. Slice transitions inside Global Composition Root continue
automatically after validation. Slice 2 is governed as the explicit, inert Deployment
composition surface; it does not authorize global startup activation or batch wiring.
