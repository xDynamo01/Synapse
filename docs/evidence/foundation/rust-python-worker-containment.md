# Windows worker containment experiment

Date: 2026-11-09. **TESTED / PASS for this Windows synthetic lifetime fixture.
R2 NOT ACCEPTED; Gate 00 remains BLOCKED.** No product launcher, Core owner,
transport, native UI or durable cancellation decision is accepted here.

## Scope and Charter

Executes Task 1 of the [containment plan](../../superpowers/plans/2026-11-09-rust-worker-containment.md).
Binding [Decision Charter](../../specs/2026-11-06-synapse-0.3-decision-charter.md):
CR-001, CR-004, MI-003, SE-005, PL-001, PL-004, PL-006, QA-001–003. Fresh code
is confined to `experiments/rust-python-boundary`; no archived runtime import,
product scaffolding, persistent business data, account, device or remote effect.
This fixture only reduces process lifetime; it grants no authority. Other
Charter product/voice/memory/Skills/MoM/Swarm obligations are N/A to this synthetic
task and remain required at their gates. No Charter deviation is proposed.

The [first-spike observations](rust-python-boundary-spike.md) remain historical,
including its genuine blocked-worker orphan. This report supersedes that
specific lifetime observation only for the newly measured Windows artifact.

## Mechanism and official contracts

Windows creates an unnamed Job Object with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`,
no breakaway flags, and one host-owned non-inheritable handle. `CreateProcessW`
uses `STARTUPINFOEXW`, `PROC_THREAD_ATTRIBUTE_JOB_LIST`, `CREATE_SUSPENDED` and
`EXTENDED_STARTUPINFO_PRESENT`. Assignment therefore happens during creation;
the launcher additionally checks membership before `ResumeThread`. There is no
assign-after-start path or cooperative-EOF/watchdog containment guarantee.

Creation-time JOB_LIST also avoids the suspended-child gap of separate
CreateProcess/AssignProcessToJobObject calls described by Microsoft. This API
requires Windows 10+/Server 2016+. Unsupported attributes, restricted nesting,
creation, membership or resume errors deny launch; there is no uncontained
fallback. Linux/macOS worker launch explicitly returns NOT IMPLEMENTED.

`PROC_THREAD_ATTRIBUTE_HANDLE_LIST` allows only child stdin/stdout and NUL
stderr. Host pipe ends, job, process and thread handles are non-inheritable.
The interpreter path is absolute and passed separately as `lpApplicationName`;
UTF-16 writable CRT-quoted arguments use no shell. The child receives only
SystemRoot, `-I -S -u`, and the engine. All Win32 handles use Rust `OwnedHandle`;
the attribute allocation has a matching destructor. The returned thread handle
closes after resume. Normal stop terminates the job, closes its last handle,
and checks a bounded wait on the retained original worker handle. Setup failure
after successful creation uses the same cleanup while the thread is suspended.
Abrupt host death relies on the kernel closing the last job handle.

Official sources inspected 2026-11-09:

- [CreateJobObjectW: final-handle kill semantics](https://learn.microsoft.com/en-us/windows/win32/api/jobapi2/nf-jobapi2-createjobobjectw).
- [UpdateProcThreadAttribute: JOB_LIST, HANDLE_LIST, lifetime and minimum OS](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-updateprocthreadattribute).
- [Microsoft explanation of creation-time job assignment and the suspended gap](https://devblogs.microsoft.com/oldnewthing/20230209-00/?p=107812).
- [CreateProcessW: inheritance, mutable command line and STARTUPINFOEX](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-createprocessw).
- [Creation flags: suspension, Unicode environment and no window](https://learn.microsoft.com/en-us/windows/win32/procthread/process-creation-flags).
- [AssignProcessToJobObject: membership, descendants and nesting restrictions](https://learn.microsoft.com/en-us/windows/win32/api/jobapi2/nf-jobapi2-assignprocesstojobobject), [Nested Jobs](https://learn.microsoft.com/en-us/windows/win32/procthread/nested-jobs).
- [Microsoft Windows Rust bindings](https://github.com/microsoft/windows-rs).

## Runtime and reproduction

Measured Windows 11 x86_64, build 10.0.26200; Rust 1.96.0
`ac68faa20c58cbccd01ee7208bf3b6e93a7d7f96`, Cargo 1.96.0
`30a34c682`, MSVC target; installed CPython **3.14.3**, MSC v.1944 AMD64.
Historical Python 3.14.10 is not the measured runtime. No toolchain installation.
Existing linker discovery is unchanged from the first spike. Exact new pin:
`windows-sys = 0.61.2`; locked transitive `windows-link = 0.2.1`. Crates were
fetched once, then all measured builds used `--locked --offline`. Existing PyO3,
serde and serde_json pins are unchanged.

Working directory: `experiments/rust-python-boundary`. PowerShell preparation:

```powershell
$env:PYO3_PYTHON = "$env:LOCALAPPDATA\Python\pythoncore-3.14-64\python.exe"
$env:SYNAPSE_SPIKE_PYTHON = $env:PYO3_PYTHON
$env:PATH = "$(Split-Path $env:PYO3_PYTHON);$env:PATH"
cargo fmt --check
cargo build --locked --offline
& $env:SYNAPSE_SPIKE_PYTHON probe.py
```

All three checks exit 0. Final compile output:
`Finished dev profile [unoptimized + debuginfo] target(s) in 2.17s`.
Clippy is NOT RUN: `cargo-clippy.exe` is not installed for the measured toolchain;
it was not installed for this task. Full machine-readable final output is the
ignored `receipt.local.json` (SHA256 below); private controller report retains
RED/GREEN commands and output. Hashes describe measured raw worktree bytes,
not a bit-reproducible/clean-machine package claim.

## RED then GREEN

Before replacing the original `Command::spawn` launcher, the engine gained only
the explicit synthetic descendant/hang fixture and the launcher forwarded that
fixture argument. The live worker and descendant identity handles were captured
before killing the owned Rust process. Running
`probe.py --containment-only --repetitions 1` exited 1:

```text
{"repetition":1,"fixture":"fixture-hang","host_returncode":1,"cleanup_ms":2000.067,"original_worker_alive":true,"original_descendant_alive":true}
AssertionError: OS containment failed: owned original identities survived 2s
```

Both orphans were then terminated/waited only through their retained handles,
which were closed. The separate `--expect-orphan --repetitions 1` baseline
confirmed the same negative and handle cleanup. No post-death PID reopening,
process-name kill, tree enumeration kill or broad cleanup was used.

Final full probe exited 0. Before each hard death the worker created exactly one
sleeping Python descendant and acknowledged a synthetic job, then remained in
the hang/busy fixture. A 50 ms fixture settling delay is test preparation only.
Rust was externally killed through its retained `Popen` handle; Rust destructors
could not perform cleanup. Both captured original process objects were signaled
before the 2-second bound, prior to any emergency cleanup, in all ten runs:

| Repetition | Worker state | Host kill to both process exits (ms) |
|---:|---|---:|
| 1 | hang | 3.248 |
| 2 | busy | 3.292 |
| 3 | hang | 2.472 |
| 4 | busy | 2.396 |
| 5 | hang | 3.211 |
| 6 | busy | 3.062 |
| 7 | hang | 2.538 |
| 8 | busy | 2.974 |
| 9 | hang | 3.051 |
| 10 | busy | 3.069 |

All ten original worker and descendant identities were dead, and all observer
identity handles were closed. Values include host wait and polling overhead;
they are engineering experiment samples, not an SLA or exhaustive crash proof.

Additional launch/lifetime evidence:

| Fixture | Result |
|---|---|
| Inject before creation | exit 1, 0 stdout bytes, no worker code |
| Inject before resume | exit 1, 0 stdout bytes, suspended worker terminated/waited |
| Supply invalid JOB_LIST handle | real CreateProcessW failure, OS error 6, exit 1, 0 stdout bytes |
| Kill owner while child initial thread remains suspended | captured original child exits in 1.476 ms; 0 stdout bytes |
| Normal Rust Drop with hung worker and descendant | both exit in 3.399 ms |
| Rust worker timeout with hung worker and descendant | both exit in 2003.170 ms, including 2-second dispatch deadline |
| Original first-spike hang request then external Rust kill | original worker exits in 2.516 ms |

Full prior regression retained: both candidates pass seven strict schema
negatives with the otherwise-valid status control, two framing negatives,
synthetic completion/value42, one-active-job rejection, session duplicate IDs,
cancel acknowledgement/no late success, restart loses volatile state, Python
abrupt exit and hang behavior. Worker Python exit preserves Rust; embedded
Python exit still kills Rust and embedded hang still requires external kill.
The normal worker timeout was 2002.285 ms. Healthy/cancel worker round trips were
0.377/0.160 ms; embedded 0.279/0.161 ms. Startup 75.069/42.734 ms and combined
working-set snapshots 21,495,808/15,966,208 bytes are single samples, not candidate
selection evidence. The common executable still loads the embedding Python DLL
in worker mode.

## Measured SHA256

| Artifact | SHA256 |
|---|---|
| RED fixture executable, original launcher | `9299a932bcce0b87ea1d06bc2c24c0d4a36e670e5f18f0f44c07a840333d69d1` |
| GREEN executable | `b2be6c78be230b15622dc8d8aa17ae0b734ad3a041b6bdb647a25e76e7c00e1f` |
| Cargo.lock | `afca0462e720be75a7913039b4fc86a4eb0b81bea09c4e07f98ab804a615edf8` |
| Cargo.toml | `3189dd04cc28db4c2031815d403becd1eff5d86288981529c7c8ebc951b64711` |
| src/main.rs | `583caf34141454486d2122f049fea35e430f8edab456ca226500880f50af71d9` |
| src/containment.rs | `487d1e9b922c68026c23760e5f6b6f412ab07ea42a5c96b580e6a12d3829b335` |
| engine.py | `41ddc06d65eeb64dc52853a55899eb36c53d2c944d4631ef170c4dffa150bd1f` |
| probe.py | `a0df76d35757a0c4a4521881aa6ae56ee8b8e0bfac892545a1e34e33f231b63b` |
| GREEN receipt.local.json | `a082561f71a3eb2278e90c652721e6e0283632a3ce3e2c2ee87c8f642dcb1b76` |
| Installed python.exe | `cce21c0e8710e304273e98ac4b2b0f5aceb639acbcd2343cbaa5c4e81619c45b` |
| Installed python314.dll | `1ac15e2224581fc678bbd17728b9aa538d47b891b72c76499ef07e54cd74f151` |

## Limits and remaining gates

This is lifetime containment of owned synthetic processes, **not a security or
capability sandbox**: no filesystem/network/token restrictions are established.
Arbitrary native memory-fault injection, adversarial same-user handle duplication,
restrictive pre-existing parent jobs, unsupported Windows versions and forced
Win32 close/wait/resource-exhaustion failures are NOT RUN. Invalid JOB_LIST
failure is exercised; actual incompatible parent-job nesting is not. Hard death
during CreateProcess internals is covered by the selected creation-time API
contract, not exhaustively injected; the post-return pre-resume gap is exercised.

Only this Windows host is TESTED. Linux/macOS are NOT RUN, and their worker path
fails closed. Embedding crash isolation remains unsolved; cancellation/replay
is volatile. Native UI/audio/browser, authority ownership, canonical storage,
remote authentication, packaging/clean machine, runtime upgrade/rollback and all
other R2/Gate 00 obligations remain BLOCKED/NOT RUN. Self-review checks exact
scope, resource lifetime, inheritance, schema regression and claim limits;
independent exact-artifact review remains the controller's next gate.
