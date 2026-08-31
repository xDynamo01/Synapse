from __future__ import annotations

import inspect
from dataclasses import FrozenInstanceError, replace

import pytest

from synapse.private_evals.contracts import EvalMaterializationStore
from synapse.private_evals.execution import CaseExecutionStatus
from synapse.private_evals.execution_records import (
    ExecutionAttemptRecord,
    LogicalExecutionProjection,
    logical_execution_projection,
)
from synapse.private_evals.result_errors import (
    ExecutionNotSuccessful,
    ResultAlreadyExistsWithDifferentContent,
    ResultCorrespondenceMismatch,
    ResultFingerprintMismatch,
    ResultIdempotencyConflict,
    ResultMaterializationInvalid,
    ResultPersistenceInvalid,
    ResultPersistenceNotFound,
    ResultPersistenceUnavailable,
)
from synapse.private_evals.result_materialization import (
    MaterializationInput,
    MaterializedOutputFactory,
    MaterializedOutputService,
    materialized_output_fingerprint,
    validate_materialized_output,
)
from synapse.private_evals.scoring import ScoringObservation
from synapse.private_evals.states import ResultStatus
from synapse.private_evals.store_errors import (
    EvalDuplicateRecord,
    EvalIdempotencyConflict,
    EvalIntegrityConflict,
    EvalInvalidStoreQuery,
    EvalRecordNotFound,
    EvalStoreUnavailable,
)
from synapse.private_evals.store_models import (
    IdempotencyKey,
    StoreWriteOutcome,
    WriteDisposition,
)
from synapse.private_evals.values import (
    ContentChecksum,
    EvalCaseId,
    MaterializedOutputId,
    Revision,
    UtcTimestamp,
)
from test_private_evals_execution import (
    FP_D,
    RUN_ID,
    case,
    logical,
    manifest,
    record,
    request,
)
from test_private_evals_models import score

NOW = UtcTimestamp("2026-07-18T15:00:00Z")
LATER = UtcTimestamp("2026-07-18T16:00:00Z")
FACTORY = MaterializedOutputFactory()


def materialization(**changes: object) -> MaterializationInput:
    request_model = changes.pop("request", request())
    assert hasattr(request_model, "logical_execution")
    attempt_model = changes.pop("attempt", record(target=request_model))
    projection = changes.pop("logical_projection") if "logical_projection" in changes else (
        logical_execution_projection(request_model.logical_execution, (attempt_model,))
    )
    return replace(
        MaterializationInput(
            request=request_model,
            attempt=attempt_model,
            logical_projection=projection,
            manifest=manifest(),
            case=case(),
            output_id=MaterializedOutputId("output-1"),
            producer_id="private-evals",
            producer_version="10.0.0",
            created_at=NOW,
            idempotency_key=IdempotencyKey("result-key-1"),
        ),
        **changes,
    )


def unsafe_attempt(
    source: ExecutionAttemptRecord | None = None,
    **changes: object,
) -> ExecutionAttemptRecord:
    source = source or record()
    item = object.__new__(ExecutionAttemptRecord)
    for name in source.__dataclass_fields__:
        object.__setattr__(item, name, changes.get(name, getattr(source, name)))
    return item


def unsafe_projection(
    source: LogicalExecutionProjection,
    **changes: object,
) -> LogicalExecutionProjection:
    item = object.__new__(LogicalExecutionProjection)
    for name in source.__dataclass_fields__:
        object.__setattr__(item, name, changes.get(name, getattr(source, name)))
    return item


def test_factory_materializes_execution_output_without_score_or_verdict_fields() -> None:
    result = FACTORY.create(materialization())
    assert result.run_id == RUN_ID
    assert result.case_reference == case().reference
    assert result.output_asset_reference == "output-asset-1"
    assert "scores" not in result.__dataclass_fields__
    assert "verdict" not in result.__dataclass_fields__
    assert "scoring_protocol" not in result.__dataclass_fields__
    assert result.provenance_reference == "provenance-1"


def test_materialized_output_is_frozen_and_eval_result_status_is_unchanged() -> None:
    record_model = FACTORY.create(materialization())
    with pytest.raises(FrozenInstanceError):
        record_model.producer_version = "changed"  # type: ignore[misc]
    assert "MATERIALIZED" not in ResultStatus.__members__


def test_evaluator_version_is_not_part_of_output_content_identity() -> None:
    source = materialization()
    changed_evaluator = replace(
        source.case.evaluator,
        implementation_checksum=ContentChecksum("c" * 64),
    )
    changed_case = replace(source.case, evaluator=changed_evaluator)
    assert materialized_output_fingerprint(source) == materialized_output_fingerprint(
        replace(source, case=changed_case)
    )


def test_scoring_protocol_is_absent_from_materialization_identity_and_record() -> None:
    input_fields = MaterializationInput.__dataclass_fields__
    record_fields = FACTORY.create(materialization()).__dataclass_fields__
    assert not {"scoring_protocol", "scoring_protocol_reference"} & input_fields.keys()
    assert not {"scoring_protocol", "scoring_protocol_reference"} & record_fields.keys()


def test_materialization_store_key_has_no_evaluator_or_scoring_protocol_dimension() -> None:
    for method_name in (
        "get_materialized_output_for_execution",
        "materialized_output_exists",
    ):
        parameters = inspect.signature(getattr(EvalMaterializationStore, method_name)).parameters
        assert tuple(parameters) == ("self", "run_id", "case_reference", "repetition")


def test_materialized_output_has_no_second_score_or_verdict_authority() -> None:
    fields = FACTORY.create(materialization()).__dataclass_fields__
    assert not {"scores", "score", "verdict", "decision"} & fields.keys()


def test_future_scoring_observation_binds_output_by_logical_key_without_mutation() -> None:
    record_model = FACTORY.create(materialization())
    before = record_model
    observation = ScoringObservation(
        record_model.run_id,
        record_model.case_reference,
        record_model.repetition,
        ResultStatus.VALID,
        (score(),),
    )
    assert (
        observation.run_id,
        observation.case_reference,
        observation.repetition,
    ) == (
        record_model.run_id,
        record_model.case_reference,
        record_model.repetition,
    )
    assert record_model == before


@pytest.mark.parametrize(
    "status",
    [
        CaseExecutionStatus.INFRASTRUCTURE_FAILED,
        CaseExecutionStatus.TIMED_OUT,
        CaseExecutionStatus.CANCELLED,
        CaseExecutionStatus.POLICY_DENIED,
        CaseExecutionStatus.INVALID,
    ],
)
def test_factory_rejects_every_non_success(status: CaseExecutionStatus) -> None:
    failed = record(status)
    projection = logical_execution_projection(logical(), (failed,))
    with pytest.raises(ExecutionNotSuccessful):
        FACTORY.create(materialization(attempt=failed, logical_projection=projection))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("output_asset_reference", None),
        ("result_checksum", None),
        ("evaluator_artifact_reference", None),
        ("provenance_reference", ""),
    ],
)
def test_factory_rejects_missing_execution_facts(field: str, value: object) -> None:
    attempt = unsafe_attempt(**{field: value})
    projection = unsafe_projection(
        logical_execution_projection(logical(), (record(),)),
        attempts=(attempt,),
    )
    with pytest.raises(ResultMaterializationInvalid):
        FACTORY.create(materialization(attempt=attempt, logical_projection=projection))


def test_factory_rejects_run_case_repetition_and_attempt_mismatch() -> None:
    different_case = replace(case(), case_id=EvalCaseId("other-case"))
    with pytest.raises(ResultCorrespondenceMismatch):
        FACTORY.create(materialization(case=different_case))
    other_request = request(logical_execution=logical(repetition=2), seed=42)
    with pytest.raises(ResultCorrespondenceMismatch):
        FACTORY.create(
            materialization(
                request=other_request,
                attempt=record(),
                logical_projection=logical_execution_projection(logical(), (record(),)),
            )
        )
    mismatched_attempt = unsafe_attempt(
        attempt_identity=request(2).attempt_identity,
    )
    with pytest.raises(ResultCorrespondenceMismatch):
        FACTORY.create(
            materialization(
                attempt=mismatched_attempt,
                logical_projection=logical_execution_projection(logical(), (record(),)),
            )
        )


def test_multiple_successes_and_attempt_after_success_are_rejected() -> None:
    first = record()
    second = record(target=request(2))
    base = logical_execution_projection(logical(), (first,))
    multiple = unsafe_projection(base, attempts=(first, second))
    with pytest.raises(ResultCorrespondenceMismatch):
        FACTORY.create(materialization(logical_projection=multiple))


def test_later_success_keeps_logical_identity_but_changes_attempt_content() -> None:
    first_result = FACTORY.create(materialization())
    first_request = request()
    second_request = request(2)
    timeout = record(CaseExecutionStatus.TIMED_OUT, target=first_request)
    success = record(target=second_request)
    projection = logical_execution_projection(logical(), (timeout, success))
    later = FACTORY.create(
        materialization(
            request=second_request,
            attempt=success,
            logical_projection=projection,
        )
    )
    assert later.run_id == first_result.run_id
    assert later.case_reference == first_result.case_reference
    assert later.repetition == first_result.repetition
    assert later.materialization_fingerprint != first_result.materialization_fingerprint


def test_output_identity_excludes_record_id_timestamp_key_producer_and_correlation() -> None:
    first_input = materialization()
    second_input = materialization(
        output_id=MaterializedOutputId("output-2"),
        created_at=LATER,
        idempotency_key=IdempotencyKey("result-key-2"),
        producer_version="10.1.0",
        request=request(correlation_reference="correlation-2"),
    )
    first = FACTORY.create(first_input)
    second = FACTORY.create(second_input)
    assert first.output_id != second.output_id
    assert first.created_at != second.created_at
    assert first.materialization_fingerprint == second.materialization_fingerprint
    assert first.checksum != second.checksum


@pytest.mark.parametrize(
    "change",
    [
        {
            "attempt": replace(
                record(), result_checksum=ContentChecksum("b" * 64), checksum=None
            )
        },
        {"attempt": replace(record(), provenance_reference="provenance-2", checksum=None)},
        {
            "attempt": replace(
                record(), evaluator_artifact_reference="evaluator-artifact-2", checksum=None
            )
        },
    ],
)
def test_semantic_content_changes_output_fingerprint(change: dict[str, object]) -> None:
    base = materialization()
    changed = materialization(**change)
    assert materialized_output_fingerprint(base) != materialized_output_fingerprint(changed)


def test_result_fingerprint_and_checksum_tampering_are_detected() -> None:
    input_model = materialization()
    result = FACTORY.create(input_model)
    with pytest.raises(ResultFingerprintMismatch):
        validate_materialized_output(input_model, replace(result, materialization_fingerprint=FP_D))
    with pytest.raises(ResultFingerprintMismatch):
        validate_materialized_output(
            input_model, replace(result, checksum=ContentChecksum("b" * 64))
        )


class FakeMaterializationStore:
    def __init__(self) -> None:
        self.results: dict[tuple[object, object, int], object] = {}
        self.save_calls = 0
        self.failure: Exception | None = None
        self.duplicate_after_store = False

    @staticmethod
    def key(result: object) -> tuple[object, object, int]:
        return (result.run_id, result.case_reference, result.repetition)  # type: ignore[attr-defined]

    def materialized_output_exists(self, run_id: object, case_reference: object, repetition: int) -> bool:
        if self.failure is not None and not isinstance(self.failure, EvalDuplicateRecord):
            raise self.failure
        return (run_id, case_reference, repetition) in self.results

    def get_materialized_output_for_execution(
        self, run_id: object, case_reference: object, repetition: int
    ) -> object:
        key = (run_id, case_reference, repetition)
        if key not in self.results:
            raise EvalRecordNotFound()
        return self.results[key]

    def save_materialized_output(self, result: object, *, idempotency_key: IdempotencyKey) -> StoreWriteOutcome:
        self.save_calls += 1
        key = self.key(result)
        if self.duplicate_after_store:
            self.results.setdefault(key, result)
            raise EvalDuplicateRecord()
        if self.failure is not None:
            raise self.failure
        if key in self.results:
            existing = self.results[key]
            if existing.materialization_fingerprint != result.materialization_fingerprint:  # type: ignore[attr-defined]
                raise EvalIntegrityConflict()
            return StoreWriteOutcome(
                str(result.output_id),  # type: ignore[attr-defined]
                Revision(1),
                Revision(1),
                WriteDisposition.IDEMPOTENT_REPLAY,
                result.checksum,  # type: ignore[attr-defined]
            )
        self.results[key] = result
        return StoreWriteOutcome(
            str(result.output_id),  # type: ignore[attr-defined]
            None,
            Revision(1),
            WriteDisposition.CREATED,
            result.checksum,  # type: ignore[attr-defined]
        )


def test_service_creates_then_replays_without_updating_run() -> None:
    store = FakeMaterializationStore()
    service = MaterializedOutputService(store)  # type: ignore[arg-type]
    created = service.materialize(materialization())
    replay = service.materialize(materialization(output_id=MaterializedOutputId("output-2")))
    assert created.disposition is WriteDisposition.CREATED
    assert replay.disposition is WriteDisposition.IDEMPOTENT_REPLAY
    assert replay.record is created.record
    assert store.save_calls == 1
    assert not hasattr(store, "update_run")


def test_service_detects_existing_divergent_content() -> None:
    store = FakeMaterializationStore()
    service = MaterializedOutputService(store)  # type: ignore[arg-type]
    service.materialize(materialization())
    with pytest.raises(ResultAlreadyExistsWithDifferentContent):
        service.materialize(materialization(attempt=replace(record(), result_checksum=ContentChecksum("b" * 64), checksum=None)))


@pytest.mark.parametrize(
    ("store_error", "domain_error"),
    [
        (EvalStoreUnavailable(), ResultPersistenceUnavailable),
        (EvalIntegrityConflict(), ResultAlreadyExistsWithDifferentContent),
        (EvalIdempotencyConflict(), ResultIdempotencyConflict),
        (EvalInvalidStoreQuery(), ResultPersistenceInvalid),
        (EvalRecordNotFound(), ResultPersistenceNotFound),
    ],
)
def test_service_translates_store_errors(
    store_error: Exception, domain_error: type[Exception]
) -> None:
    store = FakeMaterializationStore()
    store.failure = store_error
    with pytest.raises(domain_error):
        MaterializedOutputService(store).materialize(materialization())  # type: ignore[arg-type]


def test_duplicate_race_recovers_equivalent_result() -> None:
    store = FakeMaterializationStore()
    store.duplicate_after_store = True
    outcome = MaterializedOutputService(store).materialize(materialization())  # type: ignore[arg-type]
    assert outcome.disposition is WriteDisposition.IDEMPOTENT_REPLAY
    assert store.save_calls == 1


def test_concurrent_divergent_content_delegates_atomicity_to_store() -> None:
    store = FakeMaterializationStore()
    first = FACTORY.create(materialization())
    store.results[store.key(first)] = first
    with pytest.raises(ResultAlreadyExistsWithDifferentContent):
        MaterializedOutputService(store).materialize(  # type: ignore[arg-type]
            materialization(attempt=replace(record(), result_checksum=ContentChecksum("b" * 64), checksum=None))
        )
    assert store.results[store.key(first)] is first


def test_safe_repr_and_errors_do_not_echo_private_content() -> None:
    result = FACTORY.create(materialization())
    assert "output inline" not in repr(result)
    unsafe = "token=do-not-echo"
    with pytest.raises(ResultMaterializationInvalid) as caught:
        materialization(producer_id=unsafe)
    assert unsafe not in str(caught.value)
    unsafe_output = replace(
        record(), output_asset_reference="https://private/output", checksum=None
    )
    with pytest.raises(ResultMaterializationInvalid):
        FACTORY.create(materialization(attempt=unsafe_output))
