from __future__ import annotations

import re
from dataclasses import dataclass, replace
from decimal import Decimal
from enum import StrEnum

from .canonical import content_checksum, fingerprint
from .case_evaluation_errors import (
    CaseEvaluatorMismatch,
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
from .catalog import EvalCaseVersion, EvalCaseVersionRef, EvaluatorIdentity
from .contracts import EvalRunStore
from .result_models import MaterializedOutputRecord
from .runs import (
    EvalResult,
    EvalRunManifest,
    ResourceUsage,
    Score,
)
from .scoring import (
    ScoreThreshold,
    ScoringObservation,
    ScoringProtocol,
    ScoringTarget,
    ThresholdScope,
)
from .states import ResultStatus, ScoreKind, ScoreStatus, Verdict
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
    EvalResultId,
    EvalRunId,
    EvalRunManifestId,
    EvalSuiteId,
    EvalVersion,
    Fingerprint,
    MaterializedOutputId,
    UtcTimestamp,
)

_SAFE_REFERENCE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._~:-]{0,255}$")
_SENSITIVE = re.compile(
    r"(?i)(?:token|secret|password|credential|authorization|bearer|api[_-]?key|sk-)"
)


def _safe_reference(value: str) -> bool:
    return bool(
        isinstance(value, str)
        and _SAFE_REFERENCE.fullmatch(value)
        and not _SENSITIVE.search(value)
        and "/" not in value
        and "\\" not in value
        and "://" not in value
    )


class CaseEvaluationStatus(StrEnum):
    SUCCEEDED = "succeeded"
    INFRASTRUCTURE_FAILED = "infrastructure_failed"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"
    POLICY_DENIED = "policy_denied"
    INVALID = "invalid"


class CaseEvaluationReasonCode(StrEnum):
    COMPLETED = "completed"
    INFRASTRUCTURE_UNAVAILABLE = "infrastructure_unavailable"
    EVALUATION_TIMEOUT = "evaluation_timeout"
    CANCELLED_BY_REQUEST = "cancelled_by_request"
    POLICY_NOT_AUTHORIZED = "policy_not_authorized"
    RESPONSE_INVALID = "response_invalid"


@dataclass(frozen=True)
class ExpectedMetricDefinition:
    metric_id: str
    kind: ScoreKind
    scale_minimum: Decimal
    scale_maximum: Decimal
    confidence_method: str | None = None

    def __post_init__(self) -> None:
        metric = self.metric_id.strip().casefold() if isinstance(self.metric_id, str) else ""
        if not _safe_reference(metric) or not isinstance(self.kind, ScoreKind):
            raise EvaluationRequestInvalid()
        decimals = (self.scale_minimum, self.scale_maximum)
        if any(not isinstance(value, Decimal) or not value.is_finite() for value in decimals):
            raise EvaluationRequestInvalid()
        if self.scale_minimum >= self.scale_maximum:
            raise EvaluationRequestInvalid()
        if self.kind is ScoreKind.BINARY and (
            self.scale_minimum != 0 or self.scale_maximum != 1
        ):
            raise EvaluationRequestInvalid()
        if self.confidence_method is not None and not _safe_reference(self.confidence_method):
            raise EvaluationRequestInvalid()
        object.__setattr__(self, "metric_id", metric)


@dataclass(frozen=True)
class EvaluationEventIdentity:
    run_id: EvalRunId
    case_reference: EvalCaseVersionRef
    repetition: int
    materialized_output_fingerprint: Fingerprint
    evaluator: EvaluatorIdentity
    scoring_protocol_fingerprint: Fingerprint
    fingerprint: Fingerprint | None = None

    def __post_init__(self) -> None:
        if isinstance(self.repetition, bool) or not isinstance(self.repetition, int) or self.repetition < 1:
            raise EvaluationRequestInvalid()
        expected = evaluation_event_fingerprint(self)
        if self.fingerprint is None:
            object.__setattr__(self, "fingerprint", expected)
        elif self.fingerprint != expected:
            raise EvaluationRequestInvalid()


def evaluation_event_fingerprint(identity: EvaluationEventIdentity) -> Fingerprint:
    return fingerprint(
        {
            "logical_result": (identity.run_id, identity.case_reference, identity.repetition),
            "materialized_output_fingerprint": identity.materialized_output_fingerprint,
            "evaluator": identity.evaluator,
            "scoring_protocol_fingerprint": identity.scoring_protocol_fingerprint,
        }
    )


@dataclass(frozen=True)
class CaseEvaluationRequest:
    run_id: EvalRunId
    manifest_id: EvalRunManifestId
    manifest_fingerprint: Fingerprint
    suite_id: EvalSuiteId
    suite_version: EvalVersion
    case_reference: EvalCaseVersionRef
    repetition: int
    materialized_output_id: MaterializedOutputId
    materialized_output_fingerprint: Fingerprint
    materialized_output_checksum: ContentChecksum
    output_asset_reference: str
    evaluator: EvaluatorIdentity
    expected_metric: ExpectedMetricDefinition
    scoring_protocol_reference: str
    scoring_protocol_fingerprint: Fingerprint
    security_snapshot_reference: str
    security_snapshot_fingerprint: Fingerprint
    evaluator_input_asset_references: tuple[str, ...]
    timeout_seconds: Decimal
    seed: int | None
    idempotency_key: IdempotencyKey
    correlation_reference: str
    event_identity: EvaluationEventIdentity
    fingerprint: Fingerprint | None = None

    def __post_init__(self) -> None:
        typed = (
            (self.run_id, EvalRunId),
            (self.manifest_id, EvalRunManifestId),
            (self.manifest_fingerprint, Fingerprint),
            (self.suite_id, EvalSuiteId),
            (self.suite_version, EvalVersion),
            (self.case_reference, EvalCaseVersionRef),
            (self.materialized_output_id, MaterializedOutputId),
            (self.materialized_output_fingerprint, Fingerprint),
            (self.materialized_output_checksum, ContentChecksum),
            (self.evaluator, EvaluatorIdentity),
            (self.scoring_protocol_fingerprint, Fingerprint),
            (self.security_snapshot_fingerprint, Fingerprint),
            (self.idempotency_key, IdempotencyKey),
            (self.event_identity, EvaluationEventIdentity),
        )
        if any(not isinstance(value, expected) for value, expected in typed):
            raise EvaluationRequestInvalid()
        if isinstance(self.repetition, bool) or not isinstance(self.repetition, int) or self.repetition < 1:
            raise EvaluationRequestInvalid()
        if not isinstance(self.timeout_seconds, Decimal) or not self.timeout_seconds.is_finite() or self.timeout_seconds <= 0:
            raise EvaluationRequestInvalid()
        if self.seed is not None and (isinstance(self.seed, bool) or not isinstance(self.seed, int)):
            raise EvaluationRequestInvalid()
        for value in (
            self.output_asset_reference,
            self.scoring_protocol_reference,
            self.security_snapshot_reference,
            self.correlation_reference,
            *self.evaluator_input_asset_references,
        ):
            if not _safe_reference(value):
                raise EvaluationRequestInvalid()
        if not isinstance(self.expected_metric, ExpectedMetricDefinition):
            raise EvaluationRequestInvalid()
        if len(self.evaluator_input_asset_references) != len(set(self.evaluator_input_asset_references)):
            raise EvaluationRequestInvalid()
        object.__setattr__(self, "evaluator_input_asset_references", tuple(sorted(self.evaluator_input_asset_references)))
        expected = evaluation_request_fingerprint(self)
        if self.fingerprint is None:
            object.__setattr__(self, "fingerprint", expected)
        elif self.fingerprint != expected:
            raise EvaluationRequestInvalid()

    def __repr__(self) -> str:
        return (
            "CaseEvaluationRequest("
            f"run_id={self.run_id!r}, case_reference={self.case_reference!r}, "
            f"repetition={self.repetition!r}, fingerprint={self.fingerprint!r})"
        )


def evaluation_request_fingerprint(request: CaseEvaluationRequest) -> Fingerprint:
    return fingerprint(
        {
            "event_identity": request.event_identity,
            "manifest": (request.manifest_id, request.manifest_fingerprint),
            "suite": (request.suite_id, request.suite_version),
            "materialized_output": (
                request.materialized_output_id,
                request.materialized_output_fingerprint,
                request.materialized_output_checksum,
                request.output_asset_reference,
            ),
            "evaluator": request.evaluator,
            "expected_metric": request.expected_metric,
            "scoring_protocol": (
                request.scoring_protocol_reference,
                request.scoring_protocol_fingerprint,
            ),
            "security": (
                request.security_snapshot_reference,
                request.security_snapshot_fingerprint,
            ),
            "evaluator_inputs": request.evaluator_input_asset_references,
            "timeout_seconds": request.timeout_seconds,
            "seed": request.seed,
        }
    )


@dataclass(frozen=True)
class EvaluatorScore:
    """Evaluator-owned measurement facts, without case or run-scoring authority."""

    metric_id: str
    evaluator: EvaluatorIdentity
    kind: ScoreKind
    status: ScoreStatus
    raw_value: Decimal | None
    scale_minimum: Decimal
    scale_maximum: Decimal
    sample_count: int
    confidence: Decimal | None
    variance: Decimal | None
    confidence_method: str | None
    reason_code: str | None
    checksum: ContentChecksum

    def __post_init__(self) -> None:
        metric = self.metric_id.strip().casefold() if isinstance(self.metric_id, str) else ""
        if (
            not _safe_reference(metric)
            or not isinstance(self.evaluator, EvaluatorIdentity)
            or not isinstance(self.kind, ScoreKind)
            or not isinstance(self.status, ScoreStatus)
            or not isinstance(self.checksum, ContentChecksum)
        ):
            raise EvaluationScoreInvalid()
        decimals = (
            self.raw_value,
            self.scale_minimum,
            self.scale_maximum,
            self.confidence,
            self.variance,
        )
        if any(value is not None and (not isinstance(value, Decimal) or not value.is_finite()) for value in decimals):
            raise EvaluationScoreInvalid()
        if self.scale_minimum >= self.scale_maximum:
            raise EvaluationScoreInvalid()
        if self.kind is ScoreKind.BINARY and (
            self.scale_minimum != 0 or self.scale_maximum != 1
        ):
            raise EvaluationScoreInvalid()
        if isinstance(self.sample_count, bool) or self.sample_count < 0:
            raise EvaluationScoreInvalid()
        if self.confidence is not None and not Decimal("0") <= self.confidence <= Decimal("1"):
            raise EvaluationScoreInvalid()
        if self.variance is not None and self.variance < 0:
            raise EvaluationScoreInvalid()
        if (self.confidence is None) != (self.confidence_method is None):
            raise EvaluationScoreInvalid()
        if self.confidence_method is not None and not _safe_reference(self.confidence_method):
            raise EvaluationScoreInvalid()
        if self.status is ScoreStatus.VALID:
            if self.raw_value is None or self.sample_count != 1 or self.reason_code is not None:
                raise EvaluationScoreInvalid()
            if not self.scale_minimum <= self.raw_value <= self.scale_maximum:
                raise EvaluationScoreInvalid()
            if self.kind is ScoreKind.BINARY and self.raw_value not in {Decimal("0"), Decimal("1")}:
                raise EvaluationScoreInvalid()
        elif self.raw_value is not None or self.sample_count != 0 or not _safe_reference(self.reason_code or ""):
            raise EvaluationScoreInvalid()
        object.__setattr__(self, "metric_id", metric)


@dataclass(frozen=True)
class CaseEvaluationResponse:
    event_identity: EvaluationEventIdentity
    status: CaseEvaluationStatus
    evaluator: EvaluatorIdentity
    scores: tuple[EvaluatorScore, ...]
    evaluator_artifact_reference: str | None
    provenance_reference: str | None
    started_at: UtcTimestamp
    finished_at: UtcTimestamp
    resource_usage: ResourceUsage
    reason_codes: tuple[CaseEvaluationReasonCode, ...]
    fingerprint: Fingerprint | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.event_identity, EvaluationEventIdentity) or not isinstance(self.status, CaseEvaluationStatus) or not isinstance(self.evaluator, EvaluatorIdentity):
            raise EvaluationRequestInvalid()
        if any(not isinstance(item, EvaluatorScore) for item in self.scores):
            raise EvaluationScoreInvalid()
        metrics = tuple(item.metric_id.casefold() for item in self.scores)
        if len(metrics) != len(set(metrics)):
            raise DuplicateEvaluationMetric()
        if not isinstance(self.started_at, UtcTimestamp) or not isinstance(self.finished_at, UtcTimestamp) or self.finished_at.instant < self.started_at.instant:
            raise EvaluationRequestInvalid()
        if not isinstance(self.resource_usage, ResourceUsage) or not self.reason_codes or any(
            not isinstance(item, CaseEvaluationReasonCode) for item in self.reason_codes
        ):
            raise EvaluationRequestInvalid()
        expected_reason = {
            CaseEvaluationStatus.SUCCEEDED: CaseEvaluationReasonCode.COMPLETED,
            CaseEvaluationStatus.INFRASTRUCTURE_FAILED: CaseEvaluationReasonCode.INFRASTRUCTURE_UNAVAILABLE,
            CaseEvaluationStatus.TIMED_OUT: CaseEvaluationReasonCode.EVALUATION_TIMEOUT,
            CaseEvaluationStatus.CANCELLED: CaseEvaluationReasonCode.CANCELLED_BY_REQUEST,
            CaseEvaluationStatus.POLICY_DENIED: CaseEvaluationReasonCode.POLICY_NOT_AUTHORIZED,
            CaseEvaluationStatus.INVALID: CaseEvaluationReasonCode.RESPONSE_INVALID,
        }[self.status]
        if self.reason_codes != (expected_reason,):
            raise EvaluationRequestInvalid()
        succeeded = self.status is CaseEvaluationStatus.SUCCEEDED
        if succeeded:
            if len(self.scores) != 1:
                raise EvaluationMetricMissing()
            if not _safe_reference(self.evaluator_artifact_reference or "") or not _safe_reference(self.provenance_reference or ""):
                raise EvaluationRequestInvalid()
        elif (
            self.scores
            or self.evaluator_artifact_reference is not None
            or self.provenance_reference is not None
        ):
            raise EvaluationRequestInvalid()
        object.__setattr__(self, "scores", tuple(sorted(self.scores, key=lambda item: item.metric_id.casefold())))
        expected = evaluation_response_fingerprint(self)
        if self.fingerprint is None:
            object.__setattr__(self, "fingerprint", expected)
        elif self.fingerprint != expected:
            raise CaseResultFingerprintMismatch()

    def __repr__(self) -> str:
        return (
            "CaseEvaluationResponse("
            f"event_identity={self.event_identity.fingerprint!r}, status={self.status!r}, "
            f"fingerprint={self.fingerprint!r})"
        )


def evaluation_response_fingerprint(response: CaseEvaluationResponse) -> Fingerprint:
    return fingerprint(
        {
            "event_identity": response.event_identity,
            "status": response.status,
            "evaluator": response.evaluator,
            "scores": response.scores,
            "evaluator_artifact_reference": response.evaluator_artifact_reference,
            "provenance_reference": response.provenance_reference,
            "started_at": response.started_at,
            "finished_at": response.finished_at,
            "resource_usage": response.resource_usage,
            "reason_codes": tuple(sorted(response.reason_codes, key=lambda item: item.value)),
        }
    )


def validate_evaluation_scores(
    request: CaseEvaluationRequest,
    scores: tuple[EvaluatorScore, ...],
) -> None:
    if len(scores) != 1:
        raise EvaluationMetricMissing()
    score = scores[0]
    definition = request.expected_metric
    if score.metric_id != definition.metric_id:
        raise UnexpectedEvaluationMetric()
    if score.evaluator != request.evaluator:
        raise CaseEvaluatorMismatch()
    if score.kind is not definition.kind:
        raise ScoreKindMismatch()
    if (score.scale_minimum, score.scale_maximum) != (
        definition.scale_minimum,
        definition.scale_maximum,
    ):
        raise ScoreScaleMismatch()
    if score.confidence_method is not None and score.confidence_method != definition.confidence_method:
        raise EvaluationScoreInvalid()


def canonicalize_evaluator_score(
    request: CaseEvaluationRequest,
    evaluator_score: EvaluatorScore,
    target: ScoringTarget,
) -> Score:
    if not isinstance(target, ScoringTarget):
        raise EvaluationCorrespondenceMismatch()
    validate_evaluation_scores(request, (evaluator_score,))
    normalized = None
    if evaluator_score.raw_value is not None:
        normalized = (evaluator_score.raw_value - evaluator_score.scale_minimum) / (
            evaluator_score.scale_maximum - evaluator_score.scale_minimum
        )
    semantic = {
        "evaluator_score_checksum": evaluator_score.checksum,
        "metric_id": evaluator_score.metric_id,
        "evaluator": evaluator_score.evaluator,
        "kind": evaluator_score.kind,
        "status": evaluator_score.status,
        "raw_value": evaluator_score.raw_value,
        "scale": (evaluator_score.scale_minimum, evaluator_score.scale_maximum),
        "normalized_value": normalized,
        "case_weight": target.weight,
        "required": target.required,
        "critical": target.critical,
        "sample_count": evaluator_score.sample_count,
        "confidence": evaluator_score.confidence,
        "variance": evaluator_score.variance,
        "confidence_method": evaluator_score.confidence_method,
        "reason_code": evaluator_score.reason_code,
    }
    return Score(
        evaluator_score.metric_id,
        evaluator_score.evaluator,
        evaluator_score.kind,
        evaluator_score.status,
        evaluator_score.raw_value,
        evaluator_score.scale_minimum,
        evaluator_score.scale_maximum,
        normalized,
        target.weight,
        evaluator_score.sample_count,
        evaluator_score.confidence,
        evaluator_score.variance,
        evaluator_score.confidence_method,
        target.critical,
        target.required,
        evaluator_score.reason_code,
        content_checksum(semantic),
    )


def derive_case_verdict(
    scores: tuple[Score, ...],
    case_threshold: ScoreThreshold | None,
) -> Verdict:
    if len(scores) != 1:
        raise EvaluationMetricMissing()
    if any(item.status is ScoreStatus.INVALID for item in scores):
        return Verdict.INVALID
    if any(item.status is ScoreStatus.MISSING and item.required for item in scores):
        return Verdict.INCONCLUSIVE
    score = scores[0]
    if score.status is not ScoreStatus.VALID or score.normalized_value is None:
        return Verdict.INCONCLUSIVE
    if case_threshold is not None and not case_threshold.accepts(score.normalized_value):
        return Verdict.FAILED
    return Verdict.PASSED


def validate_evaluation_correspondence(
    materialized: MaterializedOutputRecord,
    request: CaseEvaluationRequest,
    response: CaseEvaluationResponse,
    manifest: EvalRunManifest,
    case: EvalCaseVersion,
    protocol: ScoringProtocol,
) -> None:
    if request.fingerprint != evaluation_request_fingerprint(request):
        raise EvaluationCorrespondenceMismatch()
    if response.fingerprint != evaluation_response_fingerprint(response):
        raise CaseResultFingerprintMismatch()
    protocol_fingerprint = fingerprint(protocol)
    case_targets = tuple(target for target in protocol.targets if target.case_reference == case.reference)
    if (
        materialized.run_id != request.run_id
        or materialized.case_reference != request.case_reference
        or materialized.repetition != request.repetition
        or materialized.output_id != request.materialized_output_id
        or materialized.materialization_fingerprint != request.materialized_output_fingerprint
        or materialized.checksum != request.materialized_output_checksum
        or materialized.output_asset_reference != request.output_asset_reference
        or request.manifest_id != manifest.manifest_id
        or request.manifest_fingerprint != fingerprint(manifest)
        or request.suite_id != manifest.suite_id
        or request.suite_version != manifest.suite_version
        or request.case_reference != case.reference
        or case.reference not in manifest.case_references
        or request.evaluator != case.evaluator
        or manifest.evaluator != case.evaluator
        or request.scoring_protocol_fingerprint != protocol_fingerprint
        or protocol.run_id != request.run_id
        or protocol.suite_id != request.suite_id
        or protocol.suite_version != request.suite_version
        or request.repetition > protocol.expected_repetitions
        or request.security_snapshot_fingerprint != fingerprint(manifest.security)
        or request.event_identity.run_id != request.run_id
        or request.event_identity.case_reference != request.case_reference
        or request.event_identity.repetition != request.repetition
        or request.event_identity.materialized_output_fingerprint
        != request.materialized_output_fingerprint
        or request.event_identity.evaluator != request.evaluator
        or request.event_identity.scoring_protocol_fingerprint
        != request.scoring_protocol_fingerprint
        or response.event_identity != request.event_identity
        or response.evaluator != request.evaluator
        or response.event_identity.fingerprint != evaluation_event_fingerprint(response.event_identity)
    ):
        raise EvaluationCorrespondenceMismatch()
    if len(case_targets) != 1 or request.expected_metric.metric_id != case_targets[0].metric_id:
        raise EvaluationCorrespondenceMismatch()
    target = case_targets[0]
    if (
        target.evaluator != request.evaluator
        or target.weight != case.weight
        or target.required != case.required
        or target.critical != case.critical
    ):
        raise EvaluationCorrespondenceMismatch()
    if response.status is not CaseEvaluationStatus.SUCCEEDED:
        raise EvaluationNotSuccessful()
    validate_evaluation_scores(request, response.scores)


@dataclass(frozen=True)
class EvalResultCreationInput:
    materialized: MaterializedOutputRecord
    request: CaseEvaluationRequest
    response: CaseEvaluationResponse
    manifest: EvalRunManifest
    case: EvalCaseVersion
    protocol: ScoringProtocol
    result_id: EvalResultId
    producer_id: str
    producer_version: str
    created_at: UtcTimestamp
    idempotency_key: IdempotencyKey

    def __post_init__(self) -> None:
        if not _safe_reference(self.producer_id) or not _safe_reference(self.producer_version):
            raise EvaluationRequestInvalid()


def _result_semantic(source: EvalResultCreationInput, verdict: Verdict) -> dict[str, object]:
    response = source.response
    scores = _canonical_result_scores(source)
    return {
        "logical_result": (
            source.request.run_id,
            source.case.reference,
            source.request.repetition,
        ),
        "materialized_output_fingerprint": source.materialized.materialization_fingerprint,
        "evaluation_event": source.request.event_identity,
        "evaluator": source.request.evaluator,
        "scoring_protocol_fingerprint": source.request.scoring_protocol_fingerprint,
        "scores": scores,
        "case_verdict": verdict,
        "evaluator_artifact_reference": response.evaluator_artifact_reference,
        "provenance_reference": response.provenance_reference,
        "producer_version": source.producer_version,
    }


def _canonical_result_scores(source: EvalResultCreationInput) -> tuple[Score, ...]:
    targets = tuple(
        target for target in source.protocol.targets if target.case_reference == source.case.reference
    )
    if len(targets) != 1 or len(source.response.scores) != 1:
        raise EvaluationCorrespondenceMismatch()
    return (
        canonicalize_evaluator_score(source.request, source.response.scores[0], targets[0]),
    )


def case_result_fingerprint(source: EvalResultCreationInput, verdict: Verdict) -> Fingerprint:
    return fingerprint(_result_semantic(source, verdict))


def case_result_checksum(
    source: EvalResultCreationInput,
    verdict: Verdict,
    result_fingerprint: Fingerprint,
) -> ContentChecksum:
    return eval_result_checksum(
        _eval_result_candidate(source, verdict, result_fingerprint)
    )


def eval_result_checksum(result: EvalResult) -> ContentChecksum:
    """Recompute record integrity exclusively from fields stored on ``EvalResult``."""

    return content_checksum(
        {
            "result_id": result.result_id,
            "run_id": result.run_id,
            "case_reference": result.case_reference,
            "repetition": result.repetition,
            "execution_record_reference": result.execution_record_reference,
            "status": result.status,
            "output_asset_id": result.output_asset_id,
            "output_reference": result.output_reference,
            "output_checksum": result.output_checksum,
            "safe_summary": result.safe_summary,
            "scores": result.scores,
            "verdict": result.verdict,
            "error_code": result.error_code,
            "resource_usage": result.resource_usage,
            "evaluator_artifact_reference": result.evaluator_artifact_reference,
            "provenance_reference": result.provenance_reference,
            "result_fingerprint": result.result_fingerprint,
            "producer_id": result.producer_id,
            "producer_version": result.producer_version,
            "created_at": result.created_at,
        }
    )


def _eval_result_candidate(
    source: EvalResultCreationInput,
    verdict: Verdict,
    result_fingerprint: Fingerprint,
) -> EvalResult:
    response = source.response
    return EvalResult(
        result_id=source.result_id,
        run_id=source.request.run_id,
        case_reference=source.case.reference,
        repetition=source.request.repetition,
        execution_record_reference=source.materialized.execution_attempt_reference.value,
        status=ResultStatus.VALID,
        output_asset_id=source.materialized.output_asset_reference,
        output_reference=None,
        output_checksum=source.materialized.output_checksum,
        safe_summary="private_evals:evaluated",
        scores=_canonical_result_scores(source),
        verdict=verdict,
        error_code=None,
        resource_usage=response.resource_usage,
        evaluator_artifact_reference=response.evaluator_artifact_reference,
        provenance_reference=response.provenance_reference,
        result_fingerprint=result_fingerprint,
        producer_id=source.producer_id,
        producer_version=source.producer_version,
        created_at=source.created_at,
        checksum=ContentChecksum("0" * 64),
    )


@dataclass(frozen=True)
class EvalResultFactory:
    def create(self, source: EvalResultCreationInput) -> EvalResult:
        validate_evaluation_correspondence(
            source.materialized,
            source.request,
            source.response,
            source.manifest,
            source.case,
            source.protocol,
        )
        scores = _canonical_result_scores(source)
        thresholds = tuple(
            item
            for item in source.protocol.thresholds
            if item.scope is ThresholdScope.CASE
            and item.case_reference == source.case.reference
        )
        if len(thresholds) > 1:
            raise EvaluationCorrespondenceMismatch()
        verdict = derive_case_verdict(scores, thresholds[0] if thresholds else None)
        result_fingerprint = case_result_fingerprint(source, verdict)
        candidate = _eval_result_candidate(source, verdict, result_fingerprint)
        expected_checksum = eval_result_checksum(candidate)
        return replace(candidate, checksum=expected_checksum)


def validate_eval_result(source: EvalResultCreationInput, result: EvalResult) -> None:
    expected = EvalResultFactory().create(source)
    if (
        result.run_id != expected.run_id
        or result.case_reference != expected.case_reference
        or result.repetition != expected.repetition
        or result.execution_record_reference != expected.execution_record_reference
        or result.status is not ResultStatus.VALID
    ):
        raise EvaluationCorrespondenceMismatch()
    if (
        result.result_fingerprint != expected.result_fingerprint
        or result.checksum != expected.checksum
        or result != expected
    ):
        raise CaseResultFingerprintMismatch()


def project_scoring_observation(result: EvalResult) -> ScoringObservation:
    if result.status is not ResultStatus.VALID or len(result.scores) != 1:
        raise EvaluationCorrespondenceMismatch()
    return ScoringObservation(
        result.run_id,
        result.case_reference,
        result.repetition,
        result.status,
        tuple(sorted(result.scores, key=lambda item: item.metric_id.casefold())),
        result.result_fingerprint,
    )


@dataclass(frozen=True)
class EvalResultWriteResult:
    result: EvalResult
    disposition: WriteDisposition
    store_outcome: StoreWriteOutcome | None


@dataclass(frozen=True)
class EvalResultService:
    store: EvalRunStore
    factory: EvalResultFactory = EvalResultFactory()

    def create_result(self, source: EvalResultCreationInput) -> EvalResultWriteResult:
        candidate = self.factory.create(source)
        try:
            if self.store.result_exists(candidate.run_id, candidate.case_reference, candidate.repetition):
                existing = self.store.get_result_for_execution(candidate.run_id, candidate.case_reference, candidate.repetition)
                return self._replay_or_conflict(existing, candidate)
            outcome = self.store.save_result(candidate, idempotency_key=source.idempotency_key)
            if outcome.disposition is WriteDisposition.UPDATED:
                raise CaseResultAlreadyExists()
            if outcome.disposition is WriteDisposition.IDEMPOTENT_REPLAY:
                existing = self.store.get_result_for_execution(candidate.run_id, candidate.case_reference, candidate.repetition)
                return self._replay_or_conflict(existing, candidate, outcome)
            if outcome.checksum != candidate.checksum:
                raise CaseResultAlreadyExists()
            return EvalResultWriteResult(candidate, WriteDisposition.CREATED, outcome)
        except EvalDuplicateRecord:
            return self._recover_duplicate(candidate)
        except EvalIntegrityConflict as exc:
            raise CaseResultAlreadyExists() from exc
        except EvalIdempotencyConflict as exc:
            raise CaseResultIdempotencyConflict() from exc
        except EvalStoreUnavailable as exc:
            raise CaseResultPersistenceUnavailable() from exc
        except EvalInvalidStoreQuery as exc:
            raise CaseResultPersistenceInvalid() from exc
        except EvalRecordNotFound as exc:
            raise CaseResultPersistenceNotFound() from exc

    def _recover_duplicate(self, candidate: EvalResult) -> EvalResultWriteResult:
        try:
            existing = self.store.get_result_for_execution(candidate.run_id, candidate.case_reference, candidate.repetition)
        except EvalStoreUnavailable as exc:
            raise CaseResultPersistenceUnavailable() from exc
        except EvalRecordNotFound as exc:
            raise CaseResultPersistenceNotFound() from exc
        return self._replay_or_conflict(existing, candidate)

    @staticmethod
    def _replay_or_conflict(
        existing: EvalResult,
        candidate: EvalResult,
        outcome: StoreWriteOutcome | None = None,
    ) -> EvalResultWriteResult:
        if (
            existing.run_id != candidate.run_id
            or existing.case_reference != candidate.case_reference
            or existing.repetition != candidate.repetition
            or existing.result_fingerprint != candidate.result_fingerprint
        ):
            raise CaseResultAlreadyExists()
        return EvalResultWriteResult(existing, WriteDisposition.IDEMPOTENT_REPLAY, outcome)
