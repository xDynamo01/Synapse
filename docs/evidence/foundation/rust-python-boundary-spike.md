# Rust/Python boundary throwaway spike

Date: 2026-11-09. **First R2 feasibility proof only. R2 NOT ACCEPTED; Gate 00
remains BLOCKED.** Neither transport nor Python/toolchain is selected for product.

## Authority and scope

Binding [Decision Charter](../../specs/2026-11-06-synapse-0.3-decision-charter.md):
CR-001–CR-004, MI-003/004, SE-001/005/006, PL-001–PL-004/006,
QA-001–QA-003. Execute only the synthetic first step of
[R2](../../superpowers/plans/2026-11-09-rust-python-foundation-revalidation.md).
All runtime source here is newly written under `experiments/rust-python-boundary`.
No product roots, archived runtime imports, accounts, model weights, real effects,
audio, network listener or canonical storage. Presentation, voice, translation,
memory, Skills, MoM/Swarm and device behavior are N/A to this bounded fixture;
their Charter obligations remain. No Charter deviation is proposed.

## Engineering calls before measurement

Both modes use the same Rust executable and verbatim synthetic Python engine.
The worker mode launches a separately owned CPython process with private stdin/
stdout pipes, `-I -S -u`, cleared environment except Windows `SystemRoot`, and
an explicitly supplied absolute interpreter. The alternative uses pinned PyO3
to embed that engine in Rust's address space. JSON was chosen for a small,
inspectable throwaway experiment; it does not choose the product transport or
supersede the gRPC candidate ADR.

Predeclared host fixture budgets in `probe.py`: launch-to-ready <=5 s; healthy
command round trip <=500 ms; cooperative cancel acknowledgement <=1 s; bounded
worker timeout, kill and wait <=3 s (internal response deadline 2 s). Before
working-set collection a separate synthetic combined working-set ceiling of
256 MiB was declared. These are engineering screening calls, **not owner-approved
SLAs**. No device, audio or model latency claim follows from them.

Four-byte big-endian length prefixes bound UTF-8 JSON to 1–4096 bytes. Schema
major `v=1` requires exactly `v,id,op,job`; Rust typed deserialization rejects
duplicates, unknown fields/types/operations and foreign majors. A second fresh
Python validator uses the same fields, with shared job/status/cancel/result
fixtures. Rust validates returned job events. This is hand-written strict
validation, **not generated schema/evolution acceptance**. Status events are
polled replies, not a durable asynchronous event/replay stream. One dispatch is
outstanding, the reply channel holds one frame, one synthetic job runs at once,
and at most eight job identifiers are retained. Busy work is rejected rather
than queued. This bounds the fixture, not a measured flooding/backpressure proof.

Job identity provides session-only duplicate-start behavior: an existing
running, successful or cancelled identity returns the existing state. Cancel
sets a terminal state under a lock; the fixture checks it every 10 ms and before
publishing success. No real effect, request-digest binding, persistent ledger or
authorization is implemented. Inherited private pipe ownership is the only
worker ownership mechanism; authenticated remote/multi-user IPC is NOT RUN.

## Measured host and dependencies

- Windows 11 Pro 10.0.26200, x86_64 MSVC; Rust **1.96.0**
  (`ac68faa20c58cbccd01ee7208bf3b6e93a7d7f96`), existing installation only.
- Actual installed CPython is **3.14.3**, MSC v.1944 AMD64, GIL enabled.
  The older `runtime-python314.windows.json` says **3.14.10**. That is a
  provenance discrepancy, not permission to install or promote either version.
  The current Python 3.14 documentation also describes 3.14.10; documentation
  version is not evidence of the installed runtime.
- Interpreter discovered offline at
  `%LOCALAPPDATA%\Python\pythoncore-3.14-64\python.exe`, with sibling
  `python314.dll` and `libs\python314.lib`. User-specific absolute paths are
  intentionally omitted. This is an already installed runtime, not a packaged
  clean-machine deployment.
- Actual linker printed by `cargo rustc -- --print link-args`:
  `%ProgramFiles%\Microsoft Visual Studio\18\Insiders\VC\Tools\MSVC\14.51.36231\bin\HostX64\x64\link.exe`;
  `link.exe /?` reported 14.51.36231.0.
- Direct crate pins: PyO3 **0.30.1**, serde **1.0.229**, serde_json **1.0.154**.
  Committed `Cargo.lock` locks all 21 packages. No toolchain/global runtime
  installation was performed; Cargo fetched experiment dependencies, then the
  locked build was rerun offline using its cache.
- `dumpbin /dependents` confirms `python314.dll`, Windows CRT and system DLL
  dependencies. Because this one comparison executable includes embedding,
  **worker mode also loads the Python DLL**. Startup/RSS comparisons include
  that bias and are not a deployable worker-only binary benchmark.

Primary upstream references consulted on 2026-11-09:
[PyO3 0.30.1 crate/support and licence](https://docs.rs/crate/pyo3/0.30.1),
[PyO3 Python attachment and execution](https://pyo3.rs/v0.30.1/python-from-rust.html),
[PyO3 build/distribution and interpreter discovery](https://pyo3.rs/main/building-and-distribution.html),
[CPython isolated command-line options](https://docs.python.org/3.14/using/cmdline.html),
[Rust Child kill/wait/drop obligations](https://doc.rust-lang.org/std/process/struct.Child.html).
The latest Rust documentation is newer than this measured compiler; successful
local compilation is the evidence for the APIs actually used. PyO3 is
MIT/Apache-2.0; this is not a completed distribution/licence inventory.

## Fail-before and pass-after receipts

Before implementing the executable, running `probe.py` exited 1 with
`AssertionError: FAIL BEFORE: real Rust executable has not been built`.
This is a missing-artifact baseline, not a claimed reproduction of a product bug.

The first real `cargo build` exited 0 in 32.06 s. Final verification:
`cargo fmt --check` exited 0, `cargo build --locked --offline` exited 0 in
2.49 s, and `probe.py` exited 0. Clippy is **NOT RUN**: the already installed
toolchain reports `cargo-clippy.exe` is not installed; it was not installed for
this spike. No unit tests substitute for the real-process probes below.

Final recorded run (fresh processes, warm OS/dependency caches, dev build,
single timing sample per row; not statistically significant or disk-cold):

| Observation | Child worker | PyO3 embedded |
|---|---:|---:|
| Launch to ready | 998.205 ms | 40.316 ms |
| Healthy status round trip | 0.490 ms | 0.284 ms |
| Cooperative cancel acknowledgement | 0.143 ms | 0.120 ms |
| Combined instantaneous working set | 20,410,368 bytes | 15,167,488 bytes |
| Python abrupt exit detection | 2.182 ms | 1.922 ms |
| Rust survives Python abrupt exit | yes | **no** |
| Worker hung-call timeout + kill/wait | 2005.858 ms | unavailable |
| Rust hard exit during cooperative job: child exits on EOF | 10.541 ms | same process |

Working set is a post-ready snapshot, not peak, private memory or unique RSS;
the worker sum may double-count shared pages. Synthetic startup varied between
runs (~60–1002 ms worker and ~39–222 ms embedding), so the table cannot select
a winner on startup performance.

Both modes passed six malformed/schema negatives: invalid JSON, foreign major,
unknown field, unknown operation, missing required `job`, duplicate `id`; plus
oversized and truncated frame rejection. Both ran a real threaded synthetic job
to value 42; duplicate starts preserved state; another active identity was
rejected; cancel remained cancelled after 1.15 s, beyond the nominal 1 s job
duration, and a repeated start could not revive the cancelled identity.

Python `os._exit(71)` was invoked during in-flight synthetic work. Worker loss
produced a structured `worker_lost`, the Python PID was dead, Rust stayed alive,
and another start failed closed with `worker_lost`. In embedded mode the same
call terminated the actual Rust host with exit 71. A 60 s blocking Python call
was killed and waited by the worker host within budget, after which further
starts failed closed. Embedded blocking required the external probe to kill the
disposable host; no in-process timeout/crash isolation is claimed. These forced
abrupt exits are not native segmentation-fault or arbitrary-extension tests.

Rust `process::exit(72)` during a cooperative job bypassed normal Rust Drop;
the child observed pipe EOF and exited. **Important negative:** externally
killing Rust while Python was blocked in the 60 s call left the Python worker
alive. The probe detected that exact owned PID and terminated/waited it using
an external Windows process handle. This is **observed missing containment**,
not product recovery. No Windows kill-on-close Job Object or descendant tree
containment is implemented, and no descendants are spawned by the fixture.

Restart deliberately returned `unknown` for a cancelled identity. This proves
that tombstones/state are volatile, **not durable cancellation/idempotency**.
There is no auto-respawn, second Core, persistent effects or replay queue to
validate. Stop/revocation across restart, queued-work ordering, duplicate real
effects, reconnect/replay and authoritative storage remain NOT RUN.

## Reproduce without changing installed toolchains

Run in a PowerShell session from the repository root, using the measured local
runtime if present. First verify `rustc -vV` and the Python version; do not use
the Windows Store `python` alias and do not silently install missing runtimes.

```powershell
$taskPythonRoot = Join-Path $env:LOCALAPPDATA 'Python/pythoncore-3.14-64'
$env:PYO3_PYTHON = Join-Path $taskPythonRoot 'python.exe'
$env:SYNAPSE_SPIKE_PYTHON = $env:PYO3_PYTHON
$env:PYTHONHOME = $taskPythonRoot
$env:PATH = "$taskPythonRoot;$env:PATH"
rustc -vV
& $env:PYO3_PYTHON -I -S -c "import sys; print(sys.version)"
cargo fetch --locked --manifest-path experiments/rust-python-boundary/Cargo.toml
cargo fmt --check --manifest-path experiments/rust-python-boundary/Cargo.toml
cargo build --locked --offline --manifest-path experiments/rust-python-boundary/Cargo.toml
& $env:SYNAPSE_SPIKE_PYTHON experiments/rust-python-boundary/probe.py
```

`cargo fetch` uses the network for pinned crates only if cache entries are
missing; final build and runtime fixture use no network. Environment changes
are session-only. `receipt.local.json` is ignored and regenerated with actual
measurements/artifact hashes. The current commands depend on the existing
interpreter DLL/stdlib and MSVC installation; clean-machine discovery/loading,
redistribution, offline installation, upgrade and rollback are **NOT RUN**.
Linux/macOS build, runtime and hardware lanes are **NOT RUN**.

## Hash-bound receipt

SHA-256, final measured dev artifact and inputs (binary hashes may change on
rebuild; do not substitute a rebuilt artifact for the one described above):

```text
executable 96539fc3250e93aa3e7498c4d4f49ca9adc1078b0ef13566f6c04eda3d78a6fb
Cargo.lock 9c2c73c070441092a487af6211e0b375424b3d5c397c168a02424363a9e43b12
Cargo.toml cf32e9777f6eb85e46546c87aa2fb0a249e4d01c5f0c20aa91c9790f06f4ebab
src/main.rs d11ec5e20eaf311d9f7db579a6ad65df7e0eadb7193a7253290381ae22e132cf
engine.py 83afab166d25e96924b4b303c7a4e499f11e9992d4431dc743bdc52b1aab5611
probe.py 64f54cc6789cc3ec58ab2ec910fae05cb67ef89c605d9eeba04372465911340f
python.exe cce21c0e8710e304273e98ac4b2b0f5aceb639acbcd2343cbaa5c4e81619c45b
python314.dll 1ac15e2224581fc678bbd17728b9aa538d47b891b72c76499ef07e54cd74f151
python314.lib 94ef1b8c9ba2cae9c66841fa7a6d1495ad9f475e2669e736817b35961e433127
```

The fixture shows that actual Rust/Python integration is feasible on this host,
and that embedding shares fatal process failure while an owned worker can
contain Python death. It also exposes restart and Rust-death containment gaps.
It grants **no full R2/Gate 00 PASS**, product scaffolding permission, runtime
selection or deployment acceptance. Exact-commit clean-clone receipts and
independent QA belong to subsequent foundation work.
