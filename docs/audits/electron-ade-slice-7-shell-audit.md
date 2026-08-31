# Electron ADE Slice 7 shell audit

> Historical/superseded: the Electron ADE implementation and release artifacts were removed under ADR 0119 on 2026-08-21. This file is retained as historical evidence only, not active frontend architecture.

Status: **COMPLETE / APPROVED** (2026-08-20).

The command-first shell loads project activity through an allowlisted IPC method and a
loopback-only main-process HTTP adapter. Runtime snapshots and versioned project layout
records are structurally validated and cross-project input is rejected. Cursor-based event
polling is an explicit degraded fallback over the backend resume contract; the independently
validated backend SSE route remains the preferred feed when continuous streaming is enabled.
