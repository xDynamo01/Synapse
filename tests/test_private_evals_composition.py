from __future__ import annotations

import ast
import asyncio
import inspect
import sqlite3
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest

import synapse.private_evals.composition as composition_module
from synapse.private_evals import (
    AggregationMethod,
    CapabilityBindingStatus,
    CreateEvalResultCommand,
    CreateScoringDecisionCommand,
    EvalEvidenceSource,
    EvalResultCreationInput,
    EvalResultFactory,
    EvalResultId,
    EvalRun,
    EvalRunFinalizationFactory,
    EvalRunFinalizationId,
    EvalRunId,
    EvalRunManifestBuilder,
    EvalSchemaVersionMismatch,
    EvaluationEventIdentity,
    EvidenceMetric,
    EvidenceMetricAllowlist,
    EvidenceProjectionCandidate,
    EvidenceProjectionKind,
    ExternalCapabilityName,
    ExternalClientBinding,
    FailureBudget,
    FailureBudgetUnit,
    FinalizeRunCommand,
    GovernanceEvidenceBinding,
    GovernanceEvidenceIdentity,
    IdempotencyKey,
    LogicalExecutionIdentity,
    MaterializedOutputFactory,
    MaterializedOutputId,
    PrivateEvalCommandContext,
    PrivateEvalQueryContext,
    PrivateEvalsCapabilityUnavailable,
    PrivateEvalsConstructionFailed,
    PrivateEvalsExternalBindings,
    PrivateEvalsLifecycleState,
    PrivateEvalsPersistenceConfig,
    PrivateEvalsRuntimeClosed,
    PrivateEvalsRuntimeConfig,
    PrivateEvalsRuntimeReadOnly,
    ProjectionReasonCode,
    RecordMaterializedOutputCommand,
    Revision,
    RunFinalizationInput,
    RunScoringInput,
    RunStatus,
    RunSummaryRequest,
    ScoreThreshold,
    ScoringDecisionFactory,
    ScoringDecisionId,
    ScoringProtocol,
    ScoringTarget,
    SubmitEvidenceCommand,
    ThresholdOperator,
    ThresholdScope,
    UnavailableExternalCapability,
    assess_run_finalization_readiness,
    compose_private_evals,
    create_expected_execution_matrix,
    fingerprint,
)
from synapse.private_evals.adapters import (
    EvidenceCoordinationReference,
    ExternalAdapterConfig,
    ReferencedRecord,
    ResolverRecordCatalog,
    StoredCaseReference,
)
from synapse.private_evals.evidence_submission import (
    EvalEvidencePlanningInput,
    EvalEvidenceSubmissionPlanner,
)
from synapse.private_evals.execution_records import (
    attempt_record,
    logical_execution_projection,
)
from synapse.private_evals.result_materialization import MaterializationInput
from synapse.private_evals.run_finalization_models import (
    RunFinalizationReadinessStatus,
)
from synapse.private_evals.states import DeterminismMode
from synapse.private_evals.store_errors import EvalStoreUnavailable
from synapse.private_evals.values import UtcTimestamp
from synapse.project_governance.models import EvalReference
from test_private_evals_adapters import (
    adapter_config,
    governance_evidence,
)
from test_private_evals_case_evaluation import (
    evaluation_request,
    evaluation_response,
    metric,
    score,
)
from test_private_evals_catalog_runtime import (
    binding,
    case,
    suite,
    suite_version,
)
from test_private_evals_evidence_submission import implementation
from test_private_evals_execution import request as execution_request
from test_private_evals_execution import response as execution_response
from test_private_evals_run_finalization import accounting
from test_private_evals_run_runtime import NOW, T1, manifest_spec
from test_private_evals_security import security_snapshot


def runtime_config(path: Path, *, read_only: bool = False) -> PrivateEvalsRuntimeConfig:
    persistence = PrivateEvalsPersistenceConfig(
        path,
        create_if_missing=not read_only,
        read_only=read_only,
    )
    adapter = ExternalAdapterConfig("private-evals-boundary", "18.0.0", 2.0)
    return PrivateEvalsRuntimeConfig(
        persistence,
        "private-evals-runtime",
        "18.0.0",
        adapter,
        adapter,
        adapter,
        adapter,
    )


def unavailable_bindings(
    *,
    status: CapabilityBindingStatus = CapabilityBindingStatus.UNAVAILABLE,
) -> PrivateEvalsExternalBindings:
    def unavailable(capability: ExternalCapabilityName):
        return UnavailableExternalCapability(
            capability,
            f"{capability.value}-binding",
            "1.0.0",
            "not_configured",
            status,
        )

    return PrivateEvalsExternalBindings(
        unavailable(ExternalCapabilityName.INTELLIGENCE_SNAPSHOT),
        unavailable(ExternalCapabilityName.CASE_EXECUTION),
        unavailable(ExternalCapabilityName.CASE_EVALUATOR),
        unavailable(ExternalCapabilityName.GOVERNANCE_WRITE),
    )


def available_bindings() -> tuple[PrivateEvalsExternalBindings, tuple[Mock, ...]]:
    snapshot_client = Mock()
    snapshot_client.snapshot.return_value = security_snapshot()
    execution_client = Mock()
    execution_client.execute_case.side_effect = lambda request: execution_response(
        target=request
    )
    evaluator_client = Mock()
    evaluator_client.evaluate = AsyncMock(
        side_effect=lambda request: evaluation_response(request)
    )
    governance_client = Mock()
    governance_client.record_evidence.side_effect = lambda evidence: evidence
    bindings = PrivateEvalsExternalBindings(
        ExternalClientBinding(
            ExternalCapabilityName.INTELLIGENCE_SNAPSHOT,
            "intelligence-test",
            "1.0.0",
            snapshot_client,
        ),
        ExternalClientBinding(
            ExternalCapabilityName.CASE_EXECUTION,
            "execution-test",
            "1.0.0",
            execution_client,
        ),
        ExternalClientBinding(
            ExternalCapabilityName.CASE_EVALUATOR,
            "evaluator-test",
            "1.0.0",
            evaluator_client,
        ),
        ExternalClientBinding(
            ExternalCapabilityName.GOVERNANCE_WRITE,
            "governance-test",
            "1.0.0",
            governance_client,
        ),
    )
    return bindings, (
        snapshot_client,
        execution_client,
        evaluator_client,
        governance_client,
    )


def seed_started_run(handle) -> None:  # noqa: ANN001
    suite_model = suite()
    case_model = case()
    binding_model = binding()
    version_model = suite_version(case_model, binding_model)
    handle.catalog.create_suite(
        suite_model, idempotency_key=IdempotencyKey("composition-suite")
    )
    handle.catalog.register_case_version(
        case_model, idempotency_key=IdempotencyKey("composition-case")
    )
    handle.catalog.register_dataset_binding(
        binding_model, idempotency_key=IdempotencyKey("composition-binding")
    )
    handle.catalog.create_suite_version(
        version_model, idempotency_key=IdempotencyKey("composition-version")
    )
    handle.catalog.freeze_case_version(
        case_model.suite_id,
        case_model.case_id,
        case_model.version,
        expected_revision=Revision(1),
        idempotency_key=IdempotencyKey("composition-case-freeze"),
    )
    handle.catalog.freeze_suite_version(
        version_model.suite_id,
        version_model.version,
        expected_revision=Revision(1),
        idempotency_key=IdempotencyKey("composition-version-freeze"),
    )
    spec, _catalog = manifest_spec()
    manifest = EvalRunManifestBuilder().build(spec)
    run = handle.runs.prepare_run(
        EvalRunId("run-1"),
        manifest,
        created_at=NOW,
        idempotency_key=IdempotencyKey("composition-run"),
    )
    run = handle.runs.begin_validation(
        run.run_id,
        timestamp=T1,
        expected_revision=run.revision,
        idempotency_key=IdempotencyKey("composition-validation"),
    )
    run = handle.runs.mark_ready(
        run.run_id,
        timestamp=T1,
        expected_revision=run.revision,
        idempotency_key=IdempotencyKey("composition-ready"),
    )
    handle.runs.start_run(
        run.run_id,
        timestamp=T1,
        expected_revision=run.revision,
        idempotency_key=IdempotencyKey("composition-start"),
    )


def summary_request() -> RunSummaryRequest:
    return RunSummaryRequest(
        PrivateEvalQueryContext(
            "actor-1",
            "implementation-binding-1",
            "a" * 64,
            "implementation-binding-1",
            "correlation-1",
            "summary-request-1",
        ),
        "run-1",
    )


def command_context(reference: str) -> PrivateEvalCommandContext:
    return PrivateEvalCommandContext(
        "actor-1",
        "authz-decision-1",
        "a" * 64,
        "implementation-binding-1",
        "correlation-1",
        reference,
        f"idempotency-{reference}",
        "2026-07-23T12:00:00Z",
    )


def test_config_bindings_and_errors_have_safe_fixed_representations(tmp_path: Path) -> None:
    config = runtime_config(tmp_path / "private-location.sqlite3")
    bindings, _clients = available_bindings()
    rendered = repr(config)
    assert "private-location" not in rendered
    assert "2.0" not in rendered
    assert "redacted" in repr(bindings.case_execution)
    for unsafe in ("secret-token", "https://private", "C:\\private"):
        with pytest.raises(Exception):
            PrivateEvalsRuntimeConfig(
                config.persistence,
                unsafe,
                "18.0.0",
                adapter_config(),
                adapter_config(),
                adapter_config(),
                adapter_config(),
            )
    assert "raw detail" not in str(PrivateEvalsConstructionFailed("raw detail"))


def test_construction_readiness_degraded_capabilities_and_close(tmp_path: Path) -> None:
    handle = compose_private_evals(
        runtime_config(tmp_path / "runtime.sqlite3"), unavailable_bindings()
    )
    readiness = handle.readiness
    assert readiness.lifecycle_state is PrivateEvalsLifecycleState.DEGRADED
    assert readiness.persistence_status is CapabilityBindingStatus.AVAILABLE
    assert readiness.local_queries_available
    assert readiness.commands_available
    assert not readiness.backend_globally_ready
    assert len(readiness.limitations) == 4
    for capability in (
        "intelligence_snapshot",
        "case_execution",
        "case_evaluator",
        "governance_write",
    ):
        with pytest.raises(PrivateEvalsCapabilityUnavailable):
            getattr(handle, capability)
    handle.close()
    handle.close()
    assert handle.readiness.lifecycle_state is PrivateEvalsLifecycleState.CLOSED
    with pytest.raises(PrivateEvalsRuntimeClosed):
        _ = handle.commands
    with pytest.raises(PrivateEvalsRuntimeClosed):
        handle.queries.run_summary(summary_request())


def test_all_external_clients_are_bound_explicitly_and_called_once(tmp_path: Path) -> None:
    bindings, clients = available_bindings()
    with compose_private_evals(
        runtime_config(tmp_path / "bound.sqlite3"), bindings
    ) as handle:
        assert (
            handle.readiness.lifecycle_state
            is PrivateEvalsLifecycleState.EXTERNALLY_BOUND
        )
        snapshot = security_snapshot()
        handle.intelligence_snapshot.snapshot(
            "project-1",
            tuple(item.reference.asset_id for item in snapshot.assets),
            tuple(item.provider_id for item in snapshot.providers),
        )
        request = execution_request()
        handle.case_execution.execute_case(request)
        asyncio.run(handle.case_evaluator.evaluate(evaluation_request()))
        handle.governance_write.record_evidence(governance_evidence())
    assert clients[0].snapshot.call_count == 1
    assert clients[1].execute_case.call_count == 1
    assert clients[2].evaluate.call_count == 1
    assert clients[3].record_evidence.call_count == 1


def test_readiness_distinguishes_disabled_unavailable_bound_read_only_and_closed(
    tmp_path: Path,
) -> None:
    with compose_private_evals(
        runtime_config(tmp_path / "disabled.sqlite3"),
        unavailable_bindings(status=CapabilityBindingStatus.DISABLED),
    ) as disabled:
        assert (
            disabled.readiness.lifecycle_state
            is PrivateEvalsLifecycleState.LOCALLY_OPERATIONAL
        )
        assert disabled.readiness.commands_available
        assert disabled.readiness.local_queries_available

    bindings, _clients = available_bindings()
    read_only_database = tmp_path / "read-only-bound.sqlite3"
    with compose_private_evals(
        runtime_config(read_only_database), unavailable_bindings()
    ):
        pass
    read_only = compose_private_evals(
        runtime_config(read_only_database, read_only=True), bindings
    )
    assert (
        read_only.readiness.lifecycle_state
        is PrivateEvalsLifecycleState.EXTERNALLY_BOUND
    )
    assert not read_only.readiness.commands_available
    assert read_only.readiness.local_queries_available
    read_only.close()
    assert read_only.readiness.lifecycle_state is PrivateEvalsLifecycleState.CLOSED


def test_context_manager_restart_and_queries_preserve_local_state(tmp_path: Path) -> None:
    database = tmp_path / "restart.sqlite3"
    with compose_private_evals(runtime_config(database), unavailable_bindings()) as handle:
        seed_started_run(handle)
        first = handle.queries.run_summary(summary_request())
        assert first.run_status == "running"
        assert handle.queries.evidence_local_state(EvalRunId("run-1")).state.value == "absent"
    reopened = compose_private_evals(runtime_config(database), unavailable_bindings())
    assert reopened.queries.run_summary(summary_request()) == first
    reopened.close()


def test_full_explicit_end_to_end_persists_evidence_and_survives_restart(
    tmp_path: Path,
) -> None:
    database = tmp_path / "full-e2e.sqlite3"
    spec, _catalog = manifest_spec()
    manifest = EvalRunManifestBuilder().build(spec)
    case_model = case()
    logical = LogicalExecutionIdentity(EvalRunId("run-1"), case_model.reference, 1)
    request = execution_request(
        logical_execution=logical,
        manifest_id=manifest.manifest_id,
        manifest_fingerprint=manifest.run_fingerprint,
        suite_id=manifest.suite_id,
        suite_version=manifest.suite_version,
        dataset_binding=manifest.dataset_binding,
        expected_evaluator=case_model.evaluator,
        model_provider_snapshot_fingerprint=fingerprint(manifest.model_provider),
        skill_references=tuple(
            item for item in manifest.component_references if item.kind.value == "skill"
        ),
        tool_references=tuple(
            item for item in manifest.component_references if item.kind.value == "tool"
        ),
        security_snapshot_fingerprint=fingerprint(manifest.security),
        operating_profile=manifest.security.operating_profile,
        seed=manifest.execution.seeds[0],
        execution_protocol=manifest.execution,
        fingerprint=None,
    )
    response = execution_response(target=request)
    attempt = attempt_record(request, response)
    projection = logical_execution_projection(logical, (attempt,))
    materialization = MaterializationInput(
        request,
        attempt,
        projection,
        manifest,
        case_model,
        MaterializedOutputId("output-e2e"),
        "private-evals",
        "18.0.0",
        UtcTimestamp("2026-07-23T12:00:00Z"),
        IdempotencyKey("materialization-e2e"),
    )
    output = MaterializedOutputFactory().create(materialization)
    definition = metric()
    target = ScoringTarget(
        case_model.reference,
        definition.metric_id,
        case_model.evaluator,
        case_model.weight,
        case_model.required,
        case_model.critical,
    )
    protocol = ScoringProtocol(
        EvalRunId("run-1"),
        manifest.suite_id,
        manifest.suite_version,
        (target,),
        1,
        1,
        DeterminismMode.DETERMINISTIC,
        AggregationMethod.ARITHMETIC_MEAN,
        (
            ScoreThreshold(
                ThresholdScope.CASE,
                ThresholdOperator.AT_LEAST,
                lower=Decimal("0.8"),
                metric_id=definition.metric_id,
                case_reference=case_model.reference,
            ),
        ),
        FailureBudget(FailureBudgetUnit.COUNT, count_limit=0),
    )
    event = EvaluationEventIdentity(
        output.run_id,
        output.case_reference,
        output.repetition,
        output.materialization_fingerprint,
        case_model.evaluator,
        fingerprint(protocol),
    )
    eval_request = evaluation_request(
        (definition,),
        materialized=output,
        protocol=protocol,
        manifest=manifest,
        event_identity=event,
        evaluator=case_model.evaluator,
        expected_metric=definition,
        scoring_protocol_reference="scoring-protocol-e2e",
        fingerprint=None,
    )
    eval_response = evaluation_response(
        eval_request,
        scores=(score(definition, evaluator_override=case_model.evaluator),),
    )
    result_source = EvalResultCreationInput(
        output,
        eval_request,
        eval_response,
        manifest,
        case_model,
        protocol,
        EvalResultId("result-e2e"),
        "private-evals",
        "18.0.0",
        UtcTimestamp("2026-07-23T12:00:00Z"),
        IdempotencyKey("evaluation-e2e"),
    )
    result = EvalResultFactory().create(result_source)
    matrix = create_expected_execution_matrix(manifest, protocol)
    scoring_source = RunScoringInput(
        EvalRunId("run-1"),
        manifest.manifest_id,
        fingerprint(manifest),
        manifest.suite_id,
        manifest.suite_version,
        protocol,
        fingerprint(protocol),
        matrix,
        (result,),
        ScoringDecisionId("decision-e2e"),
        "private-evals",
        "18.0.0",
        UtcTimestamp("2026-07-23T12:00:00Z"),
        IdempotencyKey("scoring-e2e"),
        "correlation-1",
    )
    decision = ScoringDecisionFactory().create(scoring_source)
    finalization_source = RunFinalizationInput(
        EvalRunFinalizationId("finalization-e2e"),
        replace(
            EvalRun(
                EvalRunId("run-1"),
                manifest.suite_id,
                manifest.suite_version,
                RunStatus.RUNNING,
                Revision(4),
                NOW,
                T1,
                manifest.manifest_id,
            ),
            accepted_result_count=0,
        ),
        manifest,
        matrix,
        (result,),
        decision,
        (),
        accounting(total=1, succeeded=1),
        (),
        (),
        "security-snapshot-1",
        fingerprint(manifest.security),
        "private-evals",
        "18.0.0",
        UtcTimestamp("2026-07-23T12:00:00Z"),
        IdempotencyKey("finalization-e2e"),
        "correlation-1",
    )
    assert (
        assess_run_finalization_readiness(finalization_source).status
        is RunFinalizationReadinessStatus.READY_SCORABLE
    )
    finalization = EvalRunFinalizationFactory().create(finalization_source)
    implementation_model = implementation()
    evidence_binding = GovernanceEvidenceBinding(
        implementation_model,
        "implementation-binding-1",
        "eval-requirement-1",
        manifest.suite_id.value,
        manifest.suite_version.value,
        EvidenceProjectionKind.EVAL_RESULT,
        "private-evals",
        "18.0.0",
        "correlation-1",
    )
    evidence_source = EvalEvidenceSource(
        applicable=True,
        run_id=finalization.run_id,
        suite_id=finalization.suite_id,
        suite_version=finalization.suite_version,
        run_manifest_reference=manifest.manifest_id.value,
        run_manifest_fingerprint=finalization.manifest_fingerprint,
        finalization_reference=finalization.finalization_id.value,
        finalization_fingerprint=finalization.fingerprint,
        scoring_decision_reference=decision.decision_id.value,
        scoring_decision_fingerprint=decision.decision_fingerprint,
        verdict=decision.verdict,
        security_snapshot_reference=finalization.security_snapshot_reference,
        security_snapshot_fingerprint=finalization.security_snapshot_fingerprint,
        provenance_references=("provenance-1",),
        reason_codes=(ProjectionReasonCode.EVAL_COMPLETED,),
    )
    candidate = EvidenceProjectionCandidate(
        evidence_binding,
        EvalReference(
            manifest.suite_id.value,
            manifest.suite_version.value,
            True,
            manifest.dataset_binding.binding_id.value,
            definition.metric_id,
            "0.8",
        ),
        f"private-evals-scoring:{decision.decision_id.value}",
        evidence_source,
        EvidenceMetricAllowlist(
            "allowlist-e2e",
            "1.0.0",
            (definition.metric_id,),
            "classification-v1",
            case_model.classification,
        ),
        (EvidenceMetric(definition.metric_id, Decimal("0.9")),),
    )
    planning = EvalEvidencePlanningInput(
        finalization,
        implementation_model,
        "implementation-binding-1",
        (candidate,),
        decision,
        IdempotencyKey("evidence-e2e"),
        "correlation-1",
        "private-evals",
        "18.0.0",
        UtcTimestamp("2026-07-23T12:00:00Z"),
    )
    evidence_plan = EvalEvidenceSubmissionPlanner().create(planning)
    governance_identity = GovernanceEvidenceIdentity(
        evidence_plan.specifications[0].projection_kind,
        evidence_plan.specifications[0].expected_projection_fingerprint,
        "governance-evidence-e2e",
    )
    assert evidence_plan.semantic_fingerprint is not None
    records = ResolverRecordCatalog(
        case_references=(
            StoredCaseReference(
                "case-e2e",
                case_model.suite_id,
                case_model.case_id,
                case_model.version,
            ),
        ),
        execution_requests=(ReferencedRecord("execution-request-e2e", request),),
        execution_attempts=(ReferencedRecord("execution-attempt-e2e", attempt),),
        logical_projections=(ReferencedRecord("execution-projection-e2e", projection),),
        evaluation_requests=(ReferencedRecord("evaluation-request-e2e", eval_request),),
        scoring_protocols=(ReferencedRecord("scoring-protocol-e2e", protocol),),
        expected_matrices=(ReferencedRecord("matrix-e2e", matrix),),
        execution_accounting=(
            ReferencedRecord("execution-accounting-e2e", accounting(total=1, succeeded=1)),
        ),
        implementations=(
            ReferencedRecord("implementation-e2e", implementation_model),
        ),
        projection_candidates=(ReferencedRecord("candidate-e2e", candidate),),
    )
    coordination = (
        EvidenceCoordinationReference(
            EvalRunId("run-1"),
            evidence_plan.semantic_fingerprint,
            1,
            evidence_plan.finalization_reference,
        ),
    )
    bindings, clients = available_bindings()
    expected_snapshot = security_snapshot()

    def strict_snapshot(
        project_id: str,
        asset_ids: tuple[str, ...],
        provider_ids: tuple[str, ...],
    ):
        assert clients[0].snapshot.call_count == 1
        assert project_id == "project-1"
        assert asset_ids == tuple(
            item.reference.asset_id for item in expected_snapshot.assets
        )
        assert provider_ids == tuple(
            item.provider_id for item in expected_snapshot.providers
        )
        return expected_snapshot

    def strict_execution(observed):
        assert clients[1].execute_case.call_count == 1
        assert observed == request
        return response

    async def strict_evaluation(observed):
        assert clients[2].evaluate.call_count == 1
        assert observed == eval_request
        return eval_response

    def strict_governance(observed):
        assert clients[3].record_evidence.call_count == 1
        assert observed.evidence_id == governance_identity.evidence_id
        assert replace(observed) == observed
        assert observed.project_id == implementation_model.project_id
        assert observed.rfc_id == implementation_model.rfc_id
        assert observed.evidence_type == EvidenceProjectionKind.EVAL_RESULT.value
        assert observed.produced_by == "private-evals:18.0.0"
        assert len(observed.checksum) == 64
        return observed

    clients[0].snapshot.side_effect = strict_snapshot
    clients[1].execute_case.side_effect = strict_execution
    clients[2].evaluate.side_effect = strict_evaluation
    observed_governance_records = []

    def capture_governance(observed):
        observed_governance_records.append(observed)
        return observed

    clients[3].record_evidence.side_effect = capture_governance
    with compose_private_evals(
        runtime_config(database),
        bindings,
        resolver_records=records,
        evidence_coordination=coordination,
    ) as handle:
        seed_started_run(handle)
        snapshot = expected_snapshot
        handle.intelligence_snapshot.snapshot(
            "project-1",
            tuple(item.reference.asset_id for item in snapshot.assets),
            tuple(item.provider_id for item in snapshot.providers),
        )
        assert handle.case_execution.execute_case(request) == response
        assert clients[0].snapshot.call_count == 1
        assert clients[1].execute_case.call_count == 1
        materialized = handle.commands.record_materialized_output(
            RecordMaterializedOutputCommand(
                command_context("materialization-command"),
                "run-1",
                "execution-request-e2e",
                "execution-attempt-e2e",
                "execution-projection-e2e",
                manifest.manifest_id.value,
                "case-e2e",
                "output-e2e",
                "private-evals",
                "18.0.0",
            )
        )
        observed_eval = asyncio.run(handle.case_evaluator.evaluate(eval_request))
        assert clients[2].evaluate.call_count == 1
        evaluated = handle.commands.create_eval_result(
            CreateEvalResultCommand(
                command_context("evaluation-command"),
                "run-1",
                materialized.record_reference,
                "evaluation-request-e2e",
                observed_eval,
                manifest.manifest_id.value,
                "case-e2e",
                "scoring-protocol-e2e",
                "result-e2e",
                "private-evals",
                "18.0.0",
            )
        )
        scored = handle.commands.create_scoring_decision(
            CreateScoringDecisionCommand(
                command_context("scoring-command"),
                "run-1",
                manifest.manifest_id.value,
                fingerprint(manifest).value,
                "scoring-protocol-e2e",
                fingerprint(protocol).value,
                "matrix-e2e",
                (evaluated.record_reference,),
                "decision-e2e",
                "private-evals",
                "18.0.0",
            )
        )
        finalized = handle.commands.finalize_run(
            FinalizeRunCommand(
                command_context("finalization-command"),
                "run-1",
                "finalization-e2e",
                "run-1",
                manifest.manifest_id.value,
                "matrix-e2e",
                ("result-e2e",),
                scored.decision_reference,
                (),
                "execution-accounting-e2e",
                (),
                (),
                "security-snapshot-1",
                fingerprint(manifest.security).value,
                "private-evals",
                "18.0.0",
                )
            )
        assert finalized.run_status == "completed"
        submitted = handle.commands.submit_evidence(
            SubmitEvidenceCommand(
                    command_context("evidence-command"),
                    "run-1",
                    "submission-e2e",
                    "finalization-e2e",
                "implementation-e2e",
                ("candidate-e2e",),
                scored.decision_reference,
                (governance_identity,),
                "private-evals",
                "18.0.0",
            )
        )
        assert submitted.local_outcome.value == "submitted"
        assert clients[3].record_evidence.call_count == 1
        assert len(observed_governance_records) == 1
        strict_governance(observed_governance_records[0])
        assert handle.queries.run_summary(summary_request()).run_status == "completed"
        assert (
            handle.queries.evidence_local_state(EvalRunId("run-1")).state.value
            == "submitted"
        )
    reopened = compose_private_evals(
        runtime_config(database),
        unavailable_bindings(),
        evidence_coordination=coordination,
    )
    assert reopened.queries.run_summary(summary_request()).run_status == "completed"
    assert (
        reopened.queries.evidence_local_state(EvalRunId("run-1")).state.value
        == "submitted"
    )
    reopened.close()
    assert clients[3].record_evidence.call_count == 1


def test_read_only_runtime_allows_queries_and_rejects_mutation(tmp_path: Path) -> None:
    database = tmp_path / "read-only.sqlite3"
    with compose_private_evals(runtime_config(database), unavailable_bindings()) as writable:
        seed_started_run(writable)
    read_only = compose_private_evals(
        runtime_config(database, read_only=True), unavailable_bindings()
    )
    assert read_only.readiness.read_only
    assert not read_only.readiness.commands_available
    assert read_only.queries.run_summary(summary_request()).run_status == "running"
    with pytest.raises(PrivateEvalsRuntimeReadOnly):
        _ = read_only.commands
    with pytest.raises(PrivateEvalsRuntimeReadOnly):
        _ = read_only.runs
    read_only.close()


def test_schema_mismatch_blocks_construction(tmp_path: Path) -> None:
    database = tmp_path / "schema.sqlite3"
    handle = compose_private_evals(runtime_config(database), unavailable_bindings())
    handle.close()
    with sqlite3.connect(database) as connection:
        connection.execute("UPDATE private_evals_schema SET schema_version = 999")
    with pytest.raises(EvalSchemaVersionMismatch):
        compose_private_evals(runtime_config(database), unavailable_bindings())


def test_partial_construction_failure_closes_opened_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    opened = []
    original_catalog = composition_module.SQLiteEvalCatalogStore

    class ObservedCatalog(original_catalog):
        def __init__(self, config):  # noqa: ANN001
            super().__init__(config)
            opened.append(self)

    class BrokenRunStore:
        def __init__(self, _config):  # noqa: ANN001
            raise RuntimeError("private constructor detail")

    monkeypatch.setattr(composition_module, "SQLiteEvalCatalogStore", ObservedCatalog)
    monkeypatch.setattr(composition_module, "SQLiteEvalRunStore", BrokenRunStore)
    with pytest.raises(PrivateEvalsConstructionFailed) as caught:
        compose_private_evals(
            runtime_config(tmp_path / "partial.sqlite3"), unavailable_bindings()
        )
    assert "private constructor" not in str(caught.value)
    with pytest.raises(EvalStoreUnavailable):
        opened[0].get_suite(suite().suite_id)


def test_composition_has_no_service_locator_hidden_pipeline_or_forbidden_runtime() -> None:
    source = inspect.getsource(composition_module)
    tree = ast.parse(source)
    forbidden = (
        "get_component",
        "run_all",
        "execute_pipeline",
        "auto_finalize",
        "auto_submit",
        "auto_score",
        "next_stage",
        "FastAPI",
        "httpx",
        "requests",
        "subprocess",
        "import_module",
    )
    assert not any(term in source for term in forbidden)
    assert not any(
        isinstance(node, (ast.While, ast.Global, ast.Nonlocal)) for node in ast.walk(tree)
    )
    assert not any(
        isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and "runtime" in target.id.casefold()
            for target in node.targets
        )
        for node in tree.body
    )


def test_composition_is_the_only_production_concrete_construction_authority() -> None:
    source_root = Path(composition_module.__file__).parent
    concrete_names = {
        "SQLiteEvalCatalogStore",
        "SQLiteEvalRunStore",
        "SQLiteEvalAnalysisStore",
        "SQLiteEvalMaterializationStore",
        "SQLiteEvalEvidenceStore",
        "IntelligenceSecuritySnapshotAdapter",
        "CaseExecutionBoundaryAdapter",
        "CaseEvaluatorBoundaryAdapter",
        "GovernanceEvidenceWriteAdapter",
    }
    construction_sites: set[Path] = set()
    for path in source_root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        if any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in concrete_names
            for node in ast.walk(tree)
        ):
            construction_sites.add(path.relative_to(source_root))
    assert construction_sites == {Path("composition.py")}
