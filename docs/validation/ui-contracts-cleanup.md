# UI Contracts and App Shell Backend Cleanup

> Historical/superseded: the later Electron ADE implementation and release artifacts were
> removed under ADR 0119 on 2026-08-21. This file is retained as historical backend cleanup
> evidence only.

Date: 2026-07-13

## Decision

The old App Shell and UI projection layer did not satisfy the backend contract
permanence criteria. Both existed only to shape data for the abandoned
React/Tauri client. They encoded routes, icons, panels, dock regions and
navigation, or duplicated domain responses behind a UI-specific facade.

The canonical client-neutral layer remains `backend/synapse/contracts/`. It
contains DTOs and protocols, imports no runtime modules, and does not describe
layout, navigation, framework state or presentation.

## Inventory and disposition

| Component | Responsibility | Current consumer before cleanup | Classification | Decision | Reason |
| --- | --- | --- | --- | --- | --- |
| `synapse.ui_contracts.models` | Mission, conversation, agent, notification, health and readiness projections | `/ui-contracts*`, UI commands and obsolete tests | UI-specific duplicate | Remove | Domain APIs already expose the authoritative data; no independent client consumed the facade |
| `UIContractRuntime` | Aggregate six domain runtimes into UI DTOs | Old React client contract routes | UI-specific adapter | Remove | Imported runtimes and existed only for the abandoned UI |
| `synapse.app_shell.models` | Modules, routes, icons, panels, dock regions and navigation | Old React/Tauri shell | Visual contract | Remove | Directly encoded layout and navigation |
| `AppShellRuntime` | Build the visual shell tree | `/app-shell*`, UI commands and obsolete tests | Visual runtime | Remove | No backend responsibility or active consumer |
| App Shell health/readiness flags | Report availability of obsolete UI runtimes | Old shell diagnostics | UI-specific health | Remove | Artificial readiness for removed components |
| Tauri CORS origins and desktop environment flags | Couple FastAPI health to the removed launcher | Tauri WebView | Framework-specific integration | Remove | No active desktop client and CORS is not authentication |
| React `frontend/` | Vite/React/Zustand presentation | Abandoned client | Old frontend | Remove | Not the V3 target |
| Tauri `desktop/` | WebView shell and packaging | Abandoned client | Old frontend shell | Remove | Superseded; no active frontend is present |
| `synapse.contracts` | DTOs and provider/domain protocols | Backend runtimes, adapters and future clients | Frontend-agnostic | Keep | Stable data/capability boundary with no runtime imports |
| Domain APIs for agents, conversations, missions, notifications, health and readiness | Authoritative resource responses | API clients and commands | Frontend-agnostic | Keep | Real runtime consumers and stable domain ownership |
| Avatar and Wardrobe runtimes | Provider-neutral avatar state and asset bindings | Voice, embodiment and provider runtimes | Functional backend domains | Keep | They represent capabilities and persisted domain state, not React components or layout |

## Removed surface

- Packages `backend/synapse/ui_contracts/` and `backend/synapse/app_shell/`.
- Eight `/ui-contracts*` endpoints and four `/app-shell*` endpoints.
- Commands `/ui-contracts`, `/ui-contract`, `/app-shell`,
  `/app-shell-modules`, `/app-shell-panels` and `/app-shell-navigation`.
- UI/App Shell fields and checks from health and readiness.
- Tauri-specific CORS origins, desktop environment flags and `desktop.ready`.
- `frontend/`, `desktop/`, obsolete UI/App Shell tests and implementation ADRs.
- Public mock Vision routes and commands; deterministic mock helpers remain
  internal to Vision tests.

No compatibility aliases, deprecation placeholders or empty routes remain.

## Tests and count change

The previous suite collected 991 tests. Seventeen UI Contract/App Shell/UI
endpoint tests and four desktop-shell tests were removed with their obsolete
functionality. The neutral backend health header assertion was moved into the
canonical health test. Four cleanup invariants were added, producing 974
collected tests.

`tests/test_client_contract_cleanup.py` now prevents reintroduction of removed
routes, commands, runtime attributes and frontend roots, and verifies that
`synapse.contracts` does not import runtime modules.

Focused cleanup validation: 45 tests passed in 51.69 seconds. Frozen-domain
regression: 715 passed, 259 deselected and 4 subtests passed in 369.36 seconds.
Global validation: 974 collected, 974 passed, 0 failed, 0 skipped and 4
subtests passed in 479.01 seconds; pytest reported no warnings.

The final OpenAPI contains 389 paths, no duplicate operation ID, no old
UI/App Shell path and no path containing `mock`.

## Superseded frontend note

No frontend is active. The later Electron ADE implementation was removed under ADR 0119.
Any future frontend starts from a clean governed baseline and consumes the ordinary domain
API; the backend will not recreate a visual App Shell contract.
