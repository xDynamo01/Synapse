# Skills Runtime Phase 1 finalization

Date: **2026-07-15**

## Result

Skills Runtime Phase 1 is **Implemented / Frozen**. SOUL, ROLE, SKILL and TOOL
have distinct ownership. The domain provides canonical manifests and packages,
registry, metadata discovery, deterministic resolver, progressive loader,
validation, resources, assignments, leases, version/status persistence,
structured errors, controlled installation/removal and script execution port.

## Architecture

`skills` is a new bounded context outside the global SCC. Its runtime depends
on neutral storage and script ports; bootstrap binds Storage Primitives and
ToolExecutionPort. Context Loader and Ephemeral Agents import contracts only.
Primary bootstrap receives summaries rather than instruction bodies. API and
Commands are thin delivery adapters and Skills imports neither.

Graph: 69 -> 70 contexts, 247 -> 252 governed edges, one SCC unchanged at
13 contexts / 35 internal edges, zero exact-module SCCs.

## Package and resolution behavior

Packages require `SKILL.md` and `manifest.yaml`, safe relative paths, stable ID,
explicit SemVer and checksums. Discovery is metadata-only. Resolution explains
explicit/automatic selection, resolves dependency DAGs, rejects cycles and
critical conflicts, reports unavailable requirements and enforces context
budgets. Loading is progressive and never executes scripts.

## Agents and execution safety

Persistent agents use revisioned assignments. Ephemeral agents receive leases
bounded by mission/task, expiry, context budget, resources, scripts and the
intersection of required and already-allowed tools. Cleanup deletes leases.
Skills never grant permissions, autonomy, tools or memory. Script execution is
possible only through the canonical Tool boundary with preview/approval data;
no shell/subprocess execution exists in Skills.

## Migration pilot

Researcher is the only pilot. Its original `SKILLS.md` remains unchanged.
`CONFIG.yaml` preserves legacy labels and adds an assignment to the shared
`research-synthesis@^1.0.0` package. No package content is copied into the agent
directory and no other seeded agent was migrated.

## Controlled surfaces

Skills adds 17 paths / 18 operations and three transport schemas, producing
OpenAPI 460 paths / 508 unique operations / 110 schemas. It adds 16 canonical
commands and one optional Health contributor. Direct script execution, force
lease, bypass validation and arbitrary context injection remain internal-only.

## Validation

- focused Skills functional + boundary + installation E2E: 22 passed;
- seven named Skills Runtime acceptance scenarios: 7 passed;
- agent identity/registry/primary/skills regression: 30 passed;
- architecture suite: 97 passed after advancing intentional API, Commands,
  Health, builder and OpenAPI baselines;
- global pytest: 1,157 collected; 1,155 passed; 2 skipped; 0 failed in
  665.08 s. An earlier global run had one timing-sensitive Voice retention
  failure; its isolated rerun and three subsequent global runs passed without a
  production change;
- complete ruff: passed;
- `git diff --check`: passed with pre-existing LF-to-CRLF warnings only;
- OpenAPI canonical SHA-256:
  `7086dec41eb4cfb8d0a7269bd1b912b2230f81681aa1c0dde0b646e02790811e`.

## Explicit exclusions

No automatic skill generation/modification/promotion, evolutionary benchmark,
semantic deduplication, swarm evolution, script autoediting, Workspace Runtime,
Repository/Git Runtime, SDK, frontend or Electron work was added. Agent
Templates remain absent. Phase 2 was not started.

No commit, push or pull request was created. The backend remains **NOT READY**.
