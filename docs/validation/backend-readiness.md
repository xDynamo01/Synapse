# Backend validation — 2026-10-24

Status: **backend source validation PASSED**. This is a technical validation of
the current checkout, not a claim that every optional service is configured or
that desktop release binaries have been rebuilt.

## Scope

User-authorized correction of the failures reported by the hierarchical-memory
validation, followed by full backend verification. Active checkout only; no commit,
push, dependency installation, production-data migration or permission expansion.
Existing frontend, voice, MoM, swarm and memory changes were preserved. A source
restore point was saved under `artifacts/restore-points/backend-validation-source.zip`.

## Corrections

- Chat retrieval decisions now share the conversation correlation scope and reuse
  the session workspace before retrieval intent is evaluated.
- A successful live LM Studio probe takes precedence over an obsolete inactive
  catalog snapshot. Disabled/unreachable providers still fail explicitly.
- Task activity resolves task identifiers; only conversation events use conversation
  identifiers. Project activity no longer drops a successfully created task.
- Voice health counts sessions without repeating full device/decoder diagnostics.
  The existing diagnostic payload remains available and is probed once.
- Kokoro distinguishes an absent optional installation (`unconfigured`) from a
  partial/invalid configured installation (`unavailable`). Synthesis still rejects
  missing or unverified assets; no false available status is introduced.
- VoiceStudio HTTP is injected from the composition root through a consumer-owned
  transport protocol. Speech adapters retain their no-direct-HTTP boundary. The
  transport accepts only loopback HTTP endpoints, ignores proxies, and rejects
  redirects. Existing voice catalog/profile/synthesis operations remain supported.

## Test-contract reconciliation

The defaults already enable local chat and LM Studio and select Kokoro. Tests now
assert those defaults; disabled-chat behavior explicitly writes a disabled policy.
The ready-state fixture explicitly disables absent LM Studio and local chat rather
than treating an absent enabled service as ready.

The graph is exactly 313 runtime / 352 source edges. The additional dependency is
`decision -> core` from the already implemented JEV client. The pre-existing
11-context / 31-edge SCC is unchanged. Frozen assertions remain exact, and no
cycle, direction or transport check was removed.

The API surface is exactly 511 paths, 566 operations and 141 schemas. Additions
are the memory index, voice catalog and VoiceStudio profile creation; the new
schema is `VoiceStudioProfilePayload`. Package inventories include the existing
ChatTTS and VoiceStudio modules. Public-export and persistence-format checks remain.

## Evidence

| Check | Current result |
| --- | --- |
| Initial architecture reproduction | 255 passed, 19 failed |
| Initial runtime reproduction | 95 passed, 11 failed, 4 subtests passed |
| Runtime corrections | 84 passed |
| Final targeted boundaries and new regression contracts | 35 passed |
| Live installed Gemma model | Recovered the real workspace path from temporary memory |
| Live installed Kokoro Dora | Verified 24 kHz mono WAV, 3733 ms, process exited successfully |
| Full global suite | **4623 passed, 0 failed, 5 skipped, 4 subtests passed**, 1869.28 seconds; `artifacts/reports/backend-validation-global.txt` |
| Architecture | All architecture tests passed within the final global run |
| Global source Mypy | 827 active source files passed, no incremental cache |
| Global Ruff | Passed for backend and tests |
| Diff check | No whitespace errors; normal Windows line-ending notices only |

The real-model and real-voice evidence is separate from simulated provider tests.
Neither probe populated production memory or changed the installed voice assets.
The generated voice sample is `artifacts/reports/backend-validation-voice.wav`.

## Platform limitations and warning

Five existing tests were skipped because this Windows environment does not permit
symlink creation: `test_data_maintenance.py`, `test_local_artifact_custody.py`,
`test_skills_phase17_recovery_final.py`, `test_skills_phase4_verification.py`, and
`test_storage_primitives.py`. No new skip or xfail was introduced. These cases are
not counted as passed and still require a host supporting symlink creation.

One existing Starlette/TestClient deprecation warning recommends `httpx2`. No
dependency was changed to suppress it.

## Readiness meaning

A clean backend validation demonstrates the tested source and contracts. It does
not imply every optional external provider is installed, connected, licensed or
configured, nor that desktop binaries have been rebuilt or deployed. An enabled
unreachable service must continue to report degraded/unavailable. No production
readiness promotion is inferred merely from unit-test success.
