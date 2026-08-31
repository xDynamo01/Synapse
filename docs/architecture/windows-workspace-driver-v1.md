# Windows Workspace Driver V1

The opt-in `sandbox_drivers` adapter maps an opaque Sandbox workspace identity to a
configured physical root. It creates deterministic `input`, `work`, `output`, `temp`,
and `state` directories. Host paths remain adapter-private.

Logical paths are parsed by Sandbox and revalidated for Windows drive, UNC, device,
ADS and traversal forms. Resolved targets must remain under the workspace. Symlinks,
junctions, reparse points and hardlinks are rejected; archives are not extracted.
Inputs are copied as regular files/directories and fingerprinted before and after.
Read-only inputs use the Windows read-only attribute only, not a dedicated ACL/token.

An injected consumer-owned fencing port is checked immediately before directory
creation, copying, mutable sealing state and destructive cleanup. Stale or unavailable
fencing fails closed. The port conveys no authorization. Sealing fingerprints and checks
path safety but never starts a workload. Cleanup never follows links and a partial failure
is reported rather than projected as proven.

- `WorkspaceContainment != UserSecurityIsolation`
- `FencingToken != Authorization`
- `OutputFile != PublishedArtifact`
- `CleanupRequested != CleanupProven`
- `ReadOnlyAttribute != StrongWriteIsolation`

TOCTOU limitation: Python path APIs cannot provide handle-relative NTFS operations for
every step. Reparse checks are repeated immediately around effects, but V1 does not claim
protection against a hostile same-user process racing path replacement.

## Local artifact custody and materialization

The custody adapter resolves only opaque references registered under explicitly configured
local roots. Host paths remain private to the adapter. Files and canonical directory trees
include content checksums and sizes in deterministic fingerprints; volatile timestamps are
excluded. Missing sources, stale fingerprints, unsupported file types, reparse points and
hardlinks remain distinct factual failures.

The governed binding adapter requires exact correspondence between artifact reference,
fingerprint, workspace identity, destination, resource and materialization mode. Custody is
reinspected before use, the workspace driver fingerprints again before copying, and the
delivered destination is verified. Regular files use an in-workspace temporary copy followed
by fencing revalidation and atomic replacement. Directory failures remain partial facts and
require cleanup or reconciliation; they are never projected as successful bindings.

Executable-looking files and archives remain inert bytes. Custody inspection is read-only,
does not grant authorization, and restart/replay does not trigger materialization.

- `ArtifactReference != ArtifactAvailable`
- `ArtifactAvailable != ArtifactVerified`
- `MaterializedArtifact != AuthorizedExecutable`
- `ArchiveMaterialization != ArchiveExtraction`
- `InputCustody != OutputPublication`
- `HistoricalCustody != CurrentAvailability`
- `Replay != Rematerialization`

## Structured Windows command resolution

The V1 command resolver is read-only and produces an adapter-local `ResolvedCommandV1`.
Entrypoints must be exact configured bindings: a fingerprint-bound `.exe`/`.com` inside
the workspace, an explicitly allowlisted host executable, or an explicitly configured
PowerShell/Python interpreter plus a verified workspace script. Global `PATH`, Windows
file associations, `ShellExecute`, implicit shells, downloads and package discovery are
not resolution mechanisms. Batch files remain unsupported in V1.

Arguments remain a tuple through resolution. Windows command-line serialization is a
deterministic projection for a future `CreateProcess` boundary; it is not shell escaping.
The working directory is resolved only beneath the bound workspace and unexpected
reparse points fail closed.

Environment construction starts from an explicitly configured minimal base, then applies
opaque non-secret references. It never copies the ambient process environment. Windows
case-insensitive name collisions, invalid names and oversized blocks are rejected. Secret
references yield `secret_materialization_required` without resolving or rendering values.

The command fingerprint binds the plan/workload/attempt references, workspace,
executable reference, structured argv, logical cwd binding, fingerprints of non-secret
environment values, stdio policies, mode and configuration version. Occurrence metadata
is deliberately excluded. Resolution neither validates current fencing nor grants final
execution authority; both must be revalidated immediately before a future process effect.

- `CommandSpec != ShellScript`
- `StructuredArgv != ShellEscaping`
- `MaterializedArtifact != AuthorizedExecutable`
- `ResolvedExecutable != ExecutionAuthorized`
- `SecretReference != SecretValue`
- `ResolvedCommand != CurrentFencingProof`

## Suspended Windows process start and Job containment

The V1 process driver uses the Unicode Win32 APIs directly. It validates command/grant
correspondence, executable integrity, cwd, unresolved secrets and fencing before creating
an anonymous Job Object configured with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`. It then calls
`CreateProcessW` with `CREATE_SUSPENDED | CREATE_UNICODE_ENVIRONMENT`, with no inherited
handles and the exact controlled environment from `ResolvedCommandV1`.

The suspended process is assigned with `AssignProcessToJobObject` and the association is
queried with `IsProcessInJob`. Authorization, fencing and executable integrity are checked
again before `ResumeThread`. Assignment/query/stale/resume failures terminate the suspended
process and close Job, process and thread handles; there is no fallback to an uncontained
process and no automatic breakaway.

After a successful resume the primary thread handle is closed and custody of the process
and Job handles is returned as an adapter-local managed resource. PID is only a host-local
observation. A successful resume is a factual start observation, not proof that the process
remains running or that descendants have terminated. Job Objects provide process-tree
containment primitives, not filesystem, network or identity isolation.

- `ProcessCreated != ProcessStarted`
- `UserCodeExecution => JobContainmentAlreadyEstablished`
- `KillOnJobCloseConfigured != TerminationProven`
- `InitialProcessContained != DescendantTerminationProven`
- `PID != SandboxProcessIdentity`

## Bounded stdout/stderr capture

The process driver configures stdin, stdout and stderr explicitly and does not rely on
the Synapse console handles. Captured stdout and stderr use distinct anonymous pipes.
Only the child-side handles are inheritable, and `PROC_THREAD_ATTRIBUTE_HANDLE_LIST`
restricts `CreateProcessW` inheritance to those exact handles. Parent read handles are
made non-inheritable before process creation; redundant child-side copies are closed in
the parent immediately after creation.

Independent reader threads drain stdout and stderr concurrently. Each stream retains no
more than its configured byte limit but continues draining after the limit, preventing a
full pipe from blocking the workload. Captured values remain bytes. UTF-8 decoding is an
optional factual projection, and invalid text never invalidates or changes the retained
bytes. Checksums cover the retained representation only, never an unretained complete
stream.

EOF, truncation, reader failure and incomplete finalization remain distinct. A root exit
does not finalize capture while a descendant still owns a pipe. Finalization has a bounded
wait, so it reports `incomplete` instead of blocking indefinitely. Job termination and
output finalization are separate observations. Raw output is returned only through the
adapter-local capture result; it is not logged, journaled, persisted or published as an
artifact by this driver.

Closed streams receive an explicit pipe with no retained parent reader. Discard streams
are drained without retaining or exposing payload bytes. Successful cleanup closes the
parent copies and reader resources idempotently; a failed close remains unproven cleanup.

- `TruncatedOutput != CompleteOutput`
- `ObservedOutput != PersistedOutputMetadata`
- `CapturedOutput != PublishedArtifact`
- `TerminationProven != OutputComplete`
- `SeparateStreams != GlobalOutputOrdering`

## Job Object resource limits

The driver maps effective Sandbox resource grants into a Windows-specific policy without
changing the frozen Sandbox contracts. Process count, per-process memory, aggregate Job
memory, process/Job CPU time and CPU rate are distinct dimensions. Requested values are
checked against the effective grant before any Job configuration; a larger request fails
before process creation.

Capabilities are probed at runtime on temporary anonymous Jobs. Every dimension reports
its own configurable/observable state. A successful Win32 call is followed by
`QueryInformationJobObject`; only an exact query result becomes an active enforcement
fact. Observable accounting never upgrades an unavailable or failed enforcement.

Required limits fail closed when capability probing, configuration or verification fails.
Optional limits may proceed, but their result explicitly remains unavailable,
observable-only or failed. Job configuration occurs after creation of the anonymous Job
and before `CreateProcessW`; therefore all required enforcement is verified before any
user process exists, assignment occurs while suspended, and user code still resumes only
after containment verification and authority/fencing revalidation.

Job accounting exposes active process count, CPU accounting and peak memory. These are
observations, not causal violation notifications. V1 records child rejection/process exit
separately and does not label an exit as OOM, CPU violation or successful termination
without a corresponding host fact. Wall-clock timeout remains owned by process
supervision and is not translated into a Job CPU limit.

Job limits apply to descendants according to Windows Job semantics. No breakaway fallback
is enabled. They constrain operational resource impact but retain the filesystem, network
and identity authority of the host token.

- `ObservableResource != EnforcedResource`
- `WallClockTimeout != CPUTimeLimit`
- `RequiredResourceEnforcement => ConfiguredBeforeUserCode`
- `JobResourceLimits != SecurityIsolation`

## Execution authority and end-to-end fencing

Every mutating Windows adapter is constructed with an explicit
`WindowsExecutionAuthorityGuard` and attempt-bound authority context. There is no
production no-op or permissive default. The guard coordinates validation but does not
become an authority: governance remains the grant authority, Coding Sessions remains the
ownership/fencing authority, Sandbox owns execution contracts, and Repository Runtime
retains repository mutation authority.

The driver-local execution grant binds subject, requester, workload, plan, attempt,
workspace, capabilities, resource grants, operation set, policy, revision, status and
expiry. The external grant validator confirms identity/current validity. The guard then
checks exact correspondence, current fencing and any required precondition immediately
before the host effect. It records only factual validation/effect flags and decision codes;
bearer material is not persisted or logged.

Workspace directory creation, each materialization write, temporary-copy replacement,
readonly mutation, sealing state, destructive cleanup, Job creation/configuration, stdio
handle setup, process creation, Job assignment, process resume and Job termination all
cross the guard independently. A generation transfer between two steps therefore blocks
the next step. Pure custody inspection, workspace verification, process observation,
metrics collection and pipe reads remain read-only and do not require fencing.

An idempotency reference does not weaken either validation. A fresh fingerprint or seal
also cannot substitute for current ownership. Missing grant/fencing/precondition
authorities fail closed. Repository writes are intentionally not implemented here and
must perform their own Repository Runtime authority validation immediately before
application.

- `ExecutionGrant != FencingToken`
- `FencingValid != ExecutionAuthorized`
- `PreviouslyAuthorized != CurrentlyAuthorized`
- `FreshPrecondition != CurrentOwnership`
- `Fencing != Idempotency`
- `SandboxEndToEndFencingEnforced != RepositoryEndToEndFencingEnforced`
- `ProcessContainment != SecurityIsolation`
- `FencingValid != ExecutionAuthorized`

## Process supervision and termination proof

Supervision queries the root process handle and Job accounting independently. A root exit
code is recorded as a root-process fact; active Job processes keep the execution running.
Elapsed time uses a monotonic clock. A timeout observation only makes termination eligible—it
does not request termination and cannot create proof.

Cancellation intents are idempotent factual requests. Termination remains a separate,
authorized and fenced mutation using `TerminateJobObject`, never root-PID-only termination.
Natural exit observed before that effect is reported without attributing causality to the
request. Confirmation produces a proof only after a current observation shows the root
inactive and zero active processes in the Job. Query failure yields unverified state.

Anonymous Job/process handles cannot be recovered after restart. Loss of custody is therefore
reported as orphaned/reconciliation-required; historical proofs remain historical and are not
treated as fresh host observations.

- `Timeout != TerminationProof`
- `CancellationRequested != ProcessTerminated`
- `RootExit != SandboxTermination`
- `ExitCodeZero != ExecutionSuccess`
- `KillOnJobCloseConfigured != TerminationProven`
- `PID != SandboxProcessIdentity`
# Secret materialization V1

The concrete driver resolves opaque references only through an explicitly injected provider,
after execution authority, exact subject/workload/plan/attempt/workspace scope, grant, expiry,
and usage validation. V1 supports only explicitly requested child environment delivery. Pipe
and temporary-file delivery are unavailable; argv delivery is forbidden.

- `SecretReference != SecretValue`
- `SecretValueInArgv = Forbidden`
- `EnvironmentDelivery != SecretPersistence`
- `RevocationRequested != RevocationProven`
- `Replay != SecretRematerialization`

The child environment block is constructed only for suspended process creation. The driver
then drops its environment projection, zeroes its mutable material buffer, and requires the
provider to prove lease revocation before resuming user code. Safe facts contain only opaque
identity, scope, mode, state, and a non-secret fingerprint. Replay never calls the provider;
an historical materialization without proven revocation becomes reconciliation-required.

Environment delivery does not provide strong confidentiality from the authorized workload.
A workload that receives a secret can voluntarily expose it in its own stdout or stderr;
preventing that behavior belongs to a stronger containment and output-policy layer.

## Network policy V1

The driver represents `disabled`, `loopback_only`, `allowlisted`, and
`unrestricted_by_driver_but_governed` explicitly. The default Windows capability discovery
classifies all restrictive profiles as unavailable: Job Objects provide process-tree custody,
but do not provide network isolation, and V1 does not create persistent or shared global
firewall rules. A required restrictive profile therefore blocks process start without a
silent downgrade. An optional unsupported profile remains a factual, non-enforced result.

`unrestricted_by_driver_but_governed` performs no network mutation. It still requires an
exact workload/plan/attempt/workspace capability grant and does not grant Search or external
egress authority. Injectable mechanisms must prove descendant, IPv4, IPv6, TCP, UDP,
privilege, configuration, verification, and attempt-owned cleanup coverage before a
restrictive profile can be treated as enforceable.

- `NetworkPolicyDeclared != NetworkPolicyEnforced`
- `JobObject != NetworkIsolation`
- `SandboxNetworkCapability != SearchAuthorization`
- `SandboxExecutionGrant != ExternalEgressAuthorization`
- `RequiredNetworkEnforcement => ConfiguredBeforeUserCode`
- `NetworkCleanupRequested != NetworkCleanupProven`

## Output publication and cleanup V1

Only outputs registered explicitly for an exact workspace and logical output path can be
inspected. Inspection produces safe metadata and a content fingerprint; it does not publish
the file. Local publication copies verified bytes to a temporary file inside the configured
custody root, verifies the copy, revalidates execution authority and fencing, and promotes it
atomically. The workspace source remains in place. External/global artifact publication is
unavailable in V1, and local custody never establishes artifact trust.

Publication identities are idempotent when the verified content agrees. Reuse of the same
identity with different content fails closed. Incomplete publication and cleanup facts become
reconciliation-required on replay; replay performs neither republication nor destructive
cleanup. Cleanup is ordered so output evidence and publication complete before handles and
workspace state can be removed. Destructive workspace cleanup revalidates authority and
fencing immediately before its callback.

- `OutputFile != PublishedArtifact`
- `ExecutionSuccess != ArtifactPublicationSuccess`
- `PublishedArtifact != TrustedArtifact`
- `CapturedOutput != PublishedArtifact`
- `CleanupRequested != CleanupProven`
- `Replay != ArtifactRepublication`
- `Replay != DestructiveCleanup`

## Durable driver state and restart V1

The driver-local SQLite store is versioned and append-only. It records only safe host-specific
metadata: opaque attempt/workspace references, ordered event kinds, historical PID
observations, safe component states, termination-proof references, and checksummed payloads.
It never records Win32 handle values, secret or environment plaintext, arbitrary stdout or
stderr bytes, or host absolute paths. Duplicate identical events are idempotent; contradictory
identities, sequence gaps, checksum corruption, and incompatible schema versions fail closed.

Replay is projection only. Because V1 Job Objects are anonymous, their handles cannot be
reopened after a Synapse restart and descendant membership cannot be reproved from a PID.
An attempt that was resumed without a durable termination proof is therefore classified as
orphaned and reconciliation-required. The historical PID remains an observation and is never
used to call `OpenProcess`, terminate a process, or establish current identity.

The reconciliation planner emits required manual or safe-inspection actions with an empty
automatic-action set. It does not create/resume/terminate processes, materialize workspaces,
resolve secrets, publish artifacts, mutate network policy, or clean state. Any later cleanup
must obtain current authority and fencing through the existing guarded cleanup boundary.

- `PersistedHandleMetadata != RecoverableHandle`
- `HistoricalPID != CurrentProcessIdentity`
- `Replay != HostObservation`
- `Replay != ExternalReexecution`
- `Replay != ArtifactRepublication`
- `Replay != SecretRematerialization`
- `Replay != DestructiveCleanup`
- `HistoricalAuthorization != CurrentAuthorization`
- `HistoricalFencing != CurrentFencing`

## Local Composition Root and operational health

`synapse.sandbox_driver_composition` is the only concrete Windows driver Composition Root.
It is opt-in and is not imported by global bootstrap. All operational dependencies are
explicit: process API, execution and grant validators, fencing, authority-context lookup,
secret provider, network mechanism, custody roots, command configuration, and durable-state
path. Missing dependencies remain unavailable and never select permissive fallbacks.

Build constructs in-memory adapters only. Durable SQLite creation and validation occur solely
through explicit `initialize()`. Static health does not look up contextual grants/fencing,
resolve secrets, create workspaces or processes, publish artifacts, or perform cleanup.
Controlled host capability discovery is separated as `probe()`.

Health reports capability-specific classifications rather than a global readiness boolean.
Execution readiness is evaluated for an explicit profile. L1 Job-contained execution with
governed unrestricted networking can be ready when its dependencies are configured; profiles
requiring network-disabled enforcement or L2 restricted identity remain unavailable in V1.
The configuration fingerprint contains non-secret semantic configuration only and excludes
secret values and host absolute paths.

- `Build != Initialize`
- `DriverHealth != ExecutionProfileReadiness`
- `Implemented != Available`
- `ProcessContainment != SecurityIsolation`
- `WorkspaceContainment != RestrictedIdentity`
- `NetworkPolicyDeclared != NetworkPolicyEnforced`
- `LocalComposition != GlobalActivation`
