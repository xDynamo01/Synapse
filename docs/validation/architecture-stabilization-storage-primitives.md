# Architecture Stabilization — Storage Primitives

Date: 2026-07-14. Status: controlled storage pilot complete; backend remains **NOT
READY**.

## Baseline and selection

The pre-edit inventory scanned 88 persistence-bearing Python files and consolidated
48 source-of-truth families into classifications A–F. It found seven relevant
atomic-write implementations and four specialized lock families, with inconsistent
schema, revision, pagination and recovery behavior. The complete matrix is in
`storage-inventory-before.json`.

MemoryStorage, WorkerRegistry, TaskAttemptRuntime and LocalNotificationProvider were
selected because they are operational, tested, hardware-independent and low risk.
Together they prove a single-file collection, per-record registry, nested revisioned
records, idempotency, restart, corruption handling and domain retention. Agent
identity/content, policies, raw artifacts, growing logs and DataDir maintenance were
excluded.

## Result

The neutral `synapse.storage` package supplies internal contracts, durable atomic
write, collection lock, sequential migrations, deterministic pagination,
checksums, configurable recovery/quarantine, retention dry-run and redacted neutral
events. It imports no domain or delivery layer and accepts only pre-resolved roots.

The four pilots preserve their public DTOs and exact legacy file-key shapes. Memory
still maps corruption/revision through MemoryError; Worker duplicate/not-found,
AttemptConflict and Notification NotFound remain domain errors. No API, Commands,
Health, Readiness, Context Fusion, Tools or Provider behavior was changed.

## Scale and SQLite decision

At 100 agents (200 file records), durable writes took 2.46 s, full two-page listing
1.74 s, first page after restart 57 ms and recovery scan 138 ms. At 500 agents
(1,000 files), writes took 14.56 s, full ten-page listing 7.69 s, first page 53 ms
and recovery scan 639 ms. Peak pagination memory remained below 1 MB. A denser
2,500-file write attempt exceeded 184 s.

These are non-gating workstation measurements. They support FileCollection for
small/bounded registries and SQLite evaluation for growing histories, query-heavy
stores, sustained concurrency or transaction needs. Exact results are in
`storage-scale-results.json`.

## Compatibility and validation

- before/after file key shapes: identical for all four pilots;
- public domain field shapes: identical;
- storage primitive tests cover CRUD, revision conflicts, deletion, pagination,
  invalid cursor, atomic failure, lock timeout/reentrancy, concurrency, schema,
  migration/failure, corruption, backup recovery, quarantine, restart, duplicate,
  retention dry-run/real, active/referenced preservation, paths and redacted events;
- symlink escape is tested where Windows permits symlink creation and otherwise
  explicitly skipped;
- 100/500-agent scale tests assert completeness and stable pagination without a
  machine-speed threshold.

Final evidence is recorded in `storage-primitives-after-metrics.json`: architecture
61/61; focused storage and pilots 96 passed/1 platform skip; acceptance 64/64;
global 1,077 passed/1 platform skip plus four subtests; frozen OpenAPI 425 paths,
471 operations and 100 schemas; Ruff and `git diff --check` passed.

## Preserved blockers

Remaining SCCs, legacy Agent Creator, DataDir maintenance endpoints and final
architecture audit remain open. No SQLite migration, SDK, frontend, commit, push or
pull request is part of this phase.
