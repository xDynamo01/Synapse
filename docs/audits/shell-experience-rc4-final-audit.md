# Shell Experience 0.1.0-rc.4 — final audit

> Historical/superseded: the Electron ADE implementation and release artifacts were removed under ADR 0119 on 2026-08-21. This file is retained as historical evidence only, not active frontend architecture.

Date: 2026-08-21

## Decision

Status: **SHELL EXPERIENCE NOT READY**.

The bounded shell campaign is implemented and all in-scope Electron, packaging, installed
lifecycle and visual gates pass. The remaining blocking condition is inherited and factual:
a clean desktop profile has no governed Primary Agent assignment. Plain text reaches the
canonical Primary Agent resolution boundary, which correctly refuses to invent an agent;
therefore a successful clean-profile conversational response cannot be claimed yet.

## Product result

- One composer handles text, slash commands, Voice entry and file attachments.
- `/` exposes 18 real desktop commands. Global commands are listed first and project-bound
  commands remain visible with explicit `requer projeto` availability.
- `task.create` remains the only backend-mutating desktop command. Project selection and
  panel commands are local/read-oriented and do not bypass Desktop Command Authority.
- Presence is always mounted and defaults to idle. Text requests set a factual local
  processing state while the request is pending; Voice projection drives listening and
  speaking; neither requires a separate page.
- A simple agent or task does not activate Swarm. A running Swarm projection or explicit
  `/swarm` inspection does. Role colors remain teal/blue/purple/orange/yellow/neutral.
- Dockview panels open only on demand, split inside the workspace, disable floating groups,
  persist per project and do not invoke operational lifecycle on close.
- Notification bell, unread badge and in-app popover use canonical notification endpoints
  and filter trivial categories.
- File selection occurs in main. Renderer receives opaque tokens and metadata only. Before
  a conversational turn, files are copied into governed userData storage, hashed with
  SHA-256, registered against the durable conversation and referenced by relative storage
  identifiers; absolute source paths never enter renderer persistence.
- Header no longer exposes Electron/platform trivia or the redundant internal desktop
  label. The custom frameless controls and single-instance behavior remain intact.

## Evidence

- Electron tests: 33 passed.
- TypeScript main/preload/renderer build: passed.
- Source visual smokes: Presence, slash palette and notification-open behavior passed.
- Packaged application smoke and packaged slash-palette capture: passed.
- Installed lifecycle before the final presentation-only color adjustment: clean install,
  authenticated command, restore, degraded startup, uninstall, data preservation and zero
  orphan processes passed. The final unpacked artifact smoke passed after that adjustment.
- npm production audit: 0 vulnerabilities.
- Backend Python was not changed. The immediately preceding current global evidence remains
  268 architecture tests, global Ruff, authoritative Mypy on 788 files and 4,421 regression
  tests plus 4 subtests with 5 governed skips.

## Artifacts

- Root portable: `E:\Projetos\Synapse\Synapse.exe`.
- Portable SHA-256: `ada9d96bc9fa8ef7d39eb4a5eebeedac1623eac63534ba697a17bbf7c8cec10a`.
- Installer: `apps/electron-ade/release/0.1.0-rc.4/Synapse-Setup-0.1.0-rc.4.exe`.
- Installer SHA-256: `35e70e13a3cde40e032f2da9b2ac35e6cd747e984bb28b6a5af4a28029bbe017`.
- Signing remains explicitly `UNSIGNED`.

## Required next step

Assign the intended Primary Agent through the existing governed flow, make its configured
local provider available and rerun the clean packaged plain-message smoke. No agent choice
is authorized implicitly by this UI campaign.

No stage, commit, push or history operation occurred.
