from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from synapse.intelligence_boundary.models import (
    DataClassification,
    InformationOwnership,
    OperatingProfile,
    ProcessingBoundary,
)
from synapse.private_evals.canonical import fingerprint
from synapse.private_evals.catalog import (
    ContentBinding,
    DatasetBindingRef,
    EvalCaseVersion,
    EvalCaseVersionRef,
    EvaluatorIdentity,
)
from synapse.private_evals.execution import (
    CaseExecutionRequest,
    CaseExecutionResponse,
    CaseExecutionStatus,
    ExecutionAttemptIdentity,
    ExecutionReasonCode,
    LogicalExecutionIdentity,
    ReplayDisposition,
    request_replay,
    response_replay,
    validate_execution_response,
    validate_request_against_manifest,
)
from synapse.private_evals.execution_contracts import EvalCaseExecutionPort
from synapse.private_evals.execution_errors import (
    AttemptSequenceInvalid,
    ExecutionAccountingIncomplete,
    ExecutionIdentityMismatch,
    ExecutionRecordInvalid,
    ExecutionRequestInvalid,
    ExecutionResponseMismatch,
    OutputReferenceMissing,
    RequestIdempotencyConflict,
    ResponseFingerprintMismatch,
    ResponseIntegrityConflict,
)
from synapse.private_evals.execution_policy import (
    RetryDecision,
    RetryDisposition,
    RetryPolicy,
    assess_retry,
)
from synapse.private_evals.execution_records import (
    ExecutionAccountingStatus,
    ExecutionAttemptRecord,
    LogicalExecutionProjectionStatus,
    PartialFailureSummary,
    assess_execution_accounting,
    attempt_record,
    logical_execution_projection,
)
from synapse.private_evals.runs import (
    ComponentKind,
    DecodingParameters,
    EnvironmentSnapshot,
    EvalRunManifest,
    ExecutionProtocol,
    ModelProviderSnapshot,
    ResourceUsage,
    RunProvenance,
    SecuritySnapshotRef,
    VersionedComponentRef,
)
from synapse.private_evals.states import (
    DefinitionStatus,
    DeterminismMode,
    InputKind,
    SideEffectPolicy,
)
from synapse.private_evals.store_models import IdempotencyKey
from synapse.private_evals.values import (
    ContentChecksum,
    DatasetBindingId,
    EvalCaseId,
    EvalRunId,
    EvalRunManifestId,
    EvalSuiteId,
    EvaluatorId,
    EvalVersion,
    Fingerprint,
    Revision,
    UtcTimestamp,
)

SHA_A = ContentChecksum("a" * 64)
SHA_B = ContentChecksum("b" * 64)
FP_A = Fingerprint("a" * 64)
FP_B = Fingerprint("b" * 64)
FP_C = Fingerprint("c" * 64)
FP_D = Fingerprint("d" * 64)
RUN_ID = EvalRunId("run-1")
SUITE_ID = EvalSuiteId("suite-1")
VERSION = EvalVersion("1.0.0")
NOW = UtcTimestamp("2026-07-18T12:00:00Z")
LATER = UtcTimestamp("2026-07-18T12:00:01Z")


def evaluator() -> EvaluatorIdentity:
    return EvaluatorIdentity(
        evaluator_id=EvaluatorId("evaluator-1"),
        version=VERSION,
        implementation_checksum=SHA_A,
        kind="exact_match",
        configuration_checksum=SHA_B,
    )


def case(**changes: object) -> EvalCaseVersion:
    content = ContentBinding(
        kind=InputKind.INLINE,
        classification=DataClassification.PUBLIC,
        inline_value="fixture used only outside the execution request",
    )
    return replace(
        EvalCaseVersion(
            suite_id=SUITE_ID,
            case_id=EvalCaseId("case-1"),
            version=VERSION,
            input=content,
            expected_outcome=content,
            evaluator=evaluator(),
            weight=Decimal("1"),
            tags=("core",),
            owner=InformationOwnership.PROJECT,
            classification=DataClassification.PUBLIC,
            timeout_seconds=Decimal("20"),
            side_effect_policy=SideEffectPolicy.NONE,
            required=True,
            critical=False,
            status=DefinitionStatus.FROZEN,
            checksum=SHA_A,
        ),
        **changes,
    )


def protocol() -> ExecutionProtocol:
    return ExecutionProtocol(
        determinism_mode=DeterminismMode.DETERMINISTIC,
        repetitions=2,
        concurrency=1,
        retry_count=2,
        logical_timeout_seconds=Decimal("60"),
        call_timeout_seconds=Decimal("30"),
        seeds=(41, 42),
        aggregation_protocol="mean-v1",
    )


SKILL = VersionedComponentRef(ComponentKind.SKILL, "skill-1", "1.0.0", SHA_A)
TOOL = VersionedComponentRef(ComponentKind.TOOL, "tool-1", "1.0.0", SHA_B)


def manifest(**changes: object) -> EvalRunManifest:
    security = SecuritySnapshotRef(
        operating_profile=OperatingProfile.LOCAL_SOVEREIGN,
        policy_references=("policy-1",),
        policy_checksums=(SHA_A,),
    )
    return replace(
        EvalRunManifest(
            manifest_id=EvalRunManifestId("manifest-1"),
            suite_id=SUITE_ID,
            suite_version=VERSION,
            suite_checksum=SHA_A,
            case_references=(case().reference,),
            dataset_binding=DatasetBindingRef(DatasetBindingId("dataset-1"), Revision(1), SHA_A),
            evaluator=evaluator(),
            subject_kind="model",
            source_fingerprint=FP_A,
            model_provider=ModelProviderSnapshot(
                provider_id="provider-1",
                processing_boundary=ProcessingBoundary.LOCAL_MODEL,
                model_id="model-1",
                model_version="2026-07",
                configuration_checksum=SHA_B,
                decoding=DecodingParameters(Decimal("0"), Decimal("1"), 100, seed=41),
            ),
            component_references=(TOOL, SKILL),
            security=security,
            execution=protocol(),
            environment=EnvironmentSnapshot("Windows", "x86_64", "3.12", "synapse-v3"),
            provenance=RunProvenance("actor-1", "project-1", "caller-checksum"),
            protocol_fingerprint=FP_A,
            subject_fingerprint=FP_B,
            run_fingerprint=FP_C,
            environment_fingerprint=FP_D,
            checksum=SHA_A,
        ),
        **changes,
    )


def logical(**changes: object) -> LogicalExecutionIdentity:
    changes.setdefault("fingerprint", None)
    return replace(
        LogicalExecutionIdentity(
            run_id=RUN_ID,
            case_reference=case().reference,
            repetition=1,
        ),
        **changes,
    )


def request(attempt: int = 1, **changes: object) -> CaseExecutionRequest:
    identity = changes.pop("logical_execution", logical())
    changes.setdefault("fingerprint", None)
    assert isinstance(identity, LogicalExecutionIdentity)
    logical_fingerprint = identity.fingerprint
    assert logical_fingerprint is not None
    current_manifest = manifest()
    return replace(
        CaseExecutionRequest(
            logical_execution=identity,
            attempt_identity=ExecutionAttemptIdentity(logical_fingerprint, attempt),
            manifest_id=EvalRunManifestId("manifest-1"),
            manifest_fingerprint=current_manifest.run_fingerprint,
            suite_id=SUITE_ID,
            suite_version=VERSION,
            dataset_binding=current_manifest.dataset_binding,
            input_asset_references=("asset-1", "asset-2"),
            expected_evaluator=evaluator(),
            model_provider_snapshot_reference="model-snapshot-1",
            model_provider_snapshot_fingerprint=fingerprint(current_manifest.model_provider),
            skill_references=(SKILL,),
            tool_references=(TOOL,),
            security_snapshot_reference="security-snapshot-1",
            security_snapshot_fingerprint=fingerprint(current_manifest.security),
            reauthorization_reference=None,
            canonical_egress_manifest_reference="egress-manifest-1",
            canonical_egress_manifest_fingerprint=FP_A,
            operating_profile=OperatingProfile.LOCAL_SOVEREIGN,
            timeout_seconds=Decimal("20"),
            seed=41,
            execution_protocol=protocol(),
            idempotency_key=IdempotencyKey("execution-key-1"),
            correlation_reference="correlation-1",
        ),
        **changes,
    )


def response(
    status: CaseExecutionStatus = CaseExecutionStatus.SUCCEEDED,
    *,
    target: CaseExecutionRequest | None = None,
    **changes: object,
) -> CaseExecutionResponse:
    target = target or request()
    changes.setdefault("fingerprint", None)
    successful = status is CaseExecutionStatus.SUCCEEDED
    reasons = {
        CaseExecutionStatus.SUCCEEDED: ExecutionReasonCode.COMPLETED,
        CaseExecutionStatus.INFRASTRUCTURE_FAILED: ExecutionReasonCode.INFRASTRUCTURE_UNAVAILABLE,
        CaseExecutionStatus.CANCELLED: ExecutionReasonCode.CANCELLED_BY_REQUEST,
        CaseExecutionStatus.POLICY_DENIED: ExecutionReasonCode.POLICY_NOT_AUTHORIZED,
        CaseExecutionStatus.INVALID: ExecutionReasonCode.RESPONSE_INVALID,
        CaseExecutionStatus.TIMED_OUT: ExecutionReasonCode.EXECUTION_TIMEOUT,
    }
    return replace(
        CaseExecutionResponse(
            logical_execution_reference=target.logical_execution.fingerprint,  # type: ignore[arg-type]
            attempt_reference=target.attempt_identity.fingerprint,  # type: ignore[arg-type]
            status=status,
            output_asset_reference="output-asset-1" if successful else None,
            result_checksum=SHA_A if successful else None,
            evaluator_artifact_reference="evaluator-artifact-1" if successful else None,
            usage_summary=ResourceUsage(duration_ms=100),
            started_at=NOW,
            finished_at=LATER,
            provider_execution_reference="provider-execution-1",
            provenance_reference="provenance-1",
            reason_codes=(reasons[status],),
        ),
        **changes,
    )


def retry_policy(**changes: object) -> RetryPolicy:
    return replace(
        RetryPolicy(
            maximum_attempts=3,
            retryable_statuses=(CaseExecutionStatus.INFRASTRUCTURE_FAILED,),
            retryable_reason_codes=(
                ExecutionReasonCode.INFRASTRUCTURE_UNAVAILABLE,
                ExecutionReasonCode.EXECUTION_TIMEOUT,
            ),
            retry_timed_out=True,
            retry_cancelled=False,
            backoff_reference="backoff-policy-1",
            preserve_deterministic_seed=True,
            provider_switch_allowed=False,
            security_reauthorization_required=True,
        ),
        **changes,
    )


def record(
    status: CaseExecutionStatus = CaseExecutionStatus.SUCCEEDED,
    *,
    target: CaseExecutionRequest | None = None,
) -> ExecutionAttemptRecord:
    target = target or request()
    return attempt_record(target, response(status, target=target))


def test_execution_port_has_one_structural_operation() -> None:
    assert EvalCaseExecutionPort.__abstractmethods__ == frozenset()
    assert [name for name in EvalCaseExecutionPort.__dict__ if not name.startswith("_")] == [
        "execute_case"
    ]


def test_valid_request_matches_manifest_and_contains_no_payload() -> None:
    item = request()
    validate_request_against_manifest(item, manifest(), case(), RUN_ID)
    representation = repr(item)
    assert "fixture used" not in representation
    assert "execution-key-1" not in representation


@pytest.mark.parametrize(
    "mutation",
    [
        {"manifest_id": EvalRunManifestId("other-manifest")},
        {"logical_execution": logical(run_id=EvalRunId("other-run"))},
        {
            "logical_execution": logical(
                case_reference=EvalCaseVersionRef(
                    SUITE_ID, EvalCaseId("other-case"), VERSION, SHA_A
                )
            )
        },
    ],
)
def test_request_rejects_run_manifest_and_case_mismatch(mutation: dict[str, object]) -> None:
    with pytest.raises(ExecutionIdentityMismatch):
        validate_request_against_manifest(request(**mutation), manifest(), case(), RUN_ID)


def test_invalid_repetition_and_attempt_are_rejected() -> None:
    with pytest.raises(ExecutionRequestInvalid):
        logical(repetition=0)
    with pytest.raises(ExecutionRequestInvalid):
        ExecutionAttemptIdentity(logical().fingerprint, 0)  # type: ignore[arg-type]
    with pytest.raises(ExecutionRequestInvalid):
        validate_request_against_manifest(
            request(logical_execution=logical(repetition=3)), manifest(), case(), RUN_ID
        )


def test_duplicate_sensitive_path_and_uri_references_are_rejected() -> None:
    with pytest.raises(ExecutionRequestInvalid):
        request(input_asset_references=("asset-1", "asset-1"))
    for reference in ("secret-token", "C:\\private\\file", "https://private/resource"):
        with pytest.raises(ExecutionRequestInvalid):
            request(input_asset_references=(reference,))


def test_request_fingerprint_is_deterministic_and_reference_order_is_canonical() -> None:
    first = request(input_asset_references=("asset-1", "asset-2"))
    second = request(input_asset_references=("asset-2", "asset-1"))
    assert first.fingerprint == second.fingerprint
    assert request(timeout_seconds=Decimal("20.0")).fingerprint == first.fingerprint


def test_logical_and_attempt_identity_have_distinct_semantics() -> None:
    first = logical()
    assert first == logical()
    assert ExecutionAttemptIdentity(first.fingerprint, 1).fingerprint != ExecutionAttemptIdentity(  # type: ignore[arg-type]
        first.fingerprint, 2  # type: ignore[arg-type]
    ).fingerprint
    assert logical(case_reference=replace(case().reference, checksum=SHA_B)).fingerprint != first.fingerprint
    assert logical(run_id=EvalRunId("run-2")).fingerprint != first.fingerprint
    assert logical(repetition=2).fingerprint != first.fingerprint


def test_manifest_and_security_change_request_not_logical_identity() -> None:
    identity = logical()
    assert request(logical_execution=identity, manifest_fingerprint=FP_D).logical_execution == identity
    assert request(
        logical_execution=identity, security_snapshot_fingerprint=FP_D
    ).logical_execution == identity
    assert request(manifest_fingerprint=FP_D).fingerprint != request().fingerprint
    assert request(security_snapshot_fingerprint=FP_D).fingerprint != request().fingerprint
    with pytest.raises(ExecutionIdentityMismatch):
        validate_request_against_manifest(
            request(security_snapshot_fingerprint=FP_D), manifest(), case(), RUN_ID
        )


def test_idempotency_key_and_correlation_do_not_contaminate_request_fingerprint() -> None:
    first = request()
    another_key = request(idempotency_key=IdempotencyKey("execution-key-2"))
    another_correlation = request(correlation_reference="correlation-2")
    assert first.fingerprint == another_key.fingerprint == another_correlation.fingerprint
    assert request_replay(first, another_key) is ReplayDisposition.NEW


@pytest.mark.parametrize("status", list(CaseExecutionStatus))
def test_all_typed_responses_are_valid_and_correspond(status: CaseExecutionStatus) -> None:
    target = request()
    validate_execution_response(target, response(status, target=target))


def test_success_requires_output_checksum_and_evaluator_artifact() -> None:
    with pytest.raises(OutputReferenceMissing):
        response(output_asset_reference=None)
    with pytest.raises(OutputReferenceMissing):
        response(result_checksum=None)
    with pytest.raises(OutputReferenceMissing):
        response(evaluator_artifact_reference=None)


def test_failure_cannot_expose_final_output() -> None:
    with pytest.raises(ExecutionResponseMismatch):
        response(CaseExecutionStatus.CANCELLED, output_asset_reference="output-1")


def test_response_from_another_execution_or_attempt_is_rejected() -> None:
    target = request()
    with pytest.raises(ExecutionResponseMismatch):
        validate_execution_response(
            target, response(target=target, logical_execution_reference=FP_D)
        )
    with pytest.raises(ExecutionResponseMismatch):
        validate_execution_response(target, response(target=target, attempt_reference=FP_D))


def test_response_tampering_and_invalid_timestamps_are_rejected() -> None:
    with pytest.raises(ResponseFingerprintMismatch):
        response(fingerprint=FP_D)
    with pytest.raises(ExecutionResponseMismatch):
        response(started_at=LATER, finished_at=NOW)


def unsafe_response(**changes: object) -> CaseExecutionResponse:
    source = response()
    item = object.__new__(CaseExecutionResponse)
    for name in source.__dataclass_fields__:
        object.__setattr__(item, name, changes.get(name, getattr(source, name)))
    return item


def test_manual_malformed_response_is_rejected_independently_of_constructor() -> None:
    target = request()
    with pytest.raises(ExecutionResponseMismatch):
        validate_execution_response(
            target,
            unsafe_response(
                status=CaseExecutionStatus.CANCELLED,
                reason_codes=(ExecutionReasonCode.CANCELLED_BY_REQUEST,),
            ),
        )
    with pytest.raises(ResponseFingerprintMismatch):
        validate_execution_response(target, unsafe_response(fingerprint=FP_D))


def test_attempt_fact_and_logical_projection_are_immutable_and_deterministic() -> None:
    attempt = record()
    assert attempt == record()
    projection = logical_execution_projection(logical(), (attempt,))
    assert projection.status is LogicalExecutionProjectionStatus.SUCCEEDED
    assert projection == logical_execution_projection(logical(), (attempt,))
    assert "output-asset-1" not in repr(attempt)
    assert not hasattr(attempt, "retry_disposition")


def test_identity_record_projection_and_summary_tampering_are_independent() -> None:
    with pytest.raises(ExecutionIdentityMismatch):
        replace(logical(), fingerprint=FP_D)
    attempt = record()
    with pytest.raises(ExecutionRecordInvalid):
        replace(attempt, checksum=SHA_B)
    projection = logical_execution_projection(logical(), (attempt,))
    with pytest.raises(ExecutionRecordInvalid):
        replace(projection, fingerprint=FP_D)
    with pytest.raises(ExecutionAccountingIncomplete):
        PartialFailureSummary(1, 1, 1, 0, 0, 0, 0, 0, 0, 0)


def test_logical_projection_rejects_duplicate_out_of_order_and_multiple_successes() -> None:
    first = record()
    second_request = request(2)
    second = record(target=second_request)
    with pytest.raises(AttemptSequenceInvalid):
        logical_execution_projection(logical(), (second,))
    with pytest.raises(AttemptSequenceInvalid):
        logical_execution_projection(logical(), (first, first))
    with pytest.raises(ExecutionRecordInvalid):
        logical_execution_projection(logical(), (first, second))


def test_timeout_then_success_reconstructs_one_successful_logical_projection() -> None:
    first_request = request()
    second_request = request(2)
    timeout = record(CaseExecutionStatus.TIMED_OUT, target=first_request)
    success = record(target=second_request)
    projection = logical_execution_projection(logical(), (timeout, success))
    assert projection.status is LogicalExecutionProjectionStatus.SUCCEEDED
    assert len(projection.attempts) == 2


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (CaseExecutionStatus.SUCCEEDED, RetryDisposition.TERMINAL),
        (CaseExecutionStatus.POLICY_DENIED, RetryDisposition.TERMINAL),
        (CaseExecutionStatus.INVALID, RetryDisposition.TERMINAL),
        (CaseExecutionStatus.INFRASTRUCTURE_FAILED, RetryDisposition.RETRY_ALLOWED),
        (CaseExecutionStatus.TIMED_OUT, RetryDisposition.RETRY_ALLOWED),
        (CaseExecutionStatus.CANCELLED, RetryDisposition.TERMINAL),
    ],
)
def test_retry_status_rules(status: CaseExecutionStatus, expected: RetryDisposition) -> None:
    target = request()
    decision = assess_retry(target, response(status, target=target), None, retry_policy())
    assert decision.disposition is expected


def test_retry_exhaustion_cancellation_configuration_and_sequence() -> None:
    third = request(3)
    assert assess_retry(
        third,
        response(CaseExecutionStatus.INFRASTRUCTURE_FAILED, target=third),
        None,
        retry_policy(),
    ).disposition is RetryDisposition.RETRY_EXHAUSTED
    cancelled = request()
    assert assess_retry(
        cancelled,
        response(CaseExecutionStatus.CANCELLED, target=cancelled),
        None,
        retry_policy(retry_cancelled=True),
    ).disposition is RetryDisposition.TERMINAL
    cancellation_policy = retry_policy(
        retry_cancelled=True,
        retryable_reason_codes=(ExecutionReasonCode.CANCELLED_BY_REQUEST,),
    )
    assert assess_retry(
        cancelled,
        response(CaseExecutionStatus.CANCELLED, target=cancelled),
        None,
        cancellation_policy,
    ).retry_allowed
    assert assess_retry(
        request(),
        response(CaseExecutionStatus.INFRASTRUCTURE_FAILED),
        request(3),
        retry_policy(),
    ).disposition is RetryDisposition.INVALID_RETRY_REQUEST


def test_provider_switch_and_security_reauthorization_preserve_semantics() -> None:
    first = request()
    provider_change = request(2, model_provider_snapshot_reference="model-snapshot-2")
    assert assess_retry(
        first,
        response(CaseExecutionStatus.INFRASTRUCTURE_FAILED, target=first),
        provider_change,
        retry_policy(),
    ).disposition is RetryDisposition.PROVIDER_CHANGE_PROHIBITED
    renewed_security = request(2, security_snapshot_reference="security-snapshot-2")
    assert assess_retry(
        first,
        response(CaseExecutionStatus.INFRASTRUCTURE_FAILED, target=first),
        renewed_security,
        retry_policy(),
    ).disposition is RetryDisposition.REAUTHORIZATION_REQUIRED
    authorized = request(
        2,
        security_snapshot_reference="security-snapshot-2",
        reauthorization_reference="reauth-ref-2",
    )
    assert assess_retry(
        first,
        response(CaseExecutionStatus.INFRASTRUCTURE_FAILED, target=first),
        authorized,
        retry_policy(),
    ).disposition is RetryDisposition.RETRY_ALLOWED
    semantic_security_change = request(2, security_snapshot_fingerprint=FP_D)
    assert assess_retry(
        first,
        response(CaseExecutionStatus.INFRASTRUCTURE_FAILED, target=first),
        semantic_security_change,
        retry_policy(),
    ).disposition is RetryDisposition.INVALID_RETRY_REQUEST
    renewed_egress = request(
        2,
        canonical_egress_manifest_reference="egress-manifest-2",
        reauthorization_reference="reauth-ref-2",
    )
    assert assess_retry(
        first,
        response(CaseExecutionStatus.INFRASTRUCTURE_FAILED, target=first),
        renewed_egress,
        retry_policy(),
    ).disposition is RetryDisposition.RETRY_ALLOWED
    changed_egress = request(2, canonical_egress_manifest_fingerprint=FP_D)
    assert assess_retry(
        first,
        response(CaseExecutionStatus.INFRASTRUCTURE_FAILED, target=first),
        changed_egress,
        retry_policy(),
    ).disposition is RetryDisposition.INVALID_RETRY_REQUEST
    provider_semantic_change = request(2, model_provider_snapshot_fingerprint=FP_D)
    assert assess_retry(
        first,
        response(CaseExecutionStatus.INFRASTRUCTURE_FAILED, target=first),
        provider_semantic_change,
        retry_policy(provider_switch_allowed=True),
    ).disposition is RetryDisposition.INVALID_RETRY_REQUEST


def test_retry_rejects_timeout_or_configuration_drift_and_requires_reason_policy() -> None:
    first = request()
    changed_timeout = request(2, timeout_seconds=Decimal("25"))
    assert assess_retry(
        first,
        response(CaseExecutionStatus.INFRASTRUCTURE_FAILED, target=first),
        changed_timeout,
        retry_policy(),
    ).disposition is RetryDisposition.INVALID_RETRY_REQUEST
    no_reason_policy = retry_policy(retryable_reason_codes=())
    assert assess_retry(
        first,
        response(CaseExecutionStatus.INFRASTRUCTURE_FAILED, target=first),
        None,
        no_reason_policy,
    ).disposition is RetryDisposition.TERMINAL


def test_request_and_response_replay_detect_conflicts_without_a_registry() -> None:
    first = request()
    assert request_replay(first, request()) is ReplayDisposition.SAFE_REPLAY
    with pytest.raises(RequestIdempotencyConflict):
        request_replay(first, request(timeout_seconds=Decimal("19")))
    first_response = response(target=first)
    assert response_replay(first_response, response(target=first)) is ReplayDisposition.SAFE_REPLAY
    with pytest.raises(ResponseIntegrityConflict):
        response_replay(first_response, response(target=first, finished_at=UtcTimestamp("2026-07-18T12:00:02Z")))


def retry_decision_for(
    target: CaseExecutionRequest,
    status: CaseExecutionStatus,
    policy: RetryPolicy | None = None,
) -> RetryDecision:
    return assess_retry(target, response(status, target=target), None, policy or retry_policy())


def test_summary_counts_logical_executions_not_attempts() -> None:
    success_identity = logical()
    timeout_request = request()
    success_request = request(2)
    timeout_then_success = logical_execution_projection(
        success_identity,
        (
            record(CaseExecutionStatus.TIMED_OUT, target=timeout_request),
            record(target=success_request),
        ),
    )
    exhausted_identity = logical(run_id=EvalRunId("run-exhausted"))
    exhausted_request = request(3, logical_execution=exhausted_identity)
    exhausted = logical_execution_projection(
        exhausted_identity,
        (record(CaseExecutionStatus.INFRASTRUCTURE_FAILED, target=request(logical_execution=exhausted_identity)),
         record(CaseExecutionStatus.INFRASTRUCTURE_FAILED, target=request(2, logical_execution=exhausted_identity)),
         record(CaseExecutionStatus.INFRASTRUCTURE_FAILED, target=exhausted_request)),
    )
    cancelled_identity = logical(run_id=EvalRunId("run-cancelled"))
    cancelled = logical_execution_projection(
        cancelled_identity,
        (record(CaseExecutionStatus.CANCELLED, target=request(logical_execution=cancelled_identity)),),
    )
    policy_identity = logical(run_id=EvalRunId("run-policy"))
    policy_projection = logical_execution_projection(
        policy_identity,
        (record(CaseExecutionStatus.POLICY_DENIED, target=request(logical_execution=policy_identity)),),
    )
    missing_identity = logical(run_id=EvalRunId("run-missing"))
    exhausted_decision = retry_decision_for(
        exhausted_request, CaseExecutionStatus.INFRASTRUCTURE_FAILED
    )
    accounting = assess_execution_accounting(
        (
            success_identity,
            exhausted_identity,
            cancelled_identity,
            policy_identity,
            missing_identity,
        ),
        (timeout_then_success, exhausted, cancelled, policy_projection),
        (exhausted_decision,),
    )
    assert accounting.status is ExecutionAccountingStatus.INCOMPLETE
    assert accounting.summary.total_expected == 5
    assert accounting.summary.succeeded == 1
    assert accounting.summary.infrastructure_failed == 1
    assert accounting.summary.cancelled == 1
    assert accounting.summary.policy_denied == 1
    assert accounting.summary.pending == 1
    assert accounting.summary.exhausted == 1


def test_accounting_rejects_duplicate_identity_and_tampered_retry_decision() -> None:
    identity = logical()
    failed_request = request()
    failed = logical_execution_projection(
        identity,
        (record(CaseExecutionStatus.INFRASTRUCTURE_FAILED, target=failed_request),),
    )
    decision = retry_decision_for(failed_request, CaseExecutionStatus.INFRASTRUCTURE_FAILED)
    tampered = replace(decision, response_fingerprint=FP_D)
    with pytest.raises(ExecutionAccountingIncomplete):
        assess_execution_accounting((identity,), (failed,), (tampered,))
    with pytest.raises(ExecutionAccountingIncomplete):
        assess_execution_accounting((identity, identity), (), ())
    with pytest.raises(ExecutionAccountingIncomplete):
        assess_execution_accounting((identity,), (failed, failed), ())
