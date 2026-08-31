# Tool Execution Boundary Stabilization — Validation

Date: 2026-07-14
State: **Complete / NOT READY**

## Baseline

The controlled baseline is `tool-execution-paths-before.json`. It recorded two public
registries, four operational execution authorities, ten public runtime IDs in test
mode, eight legacy builtin IDs, and direct Desktop paths from Agent Loop, Missions,
API, and Commands. Generic timeout, restart restoration, and verification were
incomplete.

## Result

There is now one public descriptor catalog and one operational authority.
`ToolRegistry.execute`, direct Desktop consumer execution, and MCP consumer execution
were removed from product call paths. Builtin, MCP, and Desktop technology calls are
explicit adapters registered into `ToolRuntime`. Agent/Chat routing, approval resume,
Agent Loop, Missions, API, Commands, discovery, and intent execution converge on the
same port. The legacy router preserves old DTOs/events while delegating execution.

The canonical runtime restores idempotency/results/verification from redacted
history, enforces timeout, exposes validation and execution listing, records
verification, represents active state, and coordinates supported cancellation.

## Compatibility and guardrails

- Frozen public test-mode catalog: 10 IDs before and after.
- Legacy builtin catalog: 8 IDs before and after, now hidden compatibility descriptors.
- Desktop internal descriptors: 4; excluded from public discovery.
- MCP identity convention unchanged.

AST tests enforce one bootstrap registry/executor, descriptor-only registry behavior,
no direct MCP/Desktop execution or concrete adapter imports from consumers, and
governance-free technology adapters. Functional tests cover catalog, legacy facade,
conflicting IDs, timeout, active/idempotent cancellation, restart idempotency,
history, verification, and redaction, complementing existing tool/MCP/Desktop suites.

The API and Commands changed only in internal Desktop wiring. Health, Readiness,
Context Fusion, Storage, general providers, Agent Creator, and DataDir maintenance
were not modified. Exact final measurements are in
`tool-execution-boundary-after-metrics.json`. The backend remains **NOT READY**.

## Final gates

- Architecture: 52 passed.
- Tools/execution/Approval/MCP selection: 116 passed.
- Frozen API/Commands/Health/Readiness/Context Fusion selection: 85 passed.
- Final boundary and consumer selection: 143 passed.
- Global: 1,050 collected and passed, zero failed/skipped, plus the four preserved
  unittest subtests; 535.63 seconds.
- OpenAPI: exact 425 paths, 471 operations/unique IDs, 100 schemas, SHA-256
  `bc0b2a3cab01aa9377bc80b50193089d288edd71901a9f650e3bd02ad48ea72f`.
- Ruff and `git diff --check`: passed.
- No commit, push, or pull request was performed.
