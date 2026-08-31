# Architecture Stabilization — API decomposition

Date: 2026-07-14
Status: **API decomposition complete; backend remains NOT READY**

## Baseline and traceability

Before movement, the full 471-row route matrix was closed in
`api-route-matrix-before.csv`. The serialized baseline is
`openapi-api-decomposition-before.json`; its normalized SHA-256 is
`bc0b2a3cab01aa9377bc80b50193089d288edd71901a9f650e3bd02ad48ea72f`.
The after matrix, snapshot and metric JSON are stored beside this report.

Baseline: 6,371 lines in `api/routes.py`, four APIRouter objects, 417 handlers
and 90 DTOs in the central file, plus 54 operations already separated across
System, World/Attention/Loop and Desktop Automation. The audit recorded 24
central imports, 10 central helpers and 12 known non-transport responsibilities.

## Metrics

| Metric | Before | After |
| --- | ---: | ---: |
| `api/routes.py` lines | 6,371 | 8 |
| bounded-context routers | 3 | 13 |
| registration points | mixed central includes | 1 |
| handlers in bounded routers | 54 | 471 |
| handlers in `api/routes.py` | 417 | 0 |
| central DTOs | 90 | 0 |
| router-local helpers | 4 including admin guard | 3 DTO mappers |
| shared transport helpers | 2 | 4 |
| known business/storage logic in routers | 12 | 0 |
| largest router | n/a | Missions, 1,307 lines / 103 operations |
| average router size | n/a | 513.08 lines |
| paths / operations / schemas | 425 / 471 / 100 | 425 / 471 / 100 |
| duplicate operation IDs | 0 | 0 |
| duplicate method/path pairs | 0 | 0 |
| tags | 0 | 0 |
| declared response codes | 471 × 200; 354 × 422 | unchanged |

Imports, DTO counts, helpers and lines for every router are recorded in
`api-decomposition-after-metrics.json`.

## OpenAPI equivalence

The complete before/after objects are structurally equal, not merely equal by
counts. Paths, methods, operation IDs, parameters, request bodies, responses,
schemas, required fields, enums, status codes, tags and security metadata are
identical. Both normalized snapshots have the same SHA-256 shown above.

## Functional preservation

Handlers retain their original function bodies and call the same container
facades. Policy, approval, idempotency, revision checks, pagination and error
mapping remain unchanged. The only ownership corrections were:

- proactive policy persistence moved from the router to the existing
  `AttentionDecisionRuntime`;
- optional agent voice-profile resolution moved to the existing `VoiceRuntime`.

No endpoints or functionality were added or removed. Commands were not
decomposed. Health, Tools, Providers and Storage were not changed.

## Validation

1. architecture: 25 passed in 11.06 s;
2. API regression: 74 modules, 814 passed and 4 subtests passed in 457.82 s;
3. acceptance: 64 passed in 25.05 s;
4. global: 997 collected, 997 passed, 0 failed, 0 skipped, 507.28 s (8:27);
5. Ruff global: passed;
6. `git diff --check`: passed, with only existing LF/CRLF notices;
7. OpenAPI: exact structural equality, 425 paths, 471 operations, 100 schemas,
   zero duplicate IDs and zero duplicate method/path pairs.

## Remaining blockers

The Agent Creator and foundation maintenance compatibility adapters remain
explicit findings. The pre-existing SCCs, Commands decomposition, Health
contributor inversion, tool/provider consolidation and storage primitives also
remain. The backend is explicitly **NOT READY**.
