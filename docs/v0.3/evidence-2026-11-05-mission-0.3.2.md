# Mission 0.3.2 corrective evidence — 2026-11-05

## Scope

Resolve FND-031-001 without reducing the eight-round inner agent tool budget,
then close any directly exposed concurrency defect required for a green global
regression. No SCC refactor or operational-readiness claim is included.

## Red/green evidence

1. Swarm acceptance RED: the tightened expectation required six model calls
   across two default agents and exactly two verifier-feedback calls; the old
   path produced eight calls.
2. Swarm acceptance GREEN: `WorkerRuntime` now stops outer verification when
   feedback produces no new tool receipt request IDs. The exact scenario and
   the complete seven-test project-tools acceptance file pass.
3. Concurrency RED: a barrier-controlled test made two identical tool inputs
   observe the same asset as absent; one execution failed with a boundary
   conflict.
4. Concurrency GREEN: the Intelligence Boundary now owns idempotent asset
   creation. Both executions succeed and exactly one deterministic tool-input
   asset exists.

## Fresh gates

| Gate | Result |
|---|---|
| Corrected Swarm acceptance scenario | PASS |
| Complete project-tools acceptance file | 7 passed |
| Integrated worker/Swarm/tool/boundary selection | 81 passed, 1 known warning |
| Architecture suite | 274 passed, 1 known warning, 141.47s |
| Ruff on changed Python files | PASS |
| Mypy on changed production files | PASS |
| Full Python suite | 4,689 passed, 5 skipped, 1 warning, 4 subtests passed, 2,011.75s |
| Frontend Vitest | 16 files, 142 tests passed |
| Frontend production build | PASS |

The sole warning is the pre-existing Starlette `httpx` test-client deprecation.
The first global run failed only on the newly exposed concurrent boundary race;
after its test-first correction, the final global run completed with exit code
zero.

## Evidence limits

- Tests use controlled composition and do not prove a real local model or real
  project-file Swarm run.
- Packaged Electron boot, restart/recovery, devices, providers and Windows
  reboot remain unvalidated.
- The backend therefore remains globally `NOT READY`.
