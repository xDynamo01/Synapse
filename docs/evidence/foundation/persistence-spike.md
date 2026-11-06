# Foundation persistence spike evidence

Date 2026-11-06

Result **TESTED / PASS on Windows**. This spike supports
[ADR 0003](../../adr/0003-foundation-persistence.md).

## Environment and reproduction

The [host capture](host-capabilities.windows.json) identifies Windows 11 x64
build 26200, 12 logical CPUs and 15.9 GiB OS-visible RAM. The run used a local
NTFS volume with approximately 543 GiB free. CPython 3.14.10 x64 standard-GIL
links SQLite 3.53.1, source ID
`2026-05-05 10:34:17 c88b22011a54b4f6fbd149e9f8e4de77658ce58143a1af0e3785e4e6475127e9`.
The adapter uses the standard library. Pytest 9.2.0 and psutil 7.2.2 are
experiment-only and resolved with uv 0.13.7 from the hashed lock.

From the repository root, after the [ADR 0001 toolchain setup](../../../experiments/runtime-compatibility/README.md),
run this in PowerShell. A configured uv 0.13.7 and CPython 3.14.10 can use
the equivalent `uv run --locked --directory experiments/persistence` command.
Each fixture removes its temporary database directory on teardown.

```powershell
$foundation = (Get-Location).Path
$persistence = Join-Path $foundation 'experiments/persistence'
$runtime = Join-Path $foundation 'experiments/runtime-compatibility/.local'
$gateUv = Join-Path $runtime 'bootstrap/Scripts/uv.exe'
$env:UV_CACHE_DIR = Join-Path $persistence '.local/uv-cache'
$env:UV_PYTHON_INSTALL_DIR = Join-Path $runtime 'python'
$env:UV_PYTHON_PREFERENCE = 'only-managed'
$env:UV_PROJECT_ENVIRONMENT = Join-Path $persistence '.venv'
$env:TMP = Join-Path $persistence '.local/tmp'
$env:TEMP = $env:TMP
[void][IO.Directory]::CreateDirectory($env:TMP)
& $gateUv --version
& $gateUv run --locked --directory $persistence python -u -B -m pytest -q -s -p no:cacheprovider
```

### Exact inputs

| Input | SHA-256 |
|---|---|
| CPython `python.exe` | `bcd8e6a0d88b5e9681e94bb4ce569ca1f76039e8ed9944ac7fcd13528d363cae` |
| CPython `DLLs/_sqlite3.pyd` | `9cde70a6d343ae4c3813ee6bd74b9aced34799255b7e78cabcef591db19c1e00` |
| CPython `DLLs/sqlite3.dll` | `ffff6f241b31862205df80020db85854352e4f23dc87cacd12409a89680fe852` |
| `experiments/persistence/uv.lock` | `33f7924d5208857776f74deea8bd9c5b9de66f7a95b48081590bd124f721faa8` |
| `experiments/persistence/storage.py` (LF) | `c8ea7f16113eaec46ac8aef0a8610be7fdd84d62a40e468ea72d19e4c953756c` |
| `experiments/persistence/tests/crash_writer.py` (LF) | `31188ace5b5d1931b7e421a3f3687b7da3933e8d1731de1db130015158b07aa7` |
| `experiments/persistence/tests/test_atomic_write.py` (LF) | `ba4451441dc149c26e00cb363d56e34c3019e889d44935239938e4171e8eaf6d` |
| `experiments/persistence/tests/test_crash_recovery.py` (LF) | `ae129fdf82e99bb7914ca60810302581a618f97cdaa40acc49377614ac85f7a9` |
| `experiments/persistence/tests/test_backup_restore.py` (LF) | `612e6bbcc77ae30b91d06b8bdbd66667e61320674edff26941d5c34391925e7e` |

The Gate 00 execution report records the exact tested commit.

## RED and GREEN

Before adding the adapter, `uv lock --project $persistence` resolved eight
packages including the experiment. The same pytest command without `-u`
exited 2. Each of the three test modules reported
`ModuleNotFoundError: No module named 'storage'`. The summary was
`3 errors in 0.23s`.

The first implemented run exposed a Windows fixture error. A venv redirector
reported one PID while the actual Python writer ran under another PID. Killing
the launcher allowed the writer to continue after its stdin closed. The
corrected fixture launches the base interpreter and asserts the writer's
self-reported PID before terminating it. Only confirmed writer terminations
count toward the decision.

The final pre-commit run exited 0.

```text
......backup_records=256 backup_bytes=32768 backup_ms=209.322 restore_ms=206.722
...Forced terminations=120 pre_commit=60 acknowledged=60 acknowledged_loss=0 partial_visibility=0 integrity_pass=120
elapsed_seconds=29.396 append_p50_ms=82.110 append_p95_ms=169.024 recover_check_p50_ms=30.083 recover_check_p95_ms=63.004 writer_resident_high_bytes=26120192 database_files_high_bytes=2081040
.
10 passed in 43.74s
```

## Fixtures and measurements

| Area | Observed result |
|---|---|
| Write contract | Distinct versions coexist. Duplicate versions and invalid references or digests fail without changing committed data. |
| Concurrent reads | Two open read transactions retain the previous snapshot during a real writer's commit. A fresh read sees the new version. Passive checkpoint reports uncopied frames until readers release their snapshots. |
| Schema and migration | Empty version-zero database migrates. Injected failure before the version bump rolls back both schema and application ID. Foreign and future schema versions fail closed. |
| Pre-commit termination | A separate interpreter inserts a multi-page synthetic reference and pauses before `COMMIT` executes. The parent verifies new WAL frames and no visibility to a live reader, kills the verified process and checks recovery. All 60 staged writes stayed absent. |
| Post-commit termination | The child reports after `append_record` returns. A keeper connection leaves the acknowledged write in the WAL. The current row is present to SQLite readers and absent from the main-file-only view. All 60 acknowledged rows and the seed survived across repeated restarts. |
| Recovery | The parent verifies the process exited, reopens through `initialize()` and runs full SQLite integrity checks after every termination. It verifies the complete committed and rejected sets after the loop. |
| Backup and restore | 256 versions backed up online with a reader pinning the old main-file snapshot. A separate new directory restores exactly those versions as an independent writable database. A later source commit stays outside the snapshot. Missing, truncated, foreign and sidecar-contaminated snapshots are rejected. Existing destination data is preserved. |

The spike budget was 120 seconds for the crash loop, 128 MiB peak resident
memory for the child and 8 MiB for the active database plus journal files,
given the host's available resources and this small synthetic workload. The
loop used 29.396 seconds, 24.91 MiB peak child working set and 1.98 MiB peak
active database file bytes sampled at the termination barriers. Append
latency includes connection setup, commit and close. Recovery latency
includes reopening, integrity validation and two record reads. The backup
timings cover one 32 KiB snapshot and restore. These figures describe the
fixture workload.

Linux/macOS runs, hardware power loss, storage-controller failures, backup
publication interrupted by power loss, encryption, external blob durability
and product-scale datasets remain **NOT RUN**. Exact process death tests
cover the pre-commit and acknowledged boundaries. Timing or outcome inside
SQLite's commit call remains unmeasured. Independent review and integration
regression remain Gate 00 obligations.
