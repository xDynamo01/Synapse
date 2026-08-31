# ADR 0117 — Frontend Operational Projection and Command-first ADE

> Historical/superseded: the Electron ADE implementation and release artifacts were removed under ADR 0119 on 2026-08-21. This file is retained as historical evidence only, not active frontend architecture.

Status: accepted

## Context

ADR 0115 selected Electron, TypeScript without an SPA framework, Dockview, Monaco and
xterm.js for a clean V3 client. The backend is now a stabilized baseline with durable
domain events, resource APIs, project governance and a Voice frontend event contract.

The new experience must support a quiet command-first ADE, project-scoped workspaces,
modular panels, Presence and Swarm views without moving visual concepts into backend
contracts or exposing private model reasoning.

## Decision

Retain the technology and process boundaries from ADR 0115. Replace its permanent
Activity Bar/Sidebar-first product direction and fake-data-first integration order with:

```text
Domain/System State
  -> Operational Events and Read Models
  -> Frontend-facing Project Activity Projection
  -> Frontend Application State
  -> Visualization Adapter
  -> GPU Scene State
```

The primary interaction surface is a conversation/command field. `/` opens a contextual
palette. Navigation chrome is transient or contextual; no permanent command sidebar is
required. Panels remain Dockview modules opened through commands and direct inspection.

### Authority boundaries

- Backend owns operational facts, revisions, project scope, authorization and recovery.
- The projection layer owns minimization and normalization, never domain authority.
- Frontend state owns selected project, open panels, layout and view preferences.
- Visualization owns role-to-color and state-to-motion mappings only.
- Closing a panel never stops an agent, worker, mission or tool execution.
- Presence and Swarm are adapters over the same project activity state.
- No layer persists or transmits chain-of-thought for presentation.

### Project identity

`project_governance.ProjectManifest.project_id` is the canonical project identity.
Coding-session workspace/worktree references and Primary Agent `workspace_id` remain
separate identities and are linked by explicit references; they are not aliases.

Presentation persistence is keyed by project ID and schema version. Inactive projects are
represented compactly. Data from one project is rejected by another project's store.

### Operational projection

Add a future backend-owned, client-neutral `operational_projection` read model only after
its input adapters and authority are governed. It will consume existing facts through
read ports or the composition root and expose:

- versioned project snapshot with monotonic revision;
- versioned, cursor-addressable project activity events;
- semantic entities and relations;
- safe resource counts/references rather than raw context;
- explicit degraded/unknown state and reconciliation markers.

It will not expose colors, coordinates, particles, animation, layout, prompts, secrets,
raw context or model reasoning.

### Transport

Use ordinary HTTP for snapshot and commands. After the projection contract is stable,
prefer SSE for the unidirectional activity feed because client commands already use HTTP
and no bidirectional socket semantics are required. The existing `/events` query can
support bounded diagnostic polling during development, but it is not the final feed:
offset over a tailed JSONL log is not a durable project cursor and its generic payload is
too broad for a minimized frontend contract.

SSE clients reconnect with the last accepted cursor, then refresh the snapshot when the
cursor is unavailable or a revision gap is detected. Polling is an explicit degraded
fallback. WebSocket remains unselected unless a later requirement proves bidirectional
streaming is necessary.

### Rendering

Renderer components observe application state; they do not own particles. A visualization
adapter derives a bounded `SceneState` for a WebGL/WebGPU renderer. Role selects palette,
activity selects motion, exceptional state selects halo and summarized magnitude selects
density. These mappings are frontend design tokens.

The adapter enforces budgets by node count, frame focus, reduced-motion preference and
measured capability. Large worker sets aggregate by role/parent and expand on drill-down.
The operational model remains complete even when scene complexity is reduced.

## First safe slice

Create a dependency-free TypeScript foundation under `apps/electron-ade/` containing:

- client-side project activity contract shape;
- project-scoped application store with monotonic revision handling;
- panel state independent from operational state;
- contextual slash-command registry;
- tests for scope, stale data, lifecycle separation and command discovery.

Do not add Electron, Dockview, GPU libraries, network transport, fixtures or backend code.

## Consequences

The visual references remain direction, not factual data or backend contracts. UI work can
start against explicit interfaces while the backend projection is governed independently.
The first visible shell waits until project selection, projection behavior and degradation
semantics are testable. ADR 0115 remains authoritative for Electron security and the
no-framework stack; this ADR supersedes its permanent IDE-navigation and fake-data-first
product assumptions.
