# Electron ADE Operational Foundation — Slice 1

> Historical/superseded: the Electron ADE implementation and release artifacts were removed under ADR 0119 on 2026-08-21. This file is retained as historical evidence only, not active frontend architecture.

## 1. Estado encontrado

- `apps/electron-ade/` did not exist; no frontend implementation was active.
- ADR 0115 had already selected Electron + TypeScript, no SPA framework, Dockview later,
  isolated preload and API modules.
- The former React/Tauri client and backend UI/App Shell projections were deliberately
  removed. Recreating layout/navigation contracts in the backend is prohibited.
- The supplied Presence and Swarm images are visual references only. Their displayed
  counts, labels, topology and status are not accepted as backend facts.

## 2. Contratos reutilizados

| Need | Existing authority |
| --- | --- |
| Generic operational envelope, correlation, severity, status | `core.events.Event` |
| Diagnostic event query and trace | `GET /events`, `GET /trace/{correlation_id}` |
| Project identity and lifecycle | `project_governance.ProjectManifest`, `/projects` |
| Project RFC/plan context | `/projects/{project_id}/context` |
| Agent lifecycle and presence | Agents runtime, presence and emitted agent events |
| Workers and swarm | Worker registry/runtime, Swarm runtime and events |
| Missions/tasks/recovery | Mission APIs, trace, attempts and recovery history |
| Tool activity | Tool runtime events and execution contracts |
| Memory/context | Memory events, Context Fusion facts and resource references |
| Approvals | Approval manager events and status APIs |
| Private Evals | Frozen eval run/read projections and Health contributor |
| Voice presentation state | `VoiceFrontendEvent`, stream and snapshot |
| Global operational status | Health, Readiness and binding inventory |

Existing event names already cover creation, activation, registration, start/completion,
failure, cancellation, communication, approvals, tool execution, context fusion, missions,
workers, swarm and Voice. No duplicate visual event vocabulary was added.

## 3. Gaps identificados

1. Generic Event payloads are heterogeneous and not a minimized stable UI contract.
2. `/events` has offset/limit over a tail, not a durable project cursor or live stream.
3. Most events do not carry an enforced canonical `project_id`.
4. No read model joins agents, workers, tasks, tools, resources and relations by project.
5. Unknown, degraded, revision-gap and resync behavior lacks one frontend-facing contract.
6. Project presentation layout persistence does not exist.
7. There is no GPU scene adapter, performance budget or reduced-motion implementation.
8. Inspector summaries need safe metadata projection instead of raw event payloads.

## 4. Arquitetura proposta

ADR 0117 defines five layers: backend facts, operational projection, transport, frontend
application state and visualization adapter/GPU scene. Presence and Swarm share the same
application state. HTTP supplies snapshots/commands; SSE is the recommended future event
feed after cursor and minimization contracts exist; polling is degraded fallback only.

## 5. Impacto backend

No backend file changed in Slice 1. The minimum future addition is a client-neutral,
project-scoped operational projection with read ports, snapshot revision, cursor events,
redaction/minimization and explicit unknown/degraded state. It must not alter frozen domain
contexts or import presentation terminology.

## 6. Arquitetura frontend

The foundation introduces project-scoped application state, operational entity/relation
types, modular panel references and a contextual slash-command registry. Electron main,
preload, API transport, Dockview and GPU rendering remain later slices. No fake runtime
activity is included.

## 7. Contratos/eventos adicionados ou propostos

Implemented client contract shapes: `project-activity-snapshot-v1` and
`project-activity-event-v1`. They are consumption boundaries, not yet backend transport
contracts. Proposed backend vocabulary should normalize existing canonical events rather
than mint duplicates. Voice continues to use its existing frontend event contract.

## 8. Arquivos alterados

- `apps/electron-ade/AGENTS.md`
- `apps/electron-ade/package.json`
- `apps/electron-ade/src/contracts/operational.ts`
- `apps/electron-ade/src/renderer/state/workspace.ts`
- `apps/electron-ade/src/renderer/commands/registry.ts`
- `apps/electron-ade/tests/workspace.test.ts`
- `docs/adr/0117-frontend-operational-projection-and-command-first-ade.md`
- this validation record and the operational roadmap

## 9. Testes executados

`npm test` with Node 24 native TypeScript stripping: **4 passed, 0 failed**.

Focused backend/client-boundary regression (`test_client_contract_cleanup`, domain
independence, dependency rules and audio/speech boundary): **17 passed, 0 failed**.

`git diff --check`: passed with only pre-existing line-ending warnings. No frontend
`node_modules`, lockfile, staged file, dependency installation, commit or push exists.

## 10. Evidências

Tests prove cross-project rejection, stale-revision rejection, panel/agent lifecycle
separation and contextual `/` discovery. The package has no runtime or development
dependency and no lockfile was generated.

## 11. Riscos restantes

- Project linkage for legacy/global events is incomplete.
- A projection could accidentally become a second domain model if its read-only authority
  and source references are not enforced.
- SSE replay requires durable cursors and bounded retention semantics.
- GPU library selection remains intentionally open pending a measured prototype.
- Electron/Dockview/Monaco/xterm supply-chain review is still required before install.

## 12. Próximo slice recomendado

Govern and implement the backend `operational_projection` foundation as pure contracts and
deterministic reducers over typed source facts. Define project scope, revisions, safe
metadata and degradation semantics first. Do not add transport, bootstrap wiring or GPU UI
in that slice.

## Acceptance status

Slice 1 satisfies the foundational criteria for project isolation, command descriptions,
panel lifecycle separation and factual state consumption. The visual shell, draggable
panels, Presence, Swarm, Inspector, Voice integration, reduced-motion and transport remain
**NOT IMPLEMENTED** and must not be inferred from the reference images.
