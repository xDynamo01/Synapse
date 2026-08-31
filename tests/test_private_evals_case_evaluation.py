from __future__ import annotations

import inspect
from dataclasses import FrozenInstanceError, replace
from decimal import Decimal

import pytest

from synapse.private_evals.canonical import content_checksum, fingerprint
from synapse.private_evals.case_evaluation import (
    CaseEvaluationReasonCode,
    CaseEvaluationRequest,
    CaseEvaluationResponse,
    CaseEvaluationStatus,
    EvalResultCreationInput,
    EvalResultFactory,
    EvalResultService,
    EvaluationEventIdentity,
    EvaluatorScore,
    ExpectedMetricDefinition,
    case_result_fingerprint,
    evaluation_request_fingerprint,
    project_scoring_observation,
    validate_eval_result,
)
from synapse.private_evals.case_evaluation_contracts import EvalCaseEvaluatorPort
from synapse.private_evals.case_evaluation_errors import (
    CaseResultAlreadyExists,
    CaseResultFingerprintMismatch,
    CaseResultIdempotencyConflict,
    CaseResultPersistenceInvalid,
    CaseResultPersistenceNotFound,
    CaseResultPersistenceUnavailable,
    DuplicateEvaluationMetric,
    EvaluationCorrespondenceMismatch,
    EvaluationMetricMissing,
    EvaluationNotSuccessful,
    EvaluationRequestInvalid,
    EvaluationScoreInvalid,
    ScoreKindMismatch,
    ScoreScaleMismatch,
    UnexpectedEvaluationMetric,
)
from synapse.private_evals.result_materialization import MaterializedOutputFactory
from synapse.private_evals.runs import ResourceUsage
from synapse.private_evals.scoring import (
    AggregationMethod,
    FailureBudget,
    FailureBudgetUnit,
    ScoreThreshold,
    ScoringProtocol,
    ScoringTarget,
    ThresholdOperator,
    ThresholdScope,
)
from synapse.private_evals.scoring_errors import InvalidScoringInput
from synapse.private_evals.states import (
    DeterminismMode,
    ResultStatus,
    ScoreKind,
    ScoreStatus,
    Verdict,
)
from synapse.private_evals.store_errors import (
    EvalDuplicateRecord,
    EvalIdempotencyConflict,
    EvalIntegrityConflict,
    EvalInvalidStoreQuery,
    EvalRecordNotFound,
    EvalStoreUnavailable,
)
from synapse.private_evals.store_models import IdempotencyKey, StoreWriteOutcome, WriteDisposition
from synapse.private_evals.values import (
    ContentChecksum,
    EvalResultId,
    Revision,
    UtcTimestamp,
)
from test_private_evals_execution import FP_D, RUN_ID, case, manifest
from test_private_evals_result_materialization import materialization

NOW = UtcTimestamp("2026-07-18T18:00:00Z")
LATER = UtcTimestamp("2026-07-18T18:00:01Z")
FACTORY = EvalResultFactory()


def metric(
    metric_id: str = "quality",
    *,
    kind: ScoreKind = ScoreKind.NUMERIC,
    minimum: str = "0",
    maximum: str = "1",
    confidence_method: str | None = None,
) -> ExpectedMetricDefinition:
    return ExpectedMetricDefinition(
        metric_id,
        kind,
        Decimal(minimum),
        Decimal(maximum),
        confidence_method,
    )


def protocol_for(
    definitions: tuple[ExpectedMetricDefinition, ...],
    *,
    threshold: str = "0.8",
) -> ScoringProtocol:
    case_model = case()
    if len(definitions) != 1:
        raise ValueError("Slice 5 permits exactly one metric target per case")
    definition = definitions[0]
    targets = (
        ScoringTarget(
            case_model.reference,
            definition.metric_id,
            case_model.evaluator,
            case_model.weight,
            case_model.required,
            case_model.critical,
        ),
    )
    thresholds = (
        ScoreThreshold(
            ThresholdScope.CASE,
            ThresholdOperator.AT_LEAST,
            lower=Decimal(threshold),
            metric_id=definition.metric_id,
            case_reference=case_model.reference,
        ),
    )
    return ScoringProtocol(
        RUN_ID,
        case_model.suite_id,
        case_model.version,
        targets,
        2,
        1,
        DeterminismMode.DETERMINISTIC,
        AggregationMethod.ARITHMETIC_MEAN,
        thresholds,
        FailureBudget(FailureBudgetUnit.COUNT, count_limit=0),
    )


def materialized_output(**changes: object):
    source = materialization()
    record = MaterializedOutputFactory().create(source)
    return replace(record, **changes) if changes else record


def evaluation_request(
    definitions: tuple[ExpectedMetricDefinition, ...] = (metric(),),
    **changes: object,
) -> CaseEvaluationRequest:
    output = changes.pop("materialized") if "materialized" in changes else materialized_output()
    protocol = changes.pop("protocol") if "protocol" in changes else protocol_for(definitions)
    manifest_model = changes.pop("manifest") if "manifest" in changes else manifest()
    event = changes.pop(
        "event_identity",
        EvaluationEventIdentity(
            output.run_id,
            output.case_reference,
            output.repetition,
            output.materialization_fingerprint,
            case().evaluator,
            fingerprint(protocol),
        ),
    )
    return replace(
        CaseEvaluationRequest(
            output.run_id,
            manifest_model.manifest_id,
            fingerprint(manifest_model),
            manifest_model.suite_id,
            manifest_model.suite_version,
            output.case_reference,
            output.repetition,
            output.output_id,
            output.materialization_fingerprint,
            output.checksum,
            output.output_asset_reference,
            case().evaluator,
            definitions[0],
            "scoring-protocol-1",
            fingerprint(protocol),
            "security-snapshot-1",
            fingerprint(manifest_model.security),
            (),
            Decimal("20"),
            41,
            IdempotencyKey("evaluation-key-1"),
            "correlation-1",
            event,
        ),
        **changes,
    )


def score(
    definition: ExpectedMetricDefinition = metric(),
    value: str = "0.9",
    *,
    status: ScoreStatus = ScoreStatus.VALID,
    evaluator_override=None,
    confidence: Decimal | None = None,
    confidence_method: str | None = None,
) -> EvaluatorScore:
    raw = Decimal(value) if status is ScoreStatus.VALID else None
    semantic = (definition.metric_id, value, status.value)
    return EvaluatorScore(
        definition.metric_id,
        evaluator_override or case().evaluator,
        definition.kind,
        status,
        raw,
        definition.scale_minimum,
        definition.scale_maximum,
        1 if status is ScoreStatus.VALID else 0,
        confidence,
        None,
        confidence_method,
        None if status is ScoreStatus.VALID else "metric_unavailable",
        content_checksum(semantic),
    )


def evaluation_response(
    request_model: CaseEvaluationRequest | None = None,
    *,
    status: CaseEvaluationStatus = CaseEvaluationStatus.SUCCEEDED,
    scores: tuple[EvaluatorScore, ...] | None = None,
    **changes: object,
) -> CaseEvaluationResponse:
    request_model = request_model or evaluation_request()
    succeeded = status is CaseEvaluationStatus.SUCCEEDED
    reasons = {
        CaseEvaluationStatus.SUCCEEDED: CaseEvaluationReasonCode.COMPLETED,
        CaseEvaluationStatus.INFRASTRUCTURE_FAILED: CaseEvaluationReasonCode.INFRASTRUCTURE_UNAVAILABLE,
        CaseEvaluationStatus.TIMED_OUT: CaseEvaluationReasonCode.EVALUATION_TIMEOUT,
        CaseEvaluationStatus.CANCELLED: CaseEvaluationReasonCode.CANCELLED_BY_REQUEST,
        CaseEvaluationStatus.POLICY_DENIED: CaseEvaluationReasonCode.POLICY_NOT_AUTHORIZED,
        CaseEvaluationStatus.INVALID: CaseEvaluationReasonCode.RESPONSE_INVALID,
    }
    default_scores = scores if scores is not None else (score(request_model.expected_metric),)
    return replace(
        CaseEvaluationResponse(
            request_model.event_identity,
            status,
            request_model.evaluator,
            default_scores if succeeded else (scores or ()),
            "evaluation-artifact-1" if succeeded else None,
            "evaluation-provenance-1" if succeeded else None,
            NOW,
            LATER,
            ResourceUsage(10),
            (reasons[status],),
        ),
        **changes,
    )


def creation_input(
    definitions: tuple[ExpectedMetricDefinition, ...] = (metric(),),
    **changes: object,
) -> EvalResultCreationInput:
    output = changes.pop("materialized") if "materialized" in changes else materialized_output()
    protocol = changes.pop("protocol") if "protocol" in changes else protocol_for(definitions)
    request_model = changes.pop(
        "request", evaluation_request(definitions, materialized=output, protocol=protocol)
    )
    response_model = (
        changes.pop("response")
        if "response" in changes
        else evaluation_response(request_model)
    )
    return replace(
        EvalResultCreationInput(
            output,
            request_model,
            response_model,
            manifest(),
            case(),
            protocol,
            EvalResultId("result-1"),
            "private-evals",
            "11.0.0",
            NOW,
            IdempotencyKey("result-key-1"),
        ),
        **changes,
    )


def unsafe_copy(source: object, **changes: object):
    item = object.__new__(type(source))
    for name in source.__dataclass_fields__:  # type: ignore[attr-defined]
        object.__setattr__(item, name, changes.get(name, getattr(source, name)))
    return item


def test_port_has_exactly_one_public_operation() -> None:
    methods = {
        name
        for name, member in inspect.getmembers(EvalCaseEvaluatorPort, inspect.isfunction)
        if not name.startswith("_")
    }
    assert methods == {"evaluate"}


def test_request_is_reference_only_frozen_and_deterministic() -> None:
    request_model = evaluation_request()
    assert request_model.fingerprint == evaluation_request_fingerprint(request_model)
    assert "output-asset-1" not in repr(request_model)
    assert not {"output", "prompt", "payload", "path", "credentials"} & request_model.__dataclass_fields__.keys()
    with pytest.raises(FrozenInstanceError):
        request_model.seed = 9  # type: ignore[misc]


def test_request_identity_excludes_idempotency_and_correlation() -> None:
    definitions = (metric("quality"),)
    protocol = protocol_for(definitions)
    first = evaluation_request(definitions, protocol=protocol)
    second = evaluation_request(
        definitions,
        protocol=protocol,
        idempotency_key=IdempotencyKey("evaluation-key-2"),
        correlation_reference="correlation-2",
    )
    assert first.fingerprint == second.fingerprint


def test_event_identity_changes_for_output_evaluator_protocol_and_case() -> None:
    request_model = evaluation_request()
    base = request_model.event_identity.fingerprint
    assert base != replace(
        request_model.event_identity,
        materialized_output_fingerprint=FP_D,
        fingerprint=None,
    ).fingerprint
    changed_evaluator = replace(case().evaluator, implementation_checksum=ContentChecksum("c" * 64))
    assert base != replace(request_model.event_identity, evaluator=changed_evaluator, fingerprint=None).fingerprint
    assert base != replace(request_model.event_identity, scoring_protocol_fingerprint=FP_D, fingerprint=None).fingerprint


def test_request_rejects_missing_reference_and_tampered_fingerprint() -> None:
    with pytest.raises(EvaluationRequestInvalid):
        evaluation_request(output_asset_reference="")
    with pytest.raises(EvaluationRequestInvalid):
        evaluation_request(fingerprint=FP_D)


@pytest.mark.parametrize(
    "status",
    [
        CaseEvaluationStatus.INFRASTRUCTURE_FAILED,
        CaseEvaluationStatus.TIMED_OUT,
        CaseEvaluationStatus.CANCELLED,
        CaseEvaluationStatus.POLICY_DENIED,
        CaseEvaluationStatus.INVALID,
    ],
)
def test_typed_failure_responses_contain_no_scores_or_artifact(status: CaseEvaluationStatus) -> None:
    response = evaluation_response(status=status)
    assert response.status is status and response.scores == ()
    assert response.evaluator_artifact_reference is None
    assert response.provenance_reference is None


def test_response_rejects_success_without_scores_failure_with_scores_and_missing_refs() -> None:
    with pytest.raises(EvaluationMetricMissing):
        evaluation_response(scores=())
    with pytest.raises(EvaluationRequestInvalid):
        evaluation_response(status=CaseEvaluationStatus.TIMED_OUT, scores=(score(),))
    with pytest.raises(EvaluationRequestInvalid):
        evaluation_response(
            status=CaseEvaluationStatus.TIMED_OUT,
            provenance_reference="final-provenance-not-allowed",
        )
    with pytest.raises(EvaluationRequestInvalid):
        evaluation_response(evaluator_artifact_reference=None)
    with pytest.raises(EvaluationRequestInvalid):
        evaluation_response(provenance_reference=None)


def test_response_rejects_invalid_timestamps_and_tampered_fingerprint() -> None:
    with pytest.raises(EvaluationRequestInvalid):
        evaluation_response(started_at=LATER, finished_at=NOW)
    with pytest.raises(CaseResultFingerprintMismatch):
        evaluation_response(fingerprint=FP_D)
    with pytest.raises(EvaluationRequestInvalid):
        evaluation_response(
            reason_codes=(CaseEvaluationReasonCode.RESPONSE_INVALID,),
        )


def test_evaluator_response_contains_facts_not_protocol_authority() -> None:
    score_fields = EvaluatorScore.__dataclass_fields__.keys()
    response_fields = CaseEvaluationResponse.__dataclass_fields__.keys()
    forbidden = {"weight", "required", "critical", "normalized_value", "threshold"}
    assert not forbidden & score_fields
    assert not forbidden & response_fields
    assert "case_thresholds" not in CaseEvaluationRequest.__dataclass_fields__


def test_eval_result_has_no_duplicated_evaluation_metadata_or_security_snapshot() -> None:
    result = FACTORY.create(creation_input())
    assert "evaluation" not in result.__dataclass_fields__
    assert "security_snapshot" not in result.__dataclass_fields__
    assert result.evaluator_artifact_reference == "evaluation-artifact-1"
    assert result.provenance_reference == "evaluation-provenance-1"


def test_factory_rejects_event_identity_that_does_not_match_request_dimensions() -> None:
    source = creation_input()
    changed_event = replace(
        source.request.event_identity,
        materialized_output_fingerprint=FP_D,
        fingerprint=None,
    )
    changed_request = replace(source.request, event_identity=changed_event, fingerprint=None)
    changed_response = evaluation_response(changed_request)
    with pytest.raises(EvaluationCorrespondenceMismatch):
        FACTORY.create(replace(source, request=changed_request, response=changed_response))


def test_one_metric_per_case_is_frozen_and_multiple_targets_are_rejected() -> None:
    request_model = evaluation_request()
    response = evaluation_response(request_model)
    assert tuple(item.metric_id for item in response.scores) == ("quality",)
    first = protocol_for((metric(),)).targets[0]
    with pytest.raises(InvalidScoringInput):
        replace(protocol_for((metric(),)), targets=(first, replace(first, metric_id="latency")))


def test_score_validation_rejects_missing_extra_duplicate_kind_scale_and_confidence() -> None:
    request_model = evaluation_request()
    with pytest.raises(EvaluationMetricMissing):
        evaluation_response(request_model, scores=())
    with pytest.raises(UnexpectedEvaluationMetric):
        FACTORY.create(creation_input(response=evaluation_response(request_model, scores=(score(metric("extra")),))))
    with pytest.raises(DuplicateEvaluationMetric):
        evaluation_response(request_model, scores=(score(), score()))
    binary = metric(kind=ScoreKind.BINARY)
    with pytest.raises(ScoreKindMismatch):
        FACTORY.create(creation_input((binary,), response=evaluation_response(evaluation_request((binary,)), scores=(score(metric()),))))
    wrong_scale = unsafe_copy(score(), scale_maximum=Decimal("2"))
    with pytest.raises(ScoreScaleMismatch):
        FACTORY.create(creation_input(response=evaluation_response(request_model, scores=(wrong_scale,))))
    confidence_definition = metric(confidence_method="wilson")
    wrong_confidence = score(
        confidence_definition,
        confidence=Decimal("0.9"),
        confidence_method="bootstrap",
    )
    with pytest.raises(EvaluationScoreInvalid):
        request = evaluation_request((confidence_definition,))
        FACTORY.create(creation_input((confidence_definition,), request=request, response=evaluation_response(request, scores=(wrong_confidence,))))


def test_decimal_equivalence_and_threshold_boundary_are_canonical() -> None:
    definition = metric()
    request_model = evaluation_request((definition,))
    boundary = score(definition, "0.8")
    result = FACTORY.create(creation_input((definition,), request=request_model, response=evaluation_response(request_model, scores=(boundary,))))
    assert result.verdict is Verdict.PASSED


def test_case_verdict_passed_failed_invalid_and_inconclusive() -> None:
    request_model = evaluation_request()
    for value, status, expected in (
        ("0.9", ScoreStatus.VALID, Verdict.PASSED),
        ("0.7", ScoreStatus.VALID, Verdict.FAILED),
        ("0.9", ScoreStatus.INVALID, Verdict.INVALID),
        ("0.9", ScoreStatus.MISSING, Verdict.INCONCLUSIVE),
    ):
        response = evaluation_response(request_model, scores=(score(value=value, status=status),))
        assert FACTORY.create(creation_input(request=request_model, response=response)).verdict is expected


def test_case_verdict_handles_optional_missing_absent_threshold_confidence_and_direction() -> None:
    definition = metric()
    optional_case = replace(case(), required=False, critical=False)
    base_protocol = protocol_for((definition,))
    optional_target = replace(base_protocol.targets[0], required=False, critical=False)
    optional_protocol = replace(base_protocol, targets=(optional_target,))
    request_model = evaluation_request((definition,), protocol=optional_protocol)
    missing = evaluation_response(
        request_model,
        scores=(score(status=ScoreStatus.MISSING),),
    )
    optional_source = creation_input(
        (definition,),
        case=optional_case,
        protocol=optional_protocol,
        request=request_model,
        response=missing,
    )
    assert FACTORY.create(optional_source).verdict is Verdict.INCONCLUSIVE

    no_threshold_protocol = replace(base_protocol, thresholds=())
    no_threshold_request = evaluation_request((definition,), protocol=no_threshold_protocol)
    no_confidence = evaluation_response(no_threshold_request, scores=(score(value="0.1"),))
    assert FACTORY.create(
        creation_input(
            (definition,),
            protocol=no_threshold_protocol,
            request=no_threshold_request,
            response=no_confidence,
        )
    ).verdict is Verdict.PASSED

    upper = ScoreThreshold(
        ThresholdScope.CASE,
        ThresholdOperator.AT_MOST,
        upper=Decimal("0.2"),
        metric_id="quality",
        case_reference=case().reference,
    )
    inverse_protocol = replace(base_protocol, thresholds=(upper,))
    inverse_request = evaluation_request((definition,), protocol=inverse_protocol)
    inverse_response = evaluation_response(inverse_request, scores=(score(value="0.1"),))
    assert FACTORY.create(
        creation_input(
            (definition,),
            protocol=inverse_protocol,
            request=inverse_request,
            response=inverse_response,
        )
    ).verdict is Verdict.PASSED


def test_case_verdict_ignores_other_cases_and_global_failure_budget() -> None:
    strict_global = replace(
        protocol_for((metric(),)),
        failure_budget=FailureBudget(FailureBudgetUnit.COUNT, count_limit=999),
    )
    assert strict_global.failure_budget.count_limit == 999
    assert FACTORY.create(creation_input()).verdict is Verdict.PASSED


def test_factory_creates_canonical_immutable_eval_result() -> None:
    source = creation_input()
    result = FACTORY.create(source)
    assert result.status is ResultStatus.VALID
    assert result.verdict is Verdict.PASSED and len(result.scores) == 1
    assert result.result_fingerprint == case_result_fingerprint(source, result.verdict)
    assert result.output_asset_id == source.materialized.output_asset_reference
    with pytest.raises(FrozenInstanceError):
        result.verdict = Verdict.FAILED  # type: ignore[misc]


@pytest.mark.parametrize(
    "change",
    ["materialized", "run", "case", "repetition", "evaluator", "protocol", "provenance"],
)
def test_factory_rejects_correspondence_divergence(change: str) -> None:
    source = creation_input()
    if change == "materialized":
        request_model = replace(source.request, materialized_output_fingerprint=FP_D, fingerprint=None)
        changed = replace(source, request=request_model)
    elif change == "run":
        changed = replace(source, materialized=replace(source.materialized, run_id=replace(RUN_ID, value="other-run")))
    elif change == "case":
        changed = replace(source, case=replace(source.case, checksum=ContentChecksum("d" * 64)))
    elif change == "repetition":
        changed = replace(source, materialized=replace(source.materialized, repetition=2))
    elif change == "evaluator":
        request_model = replace(source.request, evaluator=replace(source.request.evaluator, kind="other"), fingerprint=None)
        changed = replace(source, request=request_model)
    elif change == "protocol":
        request_model = replace(source.request, scoring_protocol_fingerprint=FP_D, fingerprint=None)
        changed = replace(source, request=request_model)
    else:
        response = unsafe_copy(source.response, provenance_reference="other-provenance")
        changed = replace(source, response=response)
    with pytest.raises((EvaluationCorrespondenceMismatch, CaseResultFingerprintMismatch)):
        FACTORY.create(changed)


def test_failures_never_produce_eval_result() -> None:
    request_model = evaluation_request()
    source = creation_input(
        request=request_model,
        response=evaluation_response(request_model, status=CaseEvaluationStatus.TIMED_OUT),
    )
    with pytest.raises(EvaluationNotSuccessful):
        FACTORY.create(source)
    recovered = replace(source, response=evaluation_response(request_model))
    assert FACTORY.create(recovered).verdict is Verdict.PASSED


def test_result_fingerprint_and_checksum_tampering_are_detected() -> None:
    source = creation_input()
    result = FACTORY.create(source)
    with pytest.raises(CaseResultFingerprintMismatch):
        validate_eval_result(source, replace(result, result_fingerprint=FP_D))
    with pytest.raises(CaseResultFingerprintMismatch):
        validate_eval_result(source, replace(result, checksum=ContentChecksum("d" * 64)))
    with pytest.raises(CaseResultFingerprintMismatch):
        validate_eval_result(source, replace(result, resource_usage=ResourceUsage(999)))


class FakeRunStore:
    def __init__(self) -> None:
        self.results: dict[tuple[object, object, int], object] = {}
        self.save_calls = 0
        self.failure: Exception | None = None
        self.duplicate_after_store = False

    @staticmethod
    def key(result: object) -> tuple[object, object, int]:
        return (result.run_id, result.case_reference, result.repetition)  # type: ignore[attr-defined]

    def result_exists(self, run_id: object, case_reference: object, repetition: int) -> bool:
        if self.failure is not None and not isinstance(self.failure, EvalDuplicateRecord):
            raise self.failure
        return (run_id, case_reference, repetition) in self.results

    def get_result_for_execution(self, run_id: object, case_reference: object, repetition: int):
        key = (run_id, case_reference, repetition)
        if key not in self.results:
            raise EvalRecordNotFound()
        return self.results[key]

    def save_result(self, result: object, *, idempotency_key: IdempotencyKey) -> StoreWriteOutcome:
        self.save_calls += 1
        key = self.key(result)
        if self.duplicate_after_store:
            self.results.setdefault(key, result)
            raise EvalDuplicateRecord()
        if self.failure is not None:
            raise self.failure
        if key in self.results:
            existing = self.results[key]
            if existing.result_fingerprint != result.result_fingerprint:  # type: ignore[attr-defined]
                raise EvalIntegrityConflict()
            return StoreWriteOutcome(str(result.result_id), Revision(1), Revision(1), WriteDisposition.IDEMPOTENT_REPLAY, existing.checksum)  # type: ignore[attr-defined]
        self.results[key] = result
        return StoreWriteOutcome(str(result.result_id), None, Revision(1), WriteDisposition.CREATED, result.checksum)  # type: ignore[attr-defined]


def test_service_creates_replays_and_never_updates_run() -> None:
    store = FakeRunStore()
    service = EvalResultService(store)  # type: ignore[arg-type]
    created = service.create_result(creation_input())
    replay = service.create_result(
        creation_input(result_id=EvalResultId("result-2"), created_at=LATER)
    )
    assert created.disposition is WriteDisposition.CREATED
    assert replay.disposition is WriteDisposition.IDEMPOTENT_REPLAY
    assert store.save_calls == 1 and not hasattr(store, "update_run")


@pytest.mark.parametrize("dimension", ["output", "evaluator", "scores", "provenance", "artifact"])
def test_service_rejects_divergent_evaluation(dimension: str) -> None:
    store = FakeRunStore()
    service = EvalResultService(store)  # type: ignore[arg-type]
    service.create_result(creation_input())
    source = creation_input()
    if dimension == "output":
        changed_output = replace(source.materialized, materialization_fingerprint=FP_D)
        changed = replace(source, materialized=changed_output)
    elif dimension == "evaluator":
        changed_response = unsafe_copy(source.response, evaluator=replace(source.response.evaluator, kind="other"))
        changed = replace(source, response=changed_response)
    elif dimension == "scores":
        changed = replace(source, response=evaluation_response(source.request, scores=(score(value="0.85"),)))
    elif dimension == "provenance":
        changed_response = unsafe_copy(source.response, provenance_reference="other-provenance")
        changed = replace(source, response=changed_response)
    else:
        changed_response = unsafe_copy(source.response, evaluator_artifact_reference="other-artifact")
        changed = replace(source, response=changed_response)
    with pytest.raises((CaseResultAlreadyExists, EvaluationCorrespondenceMismatch, CaseResultFingerprintMismatch)):
        service.create_result(changed)


def test_duplicate_race_equivalent_replays_and_divergent_conflicts() -> None:
    store = FakeRunStore()
    store.duplicate_after_store = True
    outcome = EvalResultService(store).create_result(creation_input())  # type: ignore[arg-type]
    assert outcome.disposition is WriteDisposition.IDEMPOTENT_REPLAY
    divergent_store = FakeRunStore()
    first = FACTORY.create(creation_input())
    divergent_store.results[divergent_store.key(first)] = first
    with pytest.raises(CaseResultAlreadyExists):
        EvalResultService(divergent_store).create_result(  # type: ignore[arg-type]
            creation_input(response=evaluation_response(scores=(score(value="0.85"),)))
        )


@pytest.mark.parametrize(
    ("store_error", "domain_error"),
    [
        (EvalStoreUnavailable(), CaseResultPersistenceUnavailable),
        (EvalIntegrityConflict(), CaseResultAlreadyExists),
        (EvalIdempotencyConflict(), CaseResultIdempotencyConflict),
        (EvalInvalidStoreQuery(), CaseResultPersistenceInvalid),
        (EvalRecordNotFound(), CaseResultPersistenceNotFound),
    ],
)
def test_service_translates_store_errors(store_error: Exception, domain_error: type[Exception]) -> None:
    store = FakeRunStore()
    store.failure = store_error
    with pytest.raises(domain_error):
        EvalResultService(store).create_result(creation_input())  # type: ignore[arg-type]


def test_engine_observation_projection_is_direct_and_preserves_identity() -> None:
    source = creation_input()
    result = FACTORY.create(source)
    observation = project_scoring_observation(result)
    assert observation.run_id == result.run_id
    assert tuple(item.metric_id for item in observation.scores) == ("quality",)
    assert observation.result_fingerprint == result.result_fingerprint
    assert "verdict" not in observation.__dataclass_fields__


def test_repr_and_errors_do_not_expose_sensitive_or_inline_content() -> None:
    request_model = evaluation_request()
    response = evaluation_response(request_model)
    rendered = repr(request_model) + repr(response)
    assert not any(term in rendered for term in ("prompt", "token", "provider", "output-asset-1", "C:\\"))
    unsafe = "token=do-not-echo"
    with pytest.raises(EvaluationRequestInvalid) as caught:
        evaluation_request(correlation_reference=unsafe)
    assert unsafe not in str(caught.value)
