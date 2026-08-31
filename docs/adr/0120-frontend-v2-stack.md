# ADR 0120 — Frontend V2 desktop stack

Status: `ACCEPTED FOR FRONTEND V2 PLANNING / NO DEPENDENCIES INSTALLED`

Date: 2026-08-21

## Context

The previous Electron ADE frontend was intentionally retired and must not be restored as the baseline. Synapse now needs a clean local-first desktop frontend centered on Presence, Conversation Log, first-run first-agent onboarding, voice/text shared history, Activity/Constellation, Insight, commands, notifications, and governed attachments.

The backend is Python-based and already exposes many HTTP, NDJSON, and SSE contracts for agents, primary agent selection, models/providers, conversations, voice, operational projection, system insight, tools, approvals, and notifications. The frontend must consume facts through explicit contracts and must not simulate operational state.

## Decision

Use this stack for the first frontend rebuild plan:

- Desktop shell: Electron.
- UI: React + TypeScript.
- Build/dev: Vite.
- Visualization: PixiJS for Presence and Activity/Constellation.
- State management: minimal local application state first; add a small external store only when implementation slices prove the need.
- Data fetching: explicit typed client over backend contracts first; avoid adding React Query until caching/invalidation complexity is proven.
- Layout: custom shell/panels first; avoid Dockview until persistent multi-pane docking is a proven product requirement.

No dependency is installed by this ADR.

## Alternatives considered

### Tauri 2

Benefits:

- smaller application footprint;
- narrower native shell by default;
- strong Rust-side command model.

Costs for Synapse now:

- adds Rust command/runtime layer while the backend is Python-first;
- increases sidecar, Windows debugging, packaging, and audio/device integration complexity;
- less direct fit for the existing local backend and streaming contracts;
- raises implementation cost before the product shell is validated.

Decision: not selected for the first rebuild. Revisit if application size or attack surface becomes a dominant release constraint.

### React alternatives

Solid, Svelte, Vue, and custom DOM rendering were considered.

React + TypeScript is selected because:

- mature desktop/Electron ecosystem;
- strong testing and typing support;
- suitable for a stateful workspace with panels, streams, commands, forms, and visual adapters;
- lower hiring/maintenance risk.

Alternatives do not provide enough concrete benefit for this rebuild phase.

### Three.js

Benefits:

- strong 3D scene ecosystem;
- mature WebGL abstraction.

Costs for Synapse now:

- Presence and Constellation are primarily 2D/particle/neural surfaces;
- 3D camera, lighting, and mesh complexity would add noise;
- easier to overbuild into concept art rather than functional state visualization.

Decision: not selected initially. Revisit only if real 3D navigation or depth semantics become required.

### Direct Canvas/WebGL/WebGPU

Benefits:

- maximum control;
- potential performance upside.

Costs for Synapse now:

- high implementation and testing cost;
- custom renderer maintenance burden;
- premature for first rebuild.

Decision: not selected.

### Redux, React Query, Dockview, large design systems, microfrontends

These are deferred. The first rebuild needs a narrow, testable shell and typed contracts, not broad framework commitments.

## Why selected

Electron + React + TypeScript + Vite + PixiJS matches the current constraints:

- mature Windows desktop delivery;
- direct support for secure preload/IPC allowlists;
- practical supervision of a local Python backend/sidecar in future implementation slices;
- strong support for HTTP, NDJSON, SSE, audio APIs, custom windows, and local file pickers;
- efficient 2D GPU visualization for Presence and Activity without forcing a 3D engine;
- familiar debugging and test tooling.

## Trade-offs

- Electron has a larger footprint than Tauri.
- Electron security requires strict sandbox, `contextIsolation`, preload allowlists, and no generic IPC.
- PixiJS is not a complete UI framework; it must remain behind a visualization adapter.
- Minimal state management may need to evolve when multiple panels, streams, and offline states become complex.

## Security implications

Required:

- Electron sandbox enabled.
- `contextIsolation` enabled.
- no Node integration in renderer.
- narrow preload bridge.
- no generic command or filesystem IPC.
- renderer treats backend/model output as untrusted.
- all commands route through backend command/tool authority.
- attachments use governed staging and checksum verification.

## Packaging implications

Electron is compatible with a future Windows packaging flow and local Python backend sidecar supervision, but that work is out of scope for this foundation. Packaging must be revisited in a dedicated slice after the shell and backend boundary are stable.

## Revisit conditions

Reconsider this decision if:

- Windows package size becomes a release blocker;
- security review rejects the Electron threat model even with sandboxed preload allowlists;
- visualization requires true 3D semantics;
- backend transport changes away from local HTTP/streaming;
- measured PixiJS performance is insufficient for the target scene;
- product requirements require complex persistent docking or multi-window workflows.
