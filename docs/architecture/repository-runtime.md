# Repository Runtime

Status: **Slice 14 implemented / bounded local Git and filesystem adapter / globally NOT ACTIVATED**.

## Responsibility and distinctions

Repository Runtime owns factual repository identities and immutable structural
vocabulary. A repository is the stable logical subject. A checkout is one
materialized instance of that repository. A worktree is a Git workspace associated
with a checkout/common repository. These identities are distinct and are never
interchangeable.

`RepositoryIdentity` is derived only from an admitted stable key. Branch, HEAD,
remote URL, developer path and observation time cannot participate. Checkout and
worktree identities add their own explicit materialization keys. Occurrence metadata
may accompany a future record but never changes these semantic identities.

## Paths and platform semantics

`RepositoryPath` is a relative logical path bound to a checkout and optionally a
worktree. It rejects host absolute paths, traversal, empty identities, backslashes,
repeated/trailing separators and implicit root escape. It cannot open or inspect the
path.

`RepositoryPlatformProfile` explicitly fixes platform kind, case sensitivity,
Unicode normalization and the canonical `/` separator. No ambient host behavior is
consulted. Canonical encoding is versioned as `repository-json-v1`; fingerprints use
SHA-256 over that envelope.

## Independent states and classifications

HEAD distinguishes named branch, detached HEAD, unborn branch and absent HEAD.
Detached HEAD cannot carry a branch. Index presence is independently present,
absent or not observed. Workspace status is independently clean, dirty, conflicted
or unknown. Completeness is complete, partial, unavailable or unsupported; only a
complete observation may claim clean.

Path classification has four independent axes:

- Git tracking: tracked, untracked, ignored or unknown;
- material role: source, generated, artifact, runtime state or unknown;
- sensitivity: normal, secret risk, private or unknown;
- topology: regular, submodule, nested repository, sparse excluded or unknown.

Ignored never implies generated, and tracked never implies source. Submodules and
nested repositories never grant implicit traversal.

## Contracts and authority

The package imports only the standard library and itself. Its single protocol is a
read-only structural view over an already supplied immutable observation. It is not
a Git/filesystem observation port. There is no I/O, Git technology, change set,
mutation, authorization, restore point, persistence, adapter or composition.

## Observation authority and facts

Repository observation accepts neutral facts through the consumer-owned
`RepositoryObservationFactsPort`. The port returns data only; it grants no mutation,
authorization, Git or filesystem authority. Source ID/version are semantic
provenance. The timezone-aware occurrence timestamp is retained by the result but
excluded from its semantic fingerprint.

The request fixes repository, checkout, optional worktree and platform profile.
Assessment requires exact correspondence for all four. Neutral facts keep repository
presence, checkout/common-repository binding, worktree binding, HEAD plus separate
branch/object references, index, workspace, paths, staging, topology and source
metadata explicit.

## Completeness matrix

| Dimension | Required state | `not-required` rule |
| --- | --- | --- |
| repository | complete | never |
| checkout | complete | never |
| worktree | complete | only when request has no worktree |
| HEAD | complete | never |
| index | complete | never |
| workspace | complete | never |
| paths | complete | never |
| topology | complete | never |
| platform | complete | never |

Partial and unknown produce `INCOMPLETE`; unavailable and unsupported remain distinct
outcomes. None may materialize a clean observation. Completeness, correspondence,
conflicts and unsupported dimensions remain independent fields in the assessment.

## Contradictions and diagnostics

The pure service fails closed for divergent identities/bindings, detached HEAD with
a branch reference, branch/object disagreement, clean workspace with changes or
conflicts, absent index with staging, incompatible duplicate path facts,
sparse-excluded content reported as observed, and traversal into submodules or nested
repositories. A satisfied result contains the canonical Slice 2 observation;
otherwise it contains assessment only.

Diagnostics are closed `(dimension, code)` values, sorted deterministically. They
never contain path values, file contents, absolute host locations or secret payloads.
Fact ordering cannot change assessment, result canonical form or fingerprint.

## Path and resource classification

`RepositoryPathClassificationService` consumes supplied `RepositoryPathFacts`; it
does not discover paths. Facts preserve Git tracking and repository topology exactly
as observed. Resource kind (file, directory, link or unknown), executable marker,
content kind, size class, content-observed state, rule references, ownership scope
and completeness are explicit and independent.

Material role and sensitivity are resolved only through
`RepositoryPathClassificationPolicy`. Policies have stable ID/version, versioned
material and sensitivity rule references, explicit link handling and the canonical
format version. Names and extensions have no implicit meaning. In particular,
ignored does not imply generated, tracked does not imply source, and untracked does
not imply artifact.

### Precedence and conflicts

Tracking and topology are observed facts and cannot be overridden by policy.
Material and sensitivity rules resolve their own axes only. A generated-rule
reference must resolve to a generated rule. Multiple distinct values on one axis,
unknown rule references or a source/generated combination fail closed to `unknown`
and partial completeness.

Sparse-excluded paths cannot report observed content. Submodules and nested
repositories cannot report implicitly traversed descendants. Links require an
explicit preserve/reject policy. Duplicate canonical paths detect tracking,
topology and resource-kind conflicts. Case folding and Unicode normalization come
only from the bound platform profile, so collisions follow that profile rather than
ambient host behavior.

### Catalog and diagnostics

`RepositoryPathCatalog` is immutable, canonically ordered and fingerprinted. It is
bound to repository, checkout, optional worktree, platform profile, policy identity
and the Slice 3 observation fingerprint. Occurrence metadata on input facts is
excluded from semantic output. Per-path diagnostics contain only a path fingerprint
and a closed code: never path text, absolute paths, contents, secret values or diff
payloads.

Classification is factual only. It grants no observation, mutation, authorization,
restore, persistence or execution authority.

## Repository snapshots

`RepositorySnapshotService` composes only supplied semantic facts. A request binds
repository, checkout, optional worktree, platform profile, observation fingerprint,
path-catalog fingerprint, HEAD and object/branch references, index, workspace,
sparse-checkout state and declared completeness. Exact correspondence with the Slice
3 observation and Slice 4 catalog is required; identity, binding or state mismatch
blocks snapshot materialization.

`RepositoryPathFingerprintFact` carries a path fingerprint plus optional content and
metadata fingerprints, optional content length, algorithm/version and completeness.
It never carries content. The service validates these facts but never calculates a
hash, reads a resource or expands a repository boundary. Large and binary files use
the same reference-only contract as other files.

### Fingerprint hierarchy

Snapshots keep independent fingerprints for repository metadata, HEAD, index,
source tree, workspace and path catalog. The full snapshot fingerprint composes all
bound state and dimension completeness. A semantic change at any layer changes that
layer's fingerprint and therefore the complete snapshot fingerprint. Input
occurrence metadata is excluded from request and path-fact semantic identities.

### Completeness and resource semantics

Snapshot policy explicitly lists required dimensions and accepted fingerprint
algorithm/version pairs. Complete means every required dimension is complete and
corresponding. Missing required file content, incomplete facts, unknown algorithms,
duplicate/divergent facts, catalog collisions or an incomplete catalog produce an
explicitly partial result. They are never normalized to complete.

Regular files require supplied content fingerprints under the default policy.
Directories and links have reference/metadata semantics. Sparse-excluded paths,
submodules and nested repositories require a path fingerprint fact but no content
fingerprint and are never expanded implicitly. A sparse-excluded catalog entry is
contradictory with a disabled sparse-checkout state.

Diagnostics contain only a closed dimension/code pair and an optional path
fingerprint. They contain no relative or absolute path text, content, secret, diff or
inline payload. A snapshot is factual evidence only: it is not a restore point and
grants no mutation, authorization or recovery authority.

## Factual change sets

`RepositoryChangeSetService` compares two supplied snapshots only after exact
repository, checkout, worktree and platform correspondence. The request binds the
exact base/target fingerprints and explicit monotonic ordering. Identical snapshots,
inverted ordering or binding mismatches fail closed rather than inventing a change.

Change entries use the closed types added, modified, deleted, renamed, copied,
type-changed, classification-changed, metadata-changed, conflict and unknown.
Content, metadata, tracking, material role, sensitivity and topology remain separate
axes even when one primary type summarizes an entry. Entries contain relative path
references, fingerprints, lengths and classifications only; they never contain file
payloads, diffs or applicable patches.

### Rename and copy evidence

Equal content fingerprints do not establish identity. Without explicit
`RepositoryChangeFact` evidence, an absent base path and a new target path remain
deleted plus added. Rename/copy facts must bind exact source/destination paths,
entry/content fingerprints, lengths and classifications. Policy can separately and
explicitly enable unique equal-content rename or copy inference; both are disabled
by default and policy-derived evidence remains visible on the entry.

### Compatibility, boundaries and completeness

Incomplete snapshots or facts can produce only a partial change set. Duplicate or
colliding paths, contradictory facts, missing rename/copy endpoints, traversal below
submodule/nested-repository boundaries and sensitivity reduction remain explicit
diagnostics. Sensitivity is never downgraded silently. Occurrence metadata is
excluded from request/fact semantic identity, and input order cannot affect entry
ordering or fingerprints.

A factual `deleted` entry grants no delete authority; `added` grants no creation
intent; `modified` contains no patch. Change sets expose no mutation plan,
authorization, restore, rollback, persistence or execution surface.

## Mutation plans and preconditions

`RepositoryMutationPlanService` translates factual change entries only through
explicit, versioned `RepositoryMutationRule` values. An empty policy produces no
operations. A plan binds the exact repository, checkout, optional worktree,
platform profile, base snapshot, target snapshot, change set and policy version.
It describes intended operations but contains no authorization, executable patch,
file payload or application surface.

The closed operations are create, replace, append, delete, move, copy,
metadata-update and classification-update. Each operation retains its logical
destination, applicable source, exact base/target entry fingerprints, mutation
scope, collision behavior, explicit overwrite intent, dependencies and recovery
requirement. Deleted facts require an explicit delete rule. Rename and copy rules
accept only evidence already present on the factual change entry.

### Preconditions and collision semantics

Plans preserve preconditions for repository/checkout/worktree identity, HEAD and
branch state, index, workspace fingerprint, base completeness, path
presence/absence, regular topology and the canonical case/Unicode collision state.
These are stale-state expectations for a future application boundary; planning does
not evaluate the live repository and does not silently refresh them.

Collision behavior is closed to fail-if-exists, fail-if-missing,
replace-if-matches, create-only and explicit-overwrite. Explicit-overwrite requires
an entry-specific intent fingerprint in the request. Replace, delete and move can
be required by policy to carry a recovery requirement, but that requirement is not
a restore point and proves no recoverability.

### Ordering and failure semantics

Operations are canonically topologically ordered. Move dependencies are derived
only from exact logical endpoints; cycles, duplicate destinations, contradictory
operations and source/destination collisions fail closed. Submodules, nested
repositories and sparse-excluded resources are mutation boundaries and are never
traversed. Missing rules, incomplete inputs, invalid scopes and missing overwrite or
recovery intent remain explicit safe diagnostics.

Occurrence metadata is excluded from semantic identity. Equivalent input ordering
does not change the plan fingerprint. A plan remains intention only: it grants no
Governance authority and performs no filesystem or Git mutation.

## Authorization facts and correspondence

Repository Runtime does not own authorization decisions. A
`RepositoryAuthorizationRequirement` describes requested authority for an exact
immutable mutation-plan fingerprint, actor, purpose and ordered operation set. A
`RepositoryAuthorizationFact` is only an external assertion tied to exact
repository, checkout, worktree, plan, source/reference, policy version and validity
window. Neither object grants authority.

`RepositoryAuthorizationAssessmentService` compares these supplied facts and emits
an immutable factual assessment. Its satisfied outcome means correspondence only;
it is not a Governance/Approvals decision and cannot approve, execute, stage,
commit, push or mutate a resource. Future providers implement the consumer-owned
read-only `RepositoryAuthorizationFactsPort` and return neutral snapshots.

### Correspondence matrix

Each planned operation must correspond independently across plan and repository
identities, actor, purpose, operation kind, mutation scope, logical path or redacted
path fingerprint, collision behavior, overwrite intent and recovery requirement.
Create never covers replace/delete/move/copy. Delete and explicit overwrite require
dedicated boolean facts in addition to their operation and collision matches.

Path scopes are closed and explicit: exact, prefix, recursive and wildcard. Exact
never includes descendants; prefix covers one immediate level; recursive covers all
descendants. Wildcard has no hidden path filters. Prefix, recursive, wildcard or
otherwise broader facts participate only when the requirement explicitly allows
broader-fact correspondence. Combining facts that each cover only a subset likewise
requires an explicit requirement rule.

### Completeness, freshness and conflicts

Facts carry complete/partial/unavailable state plus issued-at and validity-window
facts. Assessment time and maximum accepted age are supplied inputs; no clock is
read. Not-yet-valid, stale, expired, incomplete or unavailable facts cannot satisfy
a requirement. Asserted and revoked facts with the same external source identity
conflict and fail closed. Unknown sources or policy versions remain explicit.

Partial operation coverage remains partial. Input order and occurrence metadata do
not alter semantic fingerprints. Diagnostics contain only closed codes and
fingerprints for operations, facts and redacted sources; no path text, host path,
content, secret or external payload is retained.

## Restore-point requirements and manifests

Repository Runtime plans logical restore-point coverage but does not create a
backup. `RepositoryRestorePointRequest` binds the exact repository, checkout,
worktree, platform profile, base snapshot, mutation plan and factual authorization
assessment. Planning succeeds only when those identities correspond and the
assessment outcome records complete correspondence; that check still does not turn
the assessment into a Governance decision.

`RepositoryRestorePointRequirement` is the required coverage. It remains distinct
from a produced `RepositoryRestorePointManifest`, factual
`RepositoryRestorePointVerification`, recoverability and any future rollback. A
planned requirement proves no manifest exists. A manifest proves no verification.
Verified and recoverable states prove no rollback was requested or executed.

### Coverage and policy semantics

Policy explicitly lists operations and dimensions requiring coverage. Coverage
kinds distinguish create-time absence, replaced/deleted content, move source and
destination, metadata, HEAD, branch, index, untracked collision risk and topology
boundaries. Each requirement remains tied to the base snapshot facts and each
manifest entry contains only path/content/metadata fingerprints, logical storage
reference, size, coverage kind, completeness and integrity algorithm/version.

Generated, artifact and runtime-state handling is explicit and defaults are not
derived from tracking state. Ignored never implies generated or exclusion.
Secret-risk content uses a separate policy rule and is blocked unless explicitly
included. Entry count, per-entry size, aggregate size, required Git metadata,
untracked coverage and accepted verification algorithms are versioned policy facts.
Submodules, nested repositories and sparse-excluded resources remain closed
topology boundaries.

### Verification and recoverability

Verification facts are supplied references; the service reads no resource and
calculates no hash. Closed outcomes distinguish verified, incomplete, mismatch,
unavailable, unsupported, corrupt, oversized and sensitive-content-blocked.
Missing coverage, divergent fingerprints, duplicate logical references, entries
outside mutation scope, unknown algorithms or binding mismatches fail closed.

`recoverable=true` is structurally valid only when every required entry is present,
the manifest is complete and within policy limits, every verification fact matches,
integrity algorithms are supported, bindings correspond and there are no
diagnostics. This is a factual precondition only; no archive, restore, rollback,
filesystem operation or Git operation exists in this slice. Input order and
occurrence metadata do not affect semantic fingerprints, and diagnostics retain
only closed codes and redacted fingerprints.

## Mutation application boundary

`RepositoryMutationApplicationService` is the first Repository Runtime orchestration
allowed to invoke a side-effect port, but it contains no Git or filesystem adapter.
Its request binds the exact repository, checkout, worktree, platform profile, base
snapshot, mutation plan, satisfied authorization assessment and recoverable
restore-point result. Any mismatch produces a not-started journal before a port is
called; authorization, policy and recoverability facts are never reinterpreted.

The consumer-owned ports remain narrow and independent: precondition revalidation,
one declared operation, immediate neutral observation, sequence interruption and
partial-attempt cleanup request. A future adapter may implement these protocols,
but this slice provides no implementation, fallback or production wiring. All
declared repository/checkout/worktree, HEAD, branch, index, workspace, path,
collision, overwrite and topology preconditions must be revalidated before the
first application call.

### Steps, observation and ordering

Operations are submitted exactly once in the canonical order stored by the mutation
plan. The port must return the same attempt and operation identities; an unknown or
out-of-order identity fails closed. Every journal step records only operation
identity, precondition/application outcomes, immediate observed fingerprints,
side-effect classification, cleanup requirement and closed diagnostics. It contains
no logical or host path, content, patch, secret or executable payload.

An applied port result is only a fact about that call. Immediate observation can
record correspondence but cannot set final-state verification. The journal therefore
keeps `final_state_verified=false`; applied does not mean verified, committed or
pushed. Input occurrence metadata is excluded from semantic identity, while factual
step sequence and ordering remain fingerprinted.

### Partial mutation, interruption and cleanup

Closed outcomes distinguish not-started, precondition-failed, applied,
partially-applied, failed, interrupted, cleanup-required, cleanup-failed and
manual-intervention. Stale, mismatched, unavailable or incomplete precondition
reports stop before the first side effect. A partial, failed, unknown or out-of-scope
effect stops the remaining sequence and leaves later steps explicitly not-started.

Interruption and cleanup are separate requests and separate facts. Cleanup-required
does not prove cleanup was attempted or completed; cleanup-failed and failed
interruption remain explicit, with manual intervention when safe interruption cannot
be established. No outcome is silently promoted to success and no rollback is
performed by this boundary.

## Verification authority and unexpected mutations

Slice 11 compares an exact base snapshot, target snapshot, mutation plan, immutable
application journal, verified restore point and supplied post-application snapshot.
The journal is evidence about an attempt only: an `applied` outcome never proves the
final repository state. Complete target conformance requires every policy-required
dimension to be present and matching, including independent HEAD, branch, index and
workspace facts.

Planned paths retain separate presence, content, metadata, classification and
topology comparisons. Supplied collision facts remain independent. A change from
base on a path outside the plan remains an unexpected mutation even if another part
of the state matches target. Unexpected sensitive changes fail closed; policy makes
recovery and manual-intervention requirements explicit. Diagnostics use closed
codes and only redacted path/operation fingerprints.

## Reconciliation semantics

Reconciliation classifies evidence without changing it: state matches target, state
matches base, mixed state, unknown state, external interference suspected, rollback
candidate or manual intervention required. Matching base is factual and does not
mean rollback ran. Mixed state never becomes success and carries explicit recovery
or intervention according to policy. Partial or stale observation is unverifiable
and cannot materialize complete verification. Canonical evidence ordering and
semantic fingerprints exclude occurrence metadata.

## Recovery authority and lifecycle

Slice 12 owns logical recovery planning and abstract orchestration only. A recovery
request does not start recovery, a verified restore point does not prove rollback,
and verification divergence does not trigger an automatic action. Planning is
admitted only from an exact reconciliation result that declares recovery required
or a rollback candidate. Manual-intervention reconciliation remains terminal and
is never converted into an executable plan.

The closed lifecycle distinguishes not-required, required, planned, ready,
in-progress, partially-recovered, recovered, rollback-failed, verification-failed
and manual-intervention. A plan derives actions solely from verified restore-point
manifest entries that intersect explicit Slice 11 divergence. It cannot widen path,
metadata or Git-state coverage, and topology-boundary coverage is retained as a
boundary rather than converted into traversal authority.

Before the first abstract side effect, the consumer-owned precondition port must
revalidate the exact attempt/plan, current fingerprints, repository bindings,
restore-point recoverability and absence of external interference. Separate ports
apply one logical recovery step, return immediate observation, interrupt a failed
sequence and factually verify the restored state. These protocols provide no
concrete adapter or ambient Git/filesystem capability.

## Rollback and post-recovery semantics

Logical actions are closed to restoring content, metadata, absence, presence, HEAD,
branch state and index; reconciling covered untracked state; and verifying the
restored state. The first non-recoverable fact stops the sequence. Partial effects
remain partially recovered, interruption failure or new interference requires
manual intervention, and step success alone cannot establish recovery.

`recovered` requires a complete post-recovery verification bound to the exact base
snapshot fingerprint. Failure to apply a recovery step is `rollback-failed` (or
partial recovery after effects); successful logical steps followed by a factual
base mismatch are `verification-failed`. Journal, plan, verification and result are
immutable, canonically ordered and fingerprinted, while occurrence metadata is
excluded from semantic identity.

## Persistence ownership and record format V1

Slice 13 owns persistence of immutable Repository Runtime evidence. The consumer-
owned ports are separated into observation/snapshot, planning/authorization,
mutation lifecycle and recovery/evidence responsibilities. The only concrete
adapter is the explicitly bounded SQLite implementation; it has storage authority
only and cannot observe a repository, apply a mutation, verify final state or run
recovery.

Every artifact is stored in a `repository-record-v1` envelope under schema version
1. The closed artifact catalog covers identities and platform profiles;
observations and assessments; path catalogs and snapshots; change sets, plans and
authorization evidence; restore-point evidence; mutation attempt/journal/result;
verification and reconciliation; and recovery plan/attempt/journal/result. Records
retain canonical payload JSON, semantic and payload fingerprints, SHA-256 checksum,
idempotency key, exact stream identity, optimistic causal revision, lineage,
occurrence metadata, retention metadata, completeness and lifecycle state.

## Schema V1 and append-only semantics

Migration `repository-runtime-persistence-v1` creates schema metadata, checksumed
migration history and four responsibility-specific record tables. Historical rows
and migration history are protected by SQLite triggers that reject `UPDATE` and
`DELETE`. This slice exposes no physical purge operation; retention metadata only
records policy reference, optional retention time, legal hold and purge eligibility.

An equivalent identity/idempotency retry returns the existing record. Divergent
payload under the same semantic identity, reused idempotency with different content,
duplicate causal revision, stale expected revision or cross-store artifact kind
fails closed. Migration checksum or schema-version divergence likewise blocks use.

## Exact reads, replay and restart

Reads require both semantic identity and exact semantic fingerprint. There is no
`latest`, `current` or implicit head lookup. Replay orders records by causal revision
and reports missing revisions and unresolved lineage fingerprints rather than
repairing or hiding them. Empty or incomplete replay is never marked complete.

Restart projects the recorded lifecycle states exactly. Partial observation, plan
awaiting authorization, partial application, divergent verification, recovery
required, partial recovery, rollback failure, verification failure and manual
intervention remain explicit. Persistence never infers authorization, completion,
verification success, rollback execution or operational recovery from neighboring
records.

## Adapter technology decision

Slice 14 selects a hybrid adapter. The installed Git CLI is the factual authority
for Git semantics, invoked only through fixed argument vectors with `shell=false`.
Python standard-library filesystem APIs own byte hashing and allowlisted logical
filesystem operations. No new dependency or Git library is introduced.

Git CLI was selected because it preserves native Windows Git behavior for worktree
and common-dir resolution, detached/unborn HEAD, index/status, ignore rules,
submodule gitlinks, sparse-index markers, filters and repository configuration. A
library-only implementation would require a new dependency and still risk semantic
gaps around worktrees, filters and Windows Git behavior. Filesystem work remains
separate because Git commands are never used to stage, checkout, restore or publish.

### Parity and capability matrix

| Feature | State | Adapter behavior |
| --- | --- | --- |
| Windows paths and case profile | supported | explicit platform profile and canonical logical `/` paths |
| worktrees/common Git dir | supported | factual `rev-parse` queries; no worktree creation/removal |
| detached/unborn HEAD | supported | observed without choosing or changing a branch |
| tracked/untracked/ignored/conflicted | supported | closed porcelain/status and index parsing |
| submodules | degraded | gitlink boundary detected; never traversed or updated |
| nested repositories | degraded | `.git` boundary detected on affected path ancestors |
| sparse checkout | degraded | skip-worktree paths detected; sparse configuration is not changed |
| LFS | unavailable/degraded | filter configuration is reported; content transformation is not treated as transparent |
| hooks and filters | degraded when present | reported as explicit capability limitation; never invoked intentionally |
| encodings | degraded | Git output is decoded as UTF-8 with lossless surrogate handling; file content remains bytes |
| symlink/junction/reparse points | supported fail-closed | affected-path traversal stops at any reparse boundary |
| create/replace/append/delete/move/copy | supported within exact plan | material and operation identities must correspond |
| metadata/classification mutation | unsupported | fails closed; no ambient chmod/classification inference |
| content recovery | supported within verified coverage | exact recovery step and material binding required |
| HEAD/branch/index recovery | unsupported in this slice | would require prohibited checkout/ref/index mutation |
| staging/commit/push/remote operations | unsupported | no command is present in the closed Git argv set |

## Observation and mutation authority

The adapter is constructed with an exact canonical repository root, repository,
checkout and worktree identities, platform profile, optional mutation/recovery plan,
closed material sets and optional restore manifest. It cannot accept arbitrary Git
commands. Before the first side effect it fingerprints the canonical root, HEAD,
index, workspace status and every affected path. Any new HEAD, index, workspace or
path fact makes preconditions stale.

Observation reports HEAD/branch, index presence and staging, workspace state,
tracked/untracked/ignored/conflicted paths, sparse exclusions, submodule boundaries,
content fingerprints and filesystem metadata fingerprints. Material role and
sensitivity remain unknown unless supplied by their separate policy owner.

Filesystem effects are selected only from the immutable mutation plan. Existing
dirty and untracked paths outside the plan are neither deleted nor normalized.
Create collisions, missing replace/delete sources, missing material, target-entry
fingerprint mismatch, nested-repository traversal and root/reparse escape fail
closed. Immediate command/byte success remains a step fact; Slice 11 verification
is still required for final-state success.

## Restore and recovery limitations

Restore materialization is bound to the exact manifest and writes only redacted
fingerprint-named backup resources under the configured restore root. An operation
whose plan requires recovery remains blocked until corresponding restore coverage
has been factually verified. Partial filesystem failure remains a partial side
effect with cleanup required; cleanup never discards unrelated dirty/untracked data.

Recovery accepts only steps contained in the exact recovery plan and material bound
to the verified coverage entry. A step outside that set is impossible. Post-recovery
verification independently checks covered material and detects subsequent external
interference; successful byte application alone does not establish `recovered`.

## Coding Sessions reference-only integration

Slice 15 introduces `repository_runtime_integrations`, outside the pure Repository
Runtime domain. The dependency direction is strictly
`repository_runtime_integrations -> repository_runtime`; the Repository Runtime
never imports the integration and neither package is wired into the Composition
Root.

The integration defines opaque session, actor, project, task and correlation
references plus an exact repository/checkout/worktree/platform binding. There is no
repository, branch, worktree or `current`/`latest` session lookup. Translation can
only produce the existing neutral observation, mutation planning, authorization
requirement, application and recovery request DTOs. It never invokes their services,
creates an authorization fact, records an approval or executes an operation.

### Ownership and lease semantics

A session ownership lease is an immutable coordination fact binding the exact
session, actor, purpose, repository, checkout and worktree. It records read/write
scope, shared/exclusive mode, issue and expiry times and revocation. Write leases
must be exclusive; a concurrent active write lease for the same binding fails
closed. Read/shared leases may translate observation or planning intents but cannot
satisfy the coordination prerequisite for application or recovery.

Lease validation rejects stale session ownership, expired or revoked leases,
actor/purpose mismatch, binding mismatch, incompatible lifecycle, missing requested
capability and conflicts. The lease fingerprint and scope are preserved as bounded
occurrence metadata. A lease coordinates sessions only: it is not filesystem
security, Governance authority, an approval, an authorization assessment or proof
that mutation occurred.

## Local Composition Root

Slice 16 adds `repository_runtime_composition` as an explicit, opt-in local owner of
wiring. Its only governed dependencies are Repository Runtime and the optional
Coding Sessions integration. Neither dependency imports composition, and global
bootstrap remains unaware of all three packages.

`RepositoryRuntimeBuilder` validates exact repository, checkout and worktree
identity, absolute repository/restore/persistence locations, platform profile,
schema/record/migration versions, adapter identity, capability expectations and
optional integration consistency before exposing a runtime. It applies and verifies
SQLite migration V1, constructs the four responsibility-specific stores, creates
the local Git/filesystem adapter, captures its factual capability report and then
constructs the runtime. A build failure exposes no runtime and closes already-open
managed resources in reverse order.

### Runtime ownership and lifecycle

`RepositoryRuntime` exposes observation, classification, snapshots, change sets,
mutation planning, authorization assessment, restore points, mutation application,
verification and recovery as distinct typed service properties. Persistence stores
and adapters are likewise explicit. There is no generic execute facade and build
does not apply a mutation, choose a branch or create a worktree.

`close()` is idempotent and closes managed resources once in reverse order. After
close, every service, store and adapter property rejects access. SQLite connections
remain operation-scoped inside the persistence adapter rather than becoming hidden
long-lived Composition Root resources.

### Factual health

Health verifies persistence and migration checksum at observation time and reports
schema/record versions, adapter identity, Git availability/version, the exact
platform profile, managed-resource health and whether Coding Sessions translation
is configured. Adapter capabilities are partitioned without promotion into
supported, degraded, unsupported and unavailable. Mutation/recovery remain
degraded; staging, commit and push remain unsupported. Optional Coding Sessions
wiring creates no authority, approval or operation execution.

## Integrated E2E validation matrix

Slice 17 validates the local Composition Root against temporary real Git
repositories. It adds no production feature or global wiring.

| Journey | Evidence |
| --- | --- |
| observation to snapshot/planning | factual local adapter observation, immutable snapshots, change set and mutation plan services through `RepositoryRuntime` |
| authorization and restore | exact external authorization facts and verified restore manifest; neither implies application |
| application and verification | closed plan operation applied through the composed adapter; post-state fingerprint checked independently; divergence remains reconciliation evidence |
| recovery | partial steps, external interference and rollback failure remain distinct; recovery never starts from verification alone |
| persistence/replay | append-only write, idempotent retry, causal replay and exact restart state through composed SQLite stores |
| concurrent sessions | incompatible active write leases on the same binding fail closed |
| Git boundaries | nested repository, real submodule, sparse checkout and reparse/symlink boundaries remain explicit and non-traversable |

### Crash and restart points

Restart is exercised after observation, snapshot, mutation plan, authorization
assessment, restore verification, partial mutation, divergent verification, partial
recovery and rollback failure. Each checkpoint reopens the same schema/checksum and
retains its exact completeness and lifecycle state. Restart never creates a later
transition, starts recovery or duplicates an idempotent record.

### Concurrency and stale-state cases

Application preconditions are revalidated against the adapter baseline immediately
before the first side effect. Independent changes to HEAD, index, workspace or an
affected path produce `precondition-failed` and leave the planned target absent.
Existing dirty/untracked paths remain untouched. During recovery, external
interference produces manual intervention; partial steps never become recovered.

Capability health is also asserted against real repositories: degraded mutation,
recovery and sparse behavior is not promoted to supported; unsupported staging,
commit and push remain absent from the runtime surface; unavailable features remain
visible.

## Final freeze

Slice 18 audited and froze the Repository Runtime as **IMPLEMENTED / OPERATIONALLY
COMPLETE / FROZEN**. The authoritative inventory, public-surface justification,
contract fingerprints, authority map, lifecycle, final capability matrix,
persistence/restart semantics, integration directions, operational limitations and
executable baselines are recorded in
`docs/audits/repository-runtime-final-freeze-audit.md`.

The freeze adds no bootstrap activation, staging, commit, push, branch creation,
fetch, pull, merge, rebase, Deployment Runtime, Workers, API, CLI, background
service or new capability authority. Any future change to the frozen surface or V1
formats requires explicit architectural authorization and a new freeze decision.
