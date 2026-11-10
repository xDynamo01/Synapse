# Mission runner boundary and threat scenarios

Status: implementation design, not a passing security test or completed scan.
Scope: the Windows build/test consumer in the approved integrated mission design.
Existing `foundation-threat-model.md`, `authority-invariants.md` and
`backend-tool-boundary.md` remain authoritative references; this source policy
specializes the new consumer and does not replace their historical evidence.

## Actors and authority

The local OS user controlling stdin is the owner. Core, its private SQLite store
and explicitly configured trusted tool installations are trusted. The attacker
may control generated source, tests, filenames within a proposed scope and model
output. The attacker does not initially own the OS account, Core binary/state,
tool installation, approval or private asset configuration.

Core must first validate the immutable approved policy and current stop state.
Only fixed typed Python unittest/Rust test recipes are exposed. No executable,
arbitrary argv, shell command, environment, capability or asset path is accepted
from project/model data. Source names/content are separately bounded and must
match the approved artifact set. Actual content/check/tool digests are captured
in a Core-owned check request before launching anything.

## Consumers and effective resources

| Consumer | Resource/configuration | Required enforcing control | Evidence/status |
|---|---|---|---|
| Planner | Objective, exact Skill/context, registered local models | Structured data, Core validation, no effects/approval | Existing worker/registry; planning integration in progress |
| Asset preparation | Explicit real Python/Rust/VC/SDK installation paths | Real bounded copies into owned storage; hashes; no global ACL changes | Local paths inventoried, runtime closure unproven |
| Compiler/interpreter | Private readonly sources/runtime plus private output/temp | Verified suspended LPAC token, exact fresh SID, zero capabilities, protected ACLs, low writable labels | Proposed; real token and positive workloads required |
| Child processes | Compiler linker, Python children, generated test executable | Same LPAC boundary and owned Job, no breakaway, bounded descendants | Proposed; inspect observed child tokens and cleanup |
| Network | No guest network destinations, including inference/Core loopback | No capabilities or loopback exemptions; OS enforcement | Proposed; live controlled listeners required |
| Check result | Kernel exit/status, bounded stdout/stderr, input/tool hashes | Parent-owned observation, protected receipt outside guest ACL | Proposed; printed success is not an authority receipt |
| Integration | Exact QA-sealed staged bytes and approved destinations | Existing broker, fresh approval/stop checks, readback, owned rollback | Separate coordinator gate, not implemented by the runner |

## Native launch and filesystem rules

Use a fresh per-check AppContainer profile and Less Privileged AppContainer (LPAC)
with no capabilities. Opt out of ALL APPLICATION PACKAGES grants. Apply Job
ownership atomically at creation and launch suspended. Before resuming, the
parent must verify the kernel token: AppContainer and LPAC flags, exact profile
SID, low integrity, zero capabilities and correct Job membership. An uncertain
setup never resumes generated code and has no unrestricted fallback.

The launcher constructs its environment and inherits only the three explicitly
allowed pipe handles. No Core database/file/token/job-control/network handle,
host search path, credential/proxy variable, Cargo/Rustup/Python customization
or owner configuration reaches the guest. Python uses its copied real runtime
with isolated/no-site mode; Rust uses copied real rustc, sysroot, bundled linker
and selected import libraries. No package fetching or user Cargo config.

Only owned run objects receive per-run SID ACLs. Runtime and source are readonly
to the guest; output/temp are explicitly writable low-integrity locations.
Receipts/metadata stay Core-only. Never grant SID access to original installations,
user home, repository or Core database. Reject reparse, hardlink, ADS, device,
UNC, traversal and identity ambiguities at relevant copy/export consumers.
No hardlinks or junctions into host tools. Parent-owned manifests bind copied
assets; source tree/control metadata cannot select a different tool.

An LPAC is not a virtual filesystem root: Windows loader resources granted to
ALL RESTRICTED APPLICATION PACKAGES and its disposable profile are documented OS
baseline resources. Minimize writable profile state where actual workloads permit.
Do not claim that every readable OS object resides in the staged project.

Memory/process/output and execution/preparation time limits must be enforced.
Terminate the entire job on stop, output overflow or timeout. Root exit is not
completion until descendants and inherited pipe holders are gone. No hard disk
quota is supplied by Job Objects; preparation/export sizes are bounded and writable
storage may be monitored, but this must not be described as an absolute disk quota.

Persist an owned profile/run intent before creation. A name collision is not
permission to adopt/delete someone else's profile. Cleanup only objects created
by that recorded intent. Cleanup failures/interrupted runs remain explicit and
must not silently pass integration. Reconcile recorded ownership on restart.

## Threat scenarios and validation obligations

These are design hypotheses, not confirmed vulnerabilities in the current backend.

| Priority | Attempt and potential impact | Required mitigation/evidence |
|---|---|---|
| High | Generated Python/Rust reads credentials, Core state or unrelated project | Protected canaries outside stage stay unreadable; no plaintext in captured output; actual LPAC token checked |
| High | Generated code writes/deletes outside its temporary grant | Host-side canary identity/hash/existence unchanged after guest attempts, including descendants |
| High | Compiler include/link/plugin behavior escapes before test launch | Compiler and linker already sandboxed; copied closure, fixed args; no host build fallback |
| High | Guest contacts LM Studio/Core/network or launches a host broker | Zero network capabilities/exemptions; live listener sees no guest traffic; child/broker probes remain denied/contained |
| High | Source/output link or writable tool replaces a trusted consumer | Real copies, readonly medium runtime, no-follow handle checks, link-count/final-path checks before export |
| High | Guest forges approval, QA or successful integration in stdout | Output is untrusted diagnostics; only parent receipts plus existing Core authorization may advance state |
| Medium | Infinite loop, child fanout, memory/output flood or abandoned child | Bounded Job, cancellation/deadline, bounded pipe drain and complete descendant cleanup |
| Medium | Crash/restart reuses grants or leaves reusable private profile data | Durable owned intent, unique SID, stopped status/reconciliation, fail-closed recovery |
| Medium | Guest A accesses run B or prior run data | Fresh per-run SID; no shared writable assets/profile; cross-run canary probes |

Passing Python and Rust workloads must run inside this same boundary, including
passing and failing tests. A blocked interpreter that never started is not a
successful isolation proof. A closed network port is not proof of denial. Test
malicious probes only after verifying isolation before resume; no host execution
of generated programs for convenience. Kernel/OS compromise by the owner and
unpatched OS vulnerabilities are outside this component's claimed boundary.

Primary references: [Microsoft AppContainer launch](https://learn.microsoft.com/windows/win32/secauthz/implementing-an-appcontainer),
[AppContainer isolation](https://learn.microsoft.com/windows/win32/secauthz/appcontainer-isolation),
[Job Objects](https://learn.microsoft.com/windows/win32/procthread/job-objects),
[token inspection](https://learn.microsoft.com/windows/win32/api/securitybaseapi/nf-securitybaseapi-gettokeninformation),
[Python isolated mode](https://docs.python.org/3.14/using/cmdline.html#cmdoption-I),
[Rust linker options](https://doc.rust-lang.org/rustc/codegen-options/index.html#linker-flavor).
