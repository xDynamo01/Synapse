# Windows mission runner compatibility probes

Date 2026-11-11. Probes ran on Windows build 26200 against the controlled runner scaffold based on `117f3f5`. All workloads used synthetic files. The existing Core API still rejects `project_check_start`.

## Process boundary

The parent launched each phase suspended and checked the actual AppContainer SID, low integrity, zero capabilities and owned Job membership before resuming. The kernel access probe granted mask 2 for LPAC. The ordinary AppContainer control granted mask 3 and was reaped before resume. A minimal executable returned the expected exit code 73 inside LPAC. Even that minimal executable could not be started from another process inside LPAC, where `CreateProcessW` returned access denied 5.

## Python

The installed Python 3.14 distribution returned `0xc0000022` before emitting output. Debugger output identified a Windows side-by-side activation-context failure. Removing only the Common-Controls dependency from the manifest did not resolve it. Removing manifest resources from the private executable, runtime and native module copies let the diagnostic fixture run. `py_compile` exited 0, a passing `unittest` exited 0 and an intentionally failing assertion exited 1. The passing test exercised SQLite, ctypes and private temporary files. Winsock initialization returned 10107. Live loopback denial remains unverified.

The private binary transformations were diagnostic. A pinned headless runtime built and validated for this boundary is a candidate for production. The installed Python runtime still fails this gate.

## Rust

The copied Rust 1.96 toolchain emitted test objects. Its nested linker launch returned access denied 5. With `-Csave-temps`, the compiler retained the candidate object and its matching allocator object. A fixed parent-built invocation passed both to the copied LLD under verified LPAC and linked successfully. The generated test executable was launched by the parent under verified LPAC, exited 0 and reported one passing test. The run staged 1,109,647,837 bytes in 58.81 seconds and finished in 60.14 seconds.

A second diagnostic used the same pinned compiler with child-only `RUSTC_BOOTSTRAP=1` and `--test -Zno-link -Csave-temps -Ccodegen-units=1`. Compilation exited 0 and produced both expected objects and `check.rlink`. The fixed LLD phase exited 0 and the generated executable reported one passing test. Each phase ran under the same verified LPAC package with its own Job. Total time was 61.81 seconds. The unstable flag and bootstrap setting are diagnostic only. A production recipe needs a pinned supported compiler configuration and validated object identities.

## Acceptance state

The 55 existing Core, AI and mission CLI regression tests passed. Neither diagnostic is registered as a product capability. Durable start, cancellation and recovery, the adversarial isolation suite, separate QA and automatic integration remain pending. The private diagnostic source and raw logs are under `.superpowers/mission-runner-research/evidence/2026-11-11-lpac/`.
