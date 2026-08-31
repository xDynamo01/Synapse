# Sandbox Execution Boundary

Status: **Sandbox Execution Boundary — Slice 2 implemented, globally NOT ACTIVATED**

## Responsibility and authority

Sandbox owns the pure vocabulary that describes admission inputs, a canonical
execution plan, materialization facts, execution occurrence facts, bounded result
summaries, evidence references, cleanup and rollback outcomes. It does not own
Governance, Approval, Skill, Tool, Worker, Private Eval or resource policy decisions.
Those authorities may later supply immutable facts through adapters to consumer-owned
read ports.

| Concern | Authority in Slice 2 |
| --- | --- |
| model invariants, canonical form and fingerprints | Sandbox |
| workload/admission/plan/attempt/evidence identities | Sandbox |
| governance, policy and approval truth | external opaque reference |
| artifact and isolation capability truth | external opaque fact provider |
| execution, persistence, delivery and composition | deliberately absent |

## Models, identities and state separation

Content fingerprints use the explicit `sandbox-json-v1` canonical envelope, sorted
mapping keys, ASCII JSON and SHA-256. Content identities take only ordered semantic
inputs. Occurrence metadata, clocks, paths, human messages and mutable fields never
participate.

| Identity | Meaning | Kind | Deterministic inputs |
| --- | --- | --- | --- |
| `SandboxWorkloadId` | exact workload subject | semantic content | actor/workload facts |
| `SandboxAdmissionId` | admission fact identity | semantic occurrence | request fingerprint + authority reference |
| `SandboxPlanId` | exact plan identity | semantic content | admission + canonical plan facts |
| `SandboxAttemptId` | exact attempt occurrence | occurrence | plan + caller-owned attempt key |
| `SandboxEvidenceId` | evidence bundle identity | semantic content | attempt + result/evidence refs |
| artifact/plan fingerprint | immutable content digest | content | versioned canonical payload |

The following dimensions are independent and explicit: `structurally_complete`,
`admitted`, `authorized`, `materialized`, `executable`, `running`, and `completed`.
Admission does not authorize; declaration/request does not grant; materialization
does not make a plan executable; completion requires an explicit outcome and does
not mean success. Closed enums cover admission, authorization, materialization,
executability, execution, cleanup and rollback/manual intervention.

The request carries neutral subjects, handoff fingerprint, actor/workload identity,
purpose/correlation, policy/approval references, requested capabilities/resources,
execution/isolation profiles and opaque secret references. It never carries a secret
value. Plans contain typed grants, denials and resource limits; no command line,
absolute path, callable, driver or credential is representable. Results contain only
bounded classifications, resource summaries and opaque stdout/stderr/evidence refs.

## Deliberate omissions and Slice 3 decisions

No subprocess, filesystem, network, secret broker, store, adapter, driver,
materializer, supervisor, handler, Composition Root or production wiring exists.
`run()` and `execute()` ports are deliberately absent. `SandboxPolicyVersion` is kept
as the isolation-policy version; a second generic policy identity was removed as
redundant. A separate execution-result identity was also omitted because the exact
attempt already owns at most one immutable result fact in this slice.

Slice 3 must decide producers and transition rules for admission facts and policy
evaluation before any public operational error or execution port can exist. It must
also decide how external Governance/Approval facts bind to a request without giving
Sandbox authority over those contexts.

## Reconciled architecture baseline

The authoritative governed baseline is the repository runtime method
`_runtime_context_graph()`, which excludes `TYPE_CHECKING`, bootstrap and documented
core compatibility adapters: **70 contexts, 263 governed edges, official SCC
13 contexts/35 internal edges** before Slice 2. The generic
`tests.architecture.support.context_graph()` includes typing-only imports and
therefore reports **74 contexts, 298 edges, SCCs 3/4 and 26/84**; it is explanatory,
not the governed authority.

The final frozen Skills architecture record is authoritative for the other two
definitions before Slice 2: **602 Python modules; exact runtime graph 2,415 edges
and zero non-trivial SCCs; typing-inclusive graph 2,492 edges and four pre-existing
SCCs**. These numbers differ because the runtime graph excludes typing-only imports,
while the typing-inclusive audit intentionally retains them. A narrower ad-hoc
absolute-import graph is not an authoritative substitute for either definition.

The Sandbox package imports only the standard library and itself. No existing
bounded context imports Sandbox, it creates no governed edge, and it remains outside
all SCCs. Exact-runtime and typing-inclusive module metrics are recorded by final
verification only when reproduced with their frozen audit implementation, never
inferred from context counts or a narrower import scanner.

## Slice 3 — Admission Facts and Correspondence

Status: **Sandbox Execution Boundary — Slice 3 implemented, globally NOT ACTIVATED**

Slice 3 receives immutable facts from the consumer-owned Slice 2 provider ports and
produces only a factual assessment. The service does not admit, authorize, create an
effective grant or construct an execution plan. External Skills, Governance,
Approvals, Private Evals, artifact custody and isolation implementations remain
authoritative for their own facts; Sandbox verifies supplied identity, integrity,
completeness, freshness and correspondence without importing those contexts.

`SandboxAdmissionFactsSnapshot` is the versioned
`sandbox-admission-facts-v1` canonical artifact. It contains ordered tuples for
handoff, artifact, policy, approval, capability, resource, isolation and evidence
facts plus one explicit completeness status per dimension. Its fingerprint covers
the supplied observation timestamp and all facts. Reordering inputs cannot change
the snapshot or assessment fingerprint.

### Correspondence matrix

| Dimension | Exact correspondence | Freshness |
| --- | --- | --- |
| handoff | subject, handoff fingerprint, actor, purpose, plan intent and READY fact | not applicable |
| artifact | request subject and handoff-bound artifact fingerprint; AVAILABLE is only a fact | not applicable |
| policy | every explicit policy ref, request subject and isolation-policy version | supplied validity window vs explicit evaluation instant |
| approval | approval ref, subject, actor, purpose and plan intent | supplied validity window vs explicit evaluation instant |
| capabilities | external declaration/support facts cover requested declarations | not applicable |
| resources | external grant fact matches resource/unit and bounds requested amount | not applicable |
| isolation | exact profile ID and policy version with explicit support | not applicable |
| evidence | every required external evidence fact is explicitly available for the subject | not applicable |

Completeness preserves `ABSENT`, `INCOMPLETE`, `UNKNOWN`, `NOT_REQUIRED` and
`COMPLETE`. `NOT_REQUIRED` is accepted only by an explicit request-derived rule:
missing optional approval, no requested capabilities/resources, or no evidence
requirements. Otherwise it is a fail-closed mismatch. Freshness preserves
`UNKNOWN`, `NOT_REQUIRED`, `FRESH` and `STALE`; it never selects current/latest.

The deterministic assessment exposes per-dimension correspondence, completeness and
freshness, ordered diagnostic codes, a canonical fingerprint, and one factual
outcome: `SATISFIED`, `INCOMPLETE`, `MISMATCH`, `STALE` or `UNAVAILABLE`.
Diagnostics contain only fixed codes and dimension names, never external reference
values or payloads. `SATISFIED` is not admission or authorization.

### Reserved for Slice 4

Slice 4 may define admission policy and decision only after its authority, producer,
precedence, replay and denial semantics are explicitly approved. Authorization,
effective grants, execution plans, materialization, persistence, I/O, concrete
adapters and Composition Root wiring remain outside Slice 3 and are not implied by a
factually satisfied assessment.

## Slice 4 — Admission Policy and Decision

Status: **Sandbox Execution Boundary — Slice 4 implemented, globally NOT ACTIVATED**

Slice 4 owns one pure transformation:

`request + facts assessment + explicit admission policy -> admission decision`

It proves only whether the exact workload satisfies the policy's entry criteria.
`ADMITTED` does not mean authorized, granted, materialized, executable or running.
No authorization field, effective permission, execution plan or operational method
exists on the decision artifact.

### Policy semantics and authority

`SandboxAdmissionPolicy` is an immutable `sandbox-admission-policy-v1` artifact.
Its deterministic identity is derived from its explicit version and policy
fingerprint. The fingerprint covers:

- one requirement for every factual dimension;
- accepted completeness values and explicit `NOT_REQUIRED` permission;
- freshness requirements;
- closed treatments for mismatch, stale, unavailable and incomplete;
- allowed minimum isolation profiles and whether support must be proven;
- factual approval requirement;
- externally granted capability/resource requirements;
- the complete outcome precedence.

The policy interprets only facts already projected by the assessment. It does not
re-evaluate subjects, approval actor/purpose, artifact fingerprints, resource bounds
or capability declarations. Slice 3 remains the single owner of correspondence.
Boolean assessment properties expose only canonical factual answers needed by
policy: approval correspondence, external capability/resource grant completeness
and isolation support.

### Outcomes and precedence

The closed precedence is:

1. `DENIED` for mismatch or a present fact that violates an explicit policy
   criterion;
2. `STALE` for expired facts;
3. `UNAVAILABLE` for absent/unknown facts required by policy;
4. `INCOMPLETE` for explicitly incomplete facts;
5. `ADMITTED` only when no violation remains.

This ordering prevents a less severe state from masking a stronger one. In
particular, stale never becomes unavailable, unavailable never becomes denied, and
incomplete never becomes denied. Every violation still contributes an ordered,
bounded rationale code even when another violation determines the final outcome.

### Binding, replay and audit

The decision binds the workload/request fingerprint, assessment fingerprint, policy
identity and policy fingerprint. Its semantic fingerprint also covers outcome,
ordered rationale and safe diagnostics. `SandboxAdmissionId` is derived from that
decision fingerprint. Replaying identical semantic inputs produces the same
decision identity and fingerprint.

`occurred_at` is timezone-aware occurrence metadata and is deliberately excluded
from semantic identity. Diagnostics contain only fixed codes and optional dimension
names; they never contain external references or payloads.

The earlier provisional Slice 2 decision shape was removed because it mixed
admission and authorization state before either had a producer. The public
`SandboxAdmissionDecision` name now refers only to the Slice 4 artifact. Existing
Slice 2 request, plan and lifecycle contracts remain unchanged.

Authorization, effective grants, execution-plan construction, materialization,
persistence, I/O, concrete adapters, supervision and Composition Root wiring remain
reserved for later explicitly approved slices.

## Slice 5 — Execution Plan

Status: **Sandbox Execution Boundary — Slice 5 implemented, globally NOT ACTIVATED**

Slice 5 transforms one exact `ADMITTED` decision into an immutable structural
description. It does not authorize, grant, allocate, materialize or execute:

`request + snapshot + assessment + policy + admitted decision + specification -> plan`

The snapshot binding is retained so artifact, external grant references and
evidence requirements can be checked against the exact facts already assessed.
This is structural correspondence only; the plan service does not repeat admission
assessment or policy rules.

### Canonical plan and bindings

`SandboxExecutionPlan` is a `sandbox-execution-plan-v1` artifact. Its semantic
content binds:

- workload and subject;
- request, facts snapshot and assessment fingerprints;
- policy identity, version and fingerprint;
- admission decision identity and fingerprint;
- handoff and artifact references/fingerprints;
- closed runtime kind and explicit runtime version;
- logical entrypoint;
- requested capabilities/resources;
- opaque external capability/resource references;
- isolation profile;
- explicit resource limits;
- evidence and bounded retention requirements;
- correlation and purpose;
- ordered structural diagnostics.

`SandboxPlanFingerprint` covers that complete semantic content and
`SandboxPlanId` is derived from the fingerprint. `created_at` is timezone-aware
occurrence metadata and is excluded from both. Exact replay therefore produces the
same semantic plan identity even when occurrence metadata differs. Collections are
canonicalized by semantic keys before fingerprinting.

### Structural vocabulary

Runtime kinds are closed to the versioned declarative identifiers currently
representable by the domain (`python` and `wasm`). They do not identify a driver.
Entrypoints are bounded logical names; paths, traversal, whitespace, shell
metacharacters, command lines and callables are not representable.

Capability declarations, capability requests and opaque external-grant references
remain separate fields. No field represents an effective grant. Resource requests,
external resource references and declared limits are also separate; a limit is not
an allocation. The isolation profile is a requested structural binding, not proof
that an isolation implementation is available.

Artifact availability from Slice 3 is not materialization. A valid plan has no
`authorized`, `materialized`, `executable`, `allocation`, `run` or `execute`
surface.

### Validation and public surface

The builder fails closed unless the decision is exactly `ADMITTED` and all
request/snapshot/assessment/policy/decision bindings correspond. It also verifies
the specification against request capabilities/resources, the exact artifact fact,
external grant references, resource limits, evidence requirements, correlation and
purpose. Failures expose fixed, ordered diagnostic codes without reference values.

The provisional Slice 2 plan and its premature effective-grant/denial models were
removed because they had no authorized producer. The public `SandboxExecutionPlan`
now refers only to this Slice 5 artifact. Materialization records continue to bind
the stable `SandboxPlanId` without gaining plan-construction authority.

Authorization, effective grants, allocation, materialization, persistence,
filesystem/network/process/secret boundaries, drivers, supervision, concrete
adapters, Composition Root wiring and execution remain reserved for later slices.

## Slice 6 — Capability Grants

Status: **Sandbox Execution Boundary — Slice 6 implemented, globally NOT ACTIVATED**

Slice 6 is the first owner of effective capability grants. Its pure transformation
is:

`request + capability permission snapshot + policy + decision + exact plan -> grant set`

Admission remains unchanged. A fully denied grant set does not revoke the admission
decision, and a non-empty grant set is not global authorization.

### Authority and fact binding

The admission snapshot remains frozen in the plan. Grant evaluation therefore uses
a separate immutable `sandbox-capability-permissions-v1` snapshot observed at an
explicit instant. It reuses `SandboxCapabilityFact`, but each fact is wrapped by
`SandboxPlanCapabilityPermission` with the exact `plan_id` and plan fingerprint.

An external permission fact must correspond exactly to:

- request subject and actor;
- request purpose;
- plan execution-profile/intent;
- exact plan identity and fingerprint;
- exact requested and declared capability name;
- an opaque external reference already declared by the plan;
- a compatible isolation profile;
- an explicit validity window.

No bounded context is imported to establish those facts. External authorities remain
responsible for producing them; Sandbox only validates supplied correspondence.

### Grant derivation

Declaration, request, external permission and effective grant are four distinct
artifacts. The service iterates only exact requested capability names. It performs
no prefix expansion, inheritance or global grant creation.

Policy now carries an explicit exact capability allowlist and a separate
`allow_capability_wildcards` flag. A wildcard scope is represented by the closed
`WILDCARD` scope kind and is rejected unless both the fact and policy explicitly
permit it. Exact scopes carry opaque references.

An effective grant copies only scopes and constraints supplied by the matching
external fact. It never expands them. Its validity begins at the explicit evaluation
instant and cannot extend beyond the fact's `valid_until`. Source references remain
opaque.

### Denials and replay

`SandboxCapabilityDenial` distinguishes:

- `ABSENT`;
- `MISMATCH`;
- `STALE`;
- `INCOMPLETE`;
- `UNAVAILABLE`;
- `UNSUPPORTED`;
- `POLICY_DENIED`.

Rationale codes are fixed, safe and ordered. Input facts are canonicalized before
fingerprinting, so order cannot change the result.

`SandboxCapabilityGrantSet` binds request, admission snapshot, permission snapshot,
policy, admission decision and execution plan identities/fingerprints. Its semantic
identity covers the explicit evaluation instant, grants, denials and rationale.
`occurred_at` is separate occurrence metadata and does not affect replay identity.

The grant set contains no global `authorized`, materialized or executable state.
Resource allocations, enforcement boundaries, materialization, filesystem/network/
process/secrets controls, drivers, supervision, persistence, adapters and wiring
remain reserved for Slice 7 or later explicitly approved work.

## Slice 7 — Filesystem Boundary

Status: **Sandbox Execution Boundary — Slice 7 implemented, globally NOT ACTIVATED**

Slice 7 owns only the deterministic description of logical filesystem access:

`exact plan + capability grant set + resource snapshot + filesystem policy + requests -> filesystem grant set`

The service performs no filesystem lookup, path resolution, materialization, mount,
ACL change or mutation. Its output is an immutable specification for a future
enforcement driver, not evidence that any path exists or is executable.

### Filesystem authority and grant derivation

Filesystem access is deny-by-default. A grant is produced only by the strict
intersection of an operation explicitly requested for the exact plan, the operation's
explicit capability mapping and effective capability scope, a corresponding resource
fact, the plan-bound filesystem policy, and isolation enforcement support. A
capability without the matching opaque resource scope is insufficient, as is a
resource fact without the effective capability.

The resource snapshot is a canonical, fingerprinted external-fact artifact. Facts
bind the exact plan identity/fingerprint, logical resource, opaque scope, operations,
limits, supported enforcement guarantees, isolation profiles and explicit validity
window. Conflicting facts fail closed. Stale facts and stale capability grants remain
distinct from unavailable or incomplete facts.

The closed logical roots are `artifact`, `workspace`, `input`, `output`,
`temporary`, and explicitly permitted `state`. Operations are `read`, `create`,
`write`, `append`, `delete`, `list`, `metadata`, and `execute`. None implies another:
in particular, read does not grant mutation, create does not grant overwrite, and
write does not grant execute. Artifact mutation is structurally denied.

### Path and link model

`sandbox-logical-path-v1` accepts only bounded relative slash-separated segments.
It rejects host absolute paths, drive prefixes, alternate separators, empty or dot
segments, traversal, ambiguous home prefixes, reserved device names, trailing
dot/space forms, and unsupported characters. Invalid input is never repaired into a
valid path. Case sensitivity is an explicit policy property; case folding occurs
only after the original expression has passed validation.

Symlink, junction, reparse-point and hardlink access is represented explicitly.
`NONE` is the default and required baseline; links are never followed implicitly.
Policy and resource facts must jointly support case behavior, link rejection,
hardlink rejection, atomic replacement, executable-content controls and bounded
depth/file/byte limits where those guarantees are required.

### Grants, denials and replay

Filesystem grants carry the exact logical root/path, single operation, intersected
limits, opaque resource scope, overwrite/atomic/executable flags and safe rationale.
Denials distinguish absent capability, absent resource scope, denied operation,
invalid path, traversal, link policy, exceeded limits, unsupported enforcement,
mismatch, stale, incomplete and unavailable inputs.

Requests, policy collections and facts are canonicalized before fingerprinting.
`SandboxFilesystemGrantSet` binds the plan, a fingerprint of the complete canonical
request collection, capability grant set, filesystem policy, resource snapshot and
explicit evaluation instant. Its occurrence timestamp is excluded from semantic
identity. `SandboxFilesystemSpecification` binds the exact grant-set fingerprint and
describes only future expected enforcement.

Resource allocation, real filesystem access, materialization, mounts, ACLs, OS
adapters, network/process/secrets enforcement, subprocesses, supervision,
persistence and Composition Root wiring remain reserved for Slice 8 or later
explicitly approved work.

## Slice 8 — Network Boundary

Status: **Sandbox Execution Boundary — Slice 8 implemented, globally NOT ACTIVATED**

Slice 8 owns only deterministic derivation of declarative network access:

`exact plan + capability grant set + network resource snapshot + plan-bound policy + requests -> network grant set`

It performs no DNS query, socket operation, connection, HTTP exchange, CIDR
expansion, proxy discovery, redirect following, firewall change or OS enforcement.
The resulting specification is input for a future driver, not proof of connectivity
or executability.

### Authority and destination model

Network access is deny-by-default. A grant is the strict intersection of one
canonical request, an effective capability with the exact opaque resource scope, one
corresponding external network fact, the exact plan-bound network policy and the
plan's isolation profile.

Destinations use `sandbox-network-destination-v1` and remain one of four distinct
representations:

- exact normalized hostname;
- canonical IPv4 or IPv6 address;
- canonical IPv4 or IPv6 CIDR;
- explicit hostname wildcard.

These representations are never converted into each other during evaluation. A
hostname is not treated as a resolved address, a CIDR is not expanded, IPv4 does
not imply IPv6, an exact hostname does not include subdomains, and prefix/suffix
matching never creates a wildcard. Hostname and wildcard grants require explicit
DNS-rebinding protection from the future enforcement boundary.

### Protocols, directions and local networks

Protocols are closed to DNS, TCP, UDP, HTTP and HTTPS. Operations are also closed:
DNS query; TCP connect; UDP send/receive; HTTP(S) request; and explicit bind/listen.
Protocol/operation combinations are validated structurally. No protocol or operation
implies another, and inbound bind/listen is absent unless both policy and external
fact model it explicitly.

Loopback, link-local, private/LAN, multicast and IPv4 limited broadcast classes are
classified only from a supplied IP/CIDR representation. They remain denied unless
the exact classes are present in both policy and fact. Hostnames are never resolved
to infer a local class.

### DNS, redirects, proxy and TLS semantics

Redirect permission never transfers the original destination's authority to a new
target. It only declares that a future driver may process redirects while
revalidating every target against an independently applicable grant; explicit
redirect-revalidation enforcement is mandatory.

Proxy inheritance is false unless explicitly requested and allowed by policy and
fact. Proxy isolation remains an enforcement requirement even when inheritance is
disabled. HTTPS requires TLS declaratively, and a fact must prove TLS-validation
support. No certificates, secrets or proxy settings are accessed here.

### Grant derivation, limits and replay

Network facts bind the exact plan identity/fingerprint, destination representation,
protocols, operations, directions, ports, purpose, opaque scope, explicit validity,
isolation profiles, local classes, TLS/redirect/proxy support, limits and enforcement
guarantees. Conflicting facts fail closed. Stale, incomplete and unavailable inputs
remain distinct.

Grants copy only the requested destination, protocol, operation, direction, port
range, purpose and limits after proving each is contained by policy and fact.
Connection count, sent/received bytes, request/response counts, total duration and
idle timeout never expand. Denials distinguish absent capability or resource scope,
destination/protocol/direction/port/wildcard/local-network denial, unsupported
enforcement, mismatch, stale, incomplete, unavailable and exceeded limits.

`SandboxNetworkGrantSet` binds the exact plan, canonical request fingerprint,
capability grant set, network policy, resource snapshot and evaluation instant.
Input order is normalized. Occurrence metadata is excluded from semantic identity.
`SandboxNetworkSpecification` binds the exact grant set and enumerates only the
enforcement guarantees required by its grants.

Network I/O, DNS resolution, sockets, proxies, firewalls, OS adapters, subprocesses,
filesystem/secrets enforcement, materialization, persistence, supervision and
Composition Root wiring remain reserved for Slice 9 or later explicitly approved
work.

## Slice 9 — Process Boundary

Status: **Sandbox Execution Boundary — Slice 9 implemented, globally NOT ACTIVATED**

Slice 9 owns only the immutable description of a process tree that a future
isolation driver may validate and create:

`exact plan + capability grants + filesystem/network specifications + process facts + process policy + requests -> process grant set`

No process is created, signaled, inspected or terminated. The boundary imports no
process, shell or OS isolation API and provides no driver, supervisor or resource
accounting.

### Process authority and exact bindings

Every process artifact binds the exact execution plan, capability grant set,
filesystem specification and network specification. Runtime kind/version,
entrypoint and executable artifact fingerprint must equal the plan. The filesystem
specification must independently contain an `artifact/execute` grant marked as
executable content. A matching external process fact must bind that same plan,
runtime, entrypoint, artifact, isolation profile and explicit validity window.

Effective capability grants remain separate from process facts. Each requested
operation has an explicit capability mapping and must match the process fact's
opaque scope. Neither artifact alone creates process authority.

### Runtime, arguments and environment

The runtime and logical entrypoint reuse the closed Slice 5 types. There is no
command-line or shell field. Arguments are immutable typed elements: bounded token,
integer, boolean or opaque reference. Tokens reject whitespace, control characters
and shell metacharacters; no splitting, interpolation or parsing occurs.

Environment entries contain only an allowlisted name and an opaque value reference.
No value or host-environment inheritance is representable. Working directories are
logical filesystem roots. Standard streams use closed policies for closed, discard,
captured or logical-input behavior; none implies an inherited host stream.

### Tree, handles and lifecycle

Operations are closed to start, spawn-child, signal, terminate and inspect-status.
Start does not imply spawn-child. A child operation needs its own explicit operation
and capability grant, and its only representable permissive policy is
`same_supervised_tree`. Detached execution is always denied.

Handle inheritance defaults to none. Explicit inheritance requires an allowlist in
request, policy and fact, while `no_inherited_host_handles` remains a mandatory
enforcement guarantee.

Startup, termination and cleanup requirements are first-class immutable contracts.
They require support validation before start, creation inside the boundary,
complete-tree termination, forced termination after the grace period, inherited
handle cleanup and verified complete-tree exit. Limits independently bound process
count, tree depth, inheritable handles, argument count/bytes, environment
entries/bytes, startup duration and termination grace.

### Enforcement, denials and replay

Policy requires explicit support for kill-on-boundary-close, descendant tracking,
no detached process, no inherited host handles, verified termination, runtime
allowlisting and executable-artifact binding. Missing descendant tracking or
verified termination therefore fails closed before a process grant can exist.

Denials distinguish runtime denial/unsupported runtime, entrypoint mismatch,
missing capability, denied children, shell semantics, environment or handle denial,
detached execution, unsupported enforcement, mismatch, stale, incomplete,
unavailable and exceeded limits. Diagnostics contain fixed codes rather than
arguments, environment references or artifact identifiers.

Requests and facts are canonicalized before fingerprinting. Occurrence time is
excluded from semantic grant-set identity. `SandboxProcessSpecification` binds the
exact grant set and prior filesystem/network specifications, enumerating everything
a future driver must validate without implying executability.

Process creation, subprocesses, shells, real signals, Job Objects, tokens,
AppContainer, namespaces, cgroups, seccomp, OCI, filesystem/network enforcement,
secrets, materialization, accounting, supervision, persistence and Composition Root
wiring remain reserved for Slice 10 or later explicitly approved work.

## Slice 10 — Resource Limits

Status: **Sandbox Execution Boundary — Slice 10 implemented, globally NOT ACTIVATED**

Slice 10 owns deterministic quota derivation only:

`exact plan + capability grants + filesystem/network/process specifications + support facts + resource policy + requests -> resource grant set`

It performs no measurement, accounting, throttling, termination or operating-system
enforcement. The resulting specification is immutable preflight input for a future
driver.

### Resource authority and bindings

Requested limits, policy maxima, externally supported maxima and effective limits
are four distinct artifacts. Effective limits are derived independently per closed
dimension and retain all three source values for audit. The resource policy binds
the exact plan and fingerprints of the filesystem, network and process
specifications. The process specification must itself reference those same
filesystem and network specifications.

External support facts bind the exact plan, isolation profile, explicit validity
window, supported maximum and enforcement guarantees. Missing required requests or
support facts fail closed. Multiple requests or facts for one dimension are
contradictory rather than implicitly selected.

### Dimensions, units and scopes

The closed dimensions cover:

- CPU quota rate and accumulated CPU time;
- memory working set per process and committed memory for the process tree;
- disk space, file count/size and filesystem operation count;
- stdout, stderr, result, evidence and artifact-output bytes;
- process count, tree depth and inheritable-handle count;
- network connection count and sent/received bytes;
- startup, idle, wall-clock and termination-grace durations.

Every dimension has one semantic unit and scope. Units are closed to bytes, count,
operations, milliseconds and microseconds-per-second. Scopes are closed to
per-process, process-tree, sandbox-total, filesystem-total, network-total and
output-total. Shape mismatches produce explicit unit or scope denials; values from
different shapes are never compared. Consequently CPU time is not wall-clock time,
and a per-process memory limit cannot replace a process-tree total.

### Hard, soft, burst, grace and unlimited

A finite limit always has a positive hard value. Soft, burst and grace are optional,
positive and bounded independently by the hard value. Intersection selects the
smallest hard value from request, policy and support, then intersects each optional
field without allowing it to increase the hard quota. Soft never substitutes hard,
burst never becomes a permanent total, and grace never enlarges the principal
quota.

Unlimited is a distinct explicit representation with no numeric fields. It is
effective only when request, policy and external support all say unlimited and the
policy separately allows it. It is never inferred from an absent value.

### Cross-specification consistency and replay

For dimensions already bounded by earlier specifications, an effective quota cannot
exceed their most restrictive grant:

- filesystem byte/file limits;
- network connections and sent/received bytes;
- process count, tree depth, handles, startup duration and termination grace.

Other closed dimensions still require request, policy and support facts; their
future driver enforcement remains explicit through required enforcement codes.
Unsupported enforcement prevents a grant.

Resource requests, policy requirements and facts are canonicalized by dimension.
Semantic changes alter the grant-set fingerprint, while occurrence metadata is
excluded from identity. `SandboxResourceSpecification` contains only canonical
effective limits and exact prior-specification bindings; it neither measures nor
applies them.

Resource measurement, CPU/memory/disk/process/I/O enforcement, cgroups, Job
Objects, OS adapters, subprocesses, runtime supervision, materialization,
persistence and Composition Root wiring remain reserved for Slice 11 or later
explicitly approved work.

## Slice 11 — Secrets Boundary

Status: **Sandbox Execution Boundary — Slice 11 implemented, globally NOT ACTIVATED**

Slice 11 owns deterministic prospective secret-lease grants:

`exact plan + capability grants + resource specification + secret facts + workload policy + requests -> secret grant set`

It does not read a secret store, acquire a lease, materialize a value, expand an
environment variable, create a file, inject a process or contact a broker. A lease
specification is immutable preflight input only.

### Secret authority and opaque references

Secret declaration, request, external availability, external authorization,
effective grant and lease specification are separate artifacts. Availability is a
boolean fact and never implies authorization. External authorization is represented
by a distinct opaque reference and never implies that a lease is active.

A declaration contains only an opaque secret reference, logical provider, purpose,
opaque scope and expected closed format. There is no field for secret value,
credential material, token, private key, environment expansion, filesystem path or
provider payload. Provider names do not interpret the opaque reference.

Policy binds the exact plan identity/fingerprint, workload, subject and Slice 10
resource-specification fingerprint. Every request additionally binds an explicit
attempt identity. The external fact must correspond to the same subject, workload,
plan, attempt, declaration, purpose, provider, scope, format and isolation profile.

### Operations and capability intersection

Operations are closed to resolve-reference, acquire-lease, renew-lease,
revoke-lease and use-once. Each policy rule maps the declaration to an explicit
effective capability. The capability scope must equal the declaration's opaque
scope, and both policy and externally authorized operations must contain every
requested operation.

A request alone creates no grant. A matching fact without authorization creates no
grant. Authorization without a capability creates no grant. These checks are
performed independently and fail closed with safe diagnostics.

### Lease and renewal semantics

Requests provide timezone-aware `not_before` and requested expiry, maximum duration,
maximum usage count, renewal policy and three revocation requirements. Effective
duration and usage count are the minimum of request, policy and external support.
Expiry cannot exceed the requested expiry or fact validity. Applicable idle or
wall-clock effective limits from Slice 10 further reduce duration.

Renewal is denied unless request, policy operation, policy renewal mode, external
operation and external renewal authorization are all explicit. Use-once requires
usage count one and is structurally incompatible with renewal in request, policy,
fact and grant.

When policy requires revocation on workload termination, timeout or cancellation,
the request must demand it and the external fact must support it. Missing support
produces a lease-unsupported denial. The grant carries these requirements but does
not perform revocation.

### Denials, replay and reserved authority

Denials distinguish absent capability, unavailable secret, missing authorization,
subject/purpose/scope mismatch, unsupported provider, stale or expired facts,
incomplete input, unsupported lease, denied renewal and insufficient isolation.
Diagnostics contain fixed codes rather than complete references.

Requests, rules and facts are canonicalized by opaque reference. Occurrence metadata
is excluded from semantic grant-set identity. `SandboxSecretLeaseSpecification`
binds the exact plan, grant set and resource specification and contains no active,
materialized, injected or executable state.

Secret values, stores, brokers, environment reads, materialization, process
injection, persistence, filesystem/network/process enforcement, drivers,
supervision and Composition Root wiring remain reserved for Slice 12 or later
explicitly approved work.

## Slice 12 — Materialization

Status: **Sandbox Execution Boundary — Slice 12 implemented, globally NOT ACTIVATED**

Slice 12 owns the application boundary that turns an exact execution plan and its
Slice 6–11 grant/specification chain into a verified logical workspace record:

`exact plan + exact grants/specifications + abstract port observations -> verified materialization record`

It does not copy files, mount resources, modify ACLs, resolve secrets, contact the
network or start a process. All host-facing behavior remains behind abstract ports
whose DTOs contain logical roots, opaque references and fingerprints only.

### Materialization authority and exact bindings

Materialization requires the execution plan, capability grant set, filesystem,
network, process and resource specifications, plus the secret lease specification
when applicable. Their plan identities and fingerprints must match transitively
before the first port call. A plan or admission decision alone has no
materialization authority.

`SandboxMaterializationPlan` is immutable and canonical. Its identity covers the
exact upstream fingerprints, logical workspace identity, artifact and runtime
assets, read-only inputs, writable outputs, temporary/state roots, ordered
operations, expected workspace fingerprint and cleanup policy. Occurrence metadata
belongs to the request/record occurrence and does not affect semantic identity.

### Logical workspace and deterministic flow

The public root is the closed logical root `workspace`; host absolute paths are not
representable. Destinations use the versioned Slice 7 logical path model. Duplicate
destinations and conflicting read-only/writable bindings fail closed.

Actions are closed and ordered: prepare workspace, stage artifact, bind read-only
input, prepare output, prepare temporary area, bind runtime asset, verify content,
seal workspace and cleanup workspace. State roots reuse the read-only or writable
preparation action according to their exact filesystem grant. Secret references
participate only through the secret-specification fingerprint and never become
materialization actions.

### Custody, verification and cleanup

Artifact custody is checked against the expected fingerprint before workspace
preparation. Stale, missing or substituted artifacts stop the flow without
materializing. After staging or binding immutable content, the verification port
must recalculate its fingerprint. Workspace verification must then reproduce the
expected workspace fingerprint before sealing.

The service records every completed step and stops at the first non-recoverable
failure. Any failure after successful workspace preparation makes the operation
partial and requires an explicit cleanup call. Cleanup success remains visible as
cleanup-required/verified; cleanup failure remains cleanup-failed and can never
produce a verified record. Port diagnostics are reduced to bounded safe codes.

Only successful content verification followed by successful sealing produces
`SandboxMaterializationRecord`. The record binds expected and observed artifact
fingerprints, completed operations, cleanup state and the exact materialization
plan. A successful record proves materialization integrity only; it does not prove
authorization, executability or execution readiness.

### Ports and Slice 13 reservations

The artifact-custody, workspace-preparation and verification ports are abstract
protocols with neutral DTOs. No adapter is provided in this slice. Real filesystem
or OS operations, mounts, ACLs, containers, copying, durable persistence, secret
resolution/injection, executable preflight, execution drivers, process startup,
runtime supervision and global Composition Root wiring remain reserved for Slice
13 or later explicitly approved work.

## Slice 13 — Runtime Supervision

Status: **Sandbox Execution Boundary — Slice 13 implemented, globally NOT ACTIVATED**

Slice 13 owns deterministic supervision of one exact, already verified
materialization:

`exact materialization + exact specifications + driver facts + canonical runtime events -> supervised result`

It does not create a process, send a signal, inspect an operating system or apply
filesystem, network, resource or secret enforcement. Those effects remain behind
abstract typed ports.

### Supervision authority and bindings

An execution start request binds the exact execution plan, materialization plan and
verified materialization record, capability grants, filesystem/network/process/
resource specifications, optional secret lease specification, isolation profile
and an explicitly valid runtime-driver capability fact. All transitive identities
and fingerprints are checked before the first port call. A verified
materialization therefore remains `pending` and does not imply that a workload was
started.

The attempt identity is derived from semantic bindings and an opaque caller
attempt reference. Occurrence timestamps are excluded. Replaying the same semantic
request creates the same attempt identity; a duplicate start event is rejected by
the lifecycle reducer rather than creating another attempt.

### Lifecycle and canonical events

The closed states are pending, starting, running, termination-requested,
terminating, completed, failed, timed-out, cancelled, terminated,
termination-unverified, cleanup-required and manual-intervention.

Events are structured and sequenced: start-requested, process-created,
process-start-failed, runtime-observed, limit-triggered, termination-requested,
descendant-observed, termination-confirmed, termination-unverified,
runtime-exited and cleanup-required. Sequence numbers must be contiguous and
caller order is authoritative. Out-of-order events are never sorted or silently
normalized.

Process creation keeps the attempt in `starting`; only a valid live observation
enters `running`. Timeout and cancellation record their factual classifications
but do not claim termination. Lost observation preserves
`termination-unverified`. Resource and isolation violations are retained as
facts, without reinterpreting external policy.

### Termination proof

Functional exit is distinct from proof that the supervised process tree ended.
`SandboxTerminationProof` binds the initial process reference, known descendants,
closed termination method, driver reference, supported isolation capabilities,
absence of active descendants and verification outcome. Its occurrence timestamp
does not participate in identity.

Completed and terminated results require a verified proof. Runtime exit without
proof becomes termination-unverified and can never become a successful completed
result. Descendant escape remains a violation even if later termination is
verified.

### Ports, results and Slice 14 reservations

Abstract ports cover workload start from the process specification, runtime and
descendant observation, termination request/confirmation, bounded metric
collection and runtime isolation verification. Their test implementations produce
typed facts only; this slice supplies no OS adapter.

`SandboxSupervisionResult` binds attempt, plan and materialization fingerprints,
final state, exit classification, optional termination-proof identity, canonical
bounded metrics, violations, safe diagnostics, cleanup requirement and canonical
event-stream fingerprint. It does not claim that cleanup was completed.

Real process creation, signals, Job Objects, restricted tokens, AppContainer,
namespaces, cgroups, seccomp, OCI, concrete enforcement, durable persistence,
execution evidence/finalization and global Composition Root wiring remain reserved
for Slice 14 or later explicitly approved work.

## Slice 14 — Cancellation and Timeouts

Status: **Sandbox Execution Boundary — Slice 14 implemented, globally NOT ACTIVATED**

Slice 14 owns deterministic cancellation decisions over an exact Slice 13 attempt:

`attempt + timeout policy + explicit deadlines + explicit evaluation time + canonical cancellation events -> cancellation result`

It creates no timer, signal or process operation. Timestamps are supplied facts;
the domain never reads a clock implicitly.

### Deadline semantics

Deadlines are closed to startup, idle, wall-clock, termination grace and cleanup.
Each is an independent timezone-aware instant. Evaluation compares every instant
with a caller-supplied `evaluated_at` and returns canonical expired/pending sets.
Startup, idle and wall-clock are never substituted for each other. Termination
grace and cleanup deadlines do not move or enlarge the principal workload
deadline.

When several deadlines have expired, phase-specific precedence is explicit:
cleanup, termination grace, wall-clock, idle and startup. This selects a factual
timeout classification; it does not prove that termination began or completed.

### Cancellation authority and bindings

An explicit cancellation request binds the exact attempt identity/fingerprint,
actor reference, purpose, bounded reason code, timeout policy and deadline set.
Occurrence metadata is excluded from its semantic cause fingerprint. A timeout
decision instead binds the exact deadline-set fingerprint and selected timeout
classification.

`SandboxCancellationDecision` represents only the requested state and initial
escalation stage. A request does not imply acknowledgement; acknowledgement does
not imply termination requested; termination requested does not imply initiation
or proof.

### Escalation and event reduction

Escalation is closed and ordered: cooperative cancellation, graceful termination,
forced termination and manual intervention. Policy selects an ordered subset.
Forced termination must be explicitly allowed, and the reducer accepts only the
immediate next stage. Required stages cannot be skipped.

Cancellation events are sequence-bound and canonical. Duplicate event/stage pairs
are rejected explicitly; caller order is never normalized. Cancellation completes
only after a verified Slice 13 termination proof followed by a completion event.
The proof must confirm no active descendants.

An unverified proof remains `termination-unverified`. It produces cleanup-required
when policy requires cleanup, or advances to explicit manual intervention. Timeout
and signal-like events remain factual classifications and never masquerade as
termination.

### Result, public surface and Slice 15 reservations

`SandboxCancellationResult` binds decision, attempt, policy and deadline
fingerprints, classification, applied escalation, termination-proof identity,
descendant status, cleanup requirement, diagnostics and event-stream fingerprint.
Occurrence time does not alter semantic identity. The result does not claim that
physical cleanup occurred.

The Slice 2–13 public surface was reviewed. Existing contracts with test or
cross-slice consumers remain exported. The provisional `SandboxExecutionResult`
and `SandboxEvidenceBundle` names were reserved for their final Slice 15
contracts. Generic provisional state and usage models remained compatibility-only
until the final freeze audit; they were never Slice 14 authority. New helper functions remain
internal; only cancellation contracts, closed enums, services, identities and
their produced error are exported.

Real timers, signals, subprocesses, termination drivers, Job Objects, cgroups,
physical cleanup, durable persistence, Workers integration, runtime finalization
and global Composition Root wiring remain reserved for Slice 15 or later explicitly
approved work.

## Slice 15 — Evidence and Result Materialization

Status: **Sandbox Execution Boundary — Slice 15 implemented, globally NOT ACTIVATED**

Slice 15 owns the pure logical consolidation of one exact supervised attempt:

`admission + plan + grants/specifications + materialization + supervision + optional cancellation + termination proof + bounded evidence -> result and evidence bundle`

It does not persist records, store blobs, upload artifacts, perform cleanup or
rollback, or invoke any driver. A materialized result is an audit artifact, not a
claim that those operational actions occurred.

### Evidence custody and exact bindings

`SandboxResultMaterializationRequest` carries every authority artifact explicitly.
The service verifies the admitted decision and the exact plan, capability,
filesystem, network, process, resource, optional secret, materialization, attempt,
supervision, cancellation and termination-proof identities or fingerprints before
producing any result. Divergence yields an explicit mismatch outcome with no
apparently valid bundle.

Evidence custody remains external and opaque. Each `SandboxEvidenceItem` contains
only a closed category, opaque reference, checksum, bounded summary, estimated
size, redaction level and disclosure level. Raw payloads, secret material,
environment dumps and host paths are not representable. Stdout/stderr are retained
only as a policy-bounded tuple of opaque references in the result binding.

### Redaction, disclosure and bounds

`SandboxEvidencePolicy` is immutable, versioned and fingerprinted. It declares
required categories, allowed disclosure levels, retention metadata, item and
summary bounds, total estimated bytes, diagnostic count and stdout/stderr reference
limits. Cleanup, cancellation, diagnostics, resource usage and boundary violations
add evidence requirements when those facts are present. Missing required evidence
is `incomplete`; binding divergence is `mismatch`; redaction rejection and limit
failure remain distinct. None yields a bundle.

Evidence items are canonicalized by category and opaque reference. Duplicate
references fail closed. Projection and bundle fingerprints include semantic
content only, so caller collection order and occurrence timestamps do not alter
identity.

### Result semantics

`SandboxExecutionResult` keeps functional result and operational state as separate
axes. Closed operational outcomes are succeeded, failed, timed-out, cancelled,
terminated, policy-denied, infrastructure-failed, termination-unverified,
cleanup-required and manual-intervention. A clean success requires a compatible
completed supervision result and a termination-proof reference. Timeout never
becomes cancellation or generic failure; termination uncertainty never becomes
success; cleanup-required remains explicit.

The result binds the exact admission, plan, attempt, verified materialization,
supervision, optional cancellation, termination proof and bounded stream
references. Occurrence metadata is stored separately and excluded from semantic
fingerprints. Replaying the same canonical facts produces equivalent result,
projection and evidence bundle.

### Public surface and Slice 16 reservations

The accumulated surface was reviewed without breaking contracts already consumed
by prior slices and architecture tests. The provisional result/evidence models
were replaced by the final Slice 15 contracts. Public Slice 15 symbols are limited
to produced artifacts, their closed policy/status types, the pure service,
semantic identities and `InvalidResultMaterialization`; construction and
validation helpers remain internal. Older state and resource-summary exports are
kept solely for proven compatibility and do not participate in result authority.

Durable persistence, blob storage, artifact upload, physical cleanup, rollback,
concrete drivers, execution, integration with Governance, Private Evals, Workers
or Bootstrap, and global Composition Root wiring remain reserved for Slice 16 or
later explicitly approved work.

## Slice 16 — Persistence

Status: **Sandbox Execution Boundary — Slice 16 implemented, globally NOT ACTIVATED**

Slice 16 owns durable SQLite persistence of the definitive Slice 2–15 artifacts.
The V1 record envelope is `sandbox-record-v1` over canonical `sandbox-json-v1`.
Every record carries its semantic identity and fingerprint, artifact kind, schema
version, canonical payload checksum, explicit idempotency key, stream/sequence,
lineage fingerprints, completeness/recovery facts, occurrence metadata and
retention metadata. Occurrence timestamps, source and correlation are stored
separately and do not change semantic identity.

### Ownership and append-only stores

Four consumer-owned ports and physically separate tables divide responsibility:
catalog/configuration, admission/planning, execution lifecycle, and result/evidence.
Historical rows have database triggers that reject update and delete. State change
is represented by another record. A V1 checksumed migration creates and verifies
the exact tables, indexes and append-only triggers; an unknown schema/record version
or divergent migration checksum fails closed.

Writes use explicit idempotency keys and expected stream versions. Identical replay
returns the existing record; reuse of an identity or idempotency key with divergent
content is a conflict. Reads require both exact semantic identity and fingerprint;
there is deliberately no `latest` or `current` operation.

### Replay, completeness and restart recovery

Replay orders only by persisted causal sequence and preserves fingerprints. Missing
lineage remains a visible gap rather than a foreign-key insertion failure or an
invented parent. Payload checksum failure invalidates the read. Partial and invalid
records remain readable only as explicit incomplete facts.

Restart recovery is a read-only projection of persisted recovery facts:
incomplete attempt, partial materialization, cancellation in progress, termination
without verified proof, incomplete evidence, cleanup required and manual
intervention. It does not manufacture a terminal attempt, valid evidence bundle,
termination proof or completed cleanup. Retention metadata records policy, hold,
eligibility and optional deadline, but this slice performs no physical purge.

### Slice 17 reservations

Composition Root wiring, concrete integrations with Skills, Workers, Governance or
Bootstrap, operational recovery coordination, physical cleanup/purge, rollback,
drivers, subprocesses, and filesystem/network/process/secret enforcement remain
reserved for Slice 17 or a later explicitly approved slice.

## Slice 17 — Skills Handoff Adapter

Status: **Sandbox Execution Boundary — Slice 17 implemented, globally NOT ACTIVATED**

Slice 17 adds a reference-only adapter outside both bounded-context domains at
`synapse.sandbox_integrations`. Dependency direction is strictly:

`public Skills handoff contract -> external adapter -> public Sandbox admission DTOs`

The pure `synapse.sandbox` domain does not import Skills, and Skills does not own
Sandbox admission. The adapter has no Composition Root wiring and performs no I/O,
policy evaluation, grant calculation, persistence, materialization or execution.

### Ownership and correspondence

Skills retains ownership of skill identity/version, handoff identity, content and
entrypoint fingerprints, structural readiness, capability/resource declarations,
runtime and entrypoint. The adapter preserves those values as exact references and
checks caller-supplied workload, subject, handoff, artifact, purpose, correlation,
execution-profile and isolation-profile correspondence before producing anything.

A successful translation produces only `SandboxAdmissionRequest`, Slice 3 neutral
facts, a neutral runtime descriptor and an opaque entrypoint reference. `structurally_complete` and
`HandoffReadiness.READY` describe the source handoff only: they are not admission,
authorization, an effective grant, materialization, executability or execution.
Artifact availability remains `unknown`, and capability/resource facts remain empty
because declarations are not external grants.

### Compatibility matrix V1

| Skills handoff | Sandbox target | Explicit equivalence |
|---|---|---|
| `v1` | `SandboxAdmissionRequest:v1` | supported |
| `v1` | `sandbox-admission-facts-v1` | supported |
| runtime `python`, media `text/x-python` | `SandboxRuntimeKind.PYTHON` | supported with explicit runtime version |
| runtime `wasm`, media `application/wasm` | `SandboxRuntimeKind.WASM` | supported with explicit runtime version |
| `execution-profile:restricted` | `sandbox-profile:restricted` | supported |
| any unknown version, field, runtime, media or profile pair | none | incompatible; deterministic diagnostic |

Mismatch of subject, handoff/content/entrypoint fingerprint, entrypoint, profile,
capability or resource fails closed. Source diagnostics and incomplete readiness
never produce an admission request. The matrix is versioned as
`skills-sandbox-handoff-adapter-v1`; new fields or meanings require a new explicit
compatibility decision rather than silent omission.

### Slice 18 reservations

Composition Root wiring, invoking the Skills handoff builder, Skills execution,
installation/activation lifecycle operations, admission decisions, effective
grants, Governance or Approvals integration, persistence, materialization, Workers,
drivers and workload execution remain reserved for Slice 18 or a later explicitly
approved slice.

## Slice 18 — Local Composition Root

Status: **Sandbox Execution Boundary — Slice 18 implemented, globally NOT ACTIVATED**

Slice 18 adds the opt-in `synapse.sandbox_composition` boundary. It imports the
public Sandbox surface and the optional Slice 17 integration adapter; the pure
Sandbox domain has no reverse import, and global Bootstrap does not import or start
the runtime.

### Wiring and ownership

`SandboxRuntimeBuilder` receives one immutable `SandboxRuntimeConfig` and constructs
dependencies in a fixed order: validate the entire configuration, open explicitly
managed resources, create the SQLite database adapter, apply and verify the frozen
migration, construct the four responsibility-specific stores and recovery reader,
then assemble services and optional adapters. There is no singleton, registry,
string lookup, import side effect, auto-start or generic `execute()` facade.

`SandboxApplicationServices` exposes the already-supported explicit stages:
canonicalization/fingerprinting, admission assessment/decision, planning, grant
evaluation, materialization planning/application, supervision reducer/application,
cancellation/deadlines/escalation and result/evidence materialization. Abstract
materialization or supervision applications exist only when their complete typed
port group is supplied. The runtime adds no domain behavior.

Persistence composition applies `sandbox-record-v1` and schema V1 through the
checksum-verifying SQLite migrator. Catalog/configuration, admission/planning,
execution lifecycle and result/evidence stores remain separate. Restart opens the
same explicit database and projects incomplete facts through the read-only recovery
reader without operational recovery.

### Lifecycle and health

Configuration is validated before a database or runtime is exposed. Managed
resources open deterministically and close in reverse order if a later build step
fails. Runtime `close()` is idempotent; after close, policy, services, stores and
adapters reject access.

Health reports only observed composition facts: runtime state, SQLite/schema
verification, configured fact/integration adapters, complete materialization and
supervision port groups, managed-resource health and recovery finding count.
Isolation-driver availability and real execution availability are always `false`
in this slice. Supplying abstract supervision ports therefore never claims
executability or workload execution.

### Slice 19 reservations

Global Bootstrap activation, API/CLI exposure, Workers integration, background
services, auto-start, concrete isolation/filesystem/network/process/secret drivers,
real workload execution and operational recovery remain reserved for Slice 19 or a
later explicitly approved slice.

## Slice 19 — E2E, Restart and Recovery

Status: **Sandbox Execution Boundary — Slice 19 validated, globally NOT ACTIVATED**

Slice 19 validates the frozen Slice 2–18 contracts through the opt-in local
`SandboxRuntime`. It adds no production adapter, driver, service or public export.
All operational ports used by the scenarios are deterministic in-memory test
adapters located under `tests/`; they perform no subprocess, network, host
filesystem, secret, cleanup or workload operation.

### Integrated scenario matrix

| Scenario | Persisted/replayed fact | Required outcome |
|---|---|---|
| admitted request through plan, grants, verified materialization and supervision | decision, plan, result and evidence bundle | exact causal lineage and equivalent fingerprints on repetition |
| denied, incomplete, stale or unavailable admission facts | admission outcome | distinct fail-closed outcome; no plan inferred |
| artifact mismatch | admission/materialization diagnostic | mismatch, never silent substitution |
| partially applied materialization with failed cleanup | lifecycle recovery fact | `cleanup_required`; no materialization record |
| timeout or exit with active descendant and no proof | lifecycle/result fact | termination unverified or cleanup required; never clean success |
| cooperative, graceful and forced cancellation escalation | cancellation artifacts | stage order preserved; verified proof required for completion |
| incomplete evidence | result/evidence recovery fact | no valid bundle |
| corruption, unknown version, lineage gap or divergent idempotent write | exact read/replay/write | explicit failure or visible incompleteness |

### Restart points and recovery outcomes

The same SQLite database is closed and reopened through
`SandboxRuntimeBuilder` after an admission decision, execution plan, partial
materialization, started attempt, cancellation request, termination without proof,
and result without complete evidence. Reopen verifies migration/schema checksums,
preserves exact fingerprints and causal order, and reports the recorded
completeness/recovery state. Admission and plan records remain complete facts but
do not imply execution; all intermediate operational facts remain non-terminal.

Recovery is observed before and after restart as a read-only projection. Reading
findings does not call a materialization, supervision, cancellation, cleanup,
retry or termination adapter. Health remains factual: persistence and schema may
be healthy while isolation-driver availability and real executability remain
`false`.

### Slice 20 reservations

Freeze/final audit, production bootstrap activation, concrete isolation or
filesystem/network/process/secret drivers, subprocesses, real workload execution,
operational retry/cleanup/termination, Workers, APIs, CLI, background services and
global wiring remain reserved for Slice 20 or a later explicitly approved slice.

## Slice 20 — Final Audit and Freeze

Status: **Sandbox Execution Boundary — IMPLEMENTED / OPERATIONALLY COMPLETE / FROZEN**

The freeze covers the neutral domain, application services, immutable artifacts,
abstract operational ports, SQLite persistence/recovery, the reference-only Skills
adapter and the opt-in local Composition Root delivered by Slices 2–19. Slice 1's
threat model remains the security baseline. “Operationally complete” means the
bounded context has complete contracts and truthful unavailable-capability
reporting; it does not mean that a workload can run in this repository checkout.
The runtime is not globally activated and remains non-executable without future
concrete isolation drivers.

### Responsibility and authority map

| Authority | Frozen responsibility | Explicit non-authority |
|---|---|---|
| Skills Runtime | structural handoff, Skill identity/version, source fingerprints and readiness | admission, authorization, effective grants or executability |
| Sandbox | admission decision, immutable plan, effective scoped grant artifacts, abstract materialization/supervision/cancellation facts, results and bounded evidence | Skills lifecycle, Governance policy ownership, Approvals decisions, Worker scheduling or bootstrap activation |
| Governance and Approvals | external policy/approval facts referenced by exact fingerprint | Sandbox artifact construction or execution |
| Workers | future consumer of an explicitly activated integration | direct workload execution or bypass of Sandbox admission |
| Composition Root | explicit local wiring, migration verification, lifecycle and factual health | service lookup, singleton ownership, auto-start or generic `execute()` |

Structural completeness, installation, activation, readiness, declaration,
materialization and process creation are separate facts. None implies admission,
authorization, an effective grant, executability, successful isolation or a clean
terminal result.

### Complete lifecycle and state semantics

The frozen lifecycle is:

`handoff reference -> admission request/facts -> assessment -> policy decision -> execution plan -> scoped grants/specifications -> materialization plan/record/verification -> execution attempt/runtime events/observations -> cancellation/deadline/escalation facts -> termination proof -> result/evidence -> persistence/replay/recovery`

Every arrow requires exact identity/fingerprint correspondence. A denied,
incomplete, stale, unavailable or mismatched input remains distinct. Process
creation requires a valid observation before `running`. Timeout, cancellation,
runtime exit, termination request and signal-like facts never substitute for a
verified termination proof with no active descendants. Partial materialization,
failed cleanup, incomplete evidence and manual intervention remain explicit and
cannot become clean success.

### Public surface freeze

The final public surfaces contain 358 Sandbox exports, 8 Skills-integration exports
and 12 Composition Root exports. They are frozen by executable architecture tests.
The Sandbox count is deliberately broad because each retained family is either a
consumer-owned port, immutable service input/output, closed state/reason type,
semantic identity, typed error, format/version constant, persistence contract or
explicit SQLite adapter required by the local Composition Root. Export ownership by
producer module is:

| Family/module | Exports | Justification |
|---|---:|---|
| admission policy and assessment | 18 | admission policy inputs, decisions and diagnostics |
| cancellation | 20 | deadlines, escalation, events and terminal factual result |
| canonicalization | 3 | frozen canonical encoding and fingerprints |
| capability grants | 8 | scoped grant facts and evaluator |
| consumer-owned fact ports | 6 | typed admission/configuration dependencies |
| typed errors | 27 | fail-closed public failure surface |
| execution planning | 13 | immutable plan/specification/runtime references |
| admission facts | 18 | exact fact snapshot and completeness semantics |
| filesystem boundary | 21 | logical grants/specifications; no host I/O |
| semantic identities | 35 | exact reads, lineage and artifact binding |
| materialization | 31 | abstract ports, requests, records and verification |
| neutral foundation models | 7 | admission DTOs and explicit cleanup/rollback facts |
| network boundary | 23 | logical policy/grants/specification; no sockets |
| persistence ports and records | 19 | append-only stores, replay, completeness and recovery |
| process boundary | 25 | command-free process specification and enforcement requirements |
| resource limits | 18 | typed dimensions, grants and effective limits |
| results and evidence | 17 | bounded/redacted policy, artifacts and service |
| runtime supervision | 22 | abstract driver ports, events, proof and reducer |
| secrets boundary | 18 | opaque references/leases only; never secret values |
| SQLite adapters | 7 | local durable stores, migration and recovery reader |
| cleanup/rollback states | 2 | explicit non-operational outcome facts |

Seven unused Slice 2 provisional symbols were removed before freeze:
`ResourceUsageSummary`, `SandboxAdmissionState`, `SandboxAuthorizationState`,
`SandboxExecutabilityState`, `SandboxExecutionState`,
`SandboxMaterializationState` and `SandboxOutcome`. They had no producer or
consumer and were superseded by the precise artifacts and outcomes above. No
duplicate export or obsolete alias remains.

### Persistence and recovery freeze

Canonical payloads remain `sandbox-json-v1`; durable records remain
`sandbox-record-v1` with schema version 1. The frozen migration checksum is
`c83b149985d436d8d9959fd51b0bcdba94376f6f2377967553b33d5a4ae4cb59`.
Historical tables remain physically separate by responsibility and guarded against
update/delete. Writes retain optimistic concurrency and explicit idempotency;
exact reads require identity plus fingerprint. Replay preserves persisted causal
order and exposes gaps. Payload, version or migration corruption fails closed.

Recovery remains a read-only projection. It may expose absence of a required
terminal artifact as an incomplete recovery fact, but it never inserts that fact,
executes cleanup, retries work, requests termination, manufactures proof or creates
an evidence bundle. Retention metadata is descriptive only; no physical purge is
part of the frozen boundary.

### Health, integration and operational limitations

`SandboxRuntime.health()` reports actual SQLite/schema verification, configured
adapters and complete abstract port groups. Isolation-driver and real-execution
availability remain `false`. The only cross-context integration is the optional,
reference-only `sandbox_integrations` adapter from the frozen public Skills handoff
contract. Global Bootstrap has no Sandbox import.

Unsupported capabilities are concrete isolation, subprocess/workload execution,
host filesystem/network/process/secret enforcement, secret retrieval, physical
cleanup/rollback, retry coordination, Workers, APIs, CLI, background services and
auto-start. There is no unisolated fallback, implicit shell, host path in domain
artifacts, socket/network I/O, concrete process driver or secret value surface.

Any future driver must live outside the pure domain, implement the existing narrow
ports, provide explicit capability facts, fail closed when enforcement is
unavailable, and be composed by a separately approved activation change. Such a
change reopens the freeze and requires a new threat-model review and critical gate.

### Frozen architecture and quality baselines

The governed runtime graph is frozen at 267 edges with one pre-existing SCC of 13
contexts/35 internal edges. The source/typing-inclusive graph is frozen at 302
edges with two pre-existing SCCs of 3 contexts/4 edges and 26 contexts/84 edges.
`sandbox`, `sandbox_integrations` and `sandbox_composition` are outside all SCCs.
The production boundary contains 28 Python modules: 24 domain/application/
persistence modules, 2 integration modules and 2 Composition Root modules.

The executable freeze gate pins module/export counts, formats, schema, migration
checksum, both graphs/SCCs, lack of Bootstrap activation, lack of concrete driver
imports and read-only recovery. Global pytest, architecture tests, Sandbox tests,
Ruff, Mypy with a clean cache and `git diff --check` are required whenever the
freeze is reconsidered. Current checkout-specific test counts are recorded in the
Slice 20 delivery evidence rather than treated as a permanent semantic contract.
