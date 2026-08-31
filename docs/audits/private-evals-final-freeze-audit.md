# Private Evals Runtime — final freeze audit

Date: 2026-07-23
Decision: **IMPLEMENTED / OPERATIONALLY COMPLETE / FROZEN**
Global backend: **NOT READY**

This report is the exhaustive evidence companion to
`docs/architecture/private-evals-runtime.md`. “Public” means intentionally re-exported
through the bounded-context facade; concrete persistence remains importable by
composition and focused tests but is not part of that facade.

## Production inventory

No production file is unknown, obsolete, or removable at freeze.

| File | Responsibility / class | Surface | Slice | Required | Freeze |
|---|---|---|---:|---:|---|
| `__init__.py` | bounded-context facade / CONTRACT | public | 1–18 | yes | frozen |
| `adapters/__init__.py` | adapter facade / ADAPTER | internal | 17 | yes | frozen |
| `adapters/boundaries.py` | four narrow external bridges / ADAPTER | internal | 17 | yes | frozen |
| `adapters/errors.py` | adapter-safe errors and canonical Governance aliases / ERROR | internal | 17/final | yes | frozen |
| `adapters/queries.py` | local Evidence projection reader / QUERY | internal | 17 | yes | frozen |
| `adapters/resolvers.py` | immutable explicit-reference resolver / ADAPTER | internal | 17 | yes | frozen |
| `analysis.py` | baseline, comparison and regression authorities / ENGINE, FACTORY | public | 6 | yes | frozen |
| `canonical.py` | canonical value fingerprinting / DOMAIN | public helper | 1 | yes | frozen |
| `case_evaluation.py` | evaluation validation and result creation / FACTORY, SERVICE | public | 11 | yes | frozen |
| `case_evaluation_contracts.py` | evaluator consumer port / CONTRACT | public | 11 | yes | frozen |
| `case_evaluation_errors.py` | evaluation/result-acceptance errors / ERROR | public | 11 | yes | frozen |
| `catalog.py` | suite/case/dataset immutable models / MODEL | public | 3–4 | yes | frozen |
| `catalog_errors.py` | catalog errors / ERROR | public | 3 | yes | frozen |
| `catalog_runtime.py` | catalog lifecycle authority / RUNTIME | public | 3 | yes | frozen |
| `command_contracts.py` | six explicit resolver ports / CONTRACT | public | 15 | yes | frozen |
| `command_error_mapping.py` | safe error categorization / SERVICE | internal | 15 | yes | frozen |
| `command_errors.py` | public command boundary errors / ERROR | public | 15 | yes | frozen |
| `command_handlers.py` | isolated stage handlers / COMMAND | public | 15 | yes | frozen |
| `command_models.py` | typed reference-only commands/responses / MODEL | public | 15 | yes | frozen |
| `composition.py` | sole production assembly, handle, readiness, cleanup / COMPOSITION | public API + internal wiring | 18/final | yes | frozen |
| `contracts.py` | five store protocols / CONTRACT | public | 2 | yes | frozen |
| `errors.py` | base domain taxonomy / ERROR | public | 1,6 | yes | frozen |
| `evaluation.py` | metric/score/evaluation domain models / MODEL | public | 5,11 | yes | frozen |
| `evaluation_records.py` | immutable attempt/finalization support records / MODEL | public | 11,13 | yes | frozen |
| `evidence.py` | minimized Evidence domain models / MODEL | public | 8 | yes | frozen |
| `evidence_errors.py` | projection errors / ERROR | public | 8 | yes | frozen |
| `evidence_projection.py` | projection construction and one-write emitter / FACTORY, SERVICE | public | 8 | yes | frozen |
| `evidence_submission.py` | deterministic submission planner / ENGINE | public | 14 | yes | frozen |
| `evidence_submission_errors.py` | submission/reconciliation errors / ERROR | public | 14/final | yes | frozen |
| `evidence_submission_models.py` | attempt, receipt, envelope models / MODEL | public | 14 | yes | frozen |
| `evidence_submission_service.py` | local coordination and explicit Governance write / SERVICE | public | 14/final | yes | frozen |
| `execution.py` | execution request/response models / MODEL | public | 10 | yes | frozen |
| `execution_contracts.py` | execution consumer port / CONTRACT | public | 10 | yes | frozen |
| `execution_errors.py` | execution errors / ERROR | public | 10 | yes | frozen |
| `execution_policy.py` | retry eligibility/accounting policy / ENGINE | public | 10 | yes | frozen |
| `execution_records.py` | attempt/projection factories / FACTORY | public | 10 | yes | frozen |
| `query_handler.py` | read-only run summary / QUERY | public | 15 | yes | frozen |
| `query_models.py` | typed query requests/responses / MODEL | public | 15 | yes | frozen |
| `result_errors.py` | materialization errors / ERROR | public | 11 | yes | frozen |
| `result_materialization.py` | reference-only output materialization / FACTORY, SERVICE | public | 11 | yes | frozen |
| `result_models.py` | materialized output records / MODEL | public | 11 | yes | frozen |
| `run_errors.py` | run lifecycle errors / ERROR | public | 4 | yes | frozen |
| `run_finalization.py` | finalization factory/readiness / FACTORY, ENGINE | public | 13 | yes | frozen |
| `run_finalization_errors.py` | finalization/recovery errors / ERROR | public | 13 | yes | frozen |
| `run_finalization_models.py` | finalization and terminal-failure records / MODEL | public | 13 | yes | frozen |
| `run_finalization_policy.py` | terminality/readiness rules / ENGINE | public | 13 | yes | frozen |
| `run_finalization_service.py` | create-only finalization and recovery / SERVICE | public | 13 | yes | frozen |
| `run_runtime.py` | run lifecycle authority / RUNTIME | public | 4 | yes | frozen |
| `run_scoring.py` | expected matrix and decision factory / FACTORY, ENGINE | public | 12 | yes | frozen |
| `run_scoring_errors.py` | run-scoring errors / ERROR | public | 12 | yes | frozen |
| `run_scoring_service.py` | create-only scoring coordination / SERVICE | public | 12 | yes | frozen |
| `runs.py` | manifest/run domain models and builder / MODEL, FACTORY | public | 4 | yes | frozen |
| `scoring.py` | metric aggregation, verdict, compatibility / ENGINE | public | 5 | yes | frozen |
| `scoring_errors.py` | scoring errors / ERROR | public | 5 | yes | frozen |
| `security.py` | immutable security request/snapshot models / MODEL | public | 7 | yes | frozen |
| `security_contracts.py` | Intelligence and snapshot read ports / CONTRACT | public | 7,17 | yes | frozen |
| `security_errors.py` | security errors / ERROR | public | 7 | yes | frozen |
| `security_service.py` | fail-closed security application service / SERVICE | public | 7 | yes | frozen |
| `sqlite_serialization.py` | allowlisted canonical record codec / LEGACY/COMPATIBILITY | internal | 16 | yes | frozen v1 |
| `sqlite_stores.py` | schema v1 and five concrete stores / STORE | internal | 16/final | yes | frozen v1 |
| `states.py` | shared enums/state machines / DOMAIN | public | 1–6 | yes | frozen |
| `store_errors.py` | persistence taxonomy / ERROR | public | 2,16 | yes | frozen |
| `store_models.py` | pagination/idempotency/write outcomes / MODEL | public | 2 | yes | frozen |
| `values.py` | validated identities/checksums/timestamps / DOMAIN | public | 1 | yes | frozen |

## Public surface

The facade has **519 unique exports**. It is broad but defined: it is a typed
bounded-context SDK, not a service locator. The stable groups are domain values and
models, public errors, protocols, engines/factories/services, commands/queries, and
composition/readiness. All are **FREEZE PUBLIC**. The adapter package and concrete
wiring helpers are **KEEP INTERNAL**.

| Export/group | Consumer purpose | Stable | Leak | Decision |
|---|---|---:|---:|---|
| values, states, immutable records | construct/inspect domain facts | yes | no | FREEZE PUBLIC |
| domain errors | typed handling with fixed messages | yes | no | FREEZE PUBLIC |
| five store protocols and port protocols | implement/inject boundaries | yes | no | FREEZE PUBLIC |
| factories, engines and services | execute one named domain concern | yes | no | FREEZE PUBLIC |
| commands/responses and query models | reference-only application boundary | yes | no | FREEZE PUBLIC |
| composition config/bindings/readiness/handle/factory | explicit application assembly | yes | no | FREEZE PUBLIC |
| `PrivateEvalsPersistenceConfig` | safe local persistence configuration | yes | no raw connection | FREEZE PUBLIC |
| `SCHEMA_VERSION`, five `SQLite*Store` classes | persistence implementation | no | yes | REMOVE EXPORT |
| SQL/schema helpers and codec functions | adapter internals | no | yes | KEEP INTERNAL |
| raw clients/connections, registries, fakes, harnesses | none | no | yes | NOT EXPORTED |

There are no duplicate names, mutable registries, SQL strings, serializers, raw
connections, concrete clients, test doubles or harnesses in `__all__`.

## Authority and contracts

| Concern | Authority | Consumers | Competition | Frozen |
|---|---|---|---:|---:|
| suite/catalog | `EvalCatalogRuntime` | commands/composition | no | yes |
| run lifecycle | `EvalRunRuntime` | commands/composition | no | yes |
| case execution | `EvalCaseExecutionPort` + validating adapter | caller | no | yes |
| evaluation | evaluator port + `EvalCaseEvaluationService` | caller/command | no | yes |
| materialization | `MaterializedOutputFactory/Service` | command | no | yes |
| `EvalResult` | `EvalResultFactory/Service` | command/scoring | no | yes |
| scoring | `ScoringEngine`, then `RunScoringService` | command | no | yes |
| baseline/compatibility/comparison/regression | `analysis.py` authorities | explicit callers | no | yes |
| finalization | policy/factory/service trio | command | no | yes |
| Evidence projection | projection factory/emitter | submission service | no | yes |
| Evidence submission | planner/service | command | no | yes |
| persistence | five protocols; one SQLite implementation each | services/runtime | no | yes |
| external security | Intelligence contracts + `EvalSecurityService` | explicit caller | no | yes |
| command resolution | six resolver protocols + one resolver adapter | handlers | no | yes |
| local query projection | query handler and Evidence local reader | handle | no | yes |
| composition/readiness | `composition.py` | application bootstrap | no | yes |

| Contract | Owner | Production implementation | Test doubles | Consumers | Complete |
|---|---|---|---|---|---:|
| `EvalCatalogStore` | Private Evals | `SQLiteEvalCatalogStore` | focused fakes | catalog runtime/resolver | yes |
| `EvalRunStore` | Private Evals | `SQLiteEvalRunStore` | focused fakes | run/finalization/resolver/query | yes |
| `EvalAnalysisStore` | Private Evals | `SQLiteEvalAnalysisStore` | focused fakes | scoring/resolver | yes |
| `EvalMaterializationStore` | Private Evals | `SQLiteEvalMaterializationStore` | focused fakes | materialization/resolver | yes |
| `EvalEvidenceStore` | Private Evals | `SQLiteEvalEvidenceStore` | focused fakes | submission/local query | yes |
| `EvalCaseExecutionPort` | Private Evals | `CaseExecutionBoundaryAdapter` | strict spies | caller/composition | yes |
| `EvalCaseEvaluatorPort` | Private Evals | `CaseEvaluatorBoundaryAdapter` | strict async spies | caller/composition | yes |
| `SecuritySnapshotReadPort` | Private Evals | `IntelligenceSecuritySnapshotAdapter` | strict spies | caller/composition | yes |
| `EvidenceLocalStateReader` | Private Evals | `LocalEvidenceStateReader` | none needed | query surface | yes |
| six command resolver protocols | Private Evals | `PrivateEvalsCommandResolverAdapter` | handler fakes | handlers | yes |
| `RFCEvidenceWritePort` | Project Governance | `GovernanceEvidenceWriteAdapter` | strict spies | submission service | yes |

Only composition constructs production concrete implementations. Domain modules do not
import adapters or concrete stores, and no protocol or implementation is orphaned.

## Composition, handle and readiness

| Composition section | Responsibility | Domain logic | Location | Action |
|---|---|---:|---:|---|
| config | validated identities, versions and persistence config | no | correct | freeze |
| binding models | explicit available/unavailable/disabled facts | no | correct | freeze |
| readiness | pure projection of config, lifecycle and bindings | no | correct | corrected/freeze |
| runtime handle | narrow surfaces and lifecycle guard | no | correct | corrected/freeze |
| helpers/factory | ordered store/adapter/service wiring | no | correct | freeze |
| cleanup | reverse close on failure; idempotent close | no | correct | freeze |
| exports | typed composition API | no | correct | freeze |

The approximately 690 lines are cohesive: public immutable composition models,
construction, lifecycle ownership and readiness are tested independently, while no
scoring, verdict, approval, retry, Evidence projection, policy selection, automatic
stage choice or finalization decision is implemented there. Splitting would create a
package around one lifecycle authority without isolating new behavior.

| Handle attribute | Type | Reason | Mutable | Locator risk | Freeze |
|---|---|---|---:|---:|---:|
| `commands` | `PrivateEvalsCommandHandlers` | typed writes | no | no | yes |
| `queries` | `PrivateEvalsQuerySurface` | typed local reads | no | no | yes |
| `catalog` | `EvalCatalogRuntime` | explicit catalog lifecycle | no | no | yes |
| `runs` | `EvalRunRuntime` | explicit run lifecycle | no | no | yes |
| four external properties | narrow protocols | explicit caller-controlled boundary calls | no | no | yes |
| `readiness` | immutable snapshot | factual inspection | no | no | yes |

External adapter fields are private and redacted from `repr`; unavailable properties
raise a typed error. No connection, raw client, registry, component dictionary,
string lookup, `get_service`, or post-construction dependency replacement exists.

| State | Facts | Commands | Queries | External facts | Backend ready |
|---|---|---:|---:|---|---:|
| locally operational | persistence open; all nonavailable bindings explicitly disabled | yes unless read-only | yes | disabled | no |
| externally bound | persistence open; all four bindings available | yes unless read-only | yes | available | no |
| degraded | persistence open; at least one binding unavailable | yes unless read-only | yes | mixed/unavailable | no |
| closed | lifecycle guard closed | no | no | inspection only | no |

Readiness performs no network operation or write. Read-only is orthogonal and adds a
limitation while preserving the factual external-binding state.

| Capability | Required binding | Unavailable behavior | Dependent action | Query impact |
|---|---|---|---|---|
| persistence | schema-v1 config | construction fails or closed/read-only typed error | all local writes | queries unavailable only if closed/construction fails |
| Intelligence snapshot | typed snapshot client | typed capability unavailable | explicit snapshot read/security preparation | none |
| execution | typed execution backend | typed capability unavailable | explicit `execute_case` | none |
| evaluator | typed evaluator backend | typed capability unavailable | explicit `evaluate` | none |
| Governance write | `RFCEvidenceWritePort` client | unavailable or reconciliation required | `submit_evidence` only | local Evidence query remains available |
| local queries | open typed stores | closed error | none | local-only |

## Commands, queries and end-to-end behavior

| Command | Handler | Primary authority | Writes | Never triggers |
|---|---|---|---|---|
| record materialized output | `record_materialized_output` | materialization service | output | evaluation/scoring |
| create EvalResult | `create_eval_result` | evaluation service | result | scoring/finalization |
| create scoring decision | `create_scoring_decision` | run-scoring service | decision | finalization |
| finalize run | `finalize_run` | finalization service | finalization + run CAS | Evidence |
| submit Evidence | `submit_evidence` | submission service | attempt/receipt/envelope + one external call | approval/next stage |

Catalog and run lifecycle remain explicit typed runtime calls, not hidden command
chaining. Starting a run does not execute it, and every following stage requires a
separate caller action.

| Query | Reader | Stores | External read | Writes |
|---|---|---|---:|---:|
| run summary | `EvalRunSummaryQueryHandler` | run + analysis | no | no |
| local Evidence state | `LocalEvidenceStateReader` | Evidence | no | no |

Both queries survive restart, perform no recovery/repair, consult neither Governance
nor approval, and cannot alter readiness.

| E2E stage | Real implementation | Fake boundary | Pre-next-stage assertion | Persisted |
|---|---|---|---|---:|
| catalog/run/start | SQLite + runtimes | none | run is running | yes |
| snapshot | Intelligence adapter | strict one-call snapshot spy | exact project/assets/providers | no local record |
| execution | execution adapter | strict one-call executor | exact request/response | factual attempt used next |
| materialization | command/service/store | none | exact record reference | yes |
| evaluation | evaluator adapter | strict async one-call evaluator | exact request and valid response | next command persists result |
| scoring | command/service/engine/store | none | decision reference/checksum | yes |
| finalization | command/service/store | none | terminal run | yes |
| Evidence | command/service/adapter/store | strict one-call Governance spy | exact identity/immutable record | attempt, receipt, envelope |
| restart | new composition | unavailable markers | summaries unchanged | yes |

The strict fakes check exact inputs, immutable identities and call counts; unexpected
calls fail assertions. Adapter validation recomputes response fingerprints and checks
returned Evidence equality.

| Negative/restart scenario | Covered | Proof of no improper next record |
|---|---:|---|
| security unavailable | yes | snapshot fails closed; no execution |
| execution mismatch | yes | adapter rejects; no materialization |
| evaluator mismatch | yes | adapter rejects; no EvalResult |
| materialization conflict | yes | typed conflict; no overwrite/evaluation |
| result conflict | yes | typed conflict; no scoring |
| scoring incomplete | yes | no decision |
| finalization not ready | yes | no finalization/run transition |
| ambiguous Governance write | yes | one attempt, one call, no receipt/envelope, no retry |
| corrupt receipt | yes | typed reconciliation/integrity failure, no envelope |
| restart before finalization | yes | run/query facts retained; no finalization |
| restart after finalization | yes | terminal facts retained; no Evidence auto-submit |
| restart after Evidence attempt | yes | reconciliation required; no resend |
| restart after receipt | yes | recovery uses local receipt; no duplicate external call |
| restart after envelope | yes | idempotent local replay |
| read-only write | yes | typed rejection; query works |
| closed runtime | yes | all retained operational surfaces reject |

## Recovery and persistence compatibility

| Recovery | Trigger | Allowed | Forbidden | Persistent proof |
|---|---|---|---|---|
| finalization recovery | finalization exists/run CAS incomplete | verify and apply exact transition | rescore/rebuild | finalization fingerprint + run revision |
| terminally unscorable | verified terminal failure | persist factual terminal finalization | invent score/verdict | terminal-failure record |
| orphan Evidence attempt | attempt without receipt | require reconciliation | resend | durable attempt claim |
| ambiguous Governance write | call outcome unknown | manual reconciliation | automatic retry | attempt without receipt |
| incomplete receipt chain | some receipts | validate/reuse receipts | infer missing acceptance | receipt fingerprints |
| final envelope | complete chain | create/replay exact envelope | mutate/add attempts | envelope + idempotency fact |

Writes roll back before typed failure escapes. There is no ambiguous retry, auto-resend,
approval inference, silent repair, or hidden mutation.

| StoreWriteOutcome | Before | After | Authority | Compatibility | Action |
|---|---|---|---|---|---|
| `checksum` projection | SHA-256 of canonical serialized payload | record-owned semantic checksum when present; payload hash otherwise | record contract + `StoreWriteOutcome` | persisted bytes/schema unchanged | freeze corrected behavior |

Before correction, services compared a payload-byte checksum with the semantic checksum
they had supplied and could reject a successful store write. The adapter now translates
the outcome to the checksum services expect. Record payloads, persisted
`payload_checksum`, idempotency comparison and decode validation did not change.
Schema-v1 rows remain readable and cannot appear corrupt solely because of this change.
The synthetic Slice-16 fixture creates the original v1 row shape, verifies the stored
payload SHA-256, restarts on current code and receives the semantic checksum on replay.
No migration or schema-version change is required.

The removed `open_sqlite_private_evals_stores` factory has zero current imports, tests
or active documentation references. Production construction sites for the five stores
and four adapters exist only in `composition.py`; direct test construction is retained
for contract-level verification.

## Schema freeze

| Item | Frozen | Future migration | Rule |
|---|---:|---:|---|
| schema version 1 | yes | if structure changes | exact metadata match; no silent upgrade |
| record format version 1 | yes | if encoding changes | canonical allowlisted decode |
| 18 typed record tables | yes | yes for add/drop/shape change | exact table/column audit |
| schema metadata + idempotency | yes | yes | singleton version and immutable facts |
| required indexes | yes | if changed | audited exact names/columns |
| six restrictive foreign keys | yes | if changed | no cascade; integrity check |
| eight semantic unique indexes | yes | if changed | one logical record per authority slot |

The 18 tables are suites, suite versions, case versions, dataset bindings, runs,
manifests, results, evaluation attempts, finalizations, scoring decisions, baselines,
comparisons, regression rules, regression reports, materialized outputs, Evidence
attempts, Evidence receipts and Evidence submissions.

## Error and security audit

All public errors are frozen by family below. Every family uses fixed safe messages;
raw SQLite/provider errors, bodies, paths, tokens and stack traces are not exposed.
Retryability is intentionally expressed by the specific semantic type: unavailable
may be retried only by an explicit caller when no write ambiguity exists; conflicts,
denials/mismatches and corruption are not retryable without changed input/repair;
`EvidenceReconciliationRequired` is the sole ambiguous-write outcome and forbids
automatic retry.

| Layer/family | Public errors (including family base) | Safe | Ambiguous |
|---|---|---:|---:|
| domain | `PrivateEvalDomainError`, `InvalidIdentity`, `InvalidVersion`, `InvalidRevision`, `InvalidChecksum`, `InvalidFingerprint`, `InvalidTimestamp`, `InvalidSuite`, `InvalidCase`, `InvalidDatasetBinding`, `InvalidRun`, `InvalidRunManifest`, `InvalidResult`, `InvalidScore`, `InvalidBaseline`, `InvalidComparison`, `InvalidRegressionRule`, `InvalidRegressionReport`, `DuplicateReference`, `SensitivePayloadViolation`, `IncompatibleReference`, `RegressionEvaluationFailure`, `ComparisonFingerprintMismatch`, `ReportFingerprintMismatch` | yes | no |
| catalog | `EvalCatalogError`, `SuiteNotFound`, `SuiteAlreadyExists`, `SuiteRevisionConflict`, `SuiteVersionNotFound`, `SuiteVersionAlreadyExists`, `SuiteVersionRevisionConflict`, `InvalidSuiteTransition`, `ImmutableSuiteVersion`, `CaseVersionNotFound`, `CaseVersionAlreadyExists`, `CaseVersionRevisionConflict`, `InvalidCaseTransition`, `UnresolvedCaseReference`, `IncompatibleCaseReference`, `DatasetBindingNotFound`, `DatasetBindingAlreadyExists`, `IncompatibleDatasetBinding`, `CatalogIdempotencyConflict`, `CatalogIntegrityConflict`, `CatalogQueryInvalid`, `CatalogUnavailable` | yes | no |
| execution/evaluation | all 15 `execution_errors`, all 18 `case_evaluation_errors`, all 10 `result_errors` | yes | no |
| scoring/finalization/run | all 11 `scoring_errors`, all 14 `run_scoring_errors`, all 17 `run_errors`, all 14 `run_finalization_errors` | yes | no |
| Evidence | all 11 `evidence_errors`; all 14 `evidence_submission_errors` | yes | only `EvidenceReconciliationRequired` |
| security | all 13 `security_errors` | yes | no |
| persistence | `EvalStoreError`, `EvalRecordNotFound`, `EvalRevisionConflict`, `EvalDuplicateRecord`, `EvalIntegrityConflict`, `EvalIdempotencyConflict`, `EvalInvalidCursor`, `EvalInvalidStoreQuery`, `EvalStoreUnavailable`, `EvalSchemaVersionMismatch`, `EvalPersistenceConfigError` | yes | no |
| command/composition/adapter | all seven command errors, six composition errors, and seven adapter errors/aliases | yes | Governance alias only |

Security search classified `prompt`, `output`, payload, provider, token, credential,
secret, URL, endpoint and path occurrences as validators, deny-list terms, typed
identifiers or documentation. SQLite uses parameterized internal SQL only. There is no
HTTP/network library, subprocess, shell, pickle, `eval`, `exec`, arbitrary callable
injection, free SQL, arbitrary metadata or provider payload. `sqlite_serialization.py`
uses `importlib.import_module` only to build a fixed allowlist of trusted immutable
record types; payload tags can select only within that registry, so this is safe
internal serialization rather than dynamic code loading. Persistence-config `repr`
redacts the database path and timeout. No violation remains.

## Cross-context and graph

| Imported module | Context | Public contract/model | Required | Allowed |
|---|---|---:|---:|---:|
| `synapse.intelligence_boundary.contracts` | Intelligence Boundary | yes | yes | yes |
| `synapse.intelligence_boundary.models` | Intelligence Boundary | yes | yes | yes |
| `synapse.project_governance.contracts` | Project Governance | yes | yes | yes |
| `synapse.project_governance.models` | Project Governance | yes | yes | yes |

No forbidden context is imported. The official graph reports 70 contexts and 263
governed edges; Private Evals has exactly the two allowed outbound context edges.
The prior planning count of 73 was stale and was not used to alter the official graph.
The official SCC baseline is 13 cyclic components spanning 35 contexts, with none
containing Private Evals. The exact runtime-absolute graph has 518 modules and 1,584
edges, zero parse errors and zero cyclic components. Composition introduces no cycle
and is the only production importer of concrete Private Evals implementations.

## Test inventory

Counts below are defined test functions; parametrization expands the final collected
Private Evals selection.

| Test file | Responsibility | Count | Redundant | Missing concern |
|---|---|---:|---:|---:|
| `architecture/test_private_evals_boundaries.py` | imports, IO, security, graph, public facade | 24 | no | no |
| `test_private_evals_adapters.py` | four adapters, resolver, local reader | 32 | no | no |
| `test_private_evals_analysis.py` | baseline/comparison/regression | 20 | no | no |
| `test_private_evals_case_evaluation.py` | evaluator response and result acceptance | 27 | no | no |
| `test_private_evals_catalog_runtime.py` | catalog lifecycle | 7 | no | no |
| `test_private_evals_commands.py` | stage isolation and safe translation | 18 | no | no |
| `test_private_evals_composition.py` | wiring/readiness/E2E/restart/lifecycle | 11 | broad by design | no |
| `test_private_evals_evidence.py` | projection minimization | 17 | no | no |
| `test_private_evals_evidence_submission.py` | attempts/receipts/recovery/ambiguity | 24 | no | no |
| `test_private_evals_execution.py` | identities/retry/accounting | 26 | no | no |
| `test_private_evals_models.py` | core values/models | 17 | no | no |
| `test_private_evals_result_materialization.py` | output/result materialization | 21 | no | no |
| `test_private_evals_run_finalization.py` | readiness/finalization/recovery | 20 | no | no |
| `test_private_evals_run_runtime.py` | manifest/run lifecycle | 12 | no | no |
| `test_private_evals_run_scoring.py` | matrix and run decision | 22 | no | no |
| `test_private_evals_scoring.py` | scoring/verdict | 20 | no | no |
| `test_private_evals_security.py` | fail-closed boundary | 23 | no | no |
| `test_private_evals_sqlite_audit.py` | complete store/schema/integrity/compatibility | 19 | intentionally comprehensive | no |
| `test_private_evals_sqlite_stores.py` | core store behavior | 12 | complementary | no |
| `test_private_evals_store_contracts.py` | protocol surface | 8 | no | no |

No useful duplicate was removed. Broad tests are integration/audit tests with distinct
contract evidence; implementation-detail assertions are limited to persistence and
architecture invariants where those details are the frozen contract.

## Documentation and final limitations

The architecture document now records all Slices 1–18, the corrected readiness state
machine, internal persistence surface, compatibility decision, explicit freeze date,
public-interface groups, schema freeze, limitations and change policy. It makes no
claim of real clients, HTTP delivery or global readiness. Evidence is not approval,
baseline promotion is not automatic, composition is not a pipeline, and Skills
Runtime Phase 2 plus all future modules remain out of scope.

No HTTP/FastAPI, real client, provider call, real Evidence write, approval, next module,
stage, commit, push or PR was performed during this audit.

## Final validation

| Gate | Result |
|---|---|
| Private Evals selection, including its architecture boundary | 560 passed |
| composition test file | 11 defined tests; included in the green selection |
| architecture suite | 137 passed |
| global suite | 1,768 passed, 2 skipped, 4 subtests passed |
| Ruff, repository-wide | passed |
| Mypy Private Evals | zero issues in 64 source files |
| authoritative Mypy `backend/synapse` | baseline reproduced: 215 errors in 58 files; 518 files checked |
| `git diff --check` | passed; only existing line-ending notices |
| official governed graph | 70 contexts, 263 edges |
| Private Evals context edges | `intelligence_boundary`, `project_governance` only |
| official SCC | one non-trivial SCC: 13 contexts / 35 internal edges; Private Evals absent |
| exact runtime absolute graph | 518 modules, 1,584 edges, zero parse errors, zero non-trivial SCCs |
| security/orchestration scan | no forbidden import/call; all nine concrete construction sites in `composition.py` |
