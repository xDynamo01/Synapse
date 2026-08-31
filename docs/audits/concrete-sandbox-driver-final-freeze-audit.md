# Concrete Sandbox Driver Final Freeze Audit

## Scope and decision boundary

This audit reconciles Concrete Sandbox Driver Slices 1–16 and freezes only the
capabilities factually implemented by the local Windows Driver V1. It does not
claim a generic secure sandbox and does not activate the driver in global bootstrap.

Aggregate classification, subject to the gates recorded below:

`Concrete Sandbox Driver — IMPLEMENTED / OPERATIONALLY COMPLETE / FROZEN`

## Frozen inventory

- `synapse.sandbox_drivers`: 14 Python modules and 119 deliberate public exports.
- `synapse.sandbox_driver_composition`: 2 Python modules and 10 deliberate public exports.
- Local composition entry point: `build_windows_sandbox_driver`.
- Driver-state persistence: schema ID `windows-sandbox-driver-state-v1`, version 1.
- Architecture baseline: runtime graph 292 edges; source graph 327 edges; no driver SCC.

The exact module sets and export fingerprints are enforced by
`tests/architecture/test_concrete_sandbox_driver_freeze.py`. Private classes,
helpers, implementation ordering beyond safety-critical sequencing, and incidental
module globals are not declared public freeze surface.

## Capability matrix

| Capability | Frozen classification | Limitation |
| --- | --- | --- |
| L0 supervised execution | AVAILABLE | Windows process prerequisites required |
| L1 Job-contained execution | AVAILABLE | Process containment, not security isolation |
| Workspace containment | AVAILABLE | Restricted identity is separate and unavailable |
| Artifact input custody | AVAILABLE | Governed local custody only |
| Structured command execution | AVAILABLE | Explicit entrypoint policy |
| PowerShell explicit interpreter | AVAILABLE WHEN CONFIGURED | Must be explicitly permitted |
| Python explicit interpreter | AVAILABLE WHEN CONFIGURED | Must be explicitly permitted |
| `.bat` / `.cmd` | UNSUPPORTED | V1 does not use file association or implicit shell |
| Bounded stdout/stderr capture | AVAILABLE | Truncation remains explicit |
| Process-count/resource enforcement | CAPABILITY-SPECIFIC AVAILABLE | Requires successful host probe |
| Execution grant enforcement | AVAILABLE | Grant is not fencing token |
| Sandbox end-to-end fencing | AVAILABLE | Separate from repository fencing |
| Environment secret delivery | AVAILABLE | Ephemeral and redaction-safe |
| Pipe/temp-file secret delivery | UNAVAILABLE | No silent fallback |
| Local artifact publication | AVAILABLE | Publication does not imply trust |
| Global/external publication | UNAVAILABLE | Outside local driver custody |
| Durable replay/reconciliation | AVAILABLE | Replays facts only |
| Active anonymous Job recovery after restart | UNAVAILABLE | Historical PID is not live identity |
| Restricted identity / L2 | UNAVAILABLE | No AppContainer or restricted token |
| Disabled/loopback/allowlisted networking | UNAVAILABLE | No restrictive enforcement mechanism |
| Unrestricted-by-driver-but-governed networking | CONDITIONAL | Requires upstream authority; driver grants no egress |
| Container/VM isolation | UNAVAILABLE | Outside V1 |
| Repository end-to-end fencing | NOT IMPLEMENTED HERE | Repository Runtime retains authority |
| Global bootstrap activation | ABSENT | Composition remains local and opt-in |

## Security and authority baseline

- `ProcessContainment != SecurityIsolation`.
- `WorkspaceContainment != RestrictedIdentity`.
- `JobObject != NetworkIsolation`.
- `SandboxEndToEndFencingEnforced != RepositoryEndToEndFencingEnforced`.
- Coding Sessions owns fencing generation.
- Governance/execution authority owns grants.
- Sandbox owns execution contracts.
- The Windows driver applies host effects.
- Repository Runtime retains repository mutation authority.

No authority is transferred by composition or by a capability observation.

## Persistence, replay, and recovery baseline

The Windows driver-state schema V1 stores append-only, checksum-protected event
facts. SQLite triggers reject update and delete. Persisted facts contain safe
references and factual state, never raw handles or secret plaintext.

- `Replay != HostObservation`.
- `Replay != ExternalReexecution`.
- `Replay != SecretRematerialization`.
- `Replay != ArtifactRepublication`.
- `Replay != DestructiveCleanup`.
- `HistoricalPID != CurrentProcessIdentity`.

Recovery projections preserve uncertainty and request external/manual reconciliation
where live handles or current host truth are unavailable.

## Execution and data-separation baseline

- `ExecutionGrant != FencingToken`; `FencingValid != ExecutionAuthorized`;
  `Fencing != Idempotency`; a stale writer has zero next-mutation effect.
- `UserCodeExecution => JobContainmentAlreadyEstablished`;
  `ProcessCreated != ProcessStarted`; `Timeout != TerminationProof`;
  `CancellationRequested != ProcessTerminated`; `RootExit != SandboxTermination`.
- `TruncatedOutput != CompleteOutput`; `CapturedOutput != PublishedArtifact`;
  `OutputFile != PublishedArtifact`; `PublishedArtifact != TrustedArtifact`.
- `SecretReference != SecretValue`; secret values in argv are forbidden.

## Local composition and operational reconciliation

Build remains side-effect free and opt-in. Persistence initialization is explicit;
health is side-effect free; readiness is profile-specific. There are no driver
imports or instances in global bootstrap. The Slice 16 integrated campaign covers
the nominal materialization-to-replay journey and partial failures before user-code
execution. Focused suites retain coverage for workspace races, custody, command
policy, containment, supervision, bounded output, resources, authority/fencing,
secrets, networking, publication, cleanup, persistence, restart, and readiness.

## Final verification

The freeze decision requires current green results for the dedicated freeze gate,
the full Concrete Sandbox Driver/composition suite, the E2E/failure suite,
architecture, Ruff, authoritative Mypy, deterministic global regression with exact
coverage, diff integrity, residual audit, and zero staged files. Exact results are
recorded in the Slice 17 delivery report.

## Freeze decision

The component may be classified as frozen only when every final verification gate
is green with no timeout, omission, duplicate, reverse import, bootstrap activation,
residual controlled artifact, or unreviewed internal blocker.
