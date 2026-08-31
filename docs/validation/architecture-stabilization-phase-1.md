# Architecture Stabilization — Phase 1 validation

Date: 2026-07-14
Worktree: `backend-freeze-cleanup`
Status: **Phase 1 complete; architecture remains NOT READY**

## Starting audit

The interrupted work had thin `core/app.py` and `core/model_router.py` adapters,
one container definition, lazy FastAPI lifespan construction, initial AST
guardrails and a capable LifecycleManager. It was partial: the 819-line
`bootstrap/application.py` was the old monolith transferred, with only three
builders. Lifecycle registration was passive (an event callback and close-only
wrappers for resources it never started). Existing green tests missed both.

There was one container construction path, not two, but it remained monolithic.
`main.py` had no parallel composition and import did not build the application.

## Result and metrics

| Metric | Before | Final |
| --- | ---: | ---: |
| `core/app.py` lines | 191 | 10 |
| `bootstrap/application.py` lines | 819 | 262 |
| feature builders | 3 | 9 |
| functional-domain imports from neutral core | 29 in old root | 0, adapters excluded |
| complete container construction points | 1 in core | 1 in bootstrap |
| cyclic SCCs | 3: 157 / 6 / 2 edges | unchanged |
| real lifecycle resources | 0 | 1 (`agent-loop`) |
| measured runtime/facade container fields | not recorded | 90 |

Temporary-root measurements: construction 184.81 ms, startup 9.37 ms and
shutdown 9.41 ms. These are observations, not performance guarantees.

Commands/API were not decomposed; Tools, Providers and Storage internals were
not changed. FastAPI lifespan owns build/start/close and compatibility adapters
remain minimal.

## Functional equivalence

Frozen OpenAPI: 425 paths, 471 operations, 471 unique operation IDs and 100
schemas; zero duplicate method/path pairs. Settings retain five fields, the
built-in provider registry seven manifests, and a clean runtime zero queued
jobs. The global suite covers Commands, health/readiness, scheduler, daemon,
Agent Loop, Voice, Desktop Automation, providers and all routers. No facade or
route disappeared.

## Validation evidence

1. initial scoped Ruff: passed;
2. initial architecture: 17 passed in 14.71 s;
3. final architecture: 18 passed in 11.72 s;
4. bootstrap/lifecycle/affected runtimes: 47 passed in 57.79 s;
5. acceptance: 64 passed in 28.98 s;
6. global pytest: 990 collected, 990 passed, 0 failed, 0 skipped, 0 subtests,
   527.93 s (8:47);
7. global Ruff: passed;
8. `git diff --check`: passed (line-ending notices only).

## Core classification

| Modules | Classification |
| --- | --- |
| `config`, `data_dir`, `events`, `exceptions`, `permissions`, `serialization` | neutral foundation |
| `app`, `model_router`, `__init__` | documented compatibility adapters |
| domain or obsolete core code | none identified in Phase 1 |

## Remaining blockers

The three SCC baselines, total Commands facade, broad Health/Context Fusion
knowledge, dual tool concepts, provider taxonomy and repeated storage primitives
remain. Exact legacy exceptions are frozen by tests. Phase 2 requires separate
authorization; the backend is not marked READY.
