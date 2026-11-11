# Rebuildable Windows check runtimes

The native recipe milestone uses dedicated owner-built Python and a pinned Rust toolchain. The external projects are build inputs. The generated runtimes, logs and manifests stay in ignored staging.

## Python

Run [the builder](../../../tools/runner/build_windows_python.py) on Windows with Git, Python 3.14, MSBuild and the x64 C++ toolchain. Provide the installed MSBuild executable and a fresh working directory.

```powershell
python tools/runner/build_windows_python.py --msbuild $msbuild --work-dir $work
$env:SYNAPSE_CHECK_PYTHON_EXECUTABLE = Join-Path $work runtime/python.exe
cargo test -p synapse-core --lib dedicated_runtime_checks_pass_failure_and_empty_suite -- --ignored
```

The builder checks out CPython 3.14.3, zlib-ng and SQLite at pinned Git commits. It excludes three known activation-context manifest resources in source before compilation. It emits a dedicated interpreter, selected native modules and a SHA-256 inventory. An independent clean checkout built successfully with MSBuild 18.6.1. The runtime is a bounded offline subset of the Windows distribution. [Upstream CPython build instructions](https://github.com/python/cpython/blob/v3.14.3/PCbuild/readme.txt)

The fixed recipe first compiles the approved Python file, then loads and runs its unittest suite. It assigns the private temporary path explicitly to avoid AppContainer's automatic TEMP redirection. The runtime built from a clean checkout passed the arithmetic, SQLite and temporary-file checks. A failing assertion, an empty suite and invalid syntax each returned failure. The syntax case stopped after the compile phase.

The separate filesystem fixture observed four permission denials from an actual verified LPAC process: read, write and delete against an existing outside canary and write against staged read-only project source. The parent verified that the canary bytes were preserved.

## Rust

The fixed recipe uses Windows MSVC Rust 1.96.0 and its bundled LLVM linker. It runs the compiler, linker and test executable separately, each with a verified LPAC token. The compiler emits the ordinary object and allocator LLVM bitcode using stable flags. The runner uses fixed filenames and linker arguments and checks output identity at each handoff.

The native recipe test copied 426,538,961 bytes in 18.43 seconds. Both cases compiled and linked with exit 0. The test process returned 0 for the passing assertion and 101 for the intentional failure. The fixture exercised a filename with spaces and observed the same package SID, low integrity, zero capabilities and Job membership in all six phases.

The final serial native gate passed all three fixtures in 82.85 seconds. It refused hardlinks and alternate data streams in phase outputs and rejected ordinary AppContainer before resume. The parent proved IPv4 and IPv6 loopback listeners live. Guest Winsock initialization returned 10107, so no guest connect call was reached. Neither listener accepted a guest connection. A second 20,359-byte phase was refused when both phases exceeded the combined check output cap.

## Live planning regression

The current Core executable planned a synthetic mission through the loaded Qwen in 5.919 seconds. The exact proposed contract persisted after restart, preapproval writes were refused, and the workspace stayed empty. LM Studio reported 32,512 context tokens and four parallel slots for the loaded instance. This run exercised planning.

## Acceptance

The first CLI regression run exposed a test-fixture race: marker existence could become visible before its JSON had been written. The fixture now publishes a complete marker with an atomic replacement. The serial rerun passed 22 AI, 26 Core and 11 mission CLI tests with all features enabled. The eight Python worker tests also passed.

This verifies native recipes and individual containment controls on the current Windows host. Durable Core check commands, cancellation and restart recovery remain open. Mission generation, QA and automatic integration depend on that Core integration.
