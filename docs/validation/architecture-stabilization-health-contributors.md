# Architecture Stabilization — Health Contributors

Date: 2026-07-14

## Result

The 1,325-line domain-aware `HealthRuntime` was replaced by a neutral collector
and aggregator over one ordered registry and ten bounded-context contributors.
`ReadinessRuntime` now consumes a neutral snapshot protocol. Health, Readiness,
API, Commands and OpenAPI contracts remain equivalent.

The backend remains **NOT READY**.

## Baseline and equivalence

The pre-edit artifacts freeze 32 ordered component IDs, 82 summary fields,
states, dependencies, recommendations, metadata keys and ten controlled
scenarios. Before inversion, contributor exception and timeout were unsupported
and recorded as findings.

The after comparison is exact after redacting only timestamps, process IDs,
temporary paths and newly measured latency. Covered scenarios include the normal
system, optional provider not configured, required provider unavailable,
degraded domain, disabled feature, no camera, no GPU and no TTS. The new
exception/timeout behavior is additive only for previously unsupported failure
paths.

Artifacts:

- `health-surface-before.csv` and `health-surface-before.json`;
- `health-contributors-after-metrics.json`;
- unchanged `openapi-api-decomposition-after.json`.

## Architecture

`HealthRuntime` has zero concrete domain imports. `ReadinessRuntime` no longer
imports concrete Health. Contributors are read-only adapters without store,
delivery or bootstrap dependencies. Bootstrap registers Platform, Agents,
Delegation, Missions, Models, Voice, Perception, Tools, Context Fusion and
World contributors explicitly.

The largest SCC was reconstructed at 32 contexts/123 internal edges immediately
before inversion and is now 26 contexts/79 edges. The unrelated SCCs of four
contexts/six edges and two contexts/two edges remain unchanged.

## Metrics

| Metric | Before | After |
| --- | ---: | ---: |
| `health/runtime.py` lines | 1,325 | 229 |
| concrete domain imports in Health | 41 | 0 |
| concrete Health import in Readiness | 1 | 0 |
| contributor registries | 0 | 1 |
| contributors | 0 | 10 |
| component IDs | 32 | 32 |
| duplicate IDs | n/a | 0 |
| largest contributor | n/a | Platform, 96 lines |
| production timeout | none | 5 seconds |

Warm controlled collection remains approximately 255–300 ms; the ten-sample
after run averaged 441.815 ms because one cold system-insight sample took
1,631.023 ms. The pre-edit cold sample similarly took 1,607.134 ms.

## Failure isolation

Regression tests cover fast, slow, timed-out, exception, invalid result,
duplicate component ID, zero-component, optional-missing and repeated
contributors. Stack details are not exposed and correlation IDs are forwarded.

Validation evidence:

- architecture: 39 passed in 16.70 s;
- Health/Readiness/contributor isolation: 37 passed in 49.59 s;
- contributor domains: 337 passed plus 4 subtests in 188.73 s;
- acceptance: 64 passed in 26.69 s;
- global: 1,018 passed plus 4 subtests in 790.35 s;
- Ruff and `git diff --check`: passed.

## Preserved findings

- Agent Creator availability remains a compatibility fact.
- Readiness policy mapping is unchanged, not decomposed.
- DataDir maintenance endpoints are unchanged.
- Tools, Providers and Storage are not consolidated.
- No SDK/frontend was created and no commit, push or PR was performed.
