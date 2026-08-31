# Desktop UX 0.1.0-rc.3 — final audit

> Historical/superseded: the Electron ADE implementation and release artifacts were removed under ADR 0119 on 2026-08-21. This file is retained as historical evidence only, not active frontend architecture.

Date: 2026-08-21

## Scope and decision

This bounded campaign changed only the Electron shell input boundary, command discovery,
integrated title bar, window lifecycle, Windows packaging entry point and their tests and
release evidence. Presence, Swarm, Dockview, project semantics and backend domain
architecture were not redesigned.

Status: **DESKTOP UX NOT READY**.

The four requested surfaces are implemented. The remaining blocking gate is factual: a
clean packaged user-data directory has no governed Primary Agent assignment. The desktop
correctly resolves `/api/primary-agent` before submitting to the canonical durable
conversation, and refuses to invent an agent when the profile is absent. Consequently the
clean packaged conversational E2E cannot complete without an independent product or user
assignment of the Primary Agent.

## Implemented result

- `E:\Projetos\Synapse\Synapse.exe` is a real Electron portable build, not the NSIS
  installer and not a detached copy of `win-unpacked`'s executable.
- `Synapse-Setup-0.1.0-rc.3.exe` remains the separate assisted installer.
- Plain input uses a typed main-process bridge to the canonical conversation API.
- Slash-prefixed input opens and filters the real command registry; Up, Down, Enter and
  Escape are handled and deleting `/` returns to conversation mode.
- The BrowserWindow is frameless. The existing header owns drag regions and minimal,
  sender-bound IPC for minimize, maximize/restore, close and maximized-state observation.
- Electron's single-instance lock restores and focuses the existing main window.
- The Windows pipeline builds both artifacts and promotes only the portable executable to
  the repository root.

## Evidence

- Electron tests: 25 passed.
- Electron typecheck/build: passed.
- Electron unpacked application smoke: passed with the required marker.
- Root portable launch: application process tree observed; no setup wizard; second launch
  left one application tree; controlled shutdown left zero Synapse processes.
- Installed lifecycle: install exit 0; one authenticated task created; workspace restore
  passed; degraded startup passed; uninstall exit 0; user data preserved; zero orphans.
- Architecture: 268 passed.
- Ruff global: passed.
- Authoritative Mypy: no issues in 788 source files.
- npm production audit: 0 vulnerabilities.
- Full global pytest: 4,421 passed, 5 governed skips and 4 subtests passed in 1,032.45
  seconds.

## Required next step

Assign the intended Primary Agent through the existing governed Primary Agent flow for a
clean desktop profile, ensure its configured local model provider is available, then rerun
the packaged plain-message smoke. No implicit choice is authorized by this campaign.

## Artifacts

- Root portable: `E:\Projetos\Synapse\Synapse.exe`.
- Portable SHA-256: `66cffd60bd3575244918f3c620765b3555e4c1fce68630010e2fe453f443e252`.
- Installer: `apps/electron-ade/release/0.1.0-rc.3/Synapse-Setup-0.1.0-rc.3.exe`.
- Installer SHA-256: `06841429939c5fca4f73a2b750271279d1049f7ef6ce8c4637d9b1e0b8813202`.
- Signing remains explicitly `UNSIGNED`.

No stage, commit, push or history operation occurred.
