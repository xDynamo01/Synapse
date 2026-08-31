# ADR 0119 - Retire Electron ADE implementation

Status: Accepted

Date: 2026-08-21

## Context

The current Electron ADE frontend implementation was explicitly authorized for removal.
The backend must remain the system of record, and backend operational contracts must remain
available for reuse by a future frontend.

## Decision

Remove the old Electron ADE implementation and its desktop package/release artifacts.

The next frontend will be rebuilt from a clean governed baseline. The removed implementation
must not remain as an active source, build target, package target, launcher or release
surface.

## Consequences

- `apps/electron-ade/` is removed.
- Desktop packaging, installer scripts and Electron-specific release artifacts are removed.
- Backend operational projection contracts remain reusable.
- Backend Command Authority remains reusable where it is backend/runtime-owned.
- Backend Voice remains reusable.
- Historical Electron ADE ADRs, audits and validation records are superseded and retained
  only as historical evidence.
- The repository state is backend-preserved and frontend-not-implemented.
