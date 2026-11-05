# OPS-0002 — Disk cleanup candidates (no deletion authorized)

Measured on 2026-11-05 in the canonical checkout. Sizes are approximate and can
drift. No path was deleted.

## Regenerable candidates

| Exact path | Size (MB) | Recovery | Risk |
|---|---:|---|---|
| `.venv/` | 1107.14 | Recreate from `pyproject.toml` and `uv.lock` | Requires working Python/package sources. |
| `.cache/` | 675.63 | Re-run tests/type/lint/build operations | Loses current diagnostic caches only. |
| `apps/frontend-v2/node_modules/` | 562.04 | `npm ci` from lockfile | Requires registry availability. |
| `backend/dist/` | 407.44 | Rebuild backend sidecar/package | Preserve if an unreproducible signed artifact exists. |
| `backend/build/` | 57.14 | Rebuild package | Low if build procedure is verified. |
| `artifacts/temporary/` | 52.63 | Regenerate task artifacts | Must inventory unknown artifacts before deletion. |
| `artifacts/reports/` | 24.38 | Many are generated evidence | Some may be unique evidence; archive/select before deletion. |
| `.venv-release/` | 21.05 | Recreate release environment | Requires locked packaging dependencies. |
| `apps/frontend-v2/dist/` | 6.14 | `npm run build` | Low; current build succeeded. |
| temporary debug directories and root executable | 1.00 | Recreate or re-run diagnostics/build | Verify no unique evidence/active entrypoint first. |

Maximum apparent regenerable space: approximately **2.85 GB**. This is a planning
figure, not an allowlist for deletion.

## Models and persistent data — preserve by default

| Exact path | Size (MB) | Classification |
|---|---:|---|
| `data/models/` | 2174.58 | Downloaded local models; expensive to recover and operationally relevant. |
| `data/voice/models/` | 330.60 | Voice models; preserve until source/checksum and recovery are documented. |
| `data/voice/runtimes/` | 105.09 | Runtime assets; determine whether fully reproducible. |
| `data/project_knowledge/` | 0.06 | Persistent local knowledge; private and excluded from Git. |
| generated world-state ledgers | <0.01 | Persistent operational state; private and excluded from Git. |

Models could add roughly **2.61 GB** of recoverable space only after origin,
version, checksums and a successful redownload procedure are proven. Persistent
knowledge/state is not a cache.

## Required cleanup mission

Before any deletion: resolve exact paths, reject reparse points, inventory contents
and consumers, prove Git/backup/regeneration, record before size, use an explicit
allowlist, delete one class at a time, then rebuild/retest the affected workflow and
record after size. The canonical checkout and the old `E:\Projetos\Synapse` copy
must never be treated as disposable roots.
