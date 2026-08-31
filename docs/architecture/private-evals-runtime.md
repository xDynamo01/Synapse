# Private Evals Runtime Architecture

Status: **Private Evals Runtime — IMPLEMENTED / OPERATIONALLY COMPLETE / FROZEN (2026-07-23); backend NOT READY**
Date: **2026-07-19**

## 1. Purpose

Private Evals Runtime is the bounded context that owns private evaluation definitions,
reproducible run manifests, case execution coordination, scoring, verdicts, baseline
candidates, comparisons, regression detection and minimized Evidence projection.

The domain exists to answer, with reproducible and policy-governed evidence, whether a
declared subject satisfies a versioned evaluation protocol and whether it improves,
remains stable or regresses relative to a compatible baseline.

Private Evals is not an institutional approval authority. A passed verdict does not
approve an RFC, Implementation Plan, Skill, release or deployment. Project Governance
continues to own institutional Evidence, acceptance and approval.

## 2. Confirmed Inventory Constraints

This architecture starts from these verified constraints:

- no partial Private Evals implementation exists;
- `project_governance.models.EvalReference` is reference-only;
- Project Governance already owns Evidence, Acceptance Criteria, Quality Gates, RFCs,
  Plans and approval workflow;
- Intelligence Trust Boundary already owns canonical Information Assets,
  classification, ownership, provider trust, egress policy, minimization, redaction,
  manifests, approval bindings, provenance, ledger and operating profiles;
- Storage Primitives provide atomic writes, optimistic revisions, checksums, locks,
  migrations, recovery, retention and pagination;
- Skills Phase 1 and Tools provide versioned metadata and controlled execution;
- Missions, Workers and Swarm have useful execution behavior but expose no proven narrow
  execution port suitable for Private Evals;
- Swarm has no demonstrated default eval use case;
- Desktop-mediated upload/form submission is a known ungoverned path;
- Project Governance, Skills and Intelligence Boundary remain outside the current
  aggregated SCC;
- no frozen module needs to change to define or implement this domain;
- reproducibility must not depend on a Git commit or Repository Runtime.

The current Git state is not an architectural prerequisite and is not part of the run
identity.

## 3. Ownership

| Concept | Responsibility and identity | Mutability and invariants | Sensitive data and persistence | Owner |
| --- | --- | --- | --- | --- |
| Eval Suite | Stable logical evaluation family, identified by `suite_id` | Root metadata is revisioned; identity never changes | Contains classification and owner, not private payload | Private Evals |
| Suite Version | Immutable evaluation protocol identified by `(suite_id, version)` | Explicit SemVer; frozen before use; any semantic change creates a new version | Stores case references, protocol and checksum | Private Evals |
| Eval Case | Stable logical test within a suite, identified by `case_id` | Stable identity; behavior lives in an immutable Case Version | No duplicated dataset payload | Private Evals |
| Case Version | Immutable case definition `(suite_id, case_id, version)` | Input binding, expected outcome, evaluator, weight or policy change requires a new version | May contain bounded non-sensitive inline input; otherwise references | Private Evals |
| Dataset Binding | Immutable binding from a suite/case protocol to governed content | Freezes asset ID, custody reference, revision and checksum | Contains opaque references only | Private Evals |
| Eval Run | Lifecycle aggregate identified by `run_id` | State is revisioned; finalized content is immutable | Stores metadata and references, not raw private payload | Private Evals |
| Eval Run Manifest | Complete reproducibility snapshot identified by `manifest_id` and fingerprint | Immutable once the run becomes `ready` | Secret-free canonical metadata | Private Evals |
| Eval Result | Result for `(run, case version, repetition)` | Append-only; at most one accepted result per logical execution key | Raw output is an asset/custody reference; safe summary only | Private Evals |
| Evaluator Identity | Identifies deterministic scoring implementation | `(evaluator_id, version, checksum)` is immutable | Configuration is normalized and secret-free | Private Evals |
| Score | Typed score produced from one result | Immutable; scale and evaluator identity mandatory | No raw prompt/output | Private Evals |
| Verdict | Deterministic interpretation of scores and execution status | Derived from frozen rules; immutable after finalization | Safe reason codes and minimized details | Private Evals |
| Baseline | Candidate or institutionally accepted comparison anchor | Content immutable; status separately revisioned | References an immutable run and compatibility signature | Private Evals owns record; Governance owns authorization |
| Comparison | Compatibility decision and metric deltas between two runs | Immutable | Safe aggregates and references only | Private Evals |
| Regression Rule | Versioned policy for regression classification | Immutable rule version; changes create new version | No payload | Private Evals |
| Regression Report | Application of one rule version to one comparison | Immutable and reproducible | Safe metric/case summaries | Private Evals |
| Execution Record | Append-only attempt, cancellation, retry and infrastructure outcome | Never overwritten; superseded by later attempts | Error codes and redacted metadata only | Private Evals |
| Materialized Output | Successful execution output fact for `(run, case version, repetition)` | Create-only; at most one accepted output per logical execution | Asset, evaluator-artifact and provenance references plus checksums only | Private Evals |
| Evidence Projection | Minimized projection of a finalized run/report | Immutable checksum; projection contains references, not payload | Explicit allowlist | Private Evals produces; Governance stores/owns Evidence |

Ownership intentionally does not move RFCs, Plans, Acceptance Criteria, Quality Gates,
final approval, Information Assets, provider trust, egress policy, Skill packages, Tool
definitions, Mission/Worker lifecycle, Swarm strategies or storage mechanics into
Private Evals.

## 4. Out of Scope

- public benchmark hosting or sharing;
- dataset acquisition through browser/Desktop upload;
- arbitrary evaluator plugins or user-supplied executable code;
- Skill generation, mutation, promotion or autoevolution;
- training, fine-tuning or model promotion;
- Repository Runtime, Git operations or source checkout management;
- Coding Sessions;
- Sandbox implementation or direct process/container execution;
- Deployment Runtime or release promotion;
- distributed execution, distributed locks or multi-node scheduling;
- Swarm as the default evaluator/executor;
- institutional approval of RFCs, Plans, Skills, baselines or deployments;
- API, Commands, concrete adapters and bootstrap wiring in this phase.

## 5. Domain Model

### EvalSuite

Fields:

- `suite_id`, stable and globally unique within Private Evals;
- `name`, `description`, `owner`, `project_id`;
- `classification`, validated against the canonical Intelligence classification;
- `status`: `active`, `deprecated` or `archived`;
- `revision`, `created_at`, `updated_at`;
- default regression-rule reference and metadata allowlist.

Changing descriptive metadata increments the suite revision. Changing evaluation
behavior never mutates the Suite root; it creates a Suite Version.

### EvalSuiteVersion

Fields:

- `suite_id` and explicit SemVer `version`;
- ordered, unique `EvalCaseVersionRef` values;
- immutable dataset-binding references;
- scoring protocol version;
- default repetition, concurrency, timeout and retry policies;
- compatibility policy and required-case set;
- classification and owner snapshot;
- status: `draft`, `frozen` or `deprecated`;
- canonical checksum.

A run may reference only a `frozen` version. Once frozen or referenced by any run, the
record is immutable. Deprecation changes availability for new runs, never historical
meaning.

A new version is mandatory when cases, dataset bindings, expected outcomes, evaluator
identity/configuration, score scales, required-case policy, default repetition protocol
or comparability semantics change. Purely descriptive Suite-root changes do not require
a new Suite Version.

Compatibility is explicit, never inferred only from SemVer. A Suite Version declares
which earlier protocol versions, if any, are structurally compatible and which
dimensions may differ in a comparison.

### EvalCaseVersion

Fields:

- `suite_id`, `case_id`, explicit case `version`;
- `input_kind`: `inline` or `dataset_item_reference`;
- bounded inline value or opaque dataset/item reference;
- expected-outcome specification;
- `EvaluatorRef` with ID, version and checksum;
- normalized evaluator configuration checksum;
- weight greater than zero;
- tags from a bounded normalized set;
- owner and classification;
- logical timeout;
- `side_effect_policy`: `none`, `idempotent` or `forbidden`;
- `required` and `critical` flags;
- status: `draft`, `frozen`, `deprecated`;
- canonical checksum.

Private or restricted content must use an asset/dataset item reference. Inline input is
allowed only below a configured size limit and only when classification policy permits
duplication. Expected outcomes follow the same rule: private expected content is
represented by a governed reference or checksum, not copied into the case record.

### DatasetBinding

Fields:

- `binding_id`, `asset_id`, opaque `content_reference`;
- dataset revision and content checksum;
- item-manifest checksum and optional item count;
- classification/ownership snapshot references;
- retention-policy reference;
- selection/schema fingerprint;
- created-at and immutable checksum.

### EvalRun and EvalRunManifest

`EvalRun` contains lifecycle state, revision, current manifest reference, counters and
terminal references. `EvalRunManifest` is a separate immutable record containing every
input needed to explain and, within declared nondeterminism, repeat execution.

### EvalResult and ExecutionRecord

`EvalResult` represents one accepted, immutable measurement for one logical
`(run, case version, repetition)`. It contains that identity, execution/output
references, output checksum, safe summary, the single canonical score, local case
verdict, evaluator artifact/provenance references, semantic result fingerprint,
producer/version, creation timestamp, factual resource usage and record checksum.
`ExecutionRecord` records attempt number, idempotency key, timestamps, adapter identity,
status, redacted error code, egress manifest and output reference.

`MaterializedOutputRecord` is a separate pre-scoring fact. It records the accepted
successful execution output, successful attempt, provenance, resource usage and content
fingerprint. It contains no score, evaluator-scoring event, scoring-protocol identity or
verdict. Materialization never creates or mutates an `EvalResult`.

`EvalResult` has no internal materialized-to-evaluated lifecycle. It is created only
after evaluator output exists and remains the immutable accepted case evaluation result
defined above. Re-evaluation under a different evaluator, Case Version or scoring
protocol requires a new frozen Suite Version and a new Run; neither record is enriched
or overwritten.

A valid `EvalResult` does not copy the evaluation request, response, security snapshot
or Materialized Output record. Evaluator identity is carried by its canonical `Score`;
protocol and security identity are frozen by the referenced Run Manifest. The result
stores only final evaluator artifact/provenance references and its semantic result
fingerprint. Evaluator failures do not create an `EvalResult`; a future append-only
`EvaluationAttemptRecord` will distinguish never-attempted, failed, retried and
eventually successful evaluation without overloading result semantics.

## 6. Aggregates and Invariants

### Suite Aggregate

Root: `EvalSuite`.

Includes immutable Suite Versions and their ordered references to immutable Case
Versions and Dataset Bindings.

Invariants:

1. `suite_id` never changes.
2. `(suite_id, version)` and `(suite_id, case_id, case_version)` are unique.
3. Only frozen Case Versions and Dataset Bindings can enter a frozen Suite Version.
4. A frozen or used Suite Version is never mutated.
5. Required/critical case references are unique and present in the version.
6. Aggregate checksum covers ordered semantic content, not timestamps or display-only
   metadata.

### Run Aggregate

Root: `EvalRun`.

Includes one immutable Run Manifest, append-only Execution and Evaluation Attempt
Records, immutable Results and one terminal finalization record for runs finalized after
execution begins. Pre-execution validation denial/cancellation remains a direct Run-root
transition with its immutable reason reference.

Invariants:

1. One run references exactly one frozen Suite Version.
2. A `ready` run has a complete, secret-free Run Manifest and fingerprint.
3. One logical `(case version, repetition)` has one idempotency key and at most one
   accepted result.
4. Retries create new Execution Records; they never overwrite an earlier attempt.
5. Results must match a case/checksum in the Run Manifest.
6. Finalization checksum covers manifest, accepted result checksums, verdict and
   regression-report references.
7. Terminal runs are immutable.
8. Raw dataset, prompt and output payloads never enter run/result metadata.
9. One logical `(case version, repetition)` has at most one create-only Materialized
   Output; its identity is distinct from the later accepted Eval Result.
10. Materialized Outputs contain neither score nor verdict authority.
11. Evaluation Attempt Records are historical response facts and contain no mutable
    retry decision; terminality is a separate conclusion bound to a frozen policy
    fingerprint and maximum-attempt count.
12. A scoring verdict never determines operational lifecycle status: every coherent
    scorable run becomes `completed`, including `failed`, `inconclusive`, `blocked`,
    `policy_denied` or `invalid` scoring verdicts.
13. Finalization separates path, terminal disposition, result coverage and terminal
    causes. No single enum carries more than one of those dimensions.

### Baseline Aggregate

Root: `EvalBaseline`.

Invariants:

1. A baseline references one finalized, eligible run.
2. Baseline content and compatibility signature are immutable.
3. Promotion and revocation require a valid Governance implementation binding and an
   authorized actor; Private Evals cannot self-approve.
4. At most one active baseline exists for the same suite/version and declared comparison
   scope.
5. Activating a compatible replacement marks the old active baseline `superseded`; it
   does not delete it.

### Comparison Aggregate

Root: `EvalComparison`.

It owns the compatibility decision, controlled dimensions, deltas and result. A
Regression Report applies exactly one immutable Regression Rule Version to one
Comparison.

## 7. State Machines

### Suite Version

```text
draft --> frozen --> deprecated
  |         |
  +---------+-- no return to draft
```

- `draft` may be revised with optimistic concurrency.
- `frozen` is immutable and eligible for runs.
- `deprecated` remains readable/comparable but is unavailable for new runs unless an
  explicit administrative override is recorded.

### Run

```text
created
   |
   v
validating -----> invalid
   |  |  |
   |  |  +------> policy_denied
   |  +---------> blocked -----> validating
   |                |
   |                +----------> cancelled
   v
ready -----------> running --------------------+
  |                  |   |   |   |              |
  +--> cancelled     |   |   |   +--> policy_denied
                     |   |   +------> cancelled
                     |   +----------> failed
                     +--------------> completed
                     +--------------> partially_failed
```

Meanings:

- `created`: mutable preparation record; no execution permitted.
- `validating`: references, checksums, policies and snapshots are being validated.
- `blocked`: structurally valid, but a resolvable prerequisite such as scoped approval
  is absent. Revalidation is allowed without changing the frozen protocol inputs.
- `policy_denied`: terminal explicit security/policy denial.
- `invalid`: terminal structural or integrity failure.
- `ready`: immutable manifest/fingerprint exists; execution may start.
- `running`: one or more logical case executions are active or recoverable.
- `completed`: all required logical executions produced structurally valid results;
  the verdict may still be `failed` or `inconclusive`.
- `partially_failed`: some executions ended in infrastructure failure after allowed
  retries; preserved results remain valid.
- `failed`: run-level infrastructure or finalization failed and trustworthy completion
  cannot be established.
- `cancelled`: no new work may be dispatched; accepted completed results remain as
  partial evidence but no passed run verdict is produced.

#### Run finalization semantics

Finalization has two exclusive paths: `scorable` and `terminally_unscorable`.
`scorable` requires the complete matrix, corresponding immutable results and the exact
create-only `RunScoringDecision`; its operational disposition and lifecycle status are
always `completed`. The scoring verdict remains owned by the scoring decision.

`terminally_unscorable` requires exactly one verified terminal-failure projection for
every result gap and no scoring decision. The record represents independent dimensions:

- disposition: `failed`, `policy_denied`, `cancelled` or `invalid`;
- coverage: `none` or `partial`;
- terminal causes: execution failure, evaluation failure, policy denial, cancellation
  and/or invalid response;
- lifecycle target: derived once by the finalization policy and frozen in the record.

Terminal precedence is `invalid > policy_denied > cancelled > ordinary failure`.
All causes remain recorded even when a higher-precedence disposition wins. Ordinary
failure with partial result coverage maps to lifecycle `partially_failed`; coverage is
still a separate field and does not itself constitute a disposition.

Retry terminality is not stored on an attempt. A `RetryTerminalityProof` references the
frozen policy identity, policy fingerprint, maximum attempts, final attempt and the
status evaluated. Exhaustion requires `final_attempt == maximum_attempts`; policy
denial, cancellation and invalid response are explicitly non-retryable. Execution and
evaluation failure projections must correspond to the latest immutable attempt and its
checksum. Materialization failure is not finalizable until a dedicated immutable source
record exists.

Finalization persistence precedes the Run-root CAS. First creation uses the revision
observed by the input and rejects a stale revision before persistence. Recovery of an
already persisted, valid finalization may use the current non-terminal revision. A
terminal Run with the same reference is replay; a different reference is conflict; a
terminal Run without a reference or a corrupt finalization requires intervention.
Pre-execution cancellation already committed on a `blocked` or `ready` Run wins before
any execution finalization may be persisted. Once a Run is `running`, cancellation is
represented by terminal slot facts and competes as a finalization candidate: the first
create-only finalization wins and a divergent candidate is rejected. A persisted
finalization always wins over a later cancellation request even before the Run CAS;
recovery completes its pending lifecycle transition. No divergent terminal root is
overwritten.

Invalid transitions return a structured conflict and never mutate state. Repeating an
already completed transition with the same idempotency key returns the existing record.

Cancellation is cooperative: stop dispatch, request cancellation for active execution
IDs through the execution port, preserve terminal attempts, then finalize `cancelled`.

Retries apply only to declared infrastructure failures and only when side effects are
`none` or declared idempotent. Evaluation failure, invalid output, `policy_denied` and
critical case failure are not retried automatically.

On restart, a `running` run is reconciled under its run lock. The coordinator queries
the execution port by idempotency key. A found terminal outcome is recorded once; an
unknown execution becomes an infrastructure failure and may be retried only under the
frozen retry policy. Recovery never silently duplicates work.

## 8. Dataset Custody

Private Evals owns Dataset Bindings, not a second canonical asset system.

The core stores only:

- canonical Intelligence `asset_id`;
- opaque local custody reference;
- dataset revision;
- payload checksum;
- item/schema manifest checksum;
- classification/ownership/policy references;
- bounded descriptive metadata.

The payload remains behind a domain-owned `DatasetContentReadPort` implemented by a
future bootstrap adapter. The core never imports a filesystem, blob store or
`FileCollection` implementation and never exposes custody references through normal
delivery responses.

Binding workflow:

1. the dataset must already exist in an approved local custody implementation;
2. it must be registered as a canonical Information Asset;
3. the asset's classification, owner and external-processing policy are read from the
   Intelligence boundary;
4. the custody adapter reports revision, checksum, item-manifest checksum and size;
5. Private Evals freezes those values in an immutable Dataset Binding;
6. run validation rechecks the binding before producing the Run Manifest;
7. execution reads only the referenced items and verifies checksums as data is consumed.

Large datasets are streamed or paged through the port and never copied into Suite,
Case, Run or Evidence records. A run freezes identity, not a duplicate payload. If the
custody revision/checksum changes, the old binding is no longer valid for a new run and
a new binding is required. Historical runs retain the old reference/checksum and become
non-replayable rather than silently reading changed data if retention removed the
payload.

Retention is the intersection of the canonical Information Asset policy, dataset
binding policy and baseline/evidence references. A dataset referenced by an active
baseline or required Governance Evidence cannot be deleted by Private Evals.

Desktop upload/form submission is prohibited as a custody source and as eval egress.
An adapter must declare a governed local custody boundary; `desktop_ui_upload` or any
equivalent ungoverned boundary is rejected during validation.

Governance receives only asset/binding/run references, checksums and minimized
summaries. It never receives the dataset payload or item content.

## 9. Reproducibility Identity

Every `ready` run has an immutable `EvalRunManifest` with these required sections:

1. **Protocol**: suite ID/version/checksum, ordered case version/checksums, scoring
   protocol and regression-rule reference when applicable.
2. **Dataset**: binding ID, asset ID, revision, payload checksum, item/schema manifest
   checksum and selection fingerprint.
3. **Subject**: explicit subject kind and a safe subject fingerprint. The subject may be
   a model/provider configuration, Skill set, Tool set or caller-supplied source
   fingerprint; it is never inferred from Git.
4. **Model/provider**, when used: provider ID, processing boundary, model ID/version,
   immutable safe configuration checksum and decoding parameters.
5. **Skills/Tools**, when used: exact IDs, versions and content/definition checksums.
6. **Evaluator**: evaluator ID, version, implementation checksum and normalized
   configuration checksum.
7. **Security**: policy snapshot IDs/revisions/checksums, operating profile, required
   classifications and approved manifest references that are known at preparation time.
8. **Execution protocol**: seed policy, repetition count, bounded concurrency, retry
   policy, logical/call timeouts and side-effect policy.
9. **Environment**: allowlisted OS, architecture, Python/runtime version and declared
   capability versions. Hostname, username, absolute paths and process inventory are
   forbidden.
10. **Provenance**: creator, originating Project/RFC/Plan binding, source fingerprint
    authority and prior manifest references.

### Fingerprints

The manifest fingerprint is SHA-256 over canonical JSON with sorted keys, normalized
enums/numbers and explicit nulls where semantically relevant.

Included:

- all semantic identities, revisions, versions, checksums and execution policies above.

Excluded:

- `run_id`, `manifest_id`, timestamps and lifecycle status;
- display names/descriptions;
- raw dataset/prompt/output content;
- secrets, tokens, credentials and unrestricted provider payloads;
- absolute paths, host/user identity and transient resource metrics;
- approval secrets. A safe approval/manifest ID and checksum may be included.

Credential values never enter a fingerprint. If credential rotation affects semantics,
the safe configuration snapshot records only a credential-binding ID and version, not
the secret or its hash.

The manifest stores:

- `protocol_fingerprint`: everything that defines measurement conditions;
- `subject_fingerprint`: the declared subject under test;
- `run_fingerprint`: hash of protocol plus subject fingerprints;
- `environment_fingerprint`: allowlisted execution environment metadata.

Different `run_fingerprint` values prove different execution states. Equal fingerprints
mean equivalent declared state, not guaranteed identical output.

Case-evaluation identity has three deliberately separate layers:

1. `evaluation_event_fingerprint` is semantic identity over logical result,
   Materialized Output fingerprint, evaluator identity including configuration checksum,
   and scoring-protocol fingerprint. It excludes timeout, correlation, idempotency key,
   timestamps and resource usage.
2. `evaluation_request_fingerprint` adds manifest/output references, the single metric
   definition, security snapshot, evaluator inputs, deterministic seed and timeout. It
   identifies an exact request, not a new logical result.
3. `evaluation_response_fingerprint` identifies one returned attempt, including status,
   measurement facts, final references, timestamps, resource usage and reason code.

The semantic `result_fingerprint` derives from logical result, Materialized Output and
evaluation-event identities, evaluator/protocol identity, the canonical score, local
verdict and final evaluator artifact/provenance references. `result_id`, `created_at`,
runtime usage and response timing are excluded. The record checksum adds `result_id`,
producer and `created_at`. Thus there is no circular dependency, score ordering is
canonical, and threshold changes affect protocol/result identity without becoming an
evaluator response fact.

Nondeterminism is explicit through `determinism_mode` (`deterministic` or `stochastic`),
seed policy, repetitions and aggregation protocol. A deterministic run requires exact
seed/config identity. A stochastic run records every repetition/seed and may be compared
only when sampling protocol and minimum sample requirements are compatible.

## 10. Execution Boundary Decision

### Options considered

| Option | Benefits | Costs and risks | Decision |
| --- | --- | --- | --- |
| A. Internal executor for pure cases | Lowest coupling; simple deterministic tests | Cannot safely own model/provider/tool execution; risks creating a second execution boundary | Use only for pure scoring/evaluator functions, not subject execution |
| B. Consumer-owned narrow port backed by Missions | Reuses attempts, recovery and bounded scheduling | Adapter complexity; Missions/Tools are in the global SCC; unnecessary lifecycle duplication for ordinary evals | Optional future adapter only after demonstrated scale need |
| C. Domain-owned run lifecycle plus controlled execution boundary | Keeps eval semantics local; avoids Mission/Worker/Swarm dependency; easy unit testing; adapter can use existing Model/Tool governance | Requires one new consumer-owned execution port and a small bounded coordinator | **Selected** |

### Selected architecture

Private Evals owns run lifecycle, case/repetition scheduling, bounded concurrency, retry
decisions, result acceptance and finalization. It does not execute providers, tools,
processes or shell commands itself.

One new consumer-owned outbound port is justified:

```text
EvalCaseExecutionPort
  execute(request: CaseExecutionRequest) -> CaseExecutionOutcome
  recover(idempotency_key: str) -> CaseExecutionOutcome | None
  cancel(execution_id: str) -> CaseCancellationResult
```

Case evaluation uses a second, equally narrow consumer-owned port:

```text
EvalCaseEvaluatorPort
  evaluate(request: CaseEvaluationRequest) -> CaseEvaluationResponse
```

The request is reference-only and binds one Materialized Output to the frozen case,
evaluator, single metric definition, scoring protocol and security snapshot. Threshold,
case weight and required/critical authority stay in the core and are not sent as
evaluator-owned facts. The response contains one typed evaluator measurement fact or a
typed evaluator failure. The core validates and canonicalizes that fact into a `Score`.
The core provides no
evaluator implementation and persists no evaluator-attempt record in this phase.

The request contains immutable references, safe input envelopes, egress authorization
or manifest references, timeout and idempotency key. It does not contain provider
credentials or unrestricted raw configuration. The outcome contains execution status,
output asset/reference/checksum, safe metadata and redacted infrastructure errors. It
does not calculate the canonical score or verdict.

A future bootstrap adapter may use the governed Model Router and Tool Execution Port.
That adapter owns concrete translations. The Private Evals core imports neither model
adapters nor ToolRuntime.

Initial parallelism is bounded in-process coordination of port calls. Swarm is not used.
Missions/Workers may later back the same port if measured workload, distribution or
durable scheduling proves necessary; that changes only the bootstrap adapter, not the
Private Evals domain contract.

## 11. Scoring

Private Evals owns a closed registry of explicitly versioned evaluators. Phase 1 does not
load arbitrary evaluator code.

`EvaluatorIdentity` contains `evaluator_id`, version, implementation checksum and kind.
Changing logic or normalization requires a new evaluator version/checksum.

Minimum score kinds:

- `binary`: pass/fail observation normalized to `1` or `0`;
- `numeric`: finite decimal value with explicit inclusive minimum/maximum and normalized
  `[0, 1]` value.

Exact match, structured assertions and threshold checks are evaluator behaviors that
produce one of these two score kinds; they are not separate extensible metric systems.

Every canonical `ScoreRecord` contains:

- metric ID;
- evaluator identity;
- raw value and explicit scale;
- normalized value;
- the case weight copied from the frozen protocol by the core;
- validity status and reason code;
- repetition/sample count;
- optional confidence and sample variance, with declared calculation method;
- case-level `critical` and `required` flags copied by the core;
- checksum.

A case declares exactly one metric target. The target freezes score kind and scale;
weight and required/critical semantics belong to the case. A second metric requires a
distinct Case Version identity. This preserves one weight, one local threshold and one
logical contribution per case, preventing ambiguous weighting or double counting. The
immutable case result carries one score and a local case/repetition verdict. Run-level
failure budgets, coverage, cross-case aggregation and run verdict remain exclusively in
`ScoringEngine`/`ScoringDecision`.

Rules:

1. NaN, infinity, out-of-scale values and wrong output shape are invalid scores.
2. A missing optional-case score is reported and omitted from weighted aggregation.
3. A missing required-case score yields an inconclusive run unless a frozen rule explicitly
   classifies the structural failure as failed.
4. Repetitions are aggregated per case first, then across cases.
5. Stochastic case summaries include sample count, mean, minimum, maximum and sample
   variance. Confidence is present only when the configured method and sample size allow
   it; it is never fabricated.
6. Suite weighted score is the sum of valid normalized case scores times their unique
   case weights divided by included case weight; each case contributes at most once.
7. Critical and required failures are evaluated independently before the weighted mean;
   no average can hide them.

### Slice 12 run-scoring boundary

The expected execution matrix is a pure, fingerprinted projection of the frozen Run
Manifest and `ScoringProtocol`. The manifest is authoritative for the ordered,
checksummed Case Version references, evaluator binding, suite version, execution
determinism and repetition count. The scoring protocol must agree with those facts and
is authoritative for targets and aggregate policy. Phase one has one repetition count
for the entire run; per-case repetition counts and non-evaluable manifest cases are
prohibited rather than inferred.

Run-scoring eligibility is deliberately structural: `ready` means every expected
case/repetition slot has one canonical result, `incomplete` means at least one slot is
still absent, and `invalid` means supplied facts conflict with the frozen matrix. A
terminal execution/evaluation failure that makes a result impossible is not a fourth
scoring state and does not manufacture an observation. Execution accounting and the
future `EvaluationAttemptRecord` distinguish "not yet present" from "cannot be
produced"; future finalization consumes those terminal facts and must not ask scoring
to reinterpret them.

`RunScoringDecision` is the immutable persistence envelope around the pure
`ScoringDecision`. It adds record identity, manifest/protocol/matrix identity, ordered
result references and semantic fingerprints, explicit complete coverage, provenance,
timestamp and record checksum. It does not duplicate aggregate fields: verdict,
reasons, threshold outcomes, failure-budget use and statistics remain only in the
nested engine decision. Decision record IDs, timestamps, idempotency keys and result
record IDs/checksums do not enter semantic decision identity.

## 12. Verdicts

Case and run verdict states:

- `passed`
- `failed`
- `inconclusive`
- `invalid`
- `blocked`
- `policy_denied`

Precedence for a finalized run:

1. `invalid` when manifest, evaluator, score or result integrity is invalid. Structural
   invalidity is evaluated before authorization so a policy denial cannot hide corrupt
   or inconsistent input.
2. `policy_denied` when otherwise valid required execution or output handling is denied
   by policy.
3. `blocked` when an otherwise valid run is awaiting a resolvable prerequisite.
4. `failed` when any critical case fails, a required case fails its threshold, failure
   budget is exceeded or an applicable regression rule marks a critical regression.
5. `inconclusive` when required results are absent due to infrastructure failure,
   repetitions are insufficient, variance/confidence constraints are unmet or the
   comparison is insufficient.
6. `passed` only when every required invariant succeeds and no higher-precedence rule
   applies.

`blocked` describes a valid run awaiting a resolvable prerequisite and is not a passing
terminal verdict.

An eval failure means subject output was validly measured and failed a criterion. An
infrastructure failure means trustworthy measurement was not produced; it cannot be
converted into a subject failure merely to simplify reporting.

The local case/repetition verdict is derived without consulting any other case,
failure budget, global aggregate, baseline or regression. Its precedence is:

1. `invalid` when the sole returned score is invalid;
2. `inconclusive` when the score is missing (whether the case is required or optional);
3. `failed` when the valid normalized score does not satisfy the case-local threshold;
4. `passed` when the valid score satisfies that threshold, or when no local threshold
   exists.

Required/critical flags affect run scoring, not this local precedence. Metric direction
is represented by the frozen threshold operator (`at_least`, `at_most`, or `between`).
Confidence absence does not fabricate a failure at case level; any frozen run-level
confidence requirement remains `ScoringEngine` authority.

`CaseEvaluationResponse.status=invalid` means the evaluator response/measurement is
structurally or canonically invalid. It does not mean that the subject failed a
threshold and is not an infrastructure failure. Only `succeeded` carries a measurement,
final evaluator artifact and final provenance. `infrastructure_failed`, `timed_out`,
`cancelled`, `policy_denied` and `invalid` carry none of them, use one closed matching
reason code, coherent timestamps and factual resource usage, and never create an
`EvalResult`.

A verdict is evidence, not institutional approval. Private Evals cannot approve or
promote an RFC, Plan, Skill, model, release or Deployment.

## 13. Baselines

`EvalBaseline` fields:

- `baseline_id`;
- suite/version and comparison-scope identity;
- source `run_id`, run fingerprint and finalization checksum;
- protocol and subject fingerprints;
- compatibility signature;
- metric/case summary checksums;
- originating Governance implementation binding;
- status: `candidate`, `active`, `superseded`, `revoked`;
- immutable content checksum;
- revisioned status metadata.

Private Evals may create only a `candidate`. Transition to `active`, replacement or
revocation requires an authorized actor and a Governance `ImplementationBindingPort`
validation result. Private Evals records the external authority reference; it does not
approve itself.

Only a `completed` run with verdict `passed` or an explicitly permitted
`inconclusive` research status may become a candidate. `policy_denied`, `invalid`,
`cancelled`, `failed` or `partially_failed` runs cannot become active baselines.

Baseline content is immutable. Activating a compatible replacement marks the previous
record `superseded`. Revocation prevents new comparisons by default but preserves
history. Active/superseded baselines and their referenced run/results are retained while
Governance Evidence or regression reports reference them.

## 14. Comparisons

Each manifest separates measurement protocol from subject-under-test identity.

Two runs are comparable only when their `protocol_fingerprint` values match, or when an
explicit Suite compatibility rule proves equivalence for every non-subject dimension.

Protocol compatibility covers:

- suite protocol and ordered cases;
- dataset revision/checksum and selection;
- evaluator/scoring versions;
- required/critical cases and weights;
- policy snapshot and operating profile;
- timeout, retry and side-effect policy;
- deterministic/stochastic sampling protocol;
- allowed environment compatibility.

Model/provider/source/Skill/Tool changes may be the declared subject under test. A
Comparison records the controlled dimensions allowed to differ. Any undeclared or
multiple incompatible change produces `incompatible`, not a score delta.

Comparison results:

- `improved`
- `stable`
- `regressed`
- `incompatible`
- `insufficient_data`

`incompatible` means a truthful comparison cannot be made. `insufficient_data` means
protocols are compatible but valid samples/confidence/results are insufficient.

## 15. Regression Detection

`RegressionRuleSet` is owned and versioned by Private Evals. Identity is
`(rule_set_id, version, checksum)`. A frozen Suite Version or explicit Comparison
references exactly one version.

Minimum rule types:

- overall normalized score minimum and maximum allowed delta;
- per-metric minimum and maximum allowed delta;
- mandatory-case pass requirement;
- non-critical failure budget by count or weight;
- critical-case zero-tolerance rule;
- weighted-score threshold;
- minimum repetitions/sample count;
- maximum permitted variance or required confidence bound.

Evaluation order:

1. reject incompatible protocols;
2. verify required sample/result completeness;
3. evaluate policy/invalid/critical cases;
4. evaluate mandatory cases and per-metric thresholds;
5. evaluate failure budget;
6. evaluate weighted/global thresholds;
7. evaluate variance/confidence constraints;
8. produce immutable rule outcomes and final regression classification.

The global mean is never sufficient by itself. A critical regression, required-case
failure or policy denial overrides aggregate improvement.

For stochastic runs, thresholds apply only after minimum repetitions are satisfied.
High variance or unavailable confidence yields `insufficient_data` unless a stricter
frozen rule declares it a failure.

## 16. Evidence Emission

Private Evals emits Evidence through the frozen
`project_governance.contracts.RFCEvidenceWritePort`.

Emission is permitted only from a finalized run/report with a stable finalization
checksum. The projection allowlist contains:

- run and Run Manifest references;
- suite ID/version/checksum;
- baseline and comparison references;
- final verdict and regression classification;
- explicitly allowed aggregate metrics and critical-case reason codes;
- run/protocol/subject/finalization checksums;
- evaluator and regression-rule references;
- egress manifest references;
- minimized provenance;
- safe execution counts and duration summary;
- classification of the Evidence projection itself.

Never emitted:

- dataset or item payload;
- full private prompt or expected outcome;
- full private output;
- secrets, credentials or hashes of secrets;
- unrestricted provider request/response;
- raw logs, traces or stack dumps;
- custody paths/references that reveal private filesystem structure;
- unredacted environment metadata;
- any content not explicitly allowed by the Intelligence decision.

The Evidence artifact reference points to the immutable Private Evals finalization or
regression report. Governance validates and stores the canonical `EvidenceRecord` and
remains its authority. The frozen write contract does not promise idempotent re-emission.

Evidence submission is coordinated from the immutable `EvalRunFinalizationRecord`.
Private Evals deterministically plans only `eval_result`, `policy_block` and
`reproducibility_failure` projections that have sources in the current runtime;
comparison-owned `regression_result` and `compatibility_failure` remain unavailable.
The approved `EvalEvidenceProjectionFactory` constructs every projection and the frozen
`RFCEvidenceWritePort` records it directly. Governance supplies institutional Evidence
identities and remains the sole owner of institutional lifecycle and approval.

`RFCEvidenceWritePort` is write-only and its frozen contract declares neither an
idempotency key nor lookup/reconciliation semantics. Consequently, Private Evals must
not infer that re-emission is safe merely because a projection checksum or a requested
Evidence ID is stable. It can preserve only the historical fact of a response it
actually received. Institutional existence and later availability remain unverifiable
through this boundary.

`EvalEvidenceStore` persists only create-only local coordination facts: one write-started
attempt and, after a returned response, one separate receipt per ordered projection,
followed by one completed submission record. The attempt is the create-only claim that
prevents concurrent duplicate writes; the receipt is the immutable historical response.
An attempt without a matching receipt is deliberately ambiguous and requires manual
reconciliation. It is never automatically resubmitted because Governance may have
accepted the write before the process lost the response or local receipt write. A
semantic identity binds run, finalization fingerprint, RFC/Plan implementation binding,
ordered projection kinds/fingerprints and producer version; timestamps, local IDs,
correlation and idempotency tokens are excluded. Equivalent retries replay, while a
different binding, projection, order or Governance reference conflicts. Operational
terminal causes without an approved Evidence kind are truthfully `not_applicable`.

Safe automatic partial recovery is limited to projections with persisted receipts and
projections for which no write-started attempt exists. Complete receipts with a missing
final record reconstruct that record. A persisted final record requires the complete
attempt/receipt chain. Total local-state loss, an unresolved attempt, or later
unavailability of an institutional reference cannot be solved by the write-only port;
a future adapter/operations slice needs an explicitly governed reconciliation procedure,
without adding a read capability to this domain contract.

## 17. Inbound Ports

Inbound ports are owned by Private Evals and expose application capabilities without
exposing runtime internals.

### EvalCatalogPort

Problem solved: API, Commands and future internal consumers need a stable definition
surface without importing registries/stores.

Minimum methods:

- `register_suite(command) -> EvalSuite`
- `create_suite_version(command) -> EvalSuiteVersion`
- `register_case_version(command) -> EvalCaseVersion`
- `freeze_suite_version(reference, expected_revision) -> EvalSuiteVersion`
- `get_suite(reference) -> EvalSuiteView`
- `list_suites(query) -> Page[EvalSuiteSummary]`

### EvalRunPort

Problem solved: callers must prepare and control runs without accessing execution or
storage implementations.

Minimum methods:

- `prepare_run(command) -> EvalRun`
- `start_run(run_id, idempotency_key) -> EvalRun`
- `cancel_run(run_id, reason, expected_revision) -> EvalRun`
- `get_run(run_id) -> EvalRunView`
- `list_runs(query) -> Page[EvalRunSummary]`
- `list_results(run_id, query) -> Page[EvalResultSummary]`

### EvalAnalysisPort

Problem solved: baseline/comparison/regression behavior must remain in the domain rather
than API/Commands or Governance.

Minimum methods:

- `propose_baseline(run_id, scope) -> EvalBaseline`
- `activate_baseline(baseline_id, governance_binding, expected_revision) -> EvalBaseline`
- `compare_runs(command) -> EvalComparison`
- `evaluate_regression(comparison_id, rule_reference) -> RegressionReport`

### EvalEvidenceProjectionPort

Problem solved: Evidence emission needs a controlled, fail-closed command and cannot be
assembled in delivery code.

Minimum method:

- `emit_evidence(command) -> EvidenceProjectionReceipt`

It internally uses the outbound Governance Evidence contract; it does not make Private
Evals the Evidence authority.

### Slice 15 safe command/query boundary

The implemented inbound boundary is deliberately local to `private_evals`. Immutable,
reference-only DTOs carry an actor reference, authorization-decision reference, policy
fingerprint, implementation-binding reference, correlation/request references and, for
writes, an idempotency key and request timestamp. They never carry roles, administrator
flags, credentials, provider configuration, prompts, outputs, response payloads, tokens
or filesystem paths. Authorization remains an upstream decision; this slice neither
authenticates nor invents authority.

`PrivateEvalsCommandHandlers` exposes exactly the already-approved application stages:
create a run, start a run, record materialized output, create an Eval Result, create a
run scoring decision, finalize/recover finalization and submit Evidence. Each entry
point invokes one principal runtime/service and stops at that stage. There is no
run-everything path, implicit execution/evaluation/scoring/finalization chain, baseline
promotion, comparison, regression or approval behavior. Six narrow injected resolver
capabilities convert explicit governed references into existing records/value objects:
manifest, materialization, evaluation, scoring, finalization and Evidence submission.
Commands enumerate every record reference they consume, including each result, terminal
failure, execution projection, evaluation attempt and Evidence projection candidate.
Resolver operations return one corresponding existing record at a time or fail with
not-found, mismatch or unavailable. They never return a preassembled
`MaterializationInput`, `EvalResultCreationInput`, `RunScoringInput`,
`RunFinalizationInput` or `EvalEvidencePlanningInput`.

Materialization resolves an execution request, execution attempt, logical projection,
manifest and Case Version. Evaluation resolves a Materialized Output, evaluation
request, manifest, Case Version and scoring protocol; the command carries the typed
closed evaluator response directly. Scoring resolves one manifest, one scoring protocol,
one expected matrix and only result IDs listed by the caller. Finalization resolves one
Run, manifest, expected matrix and each explicitly listed result, scoring decision,
terminal failure, execution projection and evaluation attempt; recovery additionally
must resolve the already persisted finalization. Evidence resolves one finalization,
Governance implementation binding, each explicitly listed projection candidate and an
optional scoring decision. Governance identities are typed command facts, not discovered
defaults. No resolver adapter was added.

These Protocols do not select defaults/latest versions, enumerate all records for a Run,
recalculate fingerprints, repair correspondence, retry, call providers or advance the
pipeline. Handlers assemble approved internal input types, invoke exactly one principal
runtime/service and stop. Splitting follows authority and record capability; there is no
generic query facade or service locator.

The command dependency bundle lists each resolver capability and each approved
runtime/service explicitly. It is composition input, not a service locator or facade;
it contains no concrete store, adapter, optional dependency, global runtime or
environment access.

The authorization context validates only the structure and correspondence of actor,
authorization-decision, policy-fingerprint and implementation-binding references.
Authenticity and institutional authority remain upstream responsibilities. A future
HTTP adapter/composition layer must resolve and verify the authorization decision before
invoking this boundary. A syntactically valid reference is never sufficient proof of
authorization. Roles, administrator flags, permissions, tokens, credentials, policies
and arbitrary claims are prohibited.

`PrivateEvalsRunSummaryQuery` composes a minimized read model from existing abstract
stores plus a narrow Evidence local-state projection over attempts, receipts and the
completed local submission. Run lifecycle, scoring verdict, finalization
disposition/coverage/path and local Evidence state remain separate fields. Absence,
write-started orphan attempts, partial/complete receipts and a completed local submission
are distinct facts rather than synthesized progress or approval. Existing terminal causes
are projected directly. Cross-record correspondence, checksum or local coordination-chain
gaps are reported as `reconciliation_required`; the query never repairs them. Boundary
failures become a fixed public error envelope with a correlation reference; internal
exception messages and details are not returned. Retryability is not invented. Only
declared domain/resolution failures are translated. Unexpected programming errors remain
visible to the future operational boundary and are never mislabeled as an invalid client
request.

No FastAPI router or global Commands registration is added in this slice. Both current
delivery surfaces require a composed application runtime, and that Private Evals
composition/adapters do not exist yet. Registering now would either introduce a new
`commands/api -> private_evals` context edge or construct forbidden concrete
dependencies. HTTP versioning, transport status mapping and registration therefore
belong to Slice 16 bootstrap/composition, without changing these typed contracts.

## 18. Outbound Ports

### EvalRecordStore

Problem: core aggregates require persistence without importing `FileCollection`.

Minimum methods:

- `put(record_id, payload, expected_revision=None, create_only=False)`
- `get(record_id)`
- `list(query)`

Ownership: Private Evals. Separate injected store instances are used per collection;
the protocol has no arbitrary collection-name argument and no unrestricted delete.

Future adapter: bootstrap adapter over Storage Primitives.

### DatasetContentReadPort

Problem: verify and read referenced private/large datasets without owning a generic asset
system or copying payload into metadata.

Minimum methods:

- `inspect(content_reference) -> DatasetContentMetadata`
- `read_items(content_reference, selection, cursor, limit) -> DatasetItemPage`

Ownership: Private Evals consumer port. Future adapter: approved local custody provider
built in bootstrap. No Desktop-upload adapter is allowed.

### EvalCaseExecutionPort

Problem: execute a case without concrete Missions, Workers, Swarm, providers, tools,
subprocess or shell dependencies.

Minimum methods: `execute`, `recover`, `cancel` as defined in section 10.

Ownership: Private Evals. Future adapter: bootstrap composition over governed Model/Tool
boundaries. No frozen contract provides this exact semantic surface.

### SkillSnapshotReadPort

Problem: Skills Phase 1 resolution does not expose one guaranteed immutable,
content-checksummed snapshot shaped for a run fingerprint.

Minimum method:

- `snapshot(requirement) -> SkillExecutionSnapshot`

Future adapter projects Skills Phase 1 package/version/checksum metadata. It does not
load instructions or mutate assignments.

### ToolSnapshotReadPort

Problem: ToolExecutionPort is mutation-heavy and broader than reproducibility metadata
needs.

Minimum method:

- `snapshot(tool_id) -> ToolExecutionSnapshot`

Future adapter derives safe version/schema/definition checksum metadata from the
canonical Tool registry.

### ModelSnapshotReadPort

Problem: no frozen port exposes a secret-free immutable model/provider/configuration
snapshot without importing concrete providers.

Minimum method:

- `snapshot(request) -> ModelExecutionSnapshot`

Future adapter projects canonical Model/Provider state and rejects unresolved mutable
configuration.

### SecuritySnapshotReadPort

Problem: reproducibility requires the operating profile and policy identities/checksums,
while the existing egress port governs individual transports rather than exposing a
complete safe run snapshot.

Minimum method:

- `snapshot(project_id, asset_ids, provider_ids) -> EvalSecuritySnapshot`

Future adapter projects Intelligence/Governance policy metadata in bootstrap. It never
returns policy secrets or payload.

### Reused frozen outbound contracts

No duplicate port is introduced for:

- `IntelligenceEgressPort`: asset registration/read, egress authorization, manifest
  validation, derived asset registration and completion;
- `RFCEvidenceWritePort`: canonical Evidence recording;
- `ImplementationBindingPort`: Project/RFC/Plan binding validation and baseline
  institutional authorization;
- `ProjectContextReadPort`: bounded Project context when required.

### EvalEventSink

Problem: domain lifecycle and audit events must not couple the core to a concrete event
bus.

Minimum method:

- `emit(event: EvalDomainEvent) -> None`

Events contain IDs, states, checksums and safe counters only, never private payload.

### Clock and ID generation

`Clock.now()` and `IdGenerator.new_id(kind)` are single-method infrastructure ports.
They solve reproducible tests and lifecycle timestamp/identity coupling. They do not
participate in run fingerprints except through generated stable IDs where referenced;
timestamps remain excluded.

## 19. Persistence Strategy

Required logical collections:

| Collection | Records | Mutation model |
| --- | --- | --- |
| `eval_suites` | Suite roots | revisioned metadata/status |
| `eval_suite_versions` | immutable Suite Versions | create-only after freeze |
| `eval_case_versions` | immutable Case Versions | create-only after freeze |
| `eval_dataset_bindings` | immutable governed bindings | create-only |
| `eval_runs` | Run lifecycle roots | optimistic revisions and run lock |
| `eval_run_manifests` | immutable manifests/fingerprints | create-only |
| `eval_execution_records` | attempts/cancellation/recovery | append-only |
| `eval_evaluation_attempts` | evaluator-response attempt facts | append-only |
| `eval_materialized_outputs` | accepted successful outputs before scoring | create-only/idempotent |
| `eval_results` | accepted case/repetition results | create-only/idempotent |
| `eval_scoring_decisions` | one aggregate run-scoring decision per frozen run/protocol | create-only/idempotent |
| `eval_finalizations` | terminal checksum/verdict | create-only |
| `eval_baselines` | immutable content plus revisioned authority status | optimistic status revision |
| `eval_comparisons` | immutable comparisons | create-only |
| `eval_regression_rules` | immutable rule versions | create-only after freeze |
| `eval_regression_reports` | immutable rule evaluations | create-only |
| `eval_evidence_attempts` | write-started claims per logical projection | create-only |
| `eval_evidence_receipts` | historical Governance responses actually received | create-only |
| `eval_evidence_submissions` | completed local coordination envelope | create-only/idempotent |

Each collection receives a separate `EvalRecordStore` adapter instance with a unique
collection ID and schema version.

`EvalAnalysisStore` remains the cohesive domain-facing protocol for immutable analytic
records (scoring decisions, comparisons, regression reports/rules) plus revisioned
baseline authority. Its scoring surface is create-only and has lookups by decision ID
and logical run. A future implementation may delegate its methods to separate
collection adapters at the Composition Root; the protocol does not require one
monolithic storage object and no separate `EvalScoringStore` is justified while this
surface remains four methods with the same analytic ownership.

Atomicity rules:

- one aggregate-root transition is one atomic store write with expected revision;
- immutable child records are written before the root references them;
- run finalization writes all immutable results, then one create-only Finalization
  record, then transitions the Run root to its terminal state;
- if the last root transition fails, recovery recognizes the valid Finalization checksum
  and completes the transition idempotently;
- no cross-collection transaction abstraction is invented.

Concurrency:

- one collection lock protects each record operation;
- one logical run lock/lease in the Run root prevents two coordinators from dispatching
  the same logical execution;
- optimistic revisions reject concurrent lifecycle and baseline status changes;
- execution/result idempotency keys prevent duplicate acceptance.

Checksums cover canonical semantic payload and exclude mutable storage metadata.
Recovery verifies record and aggregate checksums, quarantines corrupt metadata according
to Storage policy and never reconstructs missing private payload from logs.

Pagination is mandatory for suites, runs, results, comparisons and execution records.
Large payloads are opaque references and never stored in these collections.

Retention is reference-aware:

- active/superseded baselines, Governance Evidence and non-expired audit requirements
  pin run metadata and result references;
- raw/private output retention follows the canonical asset policy;
- cleanup defaults to dry-run and cannot remove active Run/Baseline dependencies;
- tombstone/delete semantics are adapters' concern, not aggregate mutation.

Every collection uses explicit sequential migrations. Frozen records retain prior schema
meaning; migrations must preserve semantic checksums or record an explicit migrated-from
checksum.

## 20. Security Integration

### Preparation

1. Resolve every Dataset Binding to a canonical Information Asset.
2. Reject unclassified, ownerless or checksum-mismatched datasets.
3. Obtain the Security Snapshot and operating profile.
4. Validate provider/model/tool boundaries and side-effect policy.
5. Freeze security identities/checksums in the Run Manifest.

### Execution

Before each external or provider-mediated execution:

1. register any not-yet-registered input envelope as an Information Asset;
2. request minimization/redaction and egress authorization through
   `IntelligenceEgressPort`;
3. transition to `blocked` when scoped approval is required;
4. transition to terminal `policy_denied` on explicit denial;
5. validate the returned manifest immediately before the execution adapter call;
6. pass only the authorized/minimized input and manifest reference;
7. register the output as a derived asset with input provenance;
8. complete the egress ledger record with a safe result reference.

Redaction failure, stale manifest, changed payload checksum, expired/revoked approval,
untrusted provider or forbidden operating profile fails closed.

`invalid` is used for structural/integrity failures: missing asset, checksum mismatch,
bad manifest shape or invalid evaluator/result. `blocked` is used only for resolvable
approval/availability prerequisites. `policy_denied` records a definitive policy denial.

No dataset, prompt, expected output or result payload is emitted to events, logs,
Governance, API or Commands. Logs contain IDs, checksums, safe sizes, states and error
codes.

Desktop-mediated upload/form submission is prohibited by architecture test and runtime
validation. Private Evals has no Desktop dependency and no adapter for that path.

## 21. Future API and Commands Surface

API and Commands remain delivery adapters outside the core.

### Write operations

- register/update Suite metadata;
- create/freeze/deprecate Suite and Case Versions;
- create Dataset Binding from an already governed custody reference;
- prepare/start/cancel/revalidate a Run;
- create/freeze a Regression Rule Version;
- propose a Baseline;
- request Comparison/Regression Report;
- request minimized Evidence emission.

### Read operations

- get/list Suite summaries and versions;
- get/list Run summaries and safe lifecycle state;
- paginated result/score/verdict summaries;
- get Baseline, Comparison and Regression Report metadata;
- get Run Manifest safe projection and fingerprints;
- get Evidence projection receipt.

### Administrative operations

- deprecate definitions;
- activate/supersede/revoke Baseline with Governance binding;
- dry-run retention and recovery review;
- inspect blocked/policy-denied reason codes;
- retry only an explicitly eligible infrastructure attempt.

Responses may contain IDs, revisions, versions, checksums, statuses, verdicts, allowed
metrics, minimized provenance, safe counters and manifest/evidence references.

Responses must hide raw dataset/case input, private expected outcomes, prompts, raw
outputs, secrets, provider payloads, raw logs, absolute custody paths and unredacted
environment metadata. Even administrators receive payload through a separately governed
custody flow, not the eval metadata API.

All list operations are cursor-paginated. Mutations require actor identity, project
authorization, expected revision where applicable and idempotency key for execution.
Baseline authority and external egress require their corresponding Governance/
Intelligence validations.

Errors are structured: not found, revision conflict, invalid state, validation failure,
checksum mismatch, incompatible comparison, insufficient data, blocked, policy denied,
approval required, timeout, cancellation and infrastructure failure. Errors never echo
private payload.

## 22. Dependency Diagram

```text
Future API / Commands / internal callers
                  |
                  v
       Private Evals inbound ports
                  |
                  v
         Private Evals core domain
          |        |         |
          |        |         +--> project_governance.contracts
          |        |                RFCEvidenceWritePort
          |        |                ImplementationBindingPort
          |        |
          |        +------------> intelligence_boundary.contracts
          |                         IntelligenceEgressPort
          |
          +--> domain-owned outbound ports
                 EvalRecordStore
                 DatasetContentReadPort
                 EvalCaseExecutionPort
                 SkillSnapshotReadPort
                 ToolSnapshotReadPort
                 ModelSnapshotReadPort
                 SecuritySnapshotReadPort
                 EvalEventSink / Clock / IdGenerator
                              |
                              v
                    future Bootstrap adapters
                       |       |       |
                       |       |       +--> governed Model / Tool boundaries
                       |       +----------> Skills / policy metadata projections
                       +------------------> Storage Primitives / local custody

Governance / Intelligence / Skills / Tools / Missions / Workers / Swarm
                         -X-> Private Evals concrete runtime
```

## 23. Expected Graph Impact

The core domain is expected to add one bounded-context node and only one-way contract
edges.

Expected governed edges after full future integration, subject to actual import
measurement:

- `private_evals -> project_governance` for frozen contracts/models;
- `private_evals -> intelligence_boundary` for frozen contracts/models;
- `api -> private_evals` for inbound contracts/models, not runtime internals;
- `commands -> private_evals` for inbound contracts/models, not runtime internals;
- optionally `private_evals -> health` only if the domain implements the existing neutral
  Health contributor contract.

Skills, Tool, Model, Storage and execution dependencies remain behind Private Evals-owned
ports and bootstrap adapters, so the core need not create governed edges to their
concrete contexts.

No frozen functional domain imports `private_evals`. Bootstrap composition edges remain
excluded from the governed graph under the existing methodology.

The domain remains outside the current SCC if:

- it imports no concrete Mission, Worker, Swarm, Tool, Model, Policy, Agent or Approval
  runtime;
- no SCC member imports Private Evals concrete modules;
- delivery imports only its public contracts/models;
- adapters remain in bootstrap;
- architecture tests reject new reverse edges and any SCC membership.

Exact edge/context counts must be recalculated during implementation. This document does
not advance the current 72/261 baseline.

## 24. Required Architecture Tests

1. Private Evals imports no bootstrap, API, Commands, delivery, concrete storage,
   provider, Mission, Worker, Swarm, subprocess, shell or future-domain module.
2. Allowed cross-context imports are restricted to frozen Governance/Intelligence/
   Health contracts and models.
3. Consumers import only `private_evals.contracts` and safe public models, never runtime,
   stores, scoring internals or persistence modules.
4. Every concrete store/custody/execution/snapshot adapter exists only in bootstrap.
5. Exactly one production feature builder constructs the domain and its adapter set.
6. The official graph gains only reviewed edges; Private Evals is absent from every
   non-trivial SCC and exact-module graph remains acyclic.
7. Suite/Case Versions and Run Manifests become immutable after freeze/readiness.
8. Run state-machine transition matrix rejects every invalid transition and preserves
   idempotency.
9. No private payload field exists in Run, Result, Execution Record, Baseline,
   Comparison, Regression Report, domain event or Evidence projection models.
10. Dataset binding requires a canonical Information Asset and rejects Desktop upload
    boundaries.
11. External/provider execution is preceded by egress authorization and manifest
    validation; output is registered as a derived asset and completion is ledgered.
12. Skills/Tools/Models are fingerprinted through snapshot ports; the core imports no
    concrete registries/providers.
13. Evidence emission uses `RFCEvidenceWritePort` and an explicit field allowlist.
14. Private Evals exposes no institutional approval or direct baseline self-promotion.
15. API/Commands expose no dataset/prompt/output payload and paginate list surfaces.
16. Swarm, Repository Runtime, Coding Sessions, Deployment Runtime, Sandbox backend and
    Skills Phase 2 remain absent.

## 25. Implementation Slices

Implementation proceeds incrementally. Each slice must stop at its exit criterion
before the next begins.

| Slice | Scope | Completion criterion |
| ---: | --- | --- |
| 1 | Domain value objects and models | Ownership table represented; canonical serialization/checksum tests; no cross-domain runtime import |
| 2 | Store and infrastructure protocols | Minimal protocols compile/type-check; in-memory fakes prove aggregates without FileCollection |
| 3 | Suite/Case registry | Version/freeze/deprecate invariants and conflict tests pass; no payload duplication |
| 4 | Dataset Binding and Run Manifest/lifecycle | Binding integrity, manifest fingerprint and complete transition-matrix tests pass |
| 5 | Scoring and verdict | Binary/numeric scoring, repetitions, variance and critical overrides pass deterministic tests |
| 6 | Baseline/comparison/regression | Compatibility rejection and every result/rule precedence path pass; no global-mean-only decision |
| 7 | Security application service | Assets, policy snapshot, egress/manifest/derived-output flows pass with fakes; Desktop path denied |
| 8 | Evidence projection | Allowlist/minimization/checksum and frozen-port translation tests pass through fake `RFCEvidenceWritePort` |
| 9 | Persistence adapters | Bootstrap-only Storage Primitive adapters pass restart, revision, recovery, retention, migration and pagination tests |
| 10 | Execution/snapshot/custody adapters | Bootstrap adapters pass cancellation, recovery, idempotency and fail-closed security tests; no direct core provider/process access |
| 11 | Case evaluation and result acceptance | Minimal evaluator port; factual response validation; one metric per case; local verdict; pure result factory/projection; idempotent result service; no evaluator adapter or invocation |
| 12 | Run scoring and aggregate decision | Complete case×repetition matrix; direct observation projection; controlled pure `ScoringEngine` invocation; create-only decision/replay; no run mutation or finalization |
| 13 | Run finalization and recovery | Scorable/terminally-unscorable paths, immutable finalization, verified terminal failures, create-only persistence, Run CAS and idempotent recovery pass |
| 14 | Evidence submission | Deterministic planning, direct Governance submission, local receipts, safe partial recovery and explicit reconciliation limits |
| 15 | Commands/API boundary | Typed reference-only handlers and run-summary query; safe errors, explicit stages, idempotency/recovery propagation and zero payload leakage; HTTP/registry deferred to composed bootstrap |
| 16 | Concrete local persistence | All five approved store protocols have restartable SQLite implementations; create-only, CAS, integrity and concurrency tests pass; bootstrap remains absent |
| 17 | Composition and external adapters | Reserved: one reviewed feature builder and only the explicitly approved adapters |
| 18 | Acceptance/freeze | Reserved: composed acceptance scenarios, global gates and operational readiness decision |

The earlier slice table was planning guidance. The approved Slice 16 scope is concrete
local persistence; it does **not** authorize bootstrap composition.

## 25.1 Slice 16: Concrete Local Persistence

Slice 16 implements persistence mechanics only. The store protocols remain unchanged
and continue to be the authority consumed by domain services.

### Protocol audit and ownership

| Store protocol | Records owned | Methods | Create-only | CAS | Query patterns | Concrete decision |
| --- | --- | ---: | ---: | ---: | --- | --- |
| `EvalCatalogStore` | suites, suite versions, case versions, dataset bindings | 15 | children/versions | suites and definition status | identity, bounded filters, cursor pages | `SQLiteEvalCatalogStore` |
| `EvalRunStore` | manifests, runs, results, evaluation attempts, finalizations | 17 | all except run lifecycle | run record | identity, logical execution slot, run pages | `SQLiteEvalRunStore` |
| `EvalAnalysisStore` | scoring decisions, baselines, comparisons, regression rules/reports | 15 | all except baseline status | baseline record | identity, run decision, bounded filter pages | `SQLiteEvalAnalysisStore` |
| `EvalMaterializationStore` | materialized-output references | 4 | yes | no | identity and logical execution slot | `SQLiteEvalMaterializationStore` |
| `EvalEvidenceStore` | attempts, receipts, final local submission envelopes | 8 | yes | no | run, submission and logical fingerprint | `SQLiteEvalEvidenceStore` |

No protocol was found to mix incompatible responsibilities or to require an objective
contract change.

### Backend decision

| Candidate | Existing precedent | Atomicity | CAS | Recovery | Decision |
| --- | --- | ---: | ---: | ---: | --- |
| SQLite | Python standard library; repository had no Private Evals store precedent | yes | guarded update | process restart | selected |
| Structured filesystem | local file collections exist elsewhere | limited across files | manual | possible | rejected for this slice |
| In-memory | existing test fakes | process-local only | possible | no | retained only as test doubles |

SQLite was selected because it is local-first, transactional, dependency-light and can
enforce semantic uniqueness and optimistic concurrency without a new generic
persistence framework. The implementation uses separate typed record tables rather
than one generic repository table.

`PrivateEvalsPersistenceConfig` accepts only a database `Path`, bounded timeout,
create-if-missing, read-only and expected schema version. It does not read environment
variables or accept SQL, credentials, callbacks or arbitrary connection arguments.

Schema version `1` is recorded in the singleton `private_evals_schema`; record
serialization format version `1` is also explicit. Initialization occurs only for a
truly empty database when writable creation was requested. Missing metadata, a partial
schema, missing or extra record tables, missing required indexes, altered columns,
altered foreign keys, lower or higher schema/format versions, an empty non-creating
database and a missing non-creating database all fail closed with a typed error. There
is no silent migration or repair.

The schema owns separate tables for suites, suite versions, case versions, dataset
bindings, manifests, runs, results, evaluation attempts, finalizations, scoring
decisions, baselines, comparisons, regression rules/reports, materialized outputs,
Evidence attempts, receipts and submissions. Semantic identities are domain-derived;
SQLite-generated identifiers are not used. Unique indexes protect one-result-per-slot,
one-finalization-per-run, one-scoring-decision-per-run, one-output-per-slot and the
Evidence claim/receipt/final-envelope correspondences. Foreign keys exist only within
an aggregate's local tables and use restrictive update/delete behavior: versioned
catalog children reference their suite; Run children reference their run; and Evidence
receipts reference the corresponding Evidence attempt. Cross-store references remain
explicit domain correspondences because no cross-store transaction is assumed.

Serialization is deterministic canonical JSON with an explicit, fixed allowlist of
approved immutable dataclasses and enums. It preserves tuples, order, optionals and
decimals, rejects unknown fields/types and validates persisted payload checksums plus
record-owned semantic fingerprints/checksums before writes and after reads. Pickle,
executable deserialization and arbitrary dictionaries are not used. The codec imports
only a fixed source-controlled allowlist of approved record modules when constructing
its type registry; persisted input cannot name or import another module. Stored keys,
record revisions, indexed metadata and child/parent correspondences are checked on read
or save. Canonical byte equality is required during decode, and duplicate JSON fields
are rejected.

Integrity is layered: SQLite constraints protect physical identity and local
relationships; the payload SHA-256 protects stored bytes; strict decoding protects the
type/field boundary; record validators recompute authoritative checksums and
fingerprints; row validation compares every indexed column with the decoded record;
and `foreign_key_check` detects externally introduced orphan rows. Suite/case version
status implies its storage revision (`draft=1`, `frozen=2`, `deprecated=3`), allowing
revision corruption to fail closed even though those immutable domain records do not
carry a revision field.

Each store object owns only configuration and opens a short-lived connection per
operation; there is no global connection or service locator. Writable connections use
WAL, `synchronous=FULL`, foreign-key enforcement, bounded busy timeout and
`BEGIN IMMEDIATE`. Writes commit only after the record and its idempotency fact are
durable; typed failures roll back. `close()` prevents later use. Read-only mode opens
SQLite with `mode=ro`.

### Atomic boundaries

| Operation | Atomic unit | Transaction | Cross-store assumption |
| --- | --- | ---: | ---: |
| create immutable record | record plus idempotency fact | yes | none |
| update run/catalog/baseline with CAS | guarded revision update plus idempotency fact | yes | none |
| append evaluation attempt | exact contiguous attempt sequence plus one unique create | yes | none |
| claim Evidence attempt | one unique create | yes | none |
| save Evidence receipt | parent correspondence validation plus one create | yes | none |
| save final Evidence envelope | finalization plus complete attempt/receipt/projection chain validation and one unique create | yes | none |

The final Evidence transaction uses `BEGIN IMMEDIATE`, validates the complete local
chain from that same connection, and persists the envelope plus idempotency fact before
commit. Once the envelope exists, new attempts or receipts for its semantic submission
fingerprint are rejected; exact retries of already persisted facts remain idempotent.

Equivalent duplicates return `IDEMPOTENT_REPLAY`; divergent identities/content,
reused idempotency keys and stale revisions produce typed conflicts. No create path
overwrites a row, and neither `INSERT OR REPLACE` nor mutating upsert is used. Separate
stores may share the same database file, but services must not infer a distributed or
cross-aggregate transaction from that deployment choice.

Only protocol-declared identity lookups, bounded filters and cursor pagination are
implemented. The stores expose no free SQL, unrestricted search, output reads or
generic repository API. Persisted records remain reference-only: prompts, provider
payloads, output bodies, credentials, tokens, private filesystem paths and arbitrary
metadata are outside the schema.

### Persistence module organization

The implementation remains one internal SQLite adapter module. This is a deliberate
single-authority decision: schema ownership, connection policy, transaction behavior,
serialization validation, idempotency and row-integrity enforcement are one persistence
adapter concern. Each approved protocol still has a separate concrete class and owns
only its aggregate-specific methods; the shared private helpers expose no repository
API. Splitting the five classes now would either duplicate those invariants or create a
new internal package centered on the same shared schema without isolating a distinct
authority. A split becomes justified if a store receives a different backend/schema
lifecycle or if its aggregate-specific implementation can stand without importing the
shared SQLite mechanics. No public generic repository abstraction was introduced.

The temporary SQLite store factory described during Slice 16 was removed when the
Composition Root became the sole productive construction authority. No active import,
test or documentation path depends on it. Slice 16 itself introduced no bootstrap,
HTTP route, external client, approval, baseline promotion, comparison execution or
regression execution. The global backend remains **NOT READY**.

## 25.2 Slice 17: External Boundary Adapters

Slice 17 adds narrow adapters around already approved consumer/public ports. It does
not compose an application, select a provider or execute a real external operation.

| Operational need | Existing authority/port | Adapter decision |
| --- | --- | --- |
| canonical asset lookup, provider boundary, egress and derived asset registration | Intelligence `IntelligenceEgressPort` already consumed by `EvalSecurityService` | no redundant wrapper; keep direct public-contract dependency |
| complete security snapshot | consumer-owned `SecuritySnapshotReadPort`; no equivalent complete public Intelligence projection exists | `IntelligenceSecuritySnapshotAdapter` validates one injected snapshot client and never authorizes |
| case execution | `EvalCaseExecutionPort` | `CaseExecutionBoundaryAdapter` validates one configured backend response; no retry or backend selection |
| evaluator invocation | `EvalCaseEvaluatorPort` | `CaseEvaluatorBoundaryAdapter` validates one configured evaluator response; no retry or registry discovery |
| institutional Evidence write | Governance `RFCEvidenceWritePort` | `GovernanceEvidenceWriteAdapter` performs one write, validates the returned identity and treats transport ambiguity as reconciliation-required |
| command inputs owned by Private Evals | five SQLite stores plus six resolver capabilities | one read-only resolver adapter; transient reference-only inputs require an explicit immutable catalog |
| local Evidence query | `EvalEvidenceStore` and `EvidenceLocalStateReader` | local-only projection reader; no Governance read, recovery or resend |

The concrete boundary adapters live under `private_evals/adapters/`. They accept only
typed, preconfigured clients and an adapter identity/version/requested timeout. The
requested timeout is declarative metadata: the frozen ports expose no deadline or
cancellation argument, so enforcement belongs to the preconfigured client and the
adapter cannot guarantee cancellation. Configuration
contains no endpoint URL, credentials, token, arbitrary headers, callable, SQL or
environment lookup. Errors expose fixed messages and do not include provider bodies,
paths, endpoints or raw responses.

The repository has no safe execution backend that Private Evals may import without
creating a third cross-context edge. Sandbox is not present as an approved boundary,
and provider/tool/worker/mission runtimes remain forbidden. Consequently the execution
and evaluator adapters are validating bridges around explicitly injected implementations
of the frozen consumer ports. Real backend binding, registry selection and lifecycle
ownership remain Composition Root work.

`EvalSecurityService` already consumes only the public Intelligence contract for asset
resolution, provider boundary checks, canonical egress authorization/manifest
validation and derived-asset registration. These operations were not wrapped merely to
increase adapter count. Intelligence remains the authority for assets, custody,
classification, provider trust and egress decisions. The snapshot adapter cannot
construct or grant trust; it only validates a complete snapshot supplied by an injected
client because Intelligence currently exposes no public complete-snapshot read port.

Governance Evidence remains write-only. The adapter performs exactly one call and has
no approval, RFC mutation or Evidence read capability. A timeout/connection failure is
reported as an ambiguous external write and is never retried automatically. Later
existence cannot be confirmed through this boundary.

The command resolver uses SQLite for manifests, cases, materialized outputs, results,
runs, scoring decisions, evaluation attempts and finalizations. Inputs without an
approved persistence owner are supplied through an immutable, explicit reference
catalog; resolution never selects defaults or assembles application inputs. Case
references carry their exact suite/case/version identity. The catalog is a frozen,
non-owning per-command binding bundle for types without an approved read store. It
rejects mutable containers, wrong record types and duplicate references; it is not a
repository or restartable persistence and its construction remains Composition Root
work.

Partial Evidence coordination cannot be discovered from `run_id` through the frozen
store protocol because attempts are keyed by the one-way semantic fingerprint. The
reader therefore accepts an explicit typed `run_id -> semantic fingerprint`
correspondence for partial states. Completed submissions are resolved directly from the
store. It projects only absent, attempt-started, receipt-recorded, receipts-complete,
submitted or reconciliation-required local facts.

Tests use deterministic spies and local SQLite only. No network, provider credits,
private data, shell execution or real Governance write occurs. A test-only harness
proves the boundary sequence through persisted local Evidence receipt/submission, but
there is no production pipeline façade.

### Slice 17 corrective audit

The corrective audit keeps all four boundary adapters as narrow validation bridges.
Execution response fields that do not repeat manifest, environment, model, Skill or
Tool references are transitively bound by the request fingerprint, logical execution
fingerprint and attempt fingerprint; the response must match both identities and its
own complete factual fingerprint. The evaluator bridge additionally validates a
successful score against the request's exact metric, evaluator, kind and scale.

Governance failure classification is deliberately asymmetric:

| Failure | Local classification | Automatic retry | Reconciliation |
| --- | --- | ---: | ---: |
| invalid input before client call | unavailable | no | no |
| connection refused before establishment | unavailable | no | no |
| timeout, reset, broken pipe or lost response | ambiguous external write | no | yes |
| corrupt or divergent returned record | ambiguous external write | no | yes |
| exact returned record | recorded factual receipt | no | no |

The local Evidence reader never assigns institutional meaning. `absent` means no local
attempt; `attempt_started` means an attempt without receipt; `receipt_recorded` means
some but not all local receipts; `receipts_complete` means the expected local chain is
complete; `submitted` means the final local envelope is persisted; and
`reconciliation_required` means local integrity or correspondence is incomplete. None
of these states means Governance acceptance or approval, and the reader performs no
repair or write.

Adapter coverage is behavior-based and parametrized across every snapshot, execution
response, evaluator response and Governance receipt field. It also proves typed
asset/provider/evaluator mismatches, scoring-shape mismatch, timeout/reset
classification, strict one-call behavior, immutable resolver bindings, every resolver
method's explicit-reference behavior, absence of discovery/writes, safe errors,
test-only harness placement, transport isolation and the two-edge cross-context limit.
Unused parallel adapter errors were removed; canonical domain and command error
taxonomies remain authoritative.

At the end of Slice 17, Composition Root, real execution/evaluator clients, HTTP
delivery, approval, baseline promotion, comparison/regression execution and complete
end-to-end integration were still pending. Slice 18 supplied only the approved local
composition and deterministic integration coverage. The global backend remains
**NOT READY**.

## 25.3 Slice 18: Explicit operational composition

`private_evals.composition` is the production Composition Root and the only production
module that constructs the five concrete SQLite stores and four concrete external
adapters. It accepts `PrivateEvalsRuntimeConfig`, an explicit
`PrivateEvalsExternalBindings` value and immutable resolver/Evidence coordination
records. It performs no environment lookup, dependency discovery, dynamic import,
retry, stage transition or pipeline orchestration.

Construction is deliberately ordered:

1. validate runtime configuration and all four bindings;
2. open the catalog store and validate/create the schema;
3. open the run, analysis, materialization and Evidence stores against that schema;
4. construct the immutable command resolver and read-only Evidence reader;
5. validate external client methods and construct only the corresponding narrow
   adapters;
6. construct the approved catalog/run runtimes and materialization, result, scoring,
   finalization and Evidence-submission services;
7. construct command handlers and the run-summary query;
8. return the typed runtime handle and its factual readiness projection.

No raw SQLite connection, SQL, client, mutable registry or string-keyed component
lookup is exposed. `PrivateEvalsRuntimeHandle` exposes explicit commands, queries,
catalog/run lifecycle surfaces and the four narrow external boundaries. Every
production stage remains a separate caller action: creating a run does not start it;
starting does not execute a case; execution does not materialize; materialization does
not evaluate; evaluation does not score; scoring does not finalize; finalization does
not submit Evidence.

The handle owns store lifecycle. Construction failure closes stores already opened in
reverse order. `close()` is idempotent, the handle is a context manager, retained query
surfaces check the shared closed guard, and closed stores reject retained command/runtime
use. Restart creates a new composition over the same database; no singleton connection
or module-level runtime exists. Read-only composition opens the existing schema,
continues to serve local queries and rejects command/catalog/run mutation surfaces.

Readiness is immutable and reference-only. It reports runtime identity/version, schema
version, persistence availability, read-only state, local query and command
availability, and an identity/version/reason for each external capability. Its lifecycle
states are `locally_operational`, `externally_bound`, `degraded` and `closed`.
Explicitly disabled external capabilities yield `locally_operational`; any configured
but unavailable capability yields `degraded`; all four available bindings yield
`externally_bound`; and a closed handle yields `closed`. Capability access fails with a
typed unavailable error rather than exposing a marker as a service. Persistence and
restartable local queries remain usable in degraded mode. Read-only is an orthogonal
fact: it disables commands but does not change whether external bindings are complete.
The projection always reports `backend_globally_ready = false`.

No concrete real client is added. Deterministic fakes cover snapshot, execution,
evaluation and Governance writes in tests; ambiguous Governance writes retain the
approved no-retry/reconciliation semantics. HTTP/FastAPI, workers, schedulers,
background tasks, approval, baseline promotion and comparison/regression execution
remain outside this slice.

Slice 18 made the module operationally complete. The final audit dated 2026-07-23
confirmed the invariants below and froze this bounded context. The global backend
remains **NOT READY**.

## 25.4 Final freeze

Freeze status: **IMPLEMENTED / OPERATIONALLY COMPLETE / FROZEN**, effective
2026-07-23.

The frozen public surface consists of the domain values, immutable models and errors;
the five store protocols and their reference-only request/response contracts; catalog,
run, evaluation, materialization, scoring, finalization and Evidence services/factories;
typed commands and local queries; approved consumer ports; external binding/readiness
models; `PrivateEvalsRuntimeHandle`; and `compose_private_evals`. Concrete SQLite store
classes, schema constants/SQL, serializers, raw connections, concrete clients,
registries, test fakes and harnesses are internal.

SQLite schema version `1` and record format version `1` are frozen. The 18 typed record
tables, schema metadata, idempotency table, indexes, foreign keys and semantic unique
constraints remain compatible with databases created before the late
`StoreWriteOutcome` correction. That correction changed only the checksum projected in
the adapter outcome: services now receive the record-owned semantic checksum when one
exists, while persisted canonical payload bytes and their payload SHA-256 are
unchanged. No migration or version bump is justified.

Final limitations are deliberate: there are no real execution/evaluator/Intelligence
snapshot/Governance clients, HTTP/FastAPI delivery, background orchestration,
automatic stage progression, automatic retry of ambiguous writes, Governance read,
approval, automatic baseline promotion, comparison/regression command execution, or
global-backend readiness claim. Evidence is a minimized factual projection and never
an institutional approval.

Future behavioral or public-contract changes require an approved RFC, Plan or Mission.
Frozen contracts must not change silently; schema or record-format changes require an
explicit versioned migration; and any new external adapter or context edge requires a
boundary review. Compatibility fixes may preserve the frozen contract when backed by
tests and recorded in this document.

## 26. Risks and Tradeoffs

| Risk/tradeoff | Impact | Mitigation/decision |
| --- | --- | --- |
| Internal bounded coordination duplicates a subset of Mission scheduling | Some operational logic is domain-specific | Keep only run/case semantics; allow future Mission-backed adapter behind the same port after evidence |
| New execution port requires a bootstrap adapter | Additional integration work | Prevents concrete Model/Tool/Mission coupling and SCC entry |
| Reference-only datasets may become unavailable after retention | Historical run may be non-replayable | Record checksums/revision and truthful replay availability; pin baseline/Evidence dependencies |
| Local multi-collection persistence has no transaction | Interrupted finalization can span writes | Immutable children plus create-only Finalization and idempotent recovery |
| Source fingerprint is not backed by Git | Caller could provide incomplete identity | Require authority/provenance and checksum; mark unverified fingerprints invalid or non-comparable |
| Strict compatibility yields many `incompatible` results | Fewer convenient comparisons | Prefer truthful incompatibility over misleading deltas |
| Model/provider configuration can contain secrets | Fingerprint leakage risk | Safe normalized projection, credential-binding version only, never secret/hash |
| Minimal stochastic statistics may be insufficient for some evals | `insufficient_data` outcomes | Explicit repetition/variance/confidence rules; no speculative statistics framework |
| Broad frozen Intelligence port exposes more than some services need | Capability surface is larger | Inject only into the security application service; do not duplicate frozen contract now |
| Baseline activation through Governance binding can add process overhead | Promotion is not frictionless | Institutional authority is a requirement; candidates remain usable for explicit non-authoritative analysis |

## 27. Open Questions

These questions do not block the architecture, but must be resolved before or within the
corresponding implementation slice:

1. Maximum size and permitted classifications for inline Case input/expected values.
2. The first approved local dataset custody adapter and its paging contract limits.
3. Default retention periods for non-baseline private outputs and execution records.
4. Exact safe environment metadata allowlist per supported operating system.
5. Authority and validation mechanism for caller-supplied source fingerprints before
   Repository Runtime exists.
6. Whether phase-one comparisons permit one or several declared subject dimensions to
   differ.
7. Minimum repetition/sample defaults and the first confidence calculation, if any.
8. Which existing provider/model registry supplies the future safe snapshot adapter.
9. Whether baseline activation always requires an RFC Implementation Binding or whether
   Governance later exposes another frozen approval reference; Private Evals must not
   invent that authority.
10. Initial scale limit for cases/results before a different execution/storage adapter is
    justified.

## 28. Final Architecture Decision

Private Evals Runtime will be an independent bounded context that owns immutable
evaluation protocols, reference-only dataset bindings, reproducible run manifests,
bounded run/case coordination, scoring, verdicts, baseline candidates, comparisons,
regression reports and minimized Evidence projections.

It will not own canonical assets, provider trust, egress, institutional approval,
Skills, Tools, Missions, Workers, Swarm or storage mechanics.

The selected execution architecture is domain-owned lifecycle plus a narrow
consumer-owned `EvalCaseExecutionPort`. Concrete Model/Tool execution remains behind a
future bootstrap adapter. Missions/Workers are not dependencies of the core; they may
back that port only after a demonstrated operational need. Swarm is not in the default
design.

Datasets remain in approved local custody and canonical Intelligence ownership. Private
Evals stores immutable bindings, revisions and checksums, never copies private payload
into Governance or eval metadata. The known Desktop upload path is prohibited.

Reproducibility uses canonical manifests and protocol/subject/environment fingerprints,
not Git commits. Scoring is deliberately minimal, verdict precedence prevents averages
from hiding critical failures, and incompatible comparisons fail truthfully.

Evidence is emitted only through `RFCEvidenceWritePort` as a minimized, checksummed
projection. Governance remains the Evidence and approval authority.

No frozen external module change is required by this architecture. Work through Slice
18 provides create-only aggregate scoring, immutable run finalization, controlled
lifecycle/Evidence recovery, typed inbound boundaries, SQLite persistence and an
explicit composed runtime. It does not provide a concrete real evaluator/executor,
delivery adapter or HTTP router. The final audit froze the operationally complete
bounded context on 2026-07-23; the global backend remains **NOT READY**.
