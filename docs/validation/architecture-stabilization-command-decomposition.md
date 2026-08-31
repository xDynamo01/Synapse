# Architecture Stabilization — Command Decomposition

Date: 2026-07-14

## Result

The 6,077-line `CommandRuntime` monolith was decomposed into a 98-line public
facade/dispatcher, one registry and 14 bounded-context handlers. Bootstrap owns
explicit registration. API, Health, Tools, Providers, Storage, Agent Creator and
DataDir endpoint behavior were not redesigned.

The backend remains **NOT READY**.

## Frozen baseline and equivalence

The pre-edit source hash was
`5c8ce6379fa0e3ee89352e0d808818fbc16cc3f09bb7ba60b80e9da53133b923`.
The canonical snapshot records 339 branches, 363 accepted command names, 24
aliases, 327 domain/helper methods and 73 imports. For every branch it records
arguments/defaults, current operation, runtime dependencies, result/error shape,
policy/approval, idempotency/revision marker, category, destination and finding.

The registry comparison is exact for canonical names, aliases, argument names,
defaults, category, status and frozen source fingerprints. There are zero added
names, zero removed names and zero conflicts. Existing functional tests preserve
response shapes, error text, side effects, policy/approval, revision and
idempotency behavior.

Artifacts:

- `command-surface-before.csv` and `command-surface-before.json`;
- `command-decomposition-after-metrics.json`;
- `openapi-api-decomposition-after.json` (unchanged reference).

## Boundary enforcement

AST/import-graph tests require the facade to contain no domain handlers; block
store/storage, concrete provider, API and bootstrap imports from handlers; block
runtime construction and subprocess calls; block direct store/DataDir access;
require explicit registration and metadata for every handler; and prove unique,
baseline-equivalent names and aliases. The former Chat-to-Commands domain import
exception and both obsolete Commands infrastructure exceptions were removed.

Legacy memory/default-agent/DataDir state access is isolated behind five
transport forwards in `CommandServices`. This is not a new storage subsystem and
does not change the preserved DataDir maintenance finding.

## Metrics

| Metric | Before | After |
| --- | ---: | ---: |
| `commands/runtime.py` physical lines | 6,077 | 98 |
| domain/helper methods in facade | 327 | 0 |
| facade imports | 73 | 5 |
| handlers | 0 | 14 |
| registries | 0 | 1 |
| canonical branches | 339 | 339 |
| accepted names | 363 | 363 |
| aliases | 24 | 24 |
| duplicate names/aliases | n/a | 0 |
| direct handler store/DataDir accesses | 5 | 0 |

The largest handler is `agents_admin.py` at 745 lines; the average is 24.21
canonical branches per handler. File size alone is not a success gate.

## Validation evidence

- architecture: 32 passed in 13.03 s;
- command/domain files containing `commands.execute`: 73 files, 828 passed plus
  4 subtests in 467.14 s;
- OpenAPI: exact JSON equality, 425 paths, 471 operations, 100 schemas, SHA-256
  `bc0b2a3cab01aa9377bc80b50193089d288edd71901a9f650e3bd02ad48ea72f`.

- acceptance: 64 passed in 26.34 s;
- global: 1,004 passed plus 4 subtests in 513.32 s;
- Ruff: all checks passed;
- `git diff --check`: passed (line-ending warnings only).

## Preserved findings and next blockers

- Agent Creator cross-runtime mapping remains unchanged.
- DataDir maintenance behavior remains unchanged.
- Health contributor inversion is not addressed.
- Tools, Providers and Storage are not decomposed or consolidated.
- General domain cycles are not broken.
- No SDK or frontend was created.
- No command was added or removed.
- No commit, push or pull request was performed.
