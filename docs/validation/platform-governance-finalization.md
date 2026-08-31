# Platform Governance Finalization

## Inventory and root cause

| Component | Responsibility | Failures | Proven cause | Consumers | Gap closed |
| --- | --- | ---: | --- | --- | --- |
| Effective policy | agent/tool bounds and generic decisions | 9 | stale fixtures wrote missing legacy agents | agents, tools, decisions, workers | canonical rules, precedence, revision/history |
| Observability | events, correlation and trace | 9 | fixtures omitted participating agents | all runtimes | canonical fields, spans, filters, metrics, redaction, retention |
| Health/readiness | aggregate operational state | 3 | expected agents absent from fixture | API, commands, mission supervision | ComponentHealth, dependency graph, diagnostics |
| Foundation | safe local persistence | 1 | fixture copied a null default agent | all persistence | atomic writes, DATA_DIR/config/temp diagnostics |
| UI contracts | UI DTO projection | 4 | stale UI fixture omitted agents | UI only | deliberately untouched by this domain |

The four domain fixtures now use explicit test-agent factories. Production seed
agents were not reintroduced. The frozen public contracts remain intact.

## Surfaces

Policy API supplies list/get/create/update/delete/evaluate/validate/history;
effective/explain use the same evaluation result. Observability supplies event
filtering/pagination, trace, metrics, errors, status, and cleanup. Health
supplies global, component/module snapshots, readiness, diagnostics, and the
dependency graph. Security exposes only a safe redaction self-test. Equivalent
commands delegate to the same runtimes; JSON is required for rule mutations.

Structured errors use the existing API error mapper with stable prefixes such
as `policy_not_found`, `policy_invalid`, and `policy_conflict`. Secret values and
absolute paths are not returned.

## Validation

- Initial isolated result: 26 failed, 28 passed.
- After fixture correction: 46 passed for policy, observability, health, and
  foundation.
- Canonical contract/API regression: 54 passed; OpenAPI 401 paths, zero
  duplicate operation IDs.
- Final transverse regression: 115 passed in 71.14s.
- Frozen-domain regression: 613 passed, 4 subtests passed in 304.49s.
- Final global: 987 passed, 4 failed, 4 subtests passed in 508.50s. The only
  failures are the unchanged external UI Contract fixture cases; policy,
  observability, health, and foundation have zero failures.
- OpenAPI: 403 paths and zero duplicate operation IDs. Ruff global and
  `git diff --check` are green (line-ending notices are non-errors).
- Status: **Implemented / Frozen**.
