# Windows Release Candidate campaign — final audit

> Historical/superseded: the Electron ADE implementation and release artifacts were removed under ADR 0119 on 2026-08-21. This file is retained as historical evidence only, not active frontend architecture.

Status: **COMPLETE / SYNAPSE RELEASE CANDIDATE NOT READY** (2026-08-20).

Historical `0.1.0-rc.1` decision. Both product blockers were subsequently closed by
`0.1.0-rc.2`; see the [RC.2 final audit](windows-release-candidate-rc2-final-audit.md).

## Decisions

- Backend: **READY**, revalidated by all current global gates.
- Integrated Windows product: **NOT READY**.
- Produced installer: reproducible technical candidate evidence, not an approved Release
  Candidate and not suitable for public branded distribution.
- Portable artifact: not produced; its data, update and support semantics are not governed.

## Blocking findings

1. `NO_AUTHORIZED_DESKTOP_COMMAND_TRANSPORT`: the backend owns a command runtime, but no
   authenticated and authorized desktop API exposes it. The Electron shell can open a
   project and consume the operational projection, but it cannot factually complete the
   required `command -> agent -> task -> projection` journey. Adding a generic endpoint
   would create a new security and product authority boundary and was not inferred during
   release engineering.
2. `DEFAULT_ELECTRON_ICON`: no approved Synapse application icon exists in the repository.
   The installer therefore retains Electron's default icon. No official brand asset was
   invented.

The missing signing certificate is explicit technical debt. The installer is `UNSIGNED`;
this prevents a trusted public-distribution claim but did not prevent local validation.

## Corrective work completed

- Electron now defaults to the canonical loopback API at `127.0.0.1:8717/api/`.
- Versioned, project-scoped Dockview layout and selected-project persistence are wired and
  validated.
- Corrupt historical event-log records no longer crash the operational projection. Valid
  facts are retained, the journal is not rewritten, and the projection reports an explicit
  degraded/reconciliation-required state.
- The packaged app owns a bundled Python 3.12 backend sidecar on a dynamic loopback port,
  verifies a cryptographic launch handshake and stops the child process during shutdown.
- Packaged startup failure remains visible and does not produce a silent/white exit.
- Build output excludes source maps, tests, repository metadata and development
  `node_modules`.

## Integrated and installer evidence

- Real source backend plus Electron project smoke passed.
- Standalone packaged sidecar passed authenticated handshake and `/api/health`, and left no
  orphan process.
- Assisted per-user NSIS install into a path containing spaces passed.
- Installed application opened project `rc-installed`; restart restored the selected
  project and layout.
- Deliberate packaged-backend absence exercised the visible failure path; the executable was
  restored and no orphan remained.
- Cold startup: 7.615 s. Warm startup: 5.513 s.
- Uninstall returned exit code 0, removed application binaries, preserved user project data
  by policy and left no Electron/backend process.

## Artifact inventory

- `apps/electron-ade/release/Synapse-Setup-0.1.0-rc.1.exe`
- `apps/electron-ade/release/checksums.txt`
- `apps/electron-ade/release/release-manifest.json`
- `apps/electron-ade/release/release-notes.md`

The manifest records Windows x64, bundled sidecar, dynamic loopback, Python 3.12.11,
PyInstaller 6.21.0, Electron 43.4.0, `UNSIGNED`, `portableProduced: false`, the readiness
status and blocking identifiers. `checksums.txt` is the authoritative SHA-256 record.

## Gates

- Architecture: **268 passed**.
- Focused operational projection: **23 passed**.
- Ruff global: **passed**.
- Authoritative Mypy: **passed across 785 source files**.
- Electron ADE: **19 passed**, build and smoke passed.
- Global regression: **4,419 passed, 5 governed skips and 4 subtests passed** in
  1,079.07 seconds.
- Repository whitespace check: required before campaign closure.

## Final declaration

`SYNAPSE RELEASE CANDIDATE NOT READY`

The build is installable and its lifecycle was validated, but installability is not product
readiness. The next governed work must define and implement the desktop command authority
boundary and provide an approved application icon before this campaign can be rerun.
