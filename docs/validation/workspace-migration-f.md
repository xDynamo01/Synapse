# Synapse workspace migration — F drive

Status: validated 2026-08-30

## Canonical workspace

The active development workspace is `F:\Projetos\Synapse`. The previous
checkout at `E:\Projetos\Synapse` was preserved and is not used by the
launcher, backend sidecar, or frontend build.

Regenerable directories were intentionally not transported (`node_modules`,
`.venv`, `dist`, `build`, `out`, `release`, Python caches, and tool caches).
Source, documentation, governed assets, and existing user-independent project
data were copied without deleting the source workspace.

## Recreated runtimes

- Python: `F:\Projetos\Synapse\.venv`, CPython 3.12.11, restored with
  `uv sync --frozen --extra dev --extra packaging`.
- Node: `F:\Projetos\Synapse\apps\frontend-v2`, restored with `npm ci`;
  Electron binary materialized by the package installer.
- Backend sidecar rebuilt at
  `F:\Projetos\Synapse\backend\dist\synapse_backend`.
- Portable launcher rebuilt as `F:\Projetos\Synapse\Synapse.exe`.

## Runtime validation

Launching `F:\Projetos\Synapse\Synapse.exe` spawned the sidecar from the F
workspace. The sidecar resolved its working directory and executable under F,
while user data remained in the canonical per-user location
`C:\Users\arthu\AppData\Roaming\Synapse`.

Observed startup timing for this validation run:

- launcher invocation to sidecar/handshake readiness: approximately 10.73 s;
- backend bind/application lifecycle completed before the readiness probe;
- renderer bootstrap, conversation open, history, and notification requests
  returned HTTP 200.

The sidecar log records all required lifecycle resources as successful. The
optional repository runtime remains degraded when Git is unavailable, as
governed; it does not block application readiness.

## User data and legacy references

No AppData data or runtime state was deleted or moved. Remaining `E:` strings
are confined to historical audits, snapshots, and archived receipts; they are
not operational launcher, build, or runtime configuration paths.
