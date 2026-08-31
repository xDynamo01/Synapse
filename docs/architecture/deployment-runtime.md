# Deployment Runtime

## Slice 2 boundary

The Deployment Runtime foundation is a pure, provider-neutral bounded context. This
slice defines immutable identities, value objects and factual descriptors only. It
does not authorize or execute deployment, access artifacts, select a provider,
persist history, apply or verify a revision, promote a rollout, or perform rollback.

The domain has no dependency on Sandbox, Repository Runtime, Project Governance,
Private Evals, Coding Sessions, provider implementations, filesystem, processes or
network APIs. Future adapters and integrations must point toward `deployment`; the
domain must never import them. No production bootstrap imports this package.

## Identities and references

Intent, release, deployment attempt, environment, target, slot, revision, rollout,
promotion and rollback attempt have distinct typed identities. Request occurrence,
semantic fingerprint and idempotency key are also separate concepts:

`IdempotencyKey != DeploymentIdentity`

Authorization, apply receipt, observation, verification, provenance, custody and
secret values are represented only by bounded opaque references. A reference records
correspondence; it does not assert availability, validity or outcome.

## Environment, target and revision

`DeploymentEnvironmentV1` describes a logical environment classification, policy
reference and bounded namespaced metadata. It contains no credential or provider
endpoint. `DeploymentTargetV1` binds a target to that environment, an opaque adapter
binding, a provider-neutral target class, optional slot and capability references.

Target and slot are separate. A mechanism that has no slot uses explicit absence.
Desired and observed revisions use different public types. Revision identity is an
opaque stable fact bound to an artifact fingerprint rather than a mutable filename.

`DesiredRevision != ObservedRevision`

## Artifact boundary

`DeploymentArtifactRefV1` carries an opaque artifact identity, fingerprint reference,
provenance reference, optional custody reference and safe media classification. It
contains neither bytes nor a concrete host path and exposes no availability or
deployability boolean.

`ArtifactReference != ArtifactAvailable`

`ArtifactPublished != ArtifactDeployable`

## Intent, release and attempt

`DeploymentIntentV1` binds the requested artifact, logical environment, exact target,
desired revision, requester, policy, idempotency key and causal context. Its semantic
fingerprint includes deployment semantics and excludes request identity, idempotency,
occurrence, correlation and causation.

`DeploymentReleaseV1` is the logical deployment unit derived from an intent reference.
It does not assert that apply started. `DeploymentAttemptV1` is a separate numbered
attempt binding the release, target, artifact, desired revision, policy and
configuration fingerprint. It carries no provider receipt.

`DeploymentIntent != DeploymentAuthorization`

`DeploymentIntent != Release`

`Release != DeploymentAttempt`

## Future evidence, rollout and rollback

Apply receipts, observations and verifications remain distinct opaque references:

`ApplyReceipt != DeploymentVerification`

`Observation != Verification`

Rollout and promotion descriptors provide only identities, stage/slot references and
policy binding. They implement no canary or advancement behavior. Rollback attempts
bind distinct source and intended revisions plus an authorization reference; they do
not assert application or verification.

`RollbackIntent != RollbackApplied`

Secret requirements may use `SecretReference`, but no domain contract accepts secret
material or provider credentials.

`SecretReference != SecretValue`

## Slice 3 factual state machines

All four lifecycles are pure reducers over immutable, versioned events. An event
binds its exact subject identities, prior/resulting states, causal references and
occurrence. Authorization, apply receipt, observation and verification remain
separately typed optional facts and are required only by the transitions that consume
them. Failure and uncertain outcomes require an explicit closed failure classification.

Reducers read no clock, randomness, filesystem, process, network or provider. Replaying
events only derives an immutable projection. Each projection records event identity and
fingerprint: the same identity and fingerprint is idempotent; the same identity with
different content is contradictory.

`Replay != Redeploy`

`Replay != Rollback`

### Deployment lifecycle

The main path is:

`proposed -> authorization-pending -> authorized -> prepared -> applying -> applied -> verifying -> verified -> promotion-pending -> promoted`

Explicit lateral states preserve denial, preparation/apply/verification failure,
partial apply, unknown apply outcome, unavailable verification, rollback requirement,
reconciliation and manual intervention. `applied` requires an apply receipt but remains
non-terminal. `verified` requires both observation and verification references but also
remains non-terminal while promotion is pending. Promotion is never inferred.

`DeploymentRequested != DeploymentApplied`

`DeploymentApplied != DeploymentVerified`

`ApplySuccess != DesiredStateVerified`

`Verified != Promoted`

### Rollout lifecycle

Rollout is a separate projection with `planned -> authorized -> in-progress ->
completed`, plus explicit pause/resume, blocked, failed, rollback-required and
reconciliation-required states. A provider-neutral stage has a positive sequence,
opaque stage and gate references, optional slot and optional abstract percentage.
Advancement requires increasing sequence; resume retains the paused stage. Completion
does not create or mutate promotion.

### Promotion lifecycle

Promotion is independently `pending -> authorized -> applied`, with denied, failed,
outcome-unknown and reconciliation-required paths. Authorization requires an explicit
accepted authorization reference; applied requires its own receipt. Deployment
verification and rollout completion do not instantiate or advance this projection.

### Rollback lifecycle

Rollback is independently `requested -> authorization-pending -> authorized ->
preparing -> rolling-back -> rolled-back -> verifying -> verified`. Denial,
preparation/rollback failure, unknown outcome, unverified rollback, reconciliation and
manual intervention remain explicit. Every event binds the exact failed/current and
intended rollback revisions; no state derives a generic "previous" revision.
`rolled-back` requires the intended artifact reference and apply receipt. `verified`
additionally requires observation and verification references.

`RollbackRequested != RollbackApplied`

`RollbackApplied != RollbackVerified`

Unknown outcomes never become inferred failures or successes. They may only advance to
`reconciliation-required`; this slice performs no reconciliation or external effect.

### Terminality

Each state exposes one of `non-terminal`, `terminal-success`, `terminal-failure` or
`reconciliation-required`. Applied and verified deployment states are non-terminal.
Promoted deployment, completed rollout, applied promotion and verified rollback are
terminal successes. Unknown, partial, unverified and manual-intervention states retain
reconciliation classification rather than fabricating external certainty.

## Slice 4 operational ports

Operational boundaries are consumer-owned `Protocol`s in `deployment.ports`. They use
only immutable provider-neutral request/result contracts. This slice supplies no
implementation, adapter, invocation orchestration or production binding.

### Artifact facts

`DeploymentArtifactFactsPort` receives the exact release, attempt, artifact and
requester context. Its result has independent availability, fingerprint correspondence
and provenance-availability dimensions, plus optional observed fingerprint, custody
reference and bounded opaque limitations. It exposes no eligibility or deployability
decision.

`ArtifactFacts != ArtifactEligibility`

### Authorization

`DeploymentAuthorizationPort` receives an explicit operation, requester, release,
attempt, environment, target, artifact, desired revision, policy and causal context.
Outcomes distinguish allowed, denied, approval-required, unavailable, stale and
expired. Only allowed requires a typed authorization reference; institutional evidence
uses separate opaque evidence references. The port cannot manufacture approval.

`AuthorizationRequested != AuthorizationGranted`

### Preparation and apply

`DeploymentPreparationPort` returns prepared, blocked, unsupported or failed. Prepared
requires a typed preparation reference and carries no receipt. `DeploymentApplyPort`
accepts only an exactly corresponding release/attempt/target/artifact/revision binding,
preparation and authorization references, typed idempotency key, semantic fingerprint
and an optional opaque fencing reference. It returns applied, partially-applied, failed
or outcome-unknown; only applied requires an apply receipt. No result contains
verification.

`Prepared != Applied`

`ApplyReceipt != DeploymentVerification`

`ApplyOutcomeUnknown != ApplyFailed`

### Observation and verification

`DeploymentObservationPort` observes the exact target and desired-revision context.
Observed results require matching observation and observed-revision facts; unavailable
and unknown remain distinct. Runtime facts and limitations are bounded opaque
references. Observation does not assess deployment success.

`DeploymentVerificationPort` is separate from apply and consumes a factual available
observation plus the exact desired revision and verification policy. Outcomes distinguish
verified, failed, unavailable and indeterminate. Verified requires its own typed
verification reference; an observation reference cannot substitute for it.

`Observation != Verification`

`ObservationUnavailable != VerificationFailed`

### Rollback boundaries

Rollback uses distinct preparation and apply ports because its attempt identity and
revision direction are different from deployment apply. Requests bind the exact target,
failed/current revision, intended rollback revision, rollback artifact and authorization.
Rollback apply additionally requires preparation, idempotency and semantic fingerprint,
with an optional opaque fencing reference. Rolled-back requires a typed rollback receipt
and never verifies automatically.

Rollback observation and verification use minimal distinct ports because
`RollbackAttemptId` cannot be substituted by `DeploymentAttemptId`. Verification accepts
only an observed revision equal to the intended rollback revision. Unknown, unavailable,
partial and failed outcomes remain separate throughout.

No promotion apply port is introduced in this slice. Promotion remains a separate future
operational boundary rather than being smuggled through deployment apply.

## Slice 5 durable journal V1

Deployment persistence is split across a pure domain contract and an inward-pointing
SQLite adapter. `deployment.persistence` owns machine kinds, journal records, append
requests/results, integrity facts, the store protocol and pure replay dispatch.
`deployment_adapters.sqlite_persistence` owns SQLite configuration, schema, transactions,
canonical serialization and reconstruction. The domain never imports the adapter.

### Schema and append-only history

Schema V1 stores deployment, rollout, promotion and rollback as separate machine streams.
Each record contains machine kind/identity, strict sequence, event identity/fingerprint,
canonical JSON payload, payload checksum, correlation, causation, occurrence, record
format and schema version. A migration identity and checksum bind the exact schema.

The event table has a composite machine/sequence primary key and a globally unique event
identity. SQLite triggers reject every `UPDATE` and `DELETE`. Append uses `BEGIN
IMMEDIATE`, verifies the schema inside the operation and atomically inserts the event and
its sequence metadata. Two writers for the same next sequence therefore cannot both win.

Only `latest + 1` is accepted. A future number is a sequence gap; an older number is a
sequence conflict. Repeating the same event identity and canonical payload is factual
idempotency. Reusing that identity for different content is a contradiction. Different
identities remain distinct facts even when their semantic content resembles each other.

### Replay and restart

History is loaded in authoritative sequence order, checksummed, canonicalized,
reconstructed into typed events and passed to the pure Slice 3 reducers. Replay performs
no artifact or authorization lookup and invokes no apply, observation, verification,
promotion or rollback port. Each machine is replayed independently; references never
advance another projection.

`Replay != Redeploy`

`Replay != Rollback`

`DeploymentReplay != RolloutAdvance`

`RolloutReplay != Promotion`

Reopening the database preserves the latest sequence and reconstructs the same
projection. The next append continues from that sequence. Applying without a final
receipt remains `applying`; unknown and unavailable outcomes remain exactly unknown or
unavailable. Restart never synthesizes external completion.

`MissingEvidence != Success`

### Corruption handling and integrity facts

Reads and replay fail closed for checksum mismatch, non-canonical or malformed payload,
unsupported schema/record version, migration mismatch, missing append-only protections,
sequence gap, machine/event mismatch, contradictory identity and reducer-invalid
history. No repair or outcome inference is attempted.

Integrity and health are factual dimensions: store availability, schema compatibility,
append integrity, replay availability and corruption detection. There is no aggregate
`ready` claim. Persisted payloads consist only of safe domain identities, references,
states and classifications; the schema has no field for secret material, artifact bytes,
host paths, credentials or raw provider payloads.

## Slice 6 Governance authorization binding

The consumer-owned `deployment_integrations` package translates exact Deployment
authorization intents to the existing Decisions and Approvals authority. It does not own
policy, grant approval, duplicate the approval ledger or import back into `deployment`.

`DeploymentRuntime != ApprovalAuthority`

Prepare/apply, rollout advancement, promotion and rollback prepare/apply use distinct
typed intents. Every intent binds requester, release and attempt identity, environment,
target, artifact and revision, operation, policy, correlation, causation and semantic
fingerprint. Authority results remain factual: allowed, denied, approval-required,
unavailable, stale and expired are not collapsed.

The safe evidence projection contains only the decision identity, typed authorization
and evidence references, exact scope, policy, outcome, validity, authority/version and
fingerprints. Raw Governance metadata and approval payloads are not copied into the
Deployment journal.

`AuthorizationRef != Authorized`

Correspondence is checked again before an authorization event can be produced. Any
requester, target, environment, artifact, revision, attempt, operation, policy or
fingerprint mismatch fails closed. An allowed fact creates only an existing Slice 3
lifecycle event; it never calls an apply, promotion or rollback effect.

`DeploymentAuthorized != DeploymentApplied`

Authority revision is retained as historical evidence only and is never projected as an
ownership generation or fencing token.

`AuthorizationRevision != FencingGeneration`

Repeated identical decisions are idempotent by identity and fingerprint; contradictory
content under the same identity is rejected. Replay reads the historical authorization
reference without invoking Decisions or Approvals again. A future external operation
must independently validate current authorization according to its policy.

`Replay != Reauthorization`

## Slice 7 Artifact eligibility

Artifact eligibility is a pure assessment over explicit, typed facts. A reference is not
an observation, current availability is not eligibility, and neither historical custody
nor a provenance reference proves current validity.

`ArtifactFacts != ArtifactEligibility`

`ArtifactAvailable != ArtifactEligible`

The request binds the exact release, attempt, environment, target, artifact, desired
revision, policy/version and semantic fingerprint. Provenance evidence additionally
binds producer, artifact fingerprint and its release/attempt. Cross-attempt, policy,
artifact or revision reuse fails closed.

The assessment distinguishes eligible, ineligible, unavailable, stale,
provenance-missing, custody-unavailable and indeterminate. Fingerprint mismatch produces
a stale assessment and never rewrites the expected fingerprint.

`FingerprintMismatch != NewArtifactVersion`

The consumer-owned custody adapter calls only the existing abstract Sandbox custody
inspection contract. It maps a current inspection to availability and fingerprint facts;
it cannot request a source path, materialize, copy or execute the artifact.

`HistoricalCustody != CurrentAvailability`

Private Eval and Governance inputs remain opaque evidence references. An eval verdict
can satisfy an eligibility policy requirement, but it neither proves artifact availability
nor grants deployment authorization. Eligibility results intentionally carry no
authorization reference.

`ArtifactEligible != DeploymentAuthorized`

`EvalPass != DeploymentAuthorization`

Assessment fingerprints include every decision-supporting fact while excluding
correlation and occurrence metadata. Persisted results are historical facts: replay
returns the stored assessment without consulting custody, evals or Governance again.
Any future apply must satisfy its then-current freshness and authorization policy.

`Replay != ArtifactReassessment`

## Slice 8 Operational environment, target, slot and revision contracts

Operational descriptors extend the stable V1 identities by composition. Environments
carry a logical operational class, tier, policy and bounded capability requirements;
classification remains descriptive and never grants deployment authority.

`EnvironmentClassification != DeploymentAuthorization`

Targets describe a provider-neutral kind, opaque adapter binding, slot capability,
declared/required/observed capability facts, safe configuration references, optional
verification and rollback capabilities, opaque secret requirements and whether external
egress is required. They contain no host path, URL, port, credential value or raw
provider payload. The configuration fingerprint is derived only from immutable semantic
configuration.

`AdapterBindingRef != AdapterAvailable`

`TargetDeclaredCapability != CapabilityAvailable`

`TargetRequiresEgress != EgressAuthorized`

Slots have their own identity and target binding, a logical role and independently
observed active/inactive/unknown state. An optional observed revision must carry the
same observation reference. Single-slot and multi-slot are declared target capabilities,
not operational availability proofs.

`Target != Slot`

`SlotIdentity != ActiveSlotObservation`

Desired operational revisions bind artifact identity/fingerprint, target configuration
fingerprint, deployment configuration references and policy/version. Their deterministic
fingerprint excludes occurrence and correlation context. Observed revisions remain
observation facts and may legitimately differ from the desired revision.

`DesiredRevision != ObservedRevision`

Pure correspondence classifies match, mismatch, unavailable and indeterminate without
performing verification. Target correspondence separately checks environment, slot,
artifact/revision, attempt, adapter binding, configuration fingerprint and minimum
capability requirements before any future apply boundary is reached.

`RevisionMatch != DeploymentVerified`

## Slice 9 Generation, fencing and idempotency authority

Deployment owns a durable, monotonic `uint64` generation independently for each exact
release, target, target-slot, rollout or rollback-attempt scope. The SQLite authority
uses one atomic compare-and-advance transaction, so transfer and reacquisition always
advance the scope generation and competing writers cannot both acquire the same next
generation. Wall-clock time, authorization revisions and Coding Sessions leases are not
generation sources.

`AuthorizationRevision != FencingGeneration`

`CodingSessionsLease != DeploymentFencingToken`

The typed token binds the exact scope, generation, owner, authority identity/version,
occurrence and optional semantic fingerprint. Validation requires exact equality and
reports valid, stale, invalid, unavailable or mismatched facts. A valid token is a
mutation precondition only; it never supplies authorization, policy approval, artifact
eligibility, verification or a successful result.

`ValidFencingToken != DeploymentAuthorization`

`Applied != Verified`

Mutable release, artifact-selection, desired-revision, target-slot, apply, rollout,
promotion, rollback, evidence-publication and reconciliation operations require fencing.
Read-only observation and verification do not. The foundation records acceptance facts
only and has no concrete apply, rollout, rollback or Sandbox execution path.

Idempotency is scoped by the mutation class and exact Deployment scope. Reusing a key
with the same semantic fingerprint is idempotent; changing its semantics is a
contradiction. A repeated key presented with stale fencing remains stale and cannot be
upgraded by the earlier acceptance.

`IdempotencyKey != FencingToken`

Generation and idempotency histories are append-only, checksummed and replayed without
external effects. Restart preserves the latest generation and never regresses it.
Schema, checksum, lineage or monotonicity damage makes health fail closed instead of
projecting a usable authority.

`Replay != Reapply`

## Slice 10 Local Service/Application Adapter V1

The local adapter supports only local, single-host service/application targets with an
explicit adapter-local binding. Domain contracts never carry a host path, endpoint or
provider payload. The adapter resolves artifact custody and its controlled revision root
from local configuration, then prepares a deterministic layout with separate immutable
revision content, runtime state, logs and temporary preparation data.

Preparation copies into a temporary revision, verifies the artifact fingerprint,
revalidates authorization, current Deployment fencing, eligibility and target
correspondence, makes revision content read-only and atomically promotes the directory.
An existing identical manifest is factual `already-prepared`; conflicting content or an
incomplete temporary directory fails closed and requires reconciliation.

`PreparedRevision != ActiveRevision`

`Replay != Reprepare`

The resulting consumer-owned handoff translates to existing Sandbox workspace and
materialization request DTOs. It carries only opaque secret references, resource/network
requirements, command entrypoint and Deployment authority references. Translation never
calls the Concrete Sandbox Driver, starts a process or activates a target.

`DeploymentPreparation != SandboxExecution`

`SandboxGrant != DeploymentAuthorization`

`DeploymentFencing != SandboxFencing`

The Deployment token is retained only as a factual handoff reference. A future Sandbox
workspace mutation must independently obtain and validate Sandbox-owned fencing. No
Repository checkout, Git mutation, active-slot switch, rollback, promotion or bootstrap
wiring belongs to this adapter.

## Slice 11 Local Apply Orchestration and factual receipts

The consumer-owned local apply orchestrator accepts only a corresponding prepared
revision and revalidates current Deployment authorization and fencing before each next
effect: apply journal start, active-state staging, Sandbox start and atomic active-pointer
promotion. Previously accepted authorization is historical evidence, not proof that the
next effect remains authorized.

`PreviouslyAuthorized != CurrentlyAuthorized`

The active-state adapter keeps immutable prepared content separate from a mutable
`active.json` reference and runtime state. It writes and rereads a temporary state,
preserves the prior active reference as history, then promotes atomically. It never
deletes either revision and does not claim rollback eligibility.

`PreparedRevision != ActiveRevision`

Sandbox execution is reached through a narrow bridge to the frozen Windows process
driver. The configured Sandbox grant and Sandbox fencing reference must correspond
independently; the Deployment token is retained only as Deployment evidence. Suspended
creation, job assignment, containment verification and resume remain Sandbox-owned.

`DeploymentFencing != SandboxFencing`

`SandboxExecutionSuccess != DeploymentVerified`

An apply receipt records release, attempt, target, environment, applied and prepared
revision references, Sandbox execution, active-state mutation, previous active revision,
occurrence, limitations and semantic fingerprint. It contains no observation or
verification claim. The journal records `PREPARED -> APPLYING` followed by `APPLIED`,
`APPLY_FAILED`, `PARTIALLY_APPLIED` or `APPLY_OUTCOME_UNKNOWN`; it never synthesizes
`VERIFIED`.

`ApplyReceipt != DeploymentVerification`

`Applied != Verified`

Receipts and incomplete staging survive restart. A conclusive repeated apply returns the
same receipt without another start. Partial or unknown prior effects require
reconciliation and are not automatically retried. Journal replay and active-state
inspection are read-only.

`Replay != Redeploy`

## Slice 12 Independent local observation and verification

The local observer reads the controlled target's current `active.json` and consumes
runtime presence only through a factual read port. An apply receipt may supply
correlation identifiers, but is never used as proof of the current active revision or
process. Observation does not acquire Deployment fencing and does not mutate the active
pointer, process, workspace or revision.

`ApplyReceipt != Observation`

`ReadOnlyObservation != DeploymentMutation`

Observed facts bind release, attempt, target, environment, slot, active revision,
revision fingerprint, active-state fingerprint, evidence policy and observation time.
Unavailable, incomplete and internally inconsistent states remain explicit. A PID or
historical launch reference alone is not process identity, liveness or containment
proof.

The separate verifier compares desired state with that observation and a minimal policy.
It alone creates a `VerificationReference`. Positive correspondence of every required
fact is necessary for `VERIFIED`; a proven mismatch is `VERIFICATION_FAILED`, while
missing or stale evidence remains unavailable or indeterminate. A fresh reread of the
active-state fingerprint detects target changes between observation and verification
without fencing the read.

`Observation != Verification`

`RevisionMatch != DeploymentVerified`

The consumer-owned flow appends `APPLIED -> VERIFYING` and then `VERIFIED`,
`VERIFICATION_FAILED` or `VERIFICATION_UNAVAILABLE`. Journal replay retains historical
references only and never invokes the observer or verifier.

`Replay != Reobserve`

`Replay != Reverify`

## Slice 13 Local rollback through independent verification

Local rollback names its intended revision explicitly. The previous active revision is
only a historical/source fact and never becomes an eligible rollback target by
implication. Current artifact availability, fingerprint, provenance, custody, policy
and target correspondence must be supplied again before preparation.

`PreviousRevision != RollbackEligibleRevision`

Rollback preparation and apply use rollback-attempt fencing and a rollback-specific
authorization binding. The original deployment apply authorization and Sandbox fencing
cannot authorize these Deployment mutations. Authorization and fencing are revalidated
between preparation, staging, Sandbox start and active-pointer promotion.

`DeploymentApplyAuthorization != RollbackAuthorization`

The local adapter prepares the explicitly intended immutable revision, preserves the
currently active revision and history, and atomically promotes only when the recorded
source revision is still active. It retains replaced content, receipts and evidence;
destructive cleanup remains outside this slice.

The rollback receipt records source, intended and applied revisions, preparation,
Sandbox execution and active-state mutation, but contains no verification claim.
Partial and unknown effects require reconciliation and are never automatically retried.

`RollbackApplied != RollbackVerified`

Independent observation rereads the current active target and consumes process facts
through the existing read port. The verifier compares the observed target with the
explicit intended rollback revision and policy; neither component trusts the receipt as
proof.

`RollbackReceipt != RollbackObservation`

`RollbackObservation != RollbackVerification`

Rollback journal replay projects historical transitions only. It does not prepare,
apply, observe or verify again. An incomplete `ROLLING_BACK` state remains factual and
requires reconciliation.

`Replay != Rollback`

## Slice 14 E2E readiness audit

Status: **APPROVED FOR A SEPARATE FINAL-FREEZE SLICE**.

The Slice 14 campaign reconciles the local V1 lifecycle through controlled
prepare/apply/observe/verify and explicit rollback/observe/verify journeys. Receipts,
observations and verifications retain separate identities; partial or unknown effects
remain reconciliation requirements; restart and replay do not invoke external effects.

Current focused, architecture, Ruff, authoritative Mypy and deterministic global
regression gates passed. Exact results and the explicit test-only Mypy limitation are
recorded in
[`deployment-runtime-e2e-readiness-audit.md`](../audits/deployment-runtime-e2e-readiness-audit.md).

This slice adds no global Composition Root, bootstrap activation, provider capability,
contract change or freeze declaration.

## Slice 15 final audit and freeze

Status: **IMPLEMENTED / OPERATIONALLY COMPLETE / FROZEN**.

The final audit freezes the current Deployment V1 module/public surface, journal and
authority schemas, record formats, lifecycle/authority distinctions, adapter and
integration edges, local E2E journeys, restart/replay behavior and deliberate
limitations. The exact baseline and current gates are recorded in
[`deployment-runtime-final-freeze-audit.md`](../audits/deployment-runtime-final-freeze-audit.md).

Deployment remains absent from global bootstrap. Freeze is local to this bounded
context and does not imply global composition, production provider availability or
Backend READY. Any future public-contract, schema, migration, authority, governed-edge
or activation change requires explicit unfreeze governance.

## Global Composition Root Slice 2 — local composition surface

The explicitly governed post-freeze integration adds `synapse.deployment_composition`
outside the Deployment domain. Its build is inert: it constructs SQLite journal and
authority adapters, fencing authority and only complete configured operational groups,
without opening the database or activating lifecycle resources.

`start()` is the explicit I/O boundary. It opens managed resources, initializes the
append-only journal and authority schemas and reports factual persistence/fencing
health. Partial apply, verification or rollback dependency groups fail closed. Missing
groups remain `unavailable`; reconciliation is preserved as an explicit input fact and
never converted into recovery success.

The three new governed edges are limited to composition pointing inward to
`deployment`, `deployment_adapters` and `deployment_integrations`. No reverse import,
SCC, API, Commands or global bootstrap activation is added.
