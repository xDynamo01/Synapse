# Windows Release Candidate 0.1.0-rc.2 — final audit

> Historical/superseded: the Electron ADE implementation and release artifacts were removed under ADR 0119 on 2026-08-21. This file is retained as historical evidence only, not active frontend architecture.

Status: **COMPLETE / SYNAPSE RELEASE CANDIDATE READY** (2026-08-20).

## Blocker closure

### Desktop command authority

The prior command blocker is closed by [ADR 0118](../adr/0118-desktop-command-authority-boundary.md).
The installed E2E proved:

`Electron renderer -> allowlisted IPC -> Electron main -> ephemeral authenticated session ->
task.create capability -> existing project and agent -> canonical TaskRuntime permission ->
durable task -> correlated operational fact -> project projection -> Electron observation`.

The proof created exactly one assigned task and projection entity. Negative coverage rejects
invalid launch/session credentials, stale commands and restarted sessions, unknown command
types, malformed payloads, absent capabilities, wrong/cross-project scope and conflicting or
exact duplicate deliveries. Exact retry returns the prior result; reserved/incomplete state
requires reconciliation.

### Official icon

The approved 1254x1254 RGBA source is preserved byte-for-byte at
`apps/electron-ade/assets/branding/synapse-icon-source.png` with SHA-256
`0c3302bf2d95f0edc42aeb3b60954aadaf8304107b0561e7779b9c37341eb1c8`.
The Windows ICO contains 16, 24, 32, 48, 64, 128 and 256 pixel frames. Electron Builder
uses it for application, installer, uninstaller and installer header; the BrowserWindow uses
the faithful PNG derivative. The icon extracted from the installed executable was visually
verified. No redesign occurred.

## Installed lifecycle

- Assisted per-user clean install: passed.
- Managed packaged sidecar and dynamic loopback handshake: passed.
- Authenticated project-scoped command and projection: passed.
- Restart/selected-project restore: passed.
- Missing-sidecar degraded startup remained visible and loaded without waiting for the full
  readiness timeout: passed.
- Uninstall: exit 0, binaries removed, user task data preserved.
- Orphan Electron/backend processes: 0.
- Package hygiene: ASAR contains only compiled app files, package metadata and the runtime
  icon; no test, source icon, token, log, database, `.env`, repository metadata or developer
  dependency is packaged.

## Release identity

- Version: `0.1.0-rc.2`.
- Installer: `apps/electron-ade/release/0.1.0-rc.2/Synapse-Setup-0.1.0-rc.2.exe`.
- SHA-256: `31ab027905065aded109910927870486096995c68abdcf8bed43628d44acc99b`.
- Signing: **UNSIGNED**. No certificate or publisher identity was fabricated.
- Signed public distribution: **NO**.
- Portable build: not produced.

## Gates

- Focused command/security/API gates: 17 passed.
- Electron ADE: 21 passed; build and source/installed command smokes passed.
- Architecture: 268 passed after the authorized +1 router, +2 operation and +2 edge baseline.
- Ruff global: passed.
- Authoritative Mypy: passed on 788 source files.
- Full global regression: 4,421 passed, 5 governed skips and 4 subtests passed in
  1,040.85 seconds.
- npm production audit, SHA verification, Authenticode state and diff check: required before
  final declaration.

## Declaration

`BACKEND READY`

`ELECTRON ADE COMPLETE`

`SYNAPSE RELEASE CANDIDATE READY`

`SIGNED PUBLIC DISTRIBUTION NO`
