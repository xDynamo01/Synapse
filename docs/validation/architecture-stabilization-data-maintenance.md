# Architecture Stabilization — Administrative Data Maintenance

Date: 2026-07-14

Result: **Implemented / NOT READY**.

## Outcome

The administrative DataDir surface now has one contributor-owned coordinator.
The unsafe Foundation adapter and three generic destructive API/Command paths
were removed. API and Commands have zero direct `DataDir` access and zero
filesystem mutation calls. Four proven contributors are registered: Foundation
inspection, configuration validation, known temporary files and existing
Retention delegation.

Plans are durable, checksummed, revisioned and expiring. Execution is permission,
policy and confirmation gated; high-risk plans are approval-bound. Results are
incrementally persisted, terminal retries are idempotent, one lock serializes
work, and restart recovery never automatically performs cleanup. Unknown,
recent, symlinked, external and traversal candidates are preserved/rejected.

## Surface delta

- OpenAPI: 438→443 paths, 485→490 operations, 103→107 schemas; all 490
  operation IDs are unique.
- Commands: 351→356 canonical commands; 380 registered names including the
  unchanged 24 aliases.
- Delivery removals: Foundation cleanup-temp, Retention domain cleanup and
  Retention cleanup-all in both HTTP and Commands.
- Canonical additions: eight `/api/maintenance/*` operations and eight
  `/maintenance-*` commands.

The frozen command CSV was updated through the artifact workbook flow and
rendered for visual verification. Exact metrics are in
`data-maintenance-after-metrics.json`; the pre-edit matrix remains in
`data-maintenance-surface-before.json`.

## Validation

- Architecture: 83 passed.
- DataDir/Foundation/Storage/Maintenance: 37 passed, 2 skipped.
- Changed API/Commands: 27 passed.
- Acceptance: 73 passed.
- Global: 1,125 collected; 1,123 passed; 2 skipped; zero failed; 4 subtests
  passed; 623.03 seconds.
- Repository-wide Ruff and `git diff --check`: passed. Git reported only the
  pre-existing Windows line-ending conversion warnings.

Measured mean inspection was 13.516 ms, mean plan creation 42.190 ms, and
restart reconciliation 130.060 ms on the local validation environment. This
phase does not claim global backup/restore, storage migration or release
readiness.
