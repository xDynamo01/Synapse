# Coding Sessions

Status: **Slice 13 — Repository Runtime compatibility adapter implemented; globally not activated**

Coding Sessions owns durable coordination of an explicitly bound coding session.
It does not own repositories, authorization, isolated execution, worker scheduling,
Missions, evaluation or deployment. Slice 2 creates only the pure immutable
foundation under `synapse.coding_sessions`; no integration or runtime operation is
introduced.

## Canonical format V1

`coding-sessions-json-v1` is the sole accepted format. The encoder wraps every
semantic value with the explicit format marker, emits deterministic ASCII JSON with
sorted mapping keys and hashes the bytes with SHA-256. Mutable sequences, floats,
bytes, unknown objects and unknown format versions fail closed. Tuples retain their
positional meaning; frozensets and mappings are normalized independently of input
ordering.

Canonical encoding helpers remain internal. Public callers construct a
`CodingSessionFingerprint` through `from_content`; a fingerprint is always lowercase
`sha256:<64 hex>`.

## Identity semantics

The distinct identity types are coding session, session fact, checkpoint, intent,
external receipt, lease fact and recovery artifact. Each is a frozen value with a
separate prefix and versioned domain separator. Equal stable keys cannot make two
different identity types interchangeable.

A `CodingSessionIdentity` is derived only from an admitted stable session key. It
does not contain or derive from lifecycle, outcome, worker, process, evaluation or
deployment facts. Its `coding-session:<64 hex>` shape can be projected by a future
adapter into the already frozen Repository Runtime integration contract without the
pure domain importing that contract.

There is no current/latest session identity and no ambient lookup semantics.

## Reference model

Actor, project, task, purpose and correlation are bounded opaque local references.
External repository, checkout, worktree, worker, Sandbox, authorization, approval,
Private Eval, artifact and deployment-candidate references are distinct frozen
types carrying only:

- producer reference;
- exact artifact type;
- producer version;
- opaque identity;
- optional fingerprint.

A reference contains no producer object, payload, status, authority or inferred
truth. The future integration layer must establish correspondence; constructing a
reference never authorizes, executes, verifies, scores or publishes anything.

## Causal metadata

Future artifacts can bind a semantic identity, positive causal revision, canonical
parent/reference lineage and separate occurrence metadata. Duplicate lineage and a
fingerprint appearing as both parent and reference fail closed. Lineage collections
are immutable and canonically ordered.

Occurrence metadata is bounded, sorted and excluded from semantic content. Logging,
observation or occurrence time therefore cannot change the semantic fingerprint
unless a future fact explicitly makes time part of its own semantic content.

Errors are typed and use fixed redacted messages. Invalid values, external
identities, payloads, secrets and paths are never included in error text.

## Authority and dependency boundary

The package imports only Python standard-library pure utilities and itself. It has
no dependency on Repository Runtime, Sandbox, Workers, Missions,
Governance/Approvals, Private Evals, Deployment Runtime, persistence, adapters,
filesystem, network, subprocess or bootstrap. No existing frozen context changes in
this slice.

## Session contract

`CodingSessionContract` is the immutable declaration of one planned session. It
binds the stable session identity to actor, project, task/purpose, correlation,
policy/contract versions, causal metadata, an explicit binding and two separate
requirement collections. Its fingerprint covers semantic content and excludes
occurrence metadata.

`complete` means every binding demanded by the declared scope and requirements is
present. `valid` additionally means correspondence, version and requirement rules
hold. Neither conclusion means the session is `prepared` or `active`; both runtime
conclusions remain explicitly `not-evaluated` in this slice.

## Binding rules

A binding declares exactly one scope: `none`, `repository`, `checkout` or
`worktree`. Each level requires exactly its named repository chain and never
invents the next level. Therefore a repository reference does not select a
checkout, a checkout does not infer a worktree, and a non-repository session keeps
all three absent. Platform/context is a separate optional opaque reference.

The binding repeats session and project identity so pure assessment can establish
their correspondence. Repository-chain references must identify the same producer
and version; no Git or producer state is consulted, and opaque identities are not
decoded to invent relationships.

## Requested capabilities and completion requirements

Requested capabilities are closed declarations for repository access/mutation,
Sandbox execution, worker assistance, Private Eval, approval, artifact production
and deployment-candidate handoff. They grant no authorization or execution.

Completion requirements are separately typed declarations for corresponding
repository verification, durable checkpoint, eval result, absence of pending
recovery and valid artifact reference. They do not conclude completion. Duplicate
semantic requirements and conflicting targets remain explicit diagnostics.

Assessment diagnostics use closed codes and redacted structural subjects. They
cover missing/incompatible bindings, external-reference correspondence, duplicate
or conflicting requirements, session/project mismatch and unsupported versions.

## Multidimensional state

State is never collapsed into a single session status. The pure projection keeps
independent dimensions for lifecycle, terminal outcome, coordination, repository
correspondence, worker binding, execution binding, checkpoint, cancellation,
recovery, evaluation and deployment candidate.

Lifecycle progresses through `unknown`, `planned`, `prepared`, `active`,
`suspended` and `terminal`. Terminal outcome is separate and may represent
`completed`, `failed`, `cancelled`, `abandoned` or `manual-intervention`.
`completed` is representable but cannot currently be transitioned to: it remains
reserved for the future completion assessment.

Dimensions without persisted facts remain explicitly unknown or absent according
to their semantics. In particular, worker/execution start unbound, repository is
unbound, checkpoint and deployment candidate are absent, and cancellation is
not-requested. None of those defaults asserts an external producer fact.

## Transition matrix and authority

Every transition request declares the exact session, dimension, expected previous
state, next state, reason, causal revision, policy version and opaque evidence
fingerprints. The pure policy checks dimension typing, the per-dimension transition
matrix, causal correspondence and evidence requirements before producing an
immutable lifecycle fact.

`planned -> prepared` requires the corresponding complete and valid session
contract assessment. `prepared -> active` still requires separate activation
evidence. External reasons are confined to their own dimensions: worker success,
process exit and accepted evaluation update only worker, execution and evaluation;
mutation application can only make repository correspondence stale, never verified.

The following transitions are closed explicitly:

- terminal lifecycle back to active or any other non-terminal state;
- cancellation request directly to cancelled outcome;
- worker success, process exit or eval acceptance directly to completed outcome;
- mutation application directly to repository correspondence;
- restart directly to active or any new state;
- deployment-candidate production to a publication state;
- completed outcome before the future completion policy exists.

Recovery-required and cancellation-requested states likewise do not start recovery
or establish cancellation confirmation.

## Projection and replay

Projection sorts facts by positive causal revision and applies only an uninterrupted
chain. Every fact must correspond to the same session, reference the prior fact
fingerprint, use the supported policy and carry a reason/evidence combination valid
for its dimension. Duplicate revisions, revision gaps, lineage gaps, mismatched
sessions and invalid semantic transitions fail closed with ordered redacted
diagnostics.

Replay performs no resume action. Restart with no facts recreates only the explicit
unknown/absent defaults; restart with facts reconstructs exactly their supported
multidimensional state. Occurrence metadata is carried separately and cannot alter
transition request, lifecycle fact or projection semantic identity.

The reduced lifecycle currently exposed by `repository_runtime_integrations` is an
adapter concern for a later integration slice. This pure package does not import or
project into that context.

## Lease authority

Coding Sessions owns the factual lease chain for session coordination. Issuance,
renewal, revocation and stale declaration each create a new immutable fact; no fact
is updated or removed. A lease preserves the exact session, actor, purpose,
repository binding, scope, read/write capability, shared/exclusive mode, issued-at,
validity interval, policy, causal revision and lineage.

This authority is coordination-only. A lease is not authorization, approval,
Repository mutation authority, Sandbox admission, worker assignment or filesystem
containment. Requested lease capability must already be declared by the valid
session contract, and lease scope cannot exceed its explicit binding.

## Ownership and conflict semantics

Ownership projection always receives the complete factual input and an explicit
observation time. It never looks up a current/latest lease or active session and
never reads a global clock. The result distinguishes `unowned`, `read-owned`,
`write-owned`, `conflicted`, `stale`, `revoked` and `unknown`; its fingerprint can
serve only as evidence for a future coordination transition and executes no
transition itself.

Conflict assessment first calculates factual scope overlap:

- repository scope overlaps every scope for the same repository;
- checkout scope overlaps the same checkout and its worktrees;
- worktree scope overlaps only the same worktree;
- different repository, checkout or worktree bindings do not conflict merely
  because their modes are similar.

Overlapping exclusive write conflicts with any incompatible ownership. Shared
reads coexist. Shared write is rejected unless the exact lease policy explicitly
permits it; when permitted, compatible shared ownership can coexist.

Expired, revoked and stale leases never satisfy active ownership. Expiry depends
only on the supplied observation time, so different observations may yield
different validity projections without changing any lease fact.

## Renewal, revocation and replay

Renewal and revocation name the exact preceding fact and causal revision. Renewal
must preserve session, actor, purpose, binding, scope, capability, mode and original
issued-at while extending the validity interval. Revocation preserves the same
correspondence and appends a terminal ownership fact; historical issuance and
renewal facts remain intact.

Projection groups facts by their explicit lease identity and rebuilds each chain
from revision one. Duplicate revisions, lineage gaps, chain forks, correspondence
mismatches, unknown revocations and invalid renewal are explicit redacted
diagnostics. Occurrence metadata does not participate in semantic fingerprints.

## Future Repository Runtime compatibility

A future adapter may map a verified ownership projection into the reduced lease
reference expected by `repository_runtime_integrations`. That adapter must preserve
the exact repository/checkout/worktree binding and must not translate ownership
into authorization. The frozen Repository Runtime and its integration package are
unchanged and are not imported by this domain.

## Intent authority

An outbound intent is an immutable Coding Sessions declaration, never an external
operation. Closed categories cover Repository observation/planning/application/
verification/recovery, authorization requests, worker assistance, Sandbox
execution/cancellation, Private Eval, artifact production and deployment-candidate
handoff. Each intent preserves exact session, actor, purpose, correlation, target
authority/type, external references, contract binding, requested capability,
optional lease reference, causal lineage and policy.

Intent assessment requires a complete valid contract, declared capability, exact
actor/purpose/correlation/binding correspondence and a prepared or active lifecycle.
Write-coordinated intents additionally require an explicitly supplied active write
lease projection and matching lease fact. That lease remains coordination evidence;
it never authorizes or executes the intent.

## External receipt semantics

An external receipt records only what another named authority returned. It retains
the producer artifact, version and optional fingerprint, neutral outcome,
completeness, exact session/intent correlation, echoed references and causal
lineage. Receipt construction or correspondence does not import the producer object
or transfer its authority.

Worker success does not complete a session, Sandbox process success does not verify
execution, Repository application success does not establish repository
correspondence, approval does not execute an intent, accepted evaluation does not
complete a session, and deployment handoff does not mean publication.

## Correspondence and factual projection

Receipt assessment compares session, intent identity/fingerprint, target authority,
actor, purpose, correlation, binding, external references, producer artifact and
lineage. Producer mismatch, unknown intent, unexpected outcome, stale fingerprint,
duplicate receipt identity/revision and lineage gaps remain closed redacted
diagnostics.

Projection deterministically emits `pending`, `acknowledged`, `responded`, `stale`,
`late`, `mismatched` or `unresolved` bindings. Pending intents retain an absent
receipt identity rather than receiving a synthetic fact. Late receipts remain
representable after terminal lifecycle, but never reopen the session or produce a
lifecycle transition. Stale and late are factual statuses; causal corruption is
reported separately.

Occurrence metadata is excluded from intent and receipt semantic fingerprints. No
current/latest intent, receipt or session lookup exists.

## Journal authority and append-only semantics

The Coding Sessions journal is the canonical factual sequence for one explicit
session. Closed entry categories cover contract/binding, lifecycle,
lease/coordination, intent, external receipt, checkpoint and future
cancellation/recovery facts. Entries retain only semantic identities,
fingerprints and opaque references; external payloads and producer authority are
never copied into the journal.

Every append request names the session, expected previous revision and exact parent
fingerprint. Stream assessment orders entries by causal revision and fails closed
on duplicate revisions, revision or lineage gaps, parent/session mismatch,
duplicate semantic entries, unsupported versions and integrity mismatch. Entries
and prior streams remain immutable.

There is no latest/current lookup. Projection requires the session plus explicit
`from_revision` and `through_revision` bounds and returns only facts inside that
interval. Missing entries are never inferred. Equal causal journals have equal
fingerprints; changing causal order changes entry lineage and the stream
fingerprint. Occurrence metadata remains outside semantic identity.

## Structural checkpoint semantics

A checkpoint is a factual marker over an exact journal fingerprint and causal
revision. Its manifest can bind contract, lifecycle, ownership and intent/receipt
projection fingerprints plus opaque Repository, worker/execution, evaluation,
artifact and future cancellation/recovery references. Reference collections are
canonical sets and never embed external artifacts.

Completeness policy explicitly declares required components. Missing, stale,
mismatched or lineage-incomplete components prevent structural completeness.
Checkpoint durability states are `pending`, `durable-ready`, `incomplete`, `stale`
and `lineage-gap`.

`durable-ready` means only structurally complete and eligible for future storage.
It does not mean persisted. Persisted state and resume usability remain explicitly
`not-evaluated`; an incomplete or stale checkpoint cannot enable clean resume. A
checkpoint never completes the session, promotes lifecycle, executes an intent or
starts recovery.

## Restart preparation

Future persistence may replay a complete journal to reconstruct exactly the facts
that were durably recorded. This slice performs no storage and no automatic resume.
Journal gaps or checkpoint lineage gaps remain blockers requiring future
revalidation rather than invented transitions.

## Pause and resume

Pause is an explicit Coding Sessions lifecycle decision. Its assessment requires an
active non-terminal session, exact causal revision, known required bindings and no
coordination conflict or manual-intervention recovery. An eligible assessment can
produce a suspended lifecycle fact, but does not pause workers/processes, revoke
authorization, mutate Repository state or execute recovery.

Resume is never inferred from restart or replay. It references an exact checkpoint
identity, fingerprint and revision and requires separate persistence evidence,
complete journal lineage and revalidation of lease ownership, Repository
correspondence, cancellation, recovery and declared external prerequisites. A
structurally complete checkpoint alone is not resumable. Duplicate resume for the
same causal expectation fails closed.

## Cancellation lifecycle and races

Cancellation remains a separate factual sequence: `requested`, `acknowledged`,
`termination-unverified`, `terminated` or `failed`. Request and acknowledgement do
not prove worker/process termination. Termination evidence remains an opaque
producer reference tied to the exact request, session, actor, purpose, correlation
and causal lineage.

Cancelled outcome is only eligible when the policy-required effects have verified
evidence and acknowledgement correspondence. Eligibility itself does not update
terminal outcome. Process exit alone, worker completion or Sandbox acknowledgement
cannot complete or cancel the session.

Assessments preserve races explicitly: process exit before acknowledgement,
acknowledgement after termination evidence, worker completion after request,
concurrent pause/cancellation and late facts after terminal lifecycle. Late facts
remain journalable and never reopen a terminal session. No assessment performs an
external cancellation or lifecycle transition as a construction side effect.

## Restart semantics

Restart is a pure reconstruction over explicitly supplied contract, journal,
checkpoint, lifecycle, lease, intent and receipt facts. It performs no current-state
lookup and never activates or resumes a session. Its idempotency fingerprint binds
restart identity, expected causal revision and the exact evidence set; a duplicate
attempt remains diagnostic rather than creating a second progression.

Journal-supported contract, checkpoint and internal projections are marked
`reconstructed`. Worker, execution, Repository, authorization, evaluation and
deployment state remain `unknown` until separately revalidated. Unknown worker is
not failed, unknown process is not terminated and unknown Repository is not
corresponding.

## Multidimensional reconciliation

Reconciliation consumes restart evidence plus explicit revalidation facts and
classifies each dimension as `reconstructed`, `revalidated`, `unknown`, `stale`,
`contradictory`, `missing` or `orphaned`. It compares journal/checkpoint integrity,
lifecycle, ownership, Repository, worker, execution, cancellation, recovery,
authorization, evaluation, artifacts and deployment without performing a
transition.

The result is exactly one of `safe-to-resume`, `reconciliation-incomplete`,
`recovery-required` or `manual-intervention`. Resume eligibility requires a
suspended non-terminal session, complete causal journal, exact structurally valid
and externally persisted checkpoint, revalidated lease/Repository/worker/execution
state, corresponding authorization prerequisites, no pending cancellation, no
required recovery and no manual-intervention evidence.

Stale ownership, unknown Repository, orphan workers, unknown execution, missing
artifacts, contradictory receipts and duplicate causal expectations remain explicit
diagnostics. Absence of evidence always produces unknown/incomplete, never a safe
default.

Late facts may be represented for future append only when causally corresponding.
They do not overwrite earlier facts or reopen terminal lifecycle. Duplicate restart
and resume are rejected through identity plus expected-revision/idempotency facts.

## Recovery authority

Coding Sessions owns only the coordination model for session recovery: why recovery
is required, the logical order of requirements, the external intents or references
needed, receipt reconciliation and the factual eligibility to continue, remain
suspended, fail or require manual intervention. It does not own Repository rollback,
Sandbox cleanup or termination, Worker repair, authorization or artifact repair.

Recovery reasons are closed and include incomplete crash/restart, Repository
divergence or unknown mutation outcome, stale Repository binding or lease, orphaned
worker, unknown execution, incomplete cancellation, missing artifact, contradictory
receipt, journal/checkpoint lineage gap and unavailable external authority.

## Logical recovery plan

A recovery request binds one session and recovery identity to the exact preceding
reconciliation fingerprint and expected suspended lifecycle. The deterministic plan
contains immutable requirements and causally ordered logical steps. External steps
name their target authority and carry only opaque expected receipt references; they
never contain or invoke external authority objects.

The logical vocabulary covers Repository reobservation/recovery request, lease
reacquisition, Worker and Sandbox reconciliation, authorization reconciliation,
artifact verification, Sandbox cleanup request, Worker cancellation request,
checkpoint rebuild, final session-recovery verification and explicit manual
intervention. A plan is descriptive evidence and performs no side effect.

## Recovery states and completion

Recovery projects to `none`, `required`, `planned`, `reconciling`, `recoverable`,
`recovered`, `failed` or `manual-intervention`. Replay preserves partial facts and
cannot infer completion after restart. Duplicate attempts/revisions, lineage gaps,
missing prerequisites, stale plans, mismatched receipts, external interference and
terminal incompatibility remain explicit diagnostics.

`recovered` requires factual evidence for every planned step plus the final
session-level verification step. One successful step or an external success receipt
is insufficient: a Repository recovery request does not prove rollback, Sandbox
cleanup does not prove process termination and Worker reconciliation does not prove
worker failure. Cancellation recovery separately preserves reconciled effects,
verified termination and the still-independent cancelled session outcome.

Recovery never promotes lifecycle. A recovered assessment produces only evidence
that a future control decision may use; it does not make the session active, resume
it, mark cancellation complete or invent an external outcome.

## Persistence ownership and record V1

Coding Sessions owns its persistence contracts and the conceptual
`coding-session-record-v1` envelope. The envelope binds an exact record and session
identity, semantic stream/category, opaque artifact identity, canonical payload
fingerprint, causal revision and parent lineage, idempotency key, occurrence data
and retention metadata. The compatibility policy currently accepts V1 only;
migrations and concrete schema ownership remain reserved for a later slice.

Persistence responsibilities are separated into contract/bindings,
lifecycle/coordination, intents/receipts, journal/checkpoints,
control/cancellation, restart/reconciliation and recovery/outcome streams. There is
no generic state store and no API for latest, current or implicitly active state.

## Append-only and exact-read semantics

Append uses an expected causal revision and exact expected parent. Existing records
are immutable. Repeating the same idempotency key with the same semantic artifact
is idempotent; divergent identity or idempotency payload, revision conflicts and
lineage gaps fail closed. No contract repairs or overwrites causal history.

Reads require exact session, stream, identity and fingerprint, or an explicit
causal interval. Artifact existence and checkpoint lookup are exact operations.
Missing artifacts, unsupported versions, corrupted fingerprints, incomplete replay
and unavailable stores remain typed failures rather than fallbacks to a current
record.

## Replay and restart input

Replay is a deterministic projection of the supplied records and explicit ranges.
It preserves intermediate lifecycle, lease history, pending intents, late/stale
receipts, incomplete checkpoints, pending cancellation, unknown reconciliation,
partial recovery and manual intervention exactly as recorded. Gaps remain
incomplete; replay never promotes lifecycle, resolves external unknowns, completes
an intent or starts recovery.

The restart replay input contains only exact replay and record fingerprints,
completeness and optional checkpoint persistence evidence. External reconciliation
is still required and is never executed by persistence.

## Checkpoint persistence distinction

Checkpoint structural completeness, `durable-ready` and factual persistence are
three independent dimensions. A persisted checkpoint is not thereby resumable; a
durable-ready checkpoint is not thereby persisted. The explicit persistence
evidence binds checkpoint identity/fingerprint to an exact record identity and
record fingerprint without making a resume decision.

## SQLite schema and migration V1

The nominal `sqlite_persistence.py` adapter implements the seven consumer-owned
ports without being imported by the pure package surface. Coding Sessions owns
schema version 1, migration `coding-sessions-sqlite-v1` and its deterministic
SHA-256 migration checksum. Reopen verifies `PRAGMA user_version`, schema metadata
and the immutable migration-history row before allowing valid use.

Seven owned record tables preserve the stream separation established by the ports:
contract/bindings, lifecycle/coordination, intents/receipts,
journal/checkpoints, control/cancellation, restart/reconciliation and
recovery/outcome. Each table stores the complete V1 envelope, canonical payload,
payload checksum, semantic fingerprint, exact causal revision and parent lineage,
idempotency, occurrence and retention metadata. No generic current-state table is
introduced.

## SQLite append-only and transaction guarantees

Historical UPDATE and DELETE are rejected by per-table triggers. Each append runs
inside an explicit immediate transaction, checks exact identity/idempotency,
expected causal revision and parent lineage, and either commits one record or
rolls back without a partial write. Equivalent retries return the existing exact
record; divergent identity, key, payload, revision or lineage fail closed.

Reads select exact identity plus fingerprint or an explicit causal interval. There
is no latest/current lookup. Payload checksum, record fingerprint, record version
and parent existence are revalidated while decoding. Corruption, unsupported
versions, missing artifacts, incomplete replay, migration mismatch and database
unavailability remain explicit failures.

## Restart, replay and checkpoint evidence

Reopen and replay reproduce only persisted categories and causal evidence. They do
not promote non-terminal lifecycle, resolve leases or external reconciliation,
complete pending intents/cancellation, advance partial recovery or remove manual
intervention. Time-based validity remains outside SQLite and requires an explicit
observation time in the consuming domain assessment.

Persisted checkpoint evidence proves only that the exact checkpoint record was
written and read back with valid integrity. Structural completeness,
`durable-ready`, persistence and resume eligibility remain independent; SQLite
does not declare a checkpoint resumable.

## Repository Runtime compatibility direction

The reference-only adapter lives in `coding_sessions_integrations`, outside the
pure Coding Sessions domain. Its dependencies point toward `coding_sessions`, the
frozen `repository_runtime_integrations` contract and strictly necessary public
Repository Runtime identities/requests. Neither Repository Runtime package imports
the new integration, and the frozen contracts remain unchanged.

Coding Sessions remains the sole source of truth for session lease facts. The
frozen `CodingSessionOwnershipLease` is only a compatibility DTO: it cannot persist,
renew, revoke or reinterpret the source lease and never supplies authorization.
Projection requires an explicit Repository identity/checkout/worktree/platform
binding and proves exact correspondence with the session's opaque references.

## Compatibility and representational loss

The adapter classifies projection as `exact`, `degraded`, `unrepresentable` or
`rejected`. Lease `valid-from`, causal lineage and multidimensional lifecycle facts
that the frozen DTO cannot carry remain named losses. A loss that could enlarge
write authority or scope fails closed. Stale, expired or revoked leases, lower
topology scope, binding mismatch and unsupported lifecycle never receive a silent
fallback.

Lifecycle compatibility is informative only. Planned, active, suspended and the
safe completed/cancelled terminal outcomes map to the reduced contract; prepared
is explicitly degraded, while unknown or incompatible terminal outcomes are
unrepresentable. Projection never changes the Coding Sessions lifecycle.

## Intent and receipt mapping

Repository observation, mutation planning, authorization requirement, application
and recovery intents translate to the existing neutral requests only after exact
session, actor, purpose, correlation, binding, capability, lease, lifecycle, scope
and reference checks. Translation creates no authorization fact and executes no
request.

Inverse projection retains Repository results only as opaque producer references
with explicit outcome/completeness. Application or verification success does not
complete a session or infer Repository correspondence. A recovery receipt does not
mark session recovery complete, and no receipt performs a lifecycle transition.

## Governance and Approvals compatibility direction

The reference-only adapter remains in `coding_sessions_integrations`, outside the
pure domain. It maps an explicit authorization intent to the existing public
`DecisionRequest`, `ApprovalRequest` or `RFCGateRequest` contracts. Dependencies
point from the integration to the owning producers; Governance, Approvals and
Project Governance do not depend on Coding Sessions and their frozen authority
contracts are unchanged.

Every request carries the exact session, actor, project, task/purpose,
correlation, capability, resource/scope, repository binding when present,
external fingerprints, causal revision and policy/version. Translation neither
evaluates policy nor creates an authorization fact, grants approval, widens scope
or invokes an operation. A pending producer request is not authority.

## Receipt correspondence and lifecycle isolation

Receipt projection preserves producer identity/version/fingerprint, decision
type and status, subject correspondence, capability, resource/scope, validity,
causal lineage and policy/version. `denied`, `expired`, `revoked`, `stale`,
`conflicting` and `unknown` remain distinct closed states. Session, actor,
project, purpose, capability, scope, resource, producer/version, duplicate,
conflict and lineage mismatches fail closed and remain diagnostic facts.

A late receipt after terminal lifecycle or cancellation remains attributable
external evidence. It cannot reopen the session, advance lifecycle or confer
mutation authority. Producer success is never translated into session outcome;
the Coding Sessions domain must assess any subsequent transition separately.

## Workers and Missions compatibility direction

The reference-only work adapter lives in `coding_sessions_integrations`. Missions
retains mission and task ownership; Workers retains assignment/attempt execution
and scheduling authority. Coding Sessions can request assistance or reference an
existing mission task, assignment and attempt, but cannot choose a worker, issue
a scheduler directive, create a mission, mutate a task or execute an attempt.

Outbound envelopes preserve session, intent, actor, project, task/purpose,
correlation, requested capability, mission/task references, repository binding,
artifact and authorization references, causal revision and policy/version.
Mission-task execution, worker assistance, attempt observation and cancellation
reconciliation remain separate request kinds. No request implies assignment,
running state, termination or session cancellation.

## Worker receipts and binding projection

Receipts retain producer identities and fingerprints for assignment and attempt
without copying internal result payloads. Assignment-created, started, waiting,
completed, failed, cancelled, unavailable, orphaned, unknown and late states are
projected factually to unassigned/requested/assigned/active/waiting/released/
orphaned/unknown binding states. Worker completion or failure never completes or
fails the session and never starts recovery.

Correspondence is strict across session, intent, mission/task, assignment,
attempt, actor/purpose/correlation, repository binding, external references and
causal lineage. Stale assignments, orphan workers, duplicates, contradictory
terminal outcomes, revision conflicts and lineage gaps remain explicit. A late
result after cancellation or terminal lifecycle remains evidence and cannot
reopen the session. Cancellation acknowledgement does not prove worker
termination, and an attempt-cancelled receipt does not cancel the session.

## Sandbox compatibility direction

The Sandbox adapter remains in `coding_sessions_integrations`. Sandbox alone
decides admission and owns materialization, isolation-driver selection, process
execution/supervision, termination proof and cleanup facts. Coding Sessions emits
only admission, execution, observation, cancellation/termination and
reconciliation/recovery requests with exact references; it cannot admit, start or
terminate a process, change capability grants or declare cleanup complete.

Requests preserve session, actor, project, task/purpose, correlation, intent,
Sandbox plan and attempt, requested capabilities, repository binding, material
and authorization references, lease reference, causal revision and
policy/version. The public Sandbox admission request is reused directly. Later
execution requests remain reference-only because Sandbox start contracts require
producer-owned materialization, grant, specification and driver facts.

## Admission, execution and termination evidence

Admission-pending, admitted, denied, materialized, running, waiting, exited,
termination-requested/observed/proved, cleanup-incomplete, failed, unavailable and
unknown receipts map factually to none/requested/admitted/running/waiting/
exited-unverified/verified/failed/unknown execution bindings. Admission is not
authorization, a capability grant is not a lease, and no receipt changes session
lifecycle automatically.

Process exit, including exit code zero, produces at most `exited-unverified`.
`verified` requires a distinct Sandbox verification evidence identity and
fingerprint. Cancellation request does not prove termination; observation does
not prove termination; termination proof does not cancel the session. Cleanup
incompleteness remains explicit and cannot complete recovery.

Correspondence covers session, intent, plan/attempt, actor/purpose/correlation,
capability, authorization, repository binding, external references and causal
lineage. Contradictory, stale, late, mismatched or unsupported producer evidence
fails closed. Late evidence remains persistible but cannot reopen terminal state.

## Private Evals compatibility direction

The reference-only adapter depends on public Private Evals identities and closed
states while leaving scoring, baseline, regression, evidence and run lifecycle
authority with Private Evals. Coding Sessions can request a run, subject
evaluation, explicit baseline comparison or evidence retrieval; it cannot score,
select a baseline, decide regression, mutate a result or promote a candidate.

Requests preserve session, actor, project, task/purpose, correlation, intent,
subject/candidate identity and fingerprint, requested evaluation capability,
explicit run and baseline references, repository binding, artifact and
authorization references, causal revision and policy/version. There is no
current/latest baseline selector: comparison is rejected unless exact baseline
identity and fingerprint are supplied.

## Evaluation receipts and completion boundary

Run, scoring-result, regression-result, baseline-result and evidence receipts
remain distinct. They retain exact run/result/evidence/baseline/regression
identities and fingerprints, run/result states, verdict, comparison result and
scoring version rather than collapsing the producer output into a boolean.

Requested, accepted, running, completed, failed, unavailable, result/evidence
available, stale, late and unknown facts map to the session evaluation dimension
without changing lifecycle. Accepted or rejected evidence does not complete or
fail a session, start recovery, create a deployment candidate or promote an
artifact. Completion remains reserved for a later Coding Sessions completion
policy.

Correspondence covers session, intent, subject/candidate, run/result,
evidence/result, baseline, actor/purpose/correlation, repository binding and
causal lineage. Stale evidence cannot satisfy a current requirement. Missing
policy-required evidence, contradictory results and late results remain explicit;
late history cannot reopen a terminal session.

## Deployment reference contract

The future deployment boundary is reference-only and lives in
`coding_sessions_integrations`. It imports only Coding Sessions primitives and
does not invent or import a `deployment_runtime` package. A deployment candidate
is an immutable, fingerprinted artifact reference with exact session, actor,
project, purpose, correlation, artifacts, repository binding, source snapshot and
verification, explicit eval/approval references, causal lineage and
policy/version.

Candidate production creates no release, chooses no environment, grants no
deployment authorization, publishes no artifact, promotes no version and starts
no rollout. The handoff request identifies a future deployment authority
semantically and binds an exact candidate fingerprint, artifacts, requested
capability, requirements and expected receipt type without defining that future
authority's API.

## Handoff and invalidation semantics

Absent, candidate-produced, handoff-requested, handed-off, rejected, stale,
invalidated and unknown are factual projection states. `handed-off` proves only
reference delivery; it does not mean accepted, deployed, promoted, healthy or
rolled out and never completes the session.

Invalidations are append-only facts for repository change, stale eval,
expired/revoked approval, missing artifact or source-verification mismatch. They
do not delete candidate history. Missing required eval/approval, stale source
verification, artifact/repository mismatch, fingerprint mismatch, duplicate or
conflicting receipts, late receipt and causal/lineage failures remain explicit
and fail closed. Late receipts cannot reopen terminal lifecycle.

## Local Composition Root

`coding_sessions_composition` is an explicit, opt-in boundary outside the pure
domain. Its builder validates a typed configuration, opens declared managed
resources in deterministic order, verifies/applies the owned SQLite V1 migration,
constructs the seven responsibility-specific stores and wires only explicitly
enabled reference adapters. Partial build failure closes already-open resources
in reverse order. `close()` is idempotent and every runtime surface rejects use
after close.

The runtime exposes named `domain`, `persistence`, `integrations` and `health`
surfaces. It has no generic execute facade and performs no intent emission,
lifecycle transition, recovery, repository mutation, worker scheduling, Sandbox
admission/process execution or deployment during build. Bootstrap does not import
or activate this package.

## Health and capability matrix

Health verifies SQLite schema/migration factually and reports each optional
integration as supported, degraded or unavailable. Repository, Governance,
Workers/Missions, Sandbox references and Private Evals are supported only when
explicitly enabled. Deployment references are degraded/reference-only even when
enabled; a real Deployment Runtime remains unavailable. Sandbox concrete
execution remains unavailable without a driver and cannot be enabled by this
configuration.

SQLite restart reopens the same append-only streams and preserves contracts,
lifecycle, leases, intents/receipts, journal/checkpoints, cancellation,
reconciliation and recovery records without inventing transitions, auto-resume
or auto-recovery.

## Slice 20 integrated validation

The local Composition Root is validated with real temporary SQLite databases
across all seven append-only streams. The matrix covers durable nominal records,
exact reads, idempotent append, causal ranges and restart at intermediate
contract, lifecycle, lease, intent/receipt, checkpoint, control, reconciliation
and recovery states. Restart preserves the recorded category and fingerprint; it
does not promote lifecycle, infer completion, resume work or start recovery.

Concurrency remains factual and fail-closed. Incompatible write leases are kept
visible as a conflict with no implicit winner, compatible shared reads coexist,
and bindings to distinct worktrees remain independent. Resume requires an exact
eligible checkpoint and compatible repository, cancellation and recovery facts;
stale correspondence, pending cancellation, recovery-required state and a
duplicate request remain explicit blockers.

Reference journeys exercise Repository Runtime, Governance/Approvals,
Workers/Missions, Sandbox, Private Evals and Deployment reference adapters
through the runtime. Late or terminal external facts remain historical evidence:
they do not grant authority, reopen a terminal session, infer session completion
or prove rollout. Deployment remains reference-only and concrete Sandbox
execution remains unavailable in health.

## Final freeze

Coding Sessions is frozen after the Slice 21 audit. The executable freeze gate
protects the module inventory, public facades, canonical and persistence V1
formats, SQLite schema and migration checksum, lifecycle dimensions, stream and
capability taxonomies, integration direction, SCC isolation, absent authorities
and opt-in composition. A change to any protected baseline requires explicit
architectural authorization and a new freeze decision.

Completion remains a policy-driven prerequisite assessment: no external receipt,
worker result, process exit, evaluation result, recovery result or deployment
handoff independently completes a session. Likewise, restart does not resume,
cancellation request does not prove cancellation and a lease coordinates access
without granting authorization.

## Post-freeze reservations

Real Deployment Runtime, release/rollout/promotion/rollback, bootstrap, APIs,
CLI, concrete Sandbox driver and global activation remain outside the frozen
bounded context. They must consume the frozen reference contracts without
transferring their authority into Coding Sessions.
