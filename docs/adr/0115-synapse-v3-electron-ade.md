# ADR 0115 - Synapse V3 Electron ADE

> Historical/superseded: the Electron ADE implementation and release artifacts were removed under ADR 0119 on 2026-08-21. This file is retained as historical evidence only, not active frontend architecture.

Status: accepted

## Context

The current desktop client accumulated UI regressions from repeated incremental fixes. It still reads as a chat-centered application and carries React, Tauri, Zustand, legacy docking state, and old workspace assumptions that conflict with the target product.

Synapse V3 is a new desktop client. It is not a refactor of the current frontend. The backend remains the existing FastAPI runtime.

## Decision

Create a new Electron desktop client under `apps/electron-ade/`.

The V3 client uses:

- Electron for the desktop shell;
- TypeScript, HTML, and CSS in the renderer;
- no React, Vue, Angular, Svelte, Zustand, or SPA framework;
- Dockview for workspace docking;
- Monaco Editor and xterm.js later when the coding and terminal panes are wired;
- Arwes later only as visual treatment, not as layout or docking infrastructure.

The former `frontend/` and `desktop/` implementations were removed. The new
client will be built independently under `apps/electron-ade/`.

## Architecture

Electron main owns:

- application lifecycle;
- BrowserWindow creation;
- backend process launch/retry/health orchestration;
- IPC handlers;
- file-system access required by desktop-only features.

Electron preload exposes a small, typed, safe bridge to the renderer. Context isolation stays on. Node integration stays off.

Renderer owns:

- Activity Bar;
- contextual Sidebar;
- Dockview workspace;
- Bottom Panel;
- Status Bar;
- Command Palette;
- view modules.

Renderer never calls Node APIs directly. Renderer backend communication goes through `src/api`.

## API Layer

All backend access goes through:

- `src/api/apiClient`;
- `src/api/backendStatus`;
- `src/api/agentsApi`;
- `src/api/modelsApi`;
- `src/api/chatApi`;
- `src/api/voiceApi`;
- `src/api/memoryApi`;
- `src/api/insightApi`.

No component may call `fetch` against the backend directly.

## Persistence

V3 persists only V3 state:

- dock layout;
- open panes;
- active pane;
- Activity Bar state;
- Sidebar state;
- theme;
- selected agent;
- selected model.

It must not persist:

- absolute developer paths;
- React/Tauri workspace state;
- old layout keys;
- backend secrets;
- tokens.

Invalid persisted layout is discarded and replaced with the default IDE layout.

## Workspace

The workspace is the product center. It uses Dockview and supports pane movement, resizing, splits, merge/tab groups, maximize/restore, persistence, and reset.

There are no global tabs, session headers, chatbot landing pages, or large top bars.

## Layout

The default layout follows IDE patterns:

- left Activity Bar;
- contextual Sidebar;
- central Dockview workspace;
- bottom panel with logs, terminal, output, events, tool calls, and debug tabs;
- compact Status Bar.

Initial panes:

- Agent Console;
- Architect;
- Coder;
- Reviewer;
- Models;
- Runtime Logs;
- Context;
- Output.

## Consequences

- The current React/Tauri UI is abandoned for V3.
- Backend contracts remain useful and are reconnected through a new typed API layer.
- The first implementation phase is a static visual mock with fake data.
- Backend integration starts only after the ADE visual direction is validated.

## Non-goals

- No backend rewrite.
- No new AI features in the V3 shell phase.
- No Arwes layout engine.
- No framework SPA.
- No direct Node access from the renderer.
- No migration of old UI persistence.

## Validation

Each phase produces its own validation record. The first visual validation must confirm that opening the app reads as a multi-agent development environment, not as a chatbot, dashboard, or model launcher.
