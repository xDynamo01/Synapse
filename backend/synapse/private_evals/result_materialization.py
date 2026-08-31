from __future__ import annotations

from dataclasses import dataclass

from .canonical import content_checksum, fingerprint
from .catalog import EvalCaseVersion
from .contracts import EvalMaterializationStore
from .execution import CaseExecutionRequest, CaseExecutionStatus, validate_request_against_manifest
from .execution_errors import CaseExecutionError
from .execution_records import (
    ExecutionAttemptRecord,
    LogicalExecutionProjection,
    LogicalExecutionProjectionStatus,
    attempt_record_checksum,
    logical_projection_checksum,
    logical_projection_fingerprint,
)
from .result_errors import (
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
from .result_models import (
    MaterializedOutputRecord,
    validate_safe_materialization_reference,
)
from .runs import EvalRunManifest
from .store_errors import (
    EvalDuplicateRecord,
    EvalIdempotencyConflict,
    EvalIntegrityConflict,
    EvalInvalidStoreQuery,
    EvalRecordNotFound,
    EvalStoreUnavailable,
)
from .store_models import IdempotencyKey, StoreWriteOutcome, WriteDisposition
from .values import (
    ContentChecksum,
    Fingerprint,
    MaterializedOutputId,
    UtcTimestamp,
)


@dataclass(frozen=True)
class MaterializationInput:
    request: CaseExecutionRequest
    attempt: ExecutionAttemptRecord
    logical_projection: LogicalExecutionProjection
    manifest: EvalRunManifest
    case: EvalCaseVersion
    output_id: MaterializedOutputId
    producer_id: str
    producer_version: str
    created_at: UtcTimestamp
    idempotency_key: IdempotencyKey

    def __post_init__(self) -> None:
        for value, label in (
            (self.producer_id, "producer ID"),
            (self.producer_version, "producer version"),
        ):
            validate_safe_materialization_reference(value, label)


def _content_semantic(source: MaterializationInput) -> dict[str, object]:
    attempt = source.attempt
    return {
        "logical_execution": source.request.logical_execution,
        "attempt_identity": attempt.attempt_identity,
        "output_asset_reference": attempt.output_asset_reference,
        "output_checksum": attempt.result_checksum,
        "evaluator_artifact_reference": attempt.evaluator_artifact_reference,
        "provenance_reference": attempt.provenance_reference,
    }


def materialized_output_fingerprint(source: MaterializationInput) -> Fingerprint:
    """Content identity; excludes record ID, timestamp, producer and scoring protocol."""
    return fingerprint(_content_semantic(source))


def _record_semantic(
    source: MaterializationInput, materialization_fingerprint: Fingerprint
) -> dict[str, object]:
    return {
        **_content_semantic(source),
        "output_id": source.output_id,
        "producer": (source.producer_id, source.producer_version),
        "created_at": source.created_at,
        "materialization_fingerprint": materialization_fingerprint,
        "resource_usage": source.attempt.resource_usage,
    }


def materialized_output_checksum(
    source: MaterializationInput, materialization_fingerprint: Fingerprint
) -> ContentChecksum:
    return content_checksum(_record_semantic(source, materialization_fingerprint))


def validate_materialization_correspondence(source: MaterializationInput) -> None:
    request = source.request
    attempt = source.attempt
    projection = source.logical_projection
    try:
        validate_request_against_manifest(request, source.manifest, source.case, request.logical_execution.run_id)
    except CaseExecutionError as exc:
        raise ResultCorrespondenceMismatch() from exc
    if attempt.status is not CaseExecutionStatus.SUCCEEDED:
        raise ExecutionNotSuccessful()
    if (
        attempt.output_asset_reference is None
        or attempt.result_checksum is None
        or attempt.evaluator_artifact_reference is None
        or not attempt.provenance_reference
    ):
        raise ResultMaterializationInvalid()
    for value, label in (
        (attempt.output_asset_reference, "output asset reference"),
        (attempt.evaluator_artifact_reference, "evaluator artifact reference"),
        (attempt.provenance_reference, "provenance reference"),
    ):
        assert value is not None
        validate_safe_materialization_reference(value, label)
    if attempt.checksum != attempt_record_checksum(attempt):
        raise ResultCorrespondenceMismatch()
    if (
        projection.fingerprint != logical_projection_fingerprint(projection)
        or projection.checksum != logical_projection_checksum(projection)
        or attempt.logical_execution != request.logical_execution
        or attempt.attempt_identity != request.attempt_identity
        or attempt.request_fingerprint != request.fingerprint
        or projection.logical_execution != request.logical_execution
    ):
        raise ResultCorrespondenceMismatch()
    successes = tuple(item for item in projection.attempts if item.status is CaseExecutionStatus.SUCCEEDED)
    if (
        projection.status is not LogicalExecutionProjectionStatus.SUCCEEDED
        or successes != (attempt,)
        or projection.attempts[-1] != attempt
        or projection.successful_attempt_reference != attempt.attempt_identity.fingerprint
    ):
        raise ResultCorrespondenceMismatch()


@dataclass(frozen=True)
class MaterializedOutputFactory:
    def create(self, source: MaterializationInput) -> MaterializedOutputRecord:
        validate_materialization_correspondence(source)
        attempt = source.attempt
        materialization_fingerprint = materialized_output_fingerprint(source)
        attempt_reference = attempt.attempt_identity.fingerprint
        assert attempt_reference is not None
        assert source.request.logical_execution.fingerprint is not None
        assert attempt.output_asset_reference is not None
        assert attempt.result_checksum is not None
        assert attempt.evaluator_artifact_reference is not None
        return MaterializedOutputRecord(
            output_id=source.output_id,
            run_id=source.request.logical_execution.run_id,
            case_reference=source.case.reference,
            repetition=source.request.logical_execution.repetition,
            logical_execution_fingerprint=source.request.logical_execution.fingerprint,
            execution_attempt_reference=attempt_reference,
            output_asset_reference=attempt.output_asset_reference,
            output_checksum=attempt.result_checksum,
            evaluator_artifact_reference=attempt.evaluator_artifact_reference,
            provenance_reference=attempt.provenance_reference,
            resource_usage=attempt.resource_usage,
            producer_id=source.producer_id,
            producer_version=source.producer_version,
            created_at=source.created_at,
            materialization_fingerprint=materialization_fingerprint,
            checksum=materialized_output_checksum(source, materialization_fingerprint),
        )


def validate_materialized_output(source: MaterializationInput, record: MaterializedOutputRecord) -> None:
    expected = MaterializedOutputFactory().create(source)
    if (
        record.run_id != expected.run_id
        or record.case_reference != expected.case_reference
        or record.repetition != expected.repetition
        or record.logical_execution_fingerprint != expected.logical_execution_fingerprint
        or record.execution_attempt_reference != expected.execution_attempt_reference
    ):
        raise ResultCorrespondenceMismatch()
    if record.materialization_fingerprint != expected.materialization_fingerprint or record.checksum != expected.checksum:
        raise ResultFingerprintMismatch()


@dataclass(frozen=True)
class MaterializedOutputWriteResult:
    record: MaterializedOutputRecord
    disposition: WriteDisposition
    store_outcome: StoreWriteOutcome | None


@dataclass(frozen=True)
class MaterializedOutputService:
    store: EvalMaterializationStore
    factory: MaterializedOutputFactory = MaterializedOutputFactory()

    def materialize(self, source: MaterializationInput) -> MaterializedOutputWriteResult:
        candidate = self.factory.create(source)
        try:
            if self.store.materialized_output_exists(candidate.run_id, candidate.case_reference, candidate.repetition):
                existing = self.store.get_materialized_output_for_execution(candidate.run_id, candidate.case_reference, candidate.repetition)
                return self._replay_or_conflict(existing, candidate)
            outcome = self.store.save_materialized_output(candidate, idempotency_key=source.idempotency_key)
            if outcome.disposition is WriteDisposition.UPDATED:
                raise ResultAlreadyExistsWithDifferentContent()
            if outcome.disposition is WriteDisposition.IDEMPOTENT_REPLAY:
                existing = self.store.get_materialized_output_for_execution(candidate.run_id, candidate.case_reference, candidate.repetition)
                return self._replay_or_conflict(existing, candidate, outcome)
            if outcome.checksum != candidate.checksum:
                raise ResultAlreadyExistsWithDifferentContent()
            return MaterializedOutputWriteResult(candidate, WriteDisposition.CREATED, outcome)
        except EvalDuplicateRecord:
            return self._recover_duplicate(candidate)
        except EvalIntegrityConflict as exc:
            raise ResultAlreadyExistsWithDifferentContent() from exc
        except EvalIdempotencyConflict as exc:
            raise ResultIdempotencyConflict() from exc
        except EvalStoreUnavailable as exc:
            raise ResultPersistenceUnavailable() from exc
        except EvalRecordNotFound as exc:
            raise ResultPersistenceNotFound() from exc
        except EvalInvalidStoreQuery as exc:
            raise ResultPersistenceInvalid() from exc

    def _recover_duplicate(self, candidate: MaterializedOutputRecord) -> MaterializedOutputWriteResult:
        try:
            existing = self.store.get_materialized_output_for_execution(candidate.run_id, candidate.case_reference, candidate.repetition)
        except EvalStoreUnavailable as exc:
            raise ResultPersistenceUnavailable() from exc
        except EvalRecordNotFound as exc:
            raise ResultPersistenceNotFound() from exc
        return self._replay_or_conflict(existing, candidate)

    @staticmethod
    def _replay_or_conflict(
        existing: MaterializedOutputRecord,
        candidate: MaterializedOutputRecord,
        outcome: StoreWriteOutcome | None = None,
    ) -> MaterializedOutputWriteResult:
        if (
            existing.run_id != candidate.run_id
            or existing.case_reference != candidate.case_reference
            or existing.repetition != candidate.repetition
            or existing.materialization_fingerprint != candidate.materialization_fingerprint
        ):
            raise ResultAlreadyExistsWithDifferentContent()
        return MaterializedOutputWriteResult(existing, WriteDisposition.IDEMPOTENT_REPLAY, outcome)
