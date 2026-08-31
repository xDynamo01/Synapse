# Private Evals Slice 17 — Mypy baseline attribution audit

**Date:** 2026-07-23
**Scope:** static-analysis attribution only
**Backend:** **NOT READY**

## Decision

The authoritative Mypy scope remains `backend/synapse`, not `backend`.
The historical 215-error baseline is reproduced exactly on the current tree:
215 errors in the same 58 files while the checked source set grew from 510 to
517 modules.

The 318-error result was produced by changing the CLI target to `backend`.
That target also checks nine ignored/generated Python files under
`backend/dist`. Five generated `faster_whisper` files contribute 98 direct
errors. Their presence changes import resolution for `yaml` and contributes
five additional diagnostics in three authoritative files. Thus:

- historical/source-authoritative diagnostics: 215;
- generated artifact diagnostics: 98;
- generated-scope import-propagation diagnostics: 5;
- broad total: 318.

Private Evals has zero diagnostics. The seven source modules added after the
archived baseline are all clean. Slice 17 caused no Mypy regression.

**Decision: SLICE 17 APPROVED.**

## Evidence sources

- Archived quality run:
  `E:\Projetos\Synapse-Restore-Points\synapse-pre-cleanup-20260722-103520`
- Archived full output:
  `quality/mypy-global.log`
- Archived command record:
  `quality-baseline.md`
- Archived source inventory:
  `private-evals-manifest.csv`
- Current isolated outputs:
  `C:\Users\arthu\AppData\Local\Temp\synapse-s17-mypy-audit-20260723`

All current caches and captured outputs were written outside the workspace.
The existing workspace Mypy cache was neither deleted nor used as evidence.

## 1. Commands and execution environments

| Run | Command | Working directory | Config | Mypy | Files | Errors |
|---|---|---|---|---|---:|---:|
| Archived baseline | `mypy backend/synapse --cache-dir <external>` | `E:\Projetos\Synapse` | root `pyproject.toml` | 2.1.0 | 510 | 215 |
| Private Evals current | `python -m mypy backend/synapse/private_evals --cache-dir <external> --show-error-codes --no-pretty` | `E:\Projetos\Synapse` | root `pyproject.toml` | 2.1.0 | 63 | 0 |
| Source-authoritative current | `python -m mypy backend/synapse --cache-dir <external> --show-error-codes --no-pretty` | `E:\Projetos\Synapse` | root `pyproject.toml` | 2.1.0 | 517 | 215 |
| Historical command/current tree | `python -m mypy backend/synapse --cache-dir <separate-external> --show-error-codes --no-pretty` | `E:\Projetos\Synapse` | root `pyproject.toml` | 2.1.0 | 517 | 215 |
| Broad current | `python -m mypy backend --cache-dir <external> --show-error-codes --no-pretty` | `E:\Projetos\Synapse` | root `pyproject.toml` | 2.1.0 | 526 | 318 |

The active interpreter is
`E:\Projetos\Synapse\.venv\Scripts\python.exe`, Python 3.12.11. The baseline
cache is a Python 3.12 cache and embeds Mypy version 2.1.0. The historical
Python patch version was not written separately, but the same lock,
configuration, Mypy version and Python 3.12 target are proven.

Mypy used normal namespace/package discovery. No CLI excludes, plugins,
package lists or per-module overrides were supplied. Incremental behavior was
enabled with a new empty external cache directory for each current run.

## 2. Checked-file set comparison

| Category | Baseline | Current | Added | Removed |
|---|---:|---:|---:|---:|
| Authoritative `backend/synapse/**/*.py` | 510 | 517 | 7 | 0 |
| Private Evals source | 56 | 63 | 7 | 0 |
| Generated `backend/dist/**/*.py` | 0 | 9 | 9 in broad run | 0 |
| Broad `backend/**/*.py` | 510 | 526 | 16 | 0 |
| Files containing diagnostics | 58 | 64 broad / 58 authoritative | 6 broad | 0 |

The seven new authoritative modules are:

1. `backend/synapse/private_evals/adapters/__init__.py`
2. `backend/synapse/private_evals/adapters/boundaries.py`
3. `backend/synapse/private_evals/adapters/errors.py`
4. `backend/synapse/private_evals/adapters/queries.py`
5. `backend/synapse/private_evals/adapters/resolvers.py`
6. `backend/synapse/private_evals/sqlite_serialization.py`
7. `backend/synapse/private_evals/sqlite_stores.py`

All seven are untracked source in the current dirty workspace and all seven
have zero Mypy errors.

The statement “six additional files” applies to the number of files containing
errors in the broad run, not the number of newly checked Python modules.

## 3. Six additional error files

| File | Git state | Context | Why included now? | Errors in broad run | Slice 17? |
|---|---|---|---|---:|---:|
| `backend/dist/synapse_backend/_internal/faster_whisper/feature_extractor.py` | ignored/generated | bundled dependency | CLI target changed to `backend` | 8 | no |
| `backend/dist/synapse_backend/_internal/faster_whisper/tokenizer.py` | ignored/generated | bundled dependency | CLI target changed to `backend` | 12 | no |
| `backend/dist/synapse_backend/_internal/faster_whisper/transcribe.py` | ignored/generated | bundled dependency | CLI target changed to `backend` | 70 | no |
| `backend/dist/synapse_backend/_internal/faster_whisper/utils.py` | ignored/generated | bundled dependency | CLI target changed to `backend` | 2 | no |
| `backend/dist/synapse_backend/_internal/faster_whisper/vad.py` | ignored/generated | bundled dependency | CLI target changed to `backend` | 6 | no |
| `backend/synapse/providers/settings.py` | untracked authoritative source | Providers | broad target changes `yaml` resolution | 1 | no |

The broad scope also adds two `attr-defined` diagnostics each to the already
failing `core/serialization.py` and `storage/collection.py`. Therefore the
103-error delta touches eight files, while the count of files with at least one
error increases by six.

## 4. Error delta caused by broad scope

| File | Source scope | Broad scope | Delta | New codes | Cause |
|---|---:|---:|---:|---|---|
| generated `feature_extractor.py` | 0 | 8 | +8 | `arg-type`, `assignment`, `call-overload` | generated dependency |
| generated `tokenizer.py` | 0 | 12 | +12 | `arg-type`, `return-value`, `var-annotated` | generated dependency |
| generated `transcribe.py` | 0 | 70 | +70 | 11 codes | generated dependency |
| generated `utils.py` | 0 | 2 | +2 | `assignment`, `call-overload` | generated dependency |
| generated `vad.py` | 0 | 6 | +6 | five codes | generated dependency |
| `core/serialization.py` | 2 | 4 | +2 | `attr-defined` | generated-scope import propagation |
| `providers/settings.py` | 0 | 1 | +1 | `attr-defined` | generated-scope import propagation |
| `storage/collection.py` | 2 | 4 | +2 | `attr-defined` | generated-scope import propagation |
| **Total** | **4** | **107** | **+103** | — | scope change |

The import-propagated errors report missing `safe_load`/`safe_dump` on `yaml`.
They occur only when generated bundle content is included in the same Mypy
invocation.

## 5. Baseline versus current authoritative diagnostics

Comparison key: file, complete diagnostic message and error code, deliberately
ignoring only line number. Result: zero semantic diagnostics added and zero
removed. No errors merely moved through import propagation in the authoritative
scope.

| File | Baseline | Current | Delta | Error codes | Cause |
|---|---:|---:|---:|---|---|
| `backend/synapse/agent_loop/runtime.py` | 1 | 1 | 0 | `union-attr` | unchanged |
| `backend/synapse/agents/admin.py` | 2 | 2 | 0 | `arg-type` | unchanged |
| `backend/synapse/agents/provisioning.py` | 5 | 5 | 0 | `arg-type`, `var-annotated` | unchanged |
| `backend/synapse/approvals/manager.py` | 3 | 3 | 0 | `arg-type` | unchanged |
| `backend/synapse/audio/ingestion.py` | 1 | 1 | 0 | `arg-type` | unchanged |
| `backend/synapse/audio/runtime.py` | 1 | 1 | 0 | `arg-type` | unchanged |
| `backend/synapse/auth/devices.py` | 4 | 4 | 0 | `union-attr` | unchanged |
| `backend/synapse/bootstrap/adapters/provider_taxonomy.py` | 4 | 4 | 0 | `arg-type` | unchanged |
| `backend/synapse/bootstrap/adapters/world_state.py` | 36 | 36 | 0 | `arg-type` | unchanged |
| `backend/synapse/bootstrap/application.py` | 3 | 3 | 0 | `attr-defined` | unchanged |
| `backend/synapse/bootstrap/feature.py` | 1 | 1 | 0 | `misc` | unchanged |
| `backend/synapse/bootstrap/features/agents.py` | 1 | 1 | 0 | `assignment` | unchanged |
| `backend/synapse/bootstrap/features/intelligence_boundary.py` | 1 | 1 | 0 | `arg-type` | unchanged |
| `backend/synapse/bootstrap/features/platform.py` | 1 | 1 | 0 | `arg-type` | unchanged |
| `backend/synapse/bootstrap/features/project_governance.py` | 1 | 1 | 0 | `arg-type` | unchanged |
| `backend/synapse/chat/runtime.py` | 11 | 11 | 0 | `arg-type` | unchanged |
| `backend/synapse/commands/handlers/maintenance.py` | 5 | 5 | 0 | `arg-type`, `assignment` | unchanged |
| `backend/synapse/commands/handlers/missions_swarm.py` | 2 | 2 | 0 | `dict-item` | unchanged |
| `backend/synapse/commands/handlers/platform_governance.py` | 6 | 6 | 0 | `dict-item` | unchanged |
| `backend/synapse/commands/handlers/project_governance.py` | 1 | 1 | 0 | `assignment` | unchanged |
| `backend/synapse/commands/registry.py` | 1 | 1 | 0 | `attr-defined` | unchanged |
| `backend/synapse/context_fusion/runtime.py` | 1 | 1 | 0 | `union-attr` | unchanged |
| `backend/synapse/core/serialization.py` | 2 | 2 | 0 | `unused-ignore` | unchanged |
| `backend/synapse/daemon/runner.py` | 5 | 5 | 0 | `attr-defined` | unchanged |
| `backend/synapse/delegation/timeout_policy.py` | 6 | 6 | 0 | `union-attr` | unchanged |
| `backend/synapse/desktop_automation/providers/linux.py` | 1 | 1 | 0 | `unused-ignore` | unchanged |
| `backend/synapse/ephemeral_agents/runtime.py` | 10 | 10 | 0 | `arg-type`, `valid-type` | unchanged |
| `backend/synapse/health/runtime.py` | 1 | 1 | 0 | `union-attr` | unchanged |
| `backend/synapse/maintenance/runtime.py` | 9 | 9 | 0 | `arg-type` | unchanged |
| `backend/synapse/memory/store.py` | 10 | 10 | 0 | `attr-defined`, `valid-type`, `var-annotated` | unchanged |
| `backend/synapse/mission_control/runtime.py` | 1 | 1 | 0 | `var-annotated` | unchanged |
| `backend/synapse/missions/attempts.py` | 1 | 1 | 0 | `arg-type` | unchanged |
| `backend/synapse/missions/dag.py` | 1 | 1 | 0 | `var-annotated` | unchanged |
| `backend/synapse/missions/runtime.py` | 15 | 15 | 0 | `arg-type`, `union-attr` | unchanged |
| `backend/synapse/model_hub/runtime.py` | 2 | 2 | 0 | `union-attr` | unchanged |
| `backend/synapse/models/adapters.py` | 4 | 4 | 0 | `attr-defined`, `index` | unchanged |
| `backend/synapse/models/router.py` | 2 | 2 | 0 | `arg-type`, `union-attr` | unchanged |
| `backend/synapse/notifications/local_provider.py` | 1 | 1 | 0 | `arg-type` | unchanged |
| `backend/synapse/perception/errors.py` | 1 | 1 | 0 | `call-arg` | unchanged |
| `backend/synapse/primary_agent/runtime.py` | 4 | 4 | 0 | `arg-type`, `attr-defined` | unchanged |
| `backend/synapse/project_governance/runtime.py` | 1 | 1 | 0 | `assignment` | unchanged |
| `backend/synapse/providers/catalog.py` | 3 | 3 | 0 | `assignment` | unchanged |
| `backend/synapse/scheduler/jobs.py` | 10 | 10 | 0 | `arg-type` | unchanged |
| `backend/synapse/scheduler/runtime.py` | 4 | 4 | 0 | `assignment`, `union-attr` | unchanged |
| `backend/synapse/speech_adapters/piper_tts.py` | 1 | 1 | 0 | `arg-type` | unchanged |
| `backend/synapse/storage/collection.py` | 2 | 2 | 0 | `unused-ignore` | unchanged |
| `backend/synapse/swarm/runtime.py` | 4 | 4 | 0 | `union-attr`, `valid-type` | unchanged |
| `backend/synapse/swarm/strategies.py` | 1 | 1 | 0 | `union-attr` | unchanged |
| `backend/synapse/system_insight/providers/common.py` | 1 | 1 | 0 | `arg-type` | unchanged |
| `backend/synapse/system_insight/providers/linux.py` | 1 | 1 | 0 | `call-overload` | unchanged |
| `backend/synapse/system_insight/providers/windows.py` | 1 | 1 | 0 | `call-overload` | unchanged |
| `backend/synapse/tasks/runtime.py` | 1 | 1 | 0 | `arg-type` | unchanged |
| `backend/synapse/tools/runtime.py` | 1 | 1 | 0 | `arg-type` | unchanged |
| `backend/synapse/vision/capture.py` | 1 | 1 | 0 | `return-value` | unchanged |
| `backend/synapse/vision/errors.py` | 1 | 1 | 0 | `call-arg` | unchanged |
| `backend/synapse/wardrobe/runtime.py` | 4 | 4 | 0 | `arg-type`, `union-attr` | unchanged |
| `backend/synapse/workers/agent_worker.py` | 2 | 2 | 0 | `union-attr` | unchanged |
| `backend/synapse/workers/registry.py` | 8 | 8 | 0 | `arg-type`, `valid-type` | unchanged |

## 6. Build and dist

| Path | Included in broad run? | Included in baseline? | Generated? | Authoritative? |
|---|---:|---:|---:|---:|
| `backend/synapse` | yes | yes | no | yes |
| `backend/build` | target traversed, zero Python files | no | yes | no |
| `backend/dist` | yes, nine Python files | no | yes | no |
| `backend/dist/.../faster_whisper` | yes | no | copied dependency | no |

`backend/build` and `backend/dist` are Git-ignored PyInstaller artifacts.
There are no Python files under `backend/build`. The nine Python files under
`backend/dist` are copied third-party package content, not Synapse source.
Five contain 98 direct errors; four are clean. Generated bundle content must
not be modified to satisfy the source-authoritative Mypy gate.

## 7. Git-state attribution

For the broad run's 526 checked Python files:

| Git state | Checked files | Errors | Baseline inclusion known? |
|---|---:|---:|---|
| clean tracked | 19 | 5 | yes for authoritative source |
| modified tracked | 49 | 54 | yes for authoritative source |
| untracked | 449 | 161 | yes for existing source; seven new modules are clean |
| ignored/generated | 9 | 98 direct | excluded from baseline |
| deleted tracked | 0 checked; 6 Python paths absent | 0 | not checked |

The workspace's dirty/untracked state is not itself a new Mypy regression:
the authoritative diagnostic multiset exactly matches the archived run.

## 8. Configuration comparison

The archived and current `pyproject.toml` files are byte-identical
(SHA-256 `56BB7F63A1AFF4805275A60EB13E2BD5C9F37767BF31209F99AA110D7F369940`).
The archived and current `uv.lock` files are also byte-identical.

| Setting | Baseline | Current | Changed? | Impact |
|---|---|---|---:|---|
| config file | root `pyproject.toml` | same | no | none |
| CLI target | `backend/synapse` | `backend` in 318 run | **yes** | includes generated dist |
| `python_version` | 3.12 | 3.12 | no | none |
| `mypy_path` | `backend` | `backend` | no | none |
| `ignore_missing_imports` | true | true | no | none |
| `check_untyped_defs` | true | true | no | none |
| `warn_unused_ignores` | true | true | no | none |
| `exclude` | none | none | no | CLI scope is decisive |
| `namespace_packages` | default | default | no | none |
| `explicit_package_bases` | default | default | no | none |
| `follow_imports` | normal/default | normal/default | no | dist affects import resolution |
| plugins/overrides | none | none | no | none |
| cache | external | fresh external | no material change | reproducible |

## 9. Tooling comparison

| Tool | Archived/locked | Current | Changed? |
|---|---|---|---:|
| Mypy | 2.1.0 | 2.1.0 | no |
| Python target | 3.12 | 3.12 | no |
| Active Python | baseline patch not separately recorded | 3.12.11 | not shown causal |
| `typing-extensions` | 4.15.0 | 4.15.0 | no |
| `mypy-extensions` | 1.1.0 | 1.1.0 | no |
| Pydantic | 2.13.4 | 2.13.4 | no |
| Mypy plugins | none | none | no |
| installed `types-*` stubs | none | none | no |

Exact reproduction of all 215 authoritative semantic diagnostics further
rules out a tooling-version explanation.

## 10. Causal attribution

| Cause category | Errors | Files | Evidence |
|---|---:|---:|---|
| CAUSED BY SLICE 17 | 0 | 0 | Private Evals passes in 63 files |
| CAUSED BY EARLIER PRIVATE EVALS SLICE | 0 | 0 | seven added Private Evals/SQLite modules are clean |
| PREEXISTING AND COLLECTED | 215 | 58 | exact archived/current semantic match |
| GENERATED ARTIFACT | 98 | 5 | diagnostics under ignored `backend/dist` |
| CONFIGURATION/CLI SCOPE CHANGE | 5 | 3 | only broad run changes `yaml` resolution |
| TOOL VERSION CHANGE | 0 | 0 | byte-identical lock; Mypy 2.1.0 |
| WORKSPACE DIRTY/UNTRACKED | 0 newly attributable | 0 | authoritative baseline reproduced |
| UNKNOWN | 0 | 0 | complete 103-error attribution |

No Slice 17 file, import path or error code is causal; therefore no Slice 17
Mypy correction is indicated.

## 11. Comparable scopes and recommended baseline

| Scope | Files | Errors | Error files | Comparable to baseline? |
|---|---:|---:|---:|---:|
| Private Evals | 63 | 0 | 0 | targeted gate |
| Source authoritative | 517 | 215 | 58 | yes |
| Historical command on current tree | 517 | 215 | 58 | yes |
| Archived historical result | 510 | 215 | 58 | authority |
| Broad current `backend` | 526 | 318 | 64 | no |

This is **Case A — 215 continues to be correct**.

The recommended global baseline and command are:

```powershell
.\.venv\Scripts\python.exe -m mypy backend/synapse --cache-dir <external>
```

Expected current result: **215 errors in 58 files, 517 source files checked**.
The error/file baseline remains 215/58; the checked-file count legitimately
advances from 510 to 517 because seven clean authoritative modules were added.

`mypy backend` is a diagnostic broad scan only. It is not a replacement for
the authoritative source gate while `backend/dist` exists beneath that target.

## 12. Scope confirmations

- No source code was changed by this audit.
- Slice 17 was not changed.
- Slice 18 was not started.
- No Mypy errors were corrected.
- No configuration, architecture, store, adapter, Command or Query was changed.
- No files were deleted or moved.
- No stage, commit, push or PR occurred.
- The backend remains **NOT READY**.
