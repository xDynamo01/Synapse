# Synapse V3 — Cleanup Batch A: caches and reproducible metadata

**Date:** 2026-07-22
**Decision:** **BATCH A APPROVED**
**Backend state:** **NOT READY**
**Private Evals Runtime:** not frozen

## Restore point and preconditions

- Restore point ID: `synapse-pre-cleanup-20260722-103520`.
- External location: `E:\Projetos\Synapse-Restore-Points\synapse-pre-cleanup-20260722-103520`.
- Repository record and external `RESTORE.md`: **RESTORE POINT VERIFIED**.
- Workspace archive SHA-256: `BA7DAE2AC64BDEE9E4BBAC7CEDCF2847626233B87AFC07CEB7BA0ACA51731F90`.
- Branch: `backend-freeze-cleanup`.
- HEAD: `8196eb11c34442af563b20082bc1666755f4d8a9`.
- Pre-cleanup Git state: 158 tracked; 108 dirty tracked status entries (100 modified, 8 deleted); 1,016 untracked; 12,184 ignored; 0 staged. The additional untracked item relative to the archive baseline is the restore-point record created after archive capture.
- Pre-cleanup physical state: 1,021,230,882 bytes; 15,103 files; 1,791 directories.
- Structural comparison: branch and HEAD matched. The eight missing tracked paths were the eight deleted references already captured by the restore point. The restore-point record was the only added path. No size drift was found in baseline paths.
- Existing dirty production changes were not reverted or modified. They remain a risk because this is not a clean Git tree.

## Scope and protected exclusions

Only root tool caches, permitted `__pycache__` directories, `.pyc`/`.pyo` outside protected trees, and generated `backend/synapse_v2.egg-info` were considered. No loose `.pyc` or `.pyo` existed outside an approved `__pycache__`.

The following were explicitly excluded and preserved: `.git`, `.venv`, `.venv-release`, `backend/build`, `backend/dist`, `data`, source, test source, existing documentation, logs, audio, models, runtime/private data, configs, manifests, migrations, RFCs, Plans, contracts, adapters and bootstrap source. There were zero overlaps and zero tracked candidates.

`backend/synapse_v2.egg-info` was approved because it was ignored by `*.egg-info/`, contained generated packaging metadata, `pyproject.toml` remains the package authority, repository search found no code/test dependency on its internals, and standard packaging tooling can regenerate it.

## Exact candidate inventory and dry run

| Path | Type | Size (bytes) | Files | Git state | Allowed? |
|---|---|---:|---:|---|---:|
| `.mypy_cache` | .mypy_cache | 34119909 | 18 | ignored | yes |
| `.pytest_cache` | .pytest_cache | 205385 | 5 | ignored | yes |
| `.ruff_cache` | .ruff_cache | 50551 | 15 | ignored | yes |
| `backend/synapse/__pycache__` | source pycache | 26422 | 6 | ignored | yes |
| `backend/synapse/admin_policy/__pycache__` | source pycache | 19273 | 6 | ignored | yes |
| `backend/synapse/agent_loop/__pycache__` | source pycache | 52464 | 7 | ignored | yes |
| `backend/synapse/agent_tool_calling/__pycache__` | source pycache | 29710 | 8 | ignored | yes |
| `backend/synapse/agents/__pycache__` | source pycache | 369643 | 24 | ignored | yes |
| `backend/synapse/api/__pycache__` | source pycache | 336428 | 8 | ignored | yes |
| `backend/synapse/api/routers/__pycache__` | source pycache | 432072 | 19 | ignored | yes |
| `backend/synapse/approvals/__pycache__` | source pycache | 46542 | 6 | ignored | yes |
| `backend/synapse/attention/__pycache__` | source pycache | 50520 | 6 | ignored | yes |
| `backend/synapse/audio/__pycache__` | source pycache | 76787 | 10 | ignored | yes |
| `backend/synapse/auth/__pycache__` | source pycache | 15940 | 4 | ignored | yes |
| `backend/synapse/avatar/__pycache__` | source pycache | 46336 | 6 | ignored | yes |
| `backend/synapse/bootstrap/__pycache__` | source pycache | 39979 | 5 | ignored | yes |
| `backend/synapse/bootstrap/adapters/__pycache__` | source pycache | 47253 | 8 | ignored | yes |
| `backend/synapse/bootstrap/features/__pycache__` | source pycache | 63876 | 13 | ignored | yes |
| `backend/synapse/capabilities/__pycache__` | source pycache | 37011 | 8 | ignored | yes |
| `backend/synapse/chat/__pycache__` | source pycache | 83022 | 4 | ignored | yes |
| `backend/synapse/commands/__pycache__` | source pycache | 254376 | 9 | ignored | yes |
| `backend/synapse/commands/handlers/__pycache__` | source pycache | 388229 | 21 | ignored | yes |
| `backend/synapse/context/__pycache__` | source pycache | 24969 | 4 | ignored | yes |
| `backend/synapse/context_fusion/__pycache__` | source pycache | 73553 | 8 | ignored | yes |
| `backend/synapse/contracts/__pycache__` | source pycache | 31200 | 10 | ignored | yes |
| `backend/synapse/conversations/__pycache__` | source pycache | 84701 | 7 | ignored | yes |
| `backend/synapse/core/__pycache__` | source pycache | 131959 | 18 | ignored | yes |
| `backend/synapse/daemon/__pycache__` | source pycache | 33731 | 8 | ignored | yes |
| `backend/synapse/dead_letter/__pycache__` | source pycache | 33950 | 6 | ignored | yes |
| `backend/synapse/decisions/__pycache__` | source pycache | 42408 | 6 | ignored | yes |
| `backend/synapse/delegation/__pycache__` | source pycache | 154867 | 14 | ignored | yes |
| `backend/synapse/delegation_execution/__pycache__` | source pycache | 28376 | 6 | ignored | yes |
| `backend/synapse/delegation_inbox/__pycache__` | source pycache | 34230 | 6 | ignored | yes |
| `backend/synapse/delegation_recovery/__pycache__` | source pycache | 28456 | 6 | ignored | yes |
| `backend/synapse/desktop_automation/__pycache__` | source pycache | 90089 | 14 | ignored | yes |
| `backend/synapse/desktop_automation/providers/__pycache__` | source pycache | 75790 | 9 | ignored | yes |
| `backend/synapse/embodiment/__pycache__` | source pycache | 44872 | 6 | ignored | yes |
| `backend/synapse/ephemeral_agents/__pycache__` | source pycache | 42645 | 4 | ignored | yes |
| `backend/synapse/execution_router/__pycache__` | source pycache | 26709 | 8 | ignored | yes |
| `backend/synapse/health/__pycache__` | source pycache | 85932 | 8 | ignored | yes |
| `backend/synapse/health/contributors/__pycache__` | source pycache | 57576 | 15 | ignored | yes |
| `backend/synapse/intelligence_boundary/__pycache__` | source pycache | 81887 | 5 | ignored | yes |
| `backend/synapse/lifecycle/__pycache__` | source pycache | 22203 | 6 | ignored | yes |
| `backend/synapse/maintenance/__pycache__` | source pycache | 67934 | 7 | ignored | yes |
| `backend/synapse/mcp/__pycache__` | source pycache | 34463 | 8 | ignored | yes |
| `backend/synapse/mcp_bridge/__pycache__` | source pycache | 21733 | 6 | ignored | yes |
| `backend/synapse/memory/__pycache__` | source pycache | 36474 | 7 | ignored | yes |
| `backend/synapse/migrations/__pycache__` | source pycache | 32977 | 8 | ignored | yes |
| `backend/synapse/mission_control/__pycache__` | source pycache | 35901 | 6 | ignored | yes |
| `backend/synapse/missions/__pycache__` | source pycache | 199176 | 18 | ignored | yes |
| `backend/synapse/model_hub/__pycache__` | source pycache | 135407 | 10 | ignored | yes |
| `backend/synapse/model_providers/__pycache__` | source pycache | 38074 | 6 | ignored | yes |
| `backend/synapse/models/__pycache__` | source pycache | 78749 | 8 | ignored | yes |
| `backend/synapse/multimodal/__pycache__` | source pycache | 48241 | 7 | ignored | yes |
| `backend/synapse/notifications/__pycache__` | source pycache | 53511 | 10 | ignored | yes |
| `backend/synapse/observability/__pycache__` | source pycache | 11802 | 5 | ignored | yes |
| `backend/synapse/perception/__pycache__` | source pycache | 71872 | 8 | ignored | yes |
| `backend/synapse/policies/__pycache__` | source pycache | 50621 | 5 | ignored | yes |
| `backend/synapse/presence/__pycache__` | source pycache | 14267 | 6 | ignored | yes |
| `backend/synapse/primary_agent/__pycache__` | source pycache | 20094 | 4 | ignored | yes |
| `backend/synapse/private_evals/__pycache__` | source pycache | 811740 | 57 | ignored | yes |
| `backend/synapse/project_governance/__pycache__` | source pycache | 100196 | 5 | ignored | yes |
| `backend/synapse/provider_plugins/__pycache__` | source pycache | 47615 | 8 | ignored | yes |
| `backend/synapse/providers/__pycache__` | source pycache | 112533 | 13 | ignored | yes |
| `backend/synapse/readiness/__pycache__` | source pycache | 64058 | 7 | ignored | yes |
| `backend/synapse/resources/__pycache__` | source pycache | 14643 | 6 | ignored | yes |
| `backend/synapse/retention/__pycache__` | source pycache | 29378 | 8 | ignored | yes |
| `backend/synapse/scheduler/__pycache__` | source pycache | 102052 | 10 | ignored | yes |
| `backend/synapse/skills/__pycache__` | source pycache | 90287 | 7 | ignored | yes |
| `backend/synapse/speech_adapters/__pycache__` | source pycache | 130042 | 13 | ignored | yes |
| `backend/synapse/speech_pipeline/__pycache__` | source pycache | 56865 | 6 | ignored | yes |
| `backend/synapse/storage/__pycache__` | source pycache | 51917 | 7 | ignored | yes |
| `backend/synapse/swarm/__pycache__` | source pycache | 38215 | 4 | ignored | yes |
| `backend/synapse/system_insight/__pycache__` | source pycache | 76694 | 14 | ignored | yes |
| `backend/synapse/system_insight/providers/__pycache__` | source pycache | 31620 | 7 | ignored | yes |
| `backend/synapse/tasks/__pycache__` | source pycache | 18298 | 4 | ignored | yes |
| `backend/synapse/tool_discovery/__pycache__` | source pycache | 19305 | 6 | ignored | yes |
| `backend/synapse/tool_intents/__pycache__` | source pycache | 41194 | 6 | ignored | yes |
| `backend/synapse/tools/__pycache__` | source pycache | 189425 | 21 | ignored | yes |
| `backend/synapse/vision/__pycache__` | source pycache | 85810 | 9 | ignored | yes |
| `backend/synapse/voice/__pycache__` | source pycache | 156594 | 8 | ignored | yes |
| `backend/synapse/wardrobe/__pycache__` | source pycache | 58950 | 6 | ignored | yes |
| `backend/synapse/workers/__pycache__` | source pycache | 110133 | 8 | ignored | yes |
| `backend/synapse/world_state/__pycache__` | source pycache | 34322 | 5 | ignored | yes |
| `tests/__pycache__` | test pycache | 5880157 | 306 | ignored | yes |
| `tests/acceptance/__pycache__` | test pycache | 445529 | 64 | ignored | yes |
| `tests/architecture/__pycache__` | test pycache | 346913 | 22 | ignored | yes |
| `tests/factories/__pycache__` | test pycache | 6159 | 3 | ignored | yes |
| `backend/synapse_v2.egg-info` | egg-info | 22978 | 5 | ignored | yes |

Totals: 89 paths, 1,164 unique files, 48,146,749 bytes, zero overlap, zero tracked files. Dry run approved every row. No candidate was source, test source, documentation, data, Git metadata, environment content, build/dist content, unknown content or private/runtime data.

## Removal results

| Group | Paths | Files | Bytes removed | Errors | Already absent |
|---|---:|---:|---:|---:|---:|
| `.mypy_cache` | 1 | 18 | 34,119,909 | 0 | 0 |
| `.pytest_cache` | 1 | 5 | 205,385 | 0 | 0 |
| `.ruff_cache` | 1 | 15 | 50,551 | 0 | 0 |
| source `__pycache__` | 81 | 726 | 7,069,168 | 0 | 0 |
| test `__pycache__` | 4 | 395 | 6,678,758 | 0 | 0 |
| `egg-info` | 1 | 5 | 22,978 | 0 | 0 |
| **Total** | **89** | **1,164** | **48,146,749** | **0** | **0** |

Deferred items: none inside the allowed candidate classes. All out-of-scope material was preserved rather than classified as deferred cleanup work.

## Filesystem and regeneration

| Metric | Before | Immediately after removal | After gates, before this report |
|---|---:|---:|---:|
| Workspace bytes | 1,021,230,882 | 973,084,133 | 1,009,871,901 |
| Files | 15,103 | 13,939 | 14,682 |
| Directories | 1,791 | 1,697 | 1,789 |
| Ignored files | 12,184 | 11,020 | 11,763 |
| Untracked files | 1,016 | 1,016 | 1,016 |
| Tracked files | 158 | 158 | 158 |
| Staged files | 0 | 0 | 0 |
| Modified tracked status entries | 100 | 100 | 100 |
| Deleted tracked files | 8 | 8 | 8 |

The gates naturally recreated 88 cache paths, 743 files and 36,787,768 bytes: `.mypy_cache` 28,201,189 bytes/18 files; `.pytest_cache` 172,334/4; `.ruff_cache` 33,769/7; source `__pycache__` 4,745,122/508 across 81 paths; test `__pycache__` 3,635,354/206 across 4 paths. `egg-info` was not recreated by the gates. The caches were not removed again.

Physical recovery after regeneration and before this report: 11,358,981 bytes. Final physical recovery including this 15,895-byte report: **11,343,086 bytes**. Final workspace state: 1,009,887,796 bytes, 14,683 files and 1,790 directories.

## Private Evals protection

The pre-removal comparison matched all 135 rows of `private-evals-manifest.csv`: zero missing files, zero size/hash differences and zero extras in the selected runtime/test/doc scope. Only the explicitly allowed generated `backend/synapse/private_evals/__pycache__` was removed. After removal and after gates, every non-cache Private Evals manifest entry remained byte-identical. No `.py` file was removed.

## Quality gates and architecture

| Gate | Result | Evidence |
|---|---|---|
| `git diff --check` | PASS | exit 0; only existing LF/CRLF warnings |
| Ruff full | PASS | all checks passed; 0.83 s |
| Mypy Private Evals | PASS | 56 source files; 9.48 s |
| Private Evals tests | PASS | 399 passed across 15 test files; 6.61 s |
| Architecture tests | PASS | 130 passed; 41.44 s |
| `_runtime_context_graph()` | PASS | 70 governed contexts; 263 edges |
| Governed edges | PASS | 263, equal to baseline |
| Official SCC | PASS | one non-trivial SCC; 13 contexts / 35 internal edges; Private Evals outside it |
| Exact-module SCC | PASS | 510 modules / 1,913 edges / zero non-trivial SCCs |
| Broken-import search | PASS | zero AST parse/import-scan failures |
| Missing-module search | PASS | zero missing internal `synapse` modules |
| Mypy global | BASELINE RED, NO REGRESSION | 215 errors in 58 files, exactly equal to baseline; 510 files checked; 24.42 s |
| Global collection | PASS | 1,626 tests; 4.66 s |
| Global suite | PASS | 1,624 passed, 2 skipped, 4 subtests passed; 921.68 s |

The official SCC remains `{agents, approvals, avatar, context, conversations, decisions, delegation, embodiment, missions, models, policies, tools, voice}`. Bounded contexts, governed edges, Private Evals edges, contracts, exports and bootstrap source were unchanged. Source/test/doc hash validation reported zero differences from the restore-point manifest, excluding the eight pre-existing deleted references and generated cache files.

## Restoration sample

The verified workspace archive was extracted only into a newly created external temporary directory under `E:\Projetos\Synapse-Restore-Test`. Archive SHA-256 matched. The standalone `backend/synapse/private_evals/__pycache__/analysis.cpython-312.pyc` checksum matched; all 57 files in the sampled Private Evals `__pycache__`, all 15 files in sampled `.ruff_cache`, and all 5 files in sampled `backend/synapse_v2.egg-info` matched the restore manifest. The temporary copy was then removed. Nothing was restored into the live workspace.

## Integrity, risks and final decision

- `.venv`: preserved at 6,507 files / 373,317,583 bytes.
- `.venv-release`: preserved at 3,619 files / 29,472,587 bytes.
- `backend/build`: preserved at 17 files / 48,532,363 bytes.
- `backend/dist`: preserved at 872 files / 266,101,341 bytes.
- `data`: preserved at 117 files / 230,494,395 bytes.
- No runtime/private data, source, test source or prior documentation was removed.
- `.gitignore` remained byte-identical to the restore-point manifest.
- No stage, commit, push, PR, stash, reset, checkout, restore or `git clean` occurred.
- No stores, adapters, Composition Root, next module or next cleanup batch was started.
- Risks retained: the workspace remains materially dirty; Private Evals remains broadly untracked and not frozen; global Mypy remains red at its unchanged baseline; LF/CRLF warnings remain; the backend remains NOT READY.

**Final decision: BATCH A APPROVED.**

Batch A stops here. Batch B was not started.
