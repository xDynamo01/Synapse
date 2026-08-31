# Electron ADE removal audit

Date: 2026-08-21

Status: **FRONTEND REMOVED / BACKEND PRESERVED**

## Scope

The authorized removal targeted only the old Electron ADE frontend implementation,
frontend-specific release artifacts, desktop launcher outputs, Electron-only scripts and
active documentation that made the removed frontend look current.

Backend runtime capabilities were not removed by association.

## Classification

Removed as frontend implementation:

- `apps/electron-ade/`;
- Electron main, preload and renderer source;
- frontend contracts duplicated for Electron consumption;
- command palette, Presence, Swarm, Inspector, Dockview, Pixi and renderer state;
- Electron tests, TypeScript configs, package manifests and frontend lockfile;
- frontend `node_modules`, `dist`, `build`, assets and generated icon derivatives.

Removed as release/package artifacts:

- root `Synapse.exe`;
- Electron RC installers and portable artifacts under the removed app tree;
- `win-unpacked`;
- frontend release checksums, manifests and release notes.

Removed as frontend-only scripts:

- `scripts/build_windows_rc.ps1`;
- `scripts/run_desktop_command_e2e.ps1`;
- `scripts/validate_installed_rc.ps1`;
- `scripts/write_release_artifacts.ps1`;
- `scripts/prepare_windows_icon.py`.

Preserved as backend-owned reusable capability:

- Operational Projection backend runtime, adapters, stream and transport tests;
- Desktop/Command Authority backend/runtime contracts;
- Voice backend runtime, persistence, composition and tests;
- backend sidecar build script, with the removed Electron icon dependency deleted.

## Documentation

Active docs now state:

- Electron ADE: **REMOVED / RETIRED**;
- Frontend: **NOT IMPLEMENTED**;
- next frontend: clean governed baseline required.

Historical Electron ADE ADRs, audits and validation records are retained with an explicit
superseded notice. ADR 0119 records the removal decision.

## Residual references

Residual `electron-ade`, `Electron ADE`, `Dockview`, `Pixi`, `renderer`, `preload`,
`Synapse-Setup` and `win-unpacked` matches are historical records, ADR 0119, backend
security principles for future renderers, or backend avatar/provider terminology. No
active source, script or config points to the removed app path.

## Gates

Gate results are recorded in the final task report for the removal run.
