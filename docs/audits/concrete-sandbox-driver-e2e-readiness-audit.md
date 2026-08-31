# Concrete Sandbox Driver E2E Readiness Audit

## Scope and decision boundary

This audit reconciles Concrete Sandbox Driver Slices 1–15 through deterministic controlled
journeys, fault injection, restart projection, and the critical repository gates. It does not
add isolation capabilities or activate global bootstrap. Readiness here means readiness for a
final freeze audit of the bounded context, not production readiness of the Synapse backend.

## Proven capability baseline

| Capability | Factual status | Evidence |
|---|---|---|
| Windows workspace and materialization | Available | Contained paths, declared inputs, reparse/hardlink rejection, stale-writer fencing |
| Local artifact custody | Available | Fingerprinted file/tree custody; source preserved |
| Command resolution | Available | Allowlisted executable, structured argv, contained cwd, minimal environment |
| Process start | L1 available on Windows | Suspended CreateProcess, Job assignment and containment before resume |
| Supervision and termination proof | Available | Root/descendant observations remain distinct; proof requires observed empty Job |
| stdout/stderr capture | Available | Concurrent binary-safe bounded readers with explicit truncation/incomplete states |
| Job resource enforcement | Capability-specific | Process count, memory, CPU and metrics are independently reported |
| Grant and fencing | Enforced at mutations | Revalidated at create, configure, resume, termination, publication and cleanup boundaries |
| Secret delivery | Environment V1 available | Explicit provider and scope; parent buffer revoked before resume |
| Restricted networking | Unavailable | Job Object is not network isolation; required profiles fail closed |
| Governed unrestricted networking | Conditional | Requires matching execution capability; driver adds no egress authorization |
| Local output publication | Available | Declared output, refingerprint, atomic custody and publication verification |
| Durable driver state | Available after explicit initialize | Append-only checksummed SQLite facts and deterministic replay |
| Local composition | Available, opt-in | Explicit dependencies; no bootstrap import or auto-start |

L0 supervised and L1 Job-contained execution are available when profile prerequisites are
satisfied. L2 restricted identity, restricted network profiles, and VM/container isolation are
unavailable. The driver is not described as a generic secure sandbox.

## Failure matrix

| Failure | Required result |
|---|---|
| Invalid/revoked grant, stale/missing fencing | Zero next mutation and zero user code |
| Stale artifact/executable/workspace | Zero CreateProcess |
| Required resource or restricted network enforcement unavailable | Start denied without downgrade |
| Required secret unavailable/revoked | No resume and redaction-safe diagnostics |
| Job creation/configuration or CreateProcess failure | No success projection; factual cleanup |
| Assignment/containment/pre-resume/resume failure | Suspended process rolled back; user code absent |
| Observation or termination failure | Unknown/unverified; no fabricated proof |
| Reader failure/truncation/open descendant pipe | Failure, truncation or incomplete state remains explicit |
| Secret/network/publication/cleanup revocation failure | Reconciliation required where proof is unavailable |

The integrated campaign additionally injects Job creation, Job configuration, CreateProcess,
assignment, containment verification, and ResumeThread failures through the local Composition
Root. Existing focused tests cover deterministic generation transfer at materialization,
replacement, process creation/resume, termination, publication, and destructive cleanup.

## Restart and recovery matrix

| Durable condition | Restart projection | Automatic effect |
|---|---|---|
| Completed with termination proof | Completed/terminated-and-proven | None |
| Crash before start | Never-started | None |
| Crash after resume without proof | Handles-lost, orphaned, reconciliation-required | None; historical PID is not trusted |
| Publication/cleanup incomplete | Reconciliation-required with safe inspection/manual actions | No publication or destructive cleanup |
| Secret revocation unproven | Reconciliation-required | No secret resolution/rematerialization |
| Output finalization incomplete | Historical incomplete metadata | No fabricated EOF or recovered bytes |

Replay is not reexecution, rematerialization, secret resolution, artifact republication, host
observation, or destructive cleanup. Historical authorization and fencing never authorize a
future reconciliation mutation.

## Residual and integrity audit

- Process, thread, Job, pipe and reader cleanup outcomes are factual rather than presumed.
- Publication temporary files use the controlled custody root and are removed on tested failure paths.
- Source custody is never deleted implicitly by publication or cleanup.
- Secret values are absent from facts, diagnostics, fingerprints and durable state.
- Driver SQLite is created only by explicit initialization; tests leave databases in isolated temporary roots.
- Injected network resources expose ownership and cleanup proof; the default V1 creates none.
- No global bootstrap imports the local Composition Root.

## Freeze readiness

The bounded context is ready for its final freeze audit if the accompanying focused,
architecture, Ruff, authoritative Mypy, deterministic global regression, diff, residual and
staging gates remain green. Unsupported isolation remains an explicit limitation, not a hidden
downgrade.
