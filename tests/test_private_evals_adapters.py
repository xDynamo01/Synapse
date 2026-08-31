from __future__ import annotations

import asyncio
import copy
import inspect
from dataclasses import fields, replace
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest

from synapse.private_evals.adapters import (
    AdapterEvaluatorResponseInvalid,
    AdapterEvaluatorUnavailable,
    AdapterExecutionResponseInvalid,
    AdapterExecutionUnavailable,
    AmbiguousExternalWrite,
    CaseEvaluatorBoundaryAdapter,
    CaseExecutionBoundaryAdapter,
    EvidenceCoordinationReference,
    ExternalAdapterConfig,
    GovernanceEvidenceWriteAdapter,
    GovernanceSubmissionUnavailable,
    IntelligenceSecuritySnapshotAdapter,
    PrivateEvalsCommandResolverAdapter,
    ReferencedRecord,
    ResolverRecordCatalog,
    SecuritySnapshotMismatch,
    SecuritySnapshotUnavailable,
    SQLiteEvidenceLocalStateReader,
)
from synapse.private_evals.command_contracts import (
    EvaluationRecordResolver,
    EvidenceRecordResolver,
    FinalizationRecordResolver,
    MaterializationRecordResolver,
    RunManifestResolver,
    ScoringRecordResolver,
)
from synapse.private_evals.command_errors import ReferencedInputNotFound
from synapse.private_evals.query_models import EvidenceLocalState
from synapse.private_evals.security import security_snapshot_fingerprint
from synapse.private_evals.sqlite_stores import (
    SQLiteEvalAnalysisStore,
    SQLiteEvalCatalogStore,
    SQLiteEvalEvidenceStore,
    SQLiteEvalMaterializationStore,
    SQLiteEvalRunStore,
)
from synapse.private_evals.store_errors import EvalRecordNotFound
from synapse.private_evals.store_models import IdempotencyKey
from synapse.private_evals.values import (
    EvalRunManifestId,
    EvalVersion,
    Fingerprint,
    Revision,
)
from synapse.project_governance.models import EvidenceRecord
from test_private_evals_case_evaluation import evaluation_request, evaluation_response
from test_private_evals_execution import request as execution_request
from test_private_evals_execution import response as execution_response
from test_private_evals_security import security_snapshot
from test_private_evals_sqlite_stores import (
    config,
    evidence_records,
    seed_evidence_finalization,
)


def adapter_config() -> ExternalAdapterConfig:
    return ExternalAdapterConfig("private-evals-boundary", "17.0.0", 2.0)


def governance_evidence() -> EvidenceRecord:
    return EvidenceRecord(
        project_id="project-1",
        rfc_id="rfc-1",
        rfc_revision=1,
        plan_id="plan-1",
        evidence_type="private_eval",
        summary="reference-only-eval",
        artifact_reference="private-evals-finalization:finalization-1",
        checksum="a" * 64,
        produced_by="private-evals",
        validation_status="recorded",
        evidence_id="evidence-1",
        created_at="2026-07-22T12:00:00Z",
    )


def test_adapter_configuration_is_typed_and_safe() -> None:
    assert "2.0" not in repr(adapter_config())
    assert adapter_config().requested_timeout_seconds == 2.0
    for forbidden in ("secret-token", "https://private", "C:\\private"):
        with pytest.raises(ValueError):
            ExternalAdapterConfig(forbidden, "17.0.0")
    for invalid_timeout in (True, 0.0, 301.0, "2"):
        with pytest.raises(ValueError):
            ExternalAdapterConfig(
                "private-evals-boundary",
                "17.0.0",
                invalid_timeout,  # type: ignore[arg-type]
            )


@pytest.mark.parametrize(
    ("adapter_type", "client"),
    (
        (IntelligenceSecuritySnapshotAdapter, object()),
        (CaseExecutionBoundaryAdapter, object()),
        (CaseEvaluatorBoundaryAdapter, object()),
        (GovernanceEvidenceWriteAdapter, object()),
    ),
)
def test_boundary_adapters_require_an_injected_narrow_client(
    adapter_type: type, client: object
) -> None:
    with pytest.raises(TypeError):
        adapter_type(client, adapter_config())


def test_intelligence_snapshot_adapter_validates_exact_projection_and_calls_once() -> None:
    snapshot = security_snapshot()
    asset_ids = tuple(item.reference.asset_id for item in snapshot.assets)
    provider_ids = tuple(item.provider_id for item in snapshot.providers)
    client = Mock()
    client.snapshot.return_value = snapshot
    adapter = IntelligenceSecuritySnapshotAdapter(client, adapter_config())
    assert adapter.snapshot("project-1", asset_ids, provider_ids) == snapshot
    client.snapshot.assert_called_once_with("project-1", asset_ids, provider_ids)
    client.snapshot.return_value = security_snapshot(providers=())
    with pytest.raises(SecuritySnapshotMismatch):
        adapter.snapshot("project-1", ("asset-1",), ("provider-1",))
    assert "project-1" not in repr(SecuritySnapshotMismatch("project-1"))


@pytest.mark.parametrize("failure", [TimeoutError(), RuntimeError("raw provider body")])
def test_intelligence_snapshot_adapter_translates_unavailability(failure: Exception) -> None:
    client = Mock()
    client.snapshot.side_effect = failure
    with pytest.raises(SecuritySnapshotUnavailable) as caught:
        IntelligenceSecuritySnapshotAdapter(client, adapter_config()).snapshot(
            "project-1", ("asset-1",), ("provider-1",)
        )
    assert "provider" not in str(caught.value).casefold()
    assert client.snapshot.call_count == 1


def test_intelligence_snapshot_adapter_rejects_invalid_request_before_call() -> None:
    client = Mock()
    with pytest.raises(SecuritySnapshotMismatch):
        IntelligenceSecuritySnapshotAdapter(client, adapter_config()).snapshot(
            "project/unsafe", ("asset-1",), ("provider-1",)
        )
    client.snapshot.assert_not_called()


@pytest.mark.parametrize("mismatch", ("asset", "provider", "fingerprint", "revision"))
def test_intelligence_snapshot_adapter_rejects_typed_semantic_mismatch(
    mismatch: str,
) -> None:
    snapshot = security_snapshot()
    asset_ids = tuple(item.reference.asset_id for item in snapshot.assets)
    provider_ids = tuple(item.provider_id for item in snapshot.providers)
    if mismatch == "asset":
        changed_reference = replace(snapshot.assets[0].reference, asset_id="asset-other")
        changed_asset = replace(snapshot.assets[0], reference=changed_reference)
        candidate = copy.copy(snapshot)
        object.__setattr__(candidate, "assets", (changed_asset,))
        object.__setattr__(candidate, "fingerprint", security_snapshot_fingerprint(candidate))
    elif mismatch == "provider":
        changed_provider = replace(snapshot.providers[0], provider_id="provider-other")
        candidate = copy.copy(snapshot)
        object.__setattr__(candidate, "providers", (changed_provider,))
        object.__setattr__(candidate, "fingerprint", security_snapshot_fingerprint(candidate))
    else:
        candidate = copy.copy(snapshot)
        object.__setattr__(
            candidate,
            mismatch,
            Fingerprint("d" * 64) if mismatch == "fingerprint" else Revision(99),
        )
    client = Mock()
    client.snapshot.return_value = candidate
    with pytest.raises(SecuritySnapshotMismatch):
        IntelligenceSecuritySnapshotAdapter(client, adapter_config()).snapshot(
            "project-1", asset_ids, provider_ids
        )
    assert client.snapshot.call_count == 1


@pytest.mark.parametrize(
    "field_name",
    (
        "snapshot_reference",
        "revision",
        "checksum",
        "operating_profile",
        "policy_references",
        "policy_checksums",
        "assets",
        "providers",
        "fingerprint",
    ),
)
def test_intelligence_snapshot_adapter_rejects_each_corrupt_field_safely(
    field_name: str,
) -> None:
    snapshot = security_snapshot()
    corrupt = copy.copy(snapshot)
    object.__setattr__(corrupt, field_name, object())
    client = Mock()
    client.snapshot.return_value = corrupt
    with pytest.raises(SecuritySnapshotMismatch):
        IntelligenceSecuritySnapshotAdapter(client, adapter_config()).snapshot(
            "project-1",
            tuple(item.reference.asset_id for item in snapshot.assets),
            tuple(item.provider_id for item in snapshot.providers),
        )
    assert client.snapshot.call_count == 1


def test_execution_adapter_preserves_request_validates_response_and_never_retries() -> None:
    request = execution_request()
    response = execution_response()
    backend = Mock()
    backend.execute_case.return_value = response
    adapter = CaseExecutionBoundaryAdapter(backend, adapter_config())
    assert adapter.execute_case(request) == response
    backend.execute_case.assert_called_once_with(request)
    backend.execute_case.reset_mock(side_effect=True)
    backend.execute_case.return_value = object()
    with pytest.raises(AdapterExecutionResponseInvalid):
        adapter.execute_case(request)
    assert backend.execute_case.call_count == 1


def test_execution_adapter_translates_timeout_without_hidden_retry() -> None:
    backend = Mock()
    backend.execute_case.side_effect = TimeoutError("private endpoint")
    with pytest.raises(AdapterExecutionUnavailable) as caught:
        CaseExecutionBoundaryAdapter(backend, adapter_config()).execute_case(
            execution_request()
        )
    assert backend.execute_case.call_count == 1
    assert "endpoint" not in str(caught.value)
    assert caught.value.__cause__ is None


def test_execution_adapter_rejects_corrupt_request_before_backend_call() -> None:
    request = copy.copy(execution_request())
    object.__setattr__(request, "manifest_id", object())
    backend = Mock()
    with pytest.raises(AdapterExecutionResponseInvalid):
        CaseExecutionBoundaryAdapter(backend, adapter_config()).execute_case(request)
    backend.execute_case.assert_not_called()


@pytest.mark.parametrize(
    "field_name",
    tuple(field.name for field in fields(execution_response())),
)
def test_execution_adapter_rejects_response_adulterated_field_by_field(
    field_name: str,
) -> None:
    response = copy.copy(execution_response())
    object.__setattr__(response, field_name, object())
    backend = Mock()
    backend.execute_case.return_value = response
    with pytest.raises(AdapterExecutionResponseInvalid):
        CaseExecutionBoundaryAdapter(backend, adapter_config()).execute_case(
            execution_request()
        )
    assert backend.execute_case.call_count == 1


def test_evaluator_adapter_preserves_identity_and_never_retries() -> None:
    request = evaluation_request()
    response = evaluation_response(request)
    backend = AsyncMock()
    backend.evaluate.return_value = response
    adapter = CaseEvaluatorBoundaryAdapter(backend, adapter_config())
    assert asyncio.run(adapter.evaluate(request)) == response
    backend.evaluate.assert_awaited_once_with(request)
    backend.reset_mock(side_effect=True)
    mismatched_identity = replace(
        response.event_identity, repetition=2, fingerprint=None
    )
    backend.evaluate.return_value = replace(
        response, event_identity=mismatched_identity, fingerprint=None
    )
    with pytest.raises(AdapterEvaluatorResponseInvalid):
        asyncio.run(adapter.evaluate(request))
    assert backend.evaluate.await_count == 1


def test_evaluator_adapter_translates_timeout_without_hidden_retry() -> None:
    backend = Mock()
    backend.evaluate = AsyncMock(side_effect=TimeoutError("raw evaluator payload"))
    with pytest.raises(AdapterEvaluatorUnavailable) as caught:
        asyncio.run(
            CaseEvaluatorBoundaryAdapter(backend, adapter_config()).evaluate(
                evaluation_request()
            )
        )
    assert backend.evaluate.await_count == 1
    assert "payload" not in str(caught.value)
    assert caught.value.__cause__ is None


def test_evaluator_adapter_rejects_corrupt_request_before_backend_call() -> None:
    request = copy.copy(evaluation_request())
    object.__setattr__(request, "manifest_id", object())
    backend = Mock()
    backend.evaluate = AsyncMock()
    with pytest.raises(AdapterEvaluatorResponseInvalid):
        asyncio.run(
            CaseEvaluatorBoundaryAdapter(backend, adapter_config()).evaluate(request)
        )
    backend.evaluate.assert_not_awaited()


@pytest.mark.parametrize(
    "field_name",
    tuple(field.name for field in fields(evaluation_response(evaluation_request()))),
)
def test_evaluator_adapter_rejects_response_adulterated_field_by_field(
    field_name: str,
) -> None:
    request = evaluation_request()
    response = copy.copy(evaluation_response(request))
    object.__setattr__(response, field_name, object())
    backend = Mock()
    backend.evaluate = AsyncMock(return_value=response)
    with pytest.raises(AdapterEvaluatorResponseInvalid):
        asyncio.run(
            CaseEvaluatorBoundaryAdapter(backend, adapter_config()).evaluate(request)
        )
    assert backend.evaluate.await_count == 1


def test_evaluator_adapter_rejects_validly_fingerprinted_wrong_scoring_shape() -> None:
    request = evaluation_request()
    response = evaluation_response(request)
    wrong_metric = replace(response.scores[0], metric_id="another-metric")
    mismatched = replace(response, scores=(wrong_metric,), fingerprint=None)
    backend = Mock()
    backend.evaluate = AsyncMock(return_value=mismatched)
    with pytest.raises(AdapterEvaluatorResponseInvalid):
        asyncio.run(
            CaseEvaluatorBoundaryAdapter(backend, adapter_config()).evaluate(request)
        )
    assert backend.evaluate.await_count == 1


def test_evaluator_adapter_rejects_validly_fingerprinted_version_mismatch() -> None:
    request = evaluation_request()
    response = evaluation_response(request)
    another_version = replace(request.evaluator, version=EvalVersion("2.0.0"))
    mismatched = replace(response, evaluator=another_version, fingerprint=None)
    backend = Mock()
    backend.evaluate = AsyncMock(return_value=mismatched)
    with pytest.raises(AdapterEvaluatorResponseInvalid):
        asyncio.run(
            CaseEvaluatorBoundaryAdapter(backend, adapter_config()).evaluate(request)
        )
    assert backend.evaluate.await_count == 1


def test_governance_adapter_is_write_only_validates_receipt_and_does_not_retry() -> None:
    evidence = governance_evidence()
    client = Mock()
    client.record_evidence.return_value = evidence
    adapter = GovernanceEvidenceWriteAdapter(client, adapter_config())
    assert adapter.record_evidence(evidence) == evidence
    client.record_evidence.assert_called_once_with(evidence)
    assert not hasattr(adapter, "get_evidence")


@pytest.mark.parametrize(
    "failure",
    (
        TimeoutError("token=private"),
        ConnectionResetError("provider response lost"),
        BrokenPipeError("private endpoint"),
    ),
)
def test_governance_ambiguous_write_is_safe_and_not_retried(
    failure: Exception,
) -> None:
    client = Mock()
    client.record_evidence.side_effect = failure
    with pytest.raises(AmbiguousExternalWrite) as caught:
        GovernanceEvidenceWriteAdapter(client, adapter_config()).record_evidence(
            governance_evidence()
        )
    assert client.record_evidence.call_count == 1
    assert "token" not in str(caught.value).casefold()


def test_governance_provable_pre_write_refusal_is_unavailable_not_ambiguous() -> None:
    client = Mock()
    client.record_evidence.side_effect = ConnectionRefusedError("private endpoint")
    with pytest.raises(GovernanceSubmissionUnavailable) as caught:
        GovernanceEvidenceWriteAdapter(client, adapter_config()).record_evidence(
            governance_evidence()
        )
    assert client.record_evidence.call_count == 1
    assert "endpoint" not in str(caught.value)


def test_governance_adapter_rejects_corrupt_receipt_without_second_write() -> None:
    evidence = governance_evidence()
    client = Mock()
    client.record_evidence.return_value = replace(evidence, checksum="b" * 64)
    with pytest.raises(AmbiguousExternalWrite):
        GovernanceEvidenceWriteAdapter(client, adapter_config()).record_evidence(evidence)
    assert client.record_evidence.call_count == 1


@pytest.mark.parametrize(
    "field_name",
    tuple(field.name for field in fields(governance_evidence())),
)
def test_governance_adapter_rejects_every_divergent_receipt_field(
    field_name: str,
) -> None:
    evidence = governance_evidence()
    divergent = copy.copy(evidence)
    object.__setattr__(divergent, field_name, object())
    client = Mock()
    client.record_evidence.return_value = divergent
    with pytest.raises(AmbiguousExternalWrite):
        GovernanceEvidenceWriteAdapter(client, adapter_config()).record_evidence(evidence)
    assert client.record_evidence.call_count == 1


def test_governance_unknown_client_failure_is_ambiguous_and_hides_raw_cause() -> None:
    client = Mock()
    client.record_evidence.side_effect = RuntimeError("token=private endpoint")
    with pytest.raises(AmbiguousExternalWrite) as caught:
        GovernanceEvidenceWriteAdapter(client, adapter_config()).record_evidence(
            governance_evidence()
        )
    assert client.record_evidence.call_count == 1
    assert caught.value.__cause__ is None
    assert "private" not in str(caught.value).casefold()


def test_resolver_adapter_implements_every_method_of_all_six_capabilities() -> None:
    expected = set()
    for protocol in (
        RunManifestResolver,
        MaterializationRecordResolver,
        EvaluationRecordResolver,
        ScoringRecordResolver,
        FinalizationRecordResolver,
        EvidenceRecordResolver,
    ):
        expected.update(
            name
            for name, value in protocol.__dict__.items()
            if inspect.isfunction(value) and name != "__init__"
        )
    implemented = {
        name
        for name, value in PrivateEvalsCommandResolverAdapter.__dict__.items()
        if inspect.isfunction(value) and name.startswith("resolve_")
    }
    assert implemented == expected


def test_resolver_uses_sqlite_for_owned_records_and_explicit_catalog_for_transients(
    tmp_path: Path,
) -> None:
    database = tmp_path / "resolvers.sqlite3"
    from synapse.private_evals import (
        EvalRunManifestBuilder,
    )
    from test_private_evals_run_runtime import manifest_spec

    catalog = SQLiteEvalCatalogStore(config(database))
    run_store = SQLiteEvalRunStore(config(database, create_if_missing=False))
    analysis = SQLiteEvalAnalysisStore(config(database, create_if_missing=False))
    materialization = SQLiteEvalMaterializationStore(
        config(database, create_if_missing=False)
    )
    spec, _ = manifest_spec()
    manifest_record = EvalRunManifestBuilder().build(spec)
    run_store.save_manifest(
        manifest_record, idempotency_key=IdempotencyKey("resolver-manifest")
    )
    request = execution_request()
    resolver = PrivateEvalsCommandResolverAdapter(
        catalog,
        run_store,
        analysis,
        materialization,
        ResolverRecordCatalog(
            execution_requests=(ReferencedRecord("execution-request-1", request),)
        ),
    )
    assert resolver.resolve_manifest(manifest_record.manifest_id.value) == manifest_record
    assert resolver.resolve_execution_request("execution-request-1") == request
    with pytest.raises(ReferencedInputNotFound):
        resolver.resolve_manifest(EvalRunManifestId("missing").value)
    with pytest.raises(ReferencedInputNotFound):
        resolver.resolve_execution_request("missing-request")


def test_resolver_binding_catalog_rejects_mutability_wrong_types_and_duplicates() -> None:
    request = execution_request()
    with pytest.raises(TypeError):
        ResolverRecordCatalog(
            execution_requests=[  # type: ignore[arg-type]
                ReferencedRecord("execution-request-1", request)
            ]
        )
    with pytest.raises(TypeError):
        ResolverRecordCatalog(
            execution_requests=(ReferencedRecord("execution-request-1", object()),)  # type: ignore[arg-type]
        )
    with pytest.raises(ValueError):
        ResolverRecordCatalog(
            execution_requests=(ReferencedRecord("same-reference", request),),
            evaluation_requests=(
                ReferencedRecord("same-reference", evaluation_request()),
            ),
        )


def test_every_resolver_method_requires_explicit_reference_and_never_discovers_or_retries() -> None:
    catalog_store = Mock()
    run_store = Mock()
    analysis_store = Mock()
    materialization_store = Mock()
    for method_name in (
        "get_manifest",
        "get_result",
        "get_run",
        "get_evaluation_attempt",
        "get_finalization",
    ):
        getattr(run_store, method_name).side_effect = EvalRecordNotFound()
    analysis_store.get_scoring_decision.side_effect = EvalRecordNotFound()
    materialization_store.get_materialized_output.side_effect = EvalRecordNotFound()
    resolver = PrivateEvalsCommandResolverAdapter(
        catalog_store,
        run_store,
        analysis_store,
        materialization_store,
    )
    methods = tuple(
        value
        for name, value in inspect.getmembers(resolver, predicate=callable)
        if name.startswith("resolve_")
    )
    for method in methods:
        with pytest.raises(ReferencedInputNotFound):
            method("d" * 64)
    for store in (catalog_store, run_store, analysis_store, materialization_store):
        assert not any(
            call[0].startswith(("list_", "save_", "create_"))
            for call in store.mock_calls
        )
    assert run_store.get_manifest.call_count == 1
    assert run_store.get_result.call_count == 1
    assert run_store.get_run.call_count == 1
    assert run_store.get_evaluation_attempt.call_count == 1
    assert run_store.get_finalization.call_count == 1
    assert analysis_store.get_scoring_decision.call_count == 1
    assert materialization_store.get_materialized_output.call_count == 1


def test_evidence_local_reader_projects_partial_complete_submitted_and_reconciliation(
    tmp_path: Path,
) -> None:
    database = tmp_path / "local-evidence.sqlite3"
    attempt, receipt, submission, finalization = evidence_records()
    seed_evidence_finalization(database, finalization)
    store = SQLiteEvalEvidenceStore(config(database, create_if_missing=False))
    reference = EvidenceCoordinationReference(
        submission.run_id,
        submission.semantic_fingerprint,
        1,
        submission.finalization_reference,
    )
    reader = SQLiteEvidenceLocalStateReader(store, (reference,))
    assert reader.get_local_evidence_state(submission.run_id).state is EvidenceLocalState.ABSENT
    store.save_evidence_submission_attempt(
        attempt, idempotency_key=IdempotencyKey("reader-attempt")
    )
    assert (
        reader.get_local_evidence_state(submission.run_id).state
        is EvidenceLocalState.ATTEMPT_STARTED
    )
    store.save_evidence_submission_receipt(
        receipt, idempotency_key=IdempotencyKey("reader-receipt")
    )
    complete = reader.get_local_evidence_state(submission.run_id)
    assert complete.state is EvidenceLocalState.RECEIPTS_COMPLETE
    assert complete.chain_complete
    partial_reader = SQLiteEvidenceLocalStateReader(
        store,
        (replace(reference, expected_receipt_count=2),),
    )
    assert (
        partial_reader.get_local_evidence_state(submission.run_id).state
        is EvidenceLocalState.RECEIPT_RECORDED
    )
    store.save_evidence_submission(
        submission, idempotency_key=IdempotencyKey("reader-submission")
    )
    assert (
        reader.get_local_evidence_state(submission.run_id).state
        is EvidenceLocalState.SUBMITTED
    )


def test_evidence_local_state_taxonomy_has_one_unambiguous_partial_receipt_state() -> None:
    assert tuple(item.value for item in EvidenceLocalState) == (
        "absent",
        "attempt_started",
        "receipt_recorded",
        "receipts_complete",
        "submitted",
        "reconciliation_required",
    )


def test_evidence_local_reader_marks_orphan_receipt_for_reconciliation() -> None:
    attempt, receipt, submission, _ = evidence_records()
    store = Mock()
    store.evidence_submission_exists.return_value = False
    store.list_evidence_submission_attempts.return_value = ()
    store.list_evidence_submission_receipts.return_value = (receipt,)
    reader = SQLiteEvidenceLocalStateReader(
        store,
        (
            EvidenceCoordinationReference(
                submission.run_id,
                attempt.logical_submission_fingerprint,
                1,
                submission.finalization_reference,
            ),
        ),
    )
    projection = reader.get_local_evidence_state(submission.run_id)
    assert projection.state is EvidenceLocalState.RECONCILIATION_REQUIRED
    assert not projection.integrity_valid


def test_evidence_local_reader_rejects_conflicting_explicit_coordination(
    tmp_path: Path,
) -> None:
    database = tmp_path / "local-evidence-conflict.sqlite3"
    attempt, receipt, submission, finalization = evidence_records()
    seed_evidence_finalization(database, finalization)
    store = SQLiteEvalEvidenceStore(config(database, create_if_missing=False))
    store.save_evidence_submission_attempt(
        attempt, idempotency_key=IdempotencyKey("reader-conflict-attempt")
    )
    store.save_evidence_submission_receipt(
        receipt, idempotency_key=IdempotencyKey("reader-conflict-receipt")
    )
    store.save_evidence_submission(
        submission, idempotency_key=IdempotencyKey("reader-conflict-submission")
    )
    reader = SQLiteEvidenceLocalStateReader(
        store,
        (
            EvidenceCoordinationReference(
                submission.run_id,
                Fingerprint("f" * 64),
                1,
                submission.finalization_reference,
            ),
        ),
    )
    projection = reader.get_local_evidence_state(submission.run_id)
    assert projection.state is EvidenceLocalState.RECONCILIATION_REQUIRED
    assert not projection.integrity_valid


def test_partial_boundary_harness_stops_after_local_evidence_receipt(tmp_path: Path) -> None:
    from synapse.private_evals import (
        EvalRunFinalizationFactory,
        EvalRunManifestBuilder,
        Revision,
        ScoringDecisionFactory,
    )
    from test_private_evals_result_materialization import FACTORY, materialization
    from test_private_evals_run_finalization import finalization_input
    from test_private_evals_run_runtime import manifest_spec
    from test_private_evals_run_scoring import scoring_input

    database = tmp_path / "partial-harness.sqlite3"
    run_store = SQLiteEvalRunStore(config(database))
    analysis_store = SQLiteEvalAnalysisStore(config(database, create_if_missing=False))
    materialization_store = SQLiteEvalMaterializationStore(
        config(database, create_if_missing=False)
    )
    evidence_store = SQLiteEvalEvidenceStore(config(database, create_if_missing=False))

    finalization_source = finalization_input()
    spec, _ = manifest_spec()
    persisted_manifest = EvalRunManifestBuilder().build(spec)
    run_store.save_manifest(
        persisted_manifest,
        idempotency_key=IdempotencyKey("harness-manifest"),
    )
    run_store.create_run(
        replace(finalization_source.run, revision=Revision(1)),
        idempotency_key=IdempotencyKey("harness-run"),
    )

    execution_backend = Mock()
    execution_backend.execute_case.return_value = execution_response()
    execution_adapter = CaseExecutionBoundaryAdapter(execution_backend, adapter_config())
    assert execution_adapter.execute_case(execution_request()).output_asset_reference

    materialized = FACTORY.create(materialization())
    materialization_store.save_materialized_output(
        materialized, idempotency_key=IdempotencyKey("harness-output")
    )

    evaluation_backend = Mock()
    evaluation_backend.evaluate = AsyncMock(
        return_value=evaluation_response(evaluation_request())
    )
    evaluator_adapter = CaseEvaluatorBoundaryAdapter(evaluation_backend, adapter_config())
    assert asyncio.run(evaluator_adapter.evaluate(evaluation_request())).scores

    scoring_source = scoring_input()
    result = scoring_source.results[0]
    run_store.save_result(result, idempotency_key=IdempotencyKey("harness-result"))
    decision = ScoringDecisionFactory().create(scoring_source)
    analysis_store.save_scoring_decision(
        decision, idempotency_key=IdempotencyKey("harness-scoring")
    )
    finalization = EvalRunFinalizationFactory().create(finalization_source)
    run_store.save_finalization(
        finalization, idempotency_key=IdempotencyKey("harness-finalization")
    )

    governance_client = Mock()
    evidence = governance_evidence()
    governance_client.record_evidence.return_value = evidence
    assert GovernanceEvidenceWriteAdapter(
        governance_client, adapter_config()
    ).record_evidence(evidence) == evidence

    attempt, receipt, submission, expected_finalization = evidence_records()
    assert expected_finalization == finalization
    evidence_store.save_evidence_submission_attempt(
        attempt, idempotency_key=IdempotencyKey("harness-evidence-attempt")
    )
    evidence_store.save_evidence_submission_receipt(
        receipt, idempotency_key=IdempotencyKey("harness-evidence-receipt")
    )
    evidence_store.save_evidence_submission(
        submission, idempotency_key=IdempotencyKey("harness-evidence-submission")
    )
    assert evidence_store.get_evidence_submission_for_run(submission.run_id) == submission
    assert execution_backend.execute_case.call_count == 1
    assert evaluation_backend.evaluate.await_count == 1
    assert governance_client.record_evidence.call_count == 1
