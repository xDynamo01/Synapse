# Mission 0.3.1 — Full System Inventory plan

Status: `EXECUTED_WITH_OPEN_FINDINGS` on 2026-11-05. Outputs are indexed in
[Mission 0.3.1 status](mission-0.3.1-status.md).

## Goal and non-goals

Produce a code-grounded inventory of every material Synapse capability,
integration and visible product flow. Do not refactor Swarm, Memory, Tools or any
other runtime subsystem in this mission.

## Investigation order

1. **Entrypoints and build graph** — Python entrypoints, Electron main/preload/
   renderer, sidecar/build/package scripts and supported runnable artifacts.
2. **Composition roots** — bootstrap features/adapters, API router registry,
   frontend boundary and provider/tool/skill registrations.
3. **Contracts and dependency graph** — ports, schemas, events, imports, ownership,
   SCCs and architecture-test constraints.
4. **Persistence and governed state** — databases, migrations, restore formats,
   journals, immutable identities and runtime-local data.
5. **Execution capabilities** — agents, planner, missions, scheduler, workers,
   Swarm, MoM, tools/MCP, decisions and approvals.
6. **Knowledge and intelligence** — memory, RAG/search, context fusion, project
   knowledge, private evals and model/provider routing.
7. **Multimodal/product paths** — frontend controls, voice/audio/speech,
   perception/vision, presence, notifications and desktop automation.
8. **Operational surfaces** — security, sandbox, health/readiness, observability,
   build, packaging, recovery and resource pressure.
9. **Tests and documents** — map every claim/test/doc to capabilities and current
   evidence; flag orphaned or contradictory material.

## Required outputs

- capability catalogue with stable `CAP` IDs;
- bounded-context and ownership map;
- ports/adapters/contracts catalogue;
- composition-root and initialization map;
- producer -> contract -> consumer integration matrix;
- frontend control -> transport -> runtime consumer trace;
- tool/capability catalogue with permission and receipt semantics;
- persistence/state/recovery catalogue;
- test/evidence coverage matrix;
- orphan, duplicate, stub, mock-in-production and incomplete-implementation list;
- operational-validation backlog for Mission 0.3.2.

## Per-item classification

Each item records confirmed facts, hypotheses and unknowns separately, then uses
the definitions in `evidence-policy.md`: `IMPLEMENTED`, `INTEGRATED`, `TESTED`,
`VALIDATED`, or `OPERATIONAL`. The associated execution result is `PASS`, `FAIL`,
`BLOCKED`, or `NOT RUN`.

## Search and trace method

1. Locate public symbol/contract and owning context.
2. Find its concrete implementations and imports.
3. Find registrations/composition wiring.
4. Find all producers and consumers.
5. Trace normal, denial, cancellation, failure and recovery paths.
6. Identify static/unit/integration/E2E/operational tests and their actual layer.
7. Compare current docs to code; never use a document alone to prove wiring.

## Coverage and completion criteria

- Every material directory under `backend/synapse` is classified or explicitly
  excluded with reason.
- Every Electron-visible control and route is traced to its final real consumer.
- Every declared adapter has registration evidence or an orphan finding.
- Every port/interface has a consumer or a documented gap.
- Every persisted schema/state has owner, lifecycle and recovery status.
- Every capability has test-layer and operational-evidence status.
- Architecture and integration matrices have no unexplained node or edge.
- No operational claim rests only on code presence, mocks, static checks or LLM
  output.

## Gates

- Inventory scripts are read-only and write outputs only under `artifacts/reports`
  or approved documentation paths.
- Findings are reviewed against architecture tests and actual composition roots.
- A second pass samples every capability class and all high-risk boundaries.
- `git diff --check`, link/path checks and documentation review close the mission.
