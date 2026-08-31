from __future__ import annotations

import re
from dataclasses import dataclass, replace
from enum import StrEnum

from .canonical import content_checksum, fingerprint
from .case_evaluation import (
    derive_case_verdict,
    eval_result_checksum,
    project_scoring_observation,
)
from .catalog import EvalCaseVersionRef, EvaluatorIdentity
from .run_scoring_errors import (
    DuplicateLogicalResult,
    ExpectedResultMissing,
    RunResultCorrespondenceMismatch,
    RunResultFingerprintMismatch,
    RunScoringDecisionMismatch,
    RunScoringInputInvalid,
    RunScoringObservationMismatch,
    RunScoringProtocolMismatch,
    RunScoringTargetMismatch,
    UnexpectedRunResult,
)
from .runs import EvalResult, EvalRunManifest
from .scoring import (
    ScoringDecision,
    ScoringEngine,
    ScoringObservation,
    ScoringProtocol,
    ThresholdScope,
)
from .states import DeterminismMode, ResultStatus, Verdict
from .store_models import IdempotencyKey
from .values import (
    ContentChecksum,
    EvalResultId,
    EvalRunId,
    EvalRunManifestId,
    EvalSuiteId,
    EvalVersion,
    Fingerprint,
    ScoringDecisionId,
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


def _case_key(reference: EvalCaseVersionRef) -> tuple[str, str]:
    return reference.case_id.value, reference.version.value


@dataclass(frozen=True, order=True)
class ExpectedResultSlot:
    case_reference: EvalCaseVersionRef
    repetition: int

    def __post_init__(self) -> None:
        if not isinstance(self.case_reference, EvalCaseVersionRef):
            raise RunScoringInputInvalid()
        if (
            isinstance(self.repetition, bool)
            or not isinstance(self.repetition, int)
            or self.repetition < 1
        ):
            raise RunScoringInputInvalid()


@dataclass(frozen=True)
class ExpectedExecutionMatrix:
    manifest_id: EvalRunManifestId
    manifest_fingerprint: Fingerprint
    suite_id: EvalSuiteId
    suite_version: EvalVersion
    evaluator: EvaluatorIdentity
    determinism_mode: DeterminismMode
    expected_repetitions: int
    slots: tuple[ExpectedResultSlot, ...]
    fingerprint: Fingerprint | None = None

    def __post_init__(self) -> None:
        typed = (
            (self.manifest_id, EvalRunManifestId),
            (self.manifest_fingerprint, Fingerprint),
            (self.suite_id, EvalSuiteId),
            (self.suite_version, EvalVersion),
            (self.evaluator, EvaluatorIdentity),
            (self.determinism_mode, DeterminismMode),
        )
        if any(not isinstance(value, expected) for value, expected in typed):
            raise RunScoringInputInvalid()
        if (
            isinstance(self.expected_repetitions, bool)
            or not isinstance(self.expected_repetitions, int)
            or self.expected_repetitions < 1
            or not isinstance(self.slots, tuple)
            or not self.slots
            or any(not isinstance(slot, ExpectedResultSlot) for slot in self.slots)
            or len(self.slots) != len(set(self.slots))
        ):
            raise RunScoringInputInvalid()
        ordered = tuple(
            sorted(
                self.slots,
                key=lambda slot: (*_case_key(slot.case_reference), slot.repetition),
            )
        )
        object.__setattr__(self, "slots", ordered)
        expected_fingerprint = expected_execution_matrix_fingerprint(self)
        if self.fingerprint is None:
            object.__setattr__(self, "fingerprint", expected_fingerprint)
        elif not isinstance(self.fingerprint, Fingerprint) or self.fingerprint != expected_fingerprint:
            raise RunScoringInputInvalid()


def expected_execution_matrix_fingerprint(matrix: ExpectedExecutionMatrix) -> Fingerprint:
    return fingerprint(
        {
            "manifest_fingerprint": matrix.manifest_fingerprint,
            "suite": (matrix.suite_id, matrix.suite_version),
            "evaluator": matrix.evaluator,
            "determinism_mode": matrix.determinism_mode,
            "expected_repetitions": matrix.expected_repetitions,
            "slots": matrix.slots,
        }
    )


def create_expected_execution_matrix(
    manifest: EvalRunManifest,
    protocol: ScoringProtocol,
) -> ExpectedExecutionMatrix:
    if (
        not isinstance(manifest, EvalRunManifest)
        or not isinstance(protocol, ScoringProtocol)
        or protocol.suite_id != manifest.suite_id
        or protocol.suite_version != manifest.suite_version
        or protocol.expected_repetitions != manifest.execution.repetitions
        or protocol.determinism_mode is not manifest.execution.determinism_mode
        or {target.case_reference for target in protocol.targets}
        != set(manifest.case_references)
        or any(target.evaluator != manifest.evaluator for target in protocol.targets)
    ):
        raise RunScoringProtocolMismatch()
    slots = tuple(
        ExpectedResultSlot(case_reference, repetition)
        for case_reference in manifest.case_references
        for repetition in range(1, protocol.expected_repetitions + 1)
    )
    return ExpectedExecutionMatrix(
        manifest.manifest_id,
        fingerprint(manifest),
        manifest.suite_id,
        manifest.suite_version,
        manifest.evaluator,
        manifest.execution.determinism_mode,
        protocol.expected_repetitions,
        slots,
    )


class RunScoringEligibilityStatus(StrEnum):
    READY = "ready"
    INCOMPLETE = "incomplete"
    INVALID = "invalid"


@dataclass(frozen=True)
class RunScoringEligibility:
    status: RunScoringEligibilityStatus
    missing_slots: tuple[ExpectedResultSlot, ...] = ()


@dataclass(frozen=True)
class RunScoringInput:
    run_id: EvalRunId
    manifest_id: EvalRunManifestId
    manifest_fingerprint: Fingerprint
    suite_id: EvalSuiteId
    suite_version: EvalVersion
    protocol: ScoringProtocol
    scoring_protocol_fingerprint: Fingerprint
    expected_matrix: ExpectedExecutionMatrix
    results: tuple[EvalResult, ...]
    decision_id: ScoringDecisionId
    producer_id: str
    producer_version: str
    created_at: UtcTimestamp
    idempotency_key: IdempotencyKey
    correlation_reference: str

    def __post_init__(self) -> None:
        typed = (
            (self.run_id, EvalRunId),
            (self.manifest_id, EvalRunManifestId),
            (self.manifest_fingerprint, Fingerprint),
            (self.suite_id, EvalSuiteId),
            (self.suite_version, EvalVersion),
            (self.protocol, ScoringProtocol),
            (self.scoring_protocol_fingerprint, Fingerprint),
            (self.expected_matrix, ExpectedExecutionMatrix),
            (self.decision_id, ScoringDecisionId),
            (self.created_at, UtcTimestamp),
            (self.idempotency_key, IdempotencyKey),
        )
        if any(not isinstance(value, expected) for value, expected in typed):
            raise RunScoringInputInvalid()
        if not isinstance(self.results, tuple) or any(
            not isinstance(result, EvalResult) for result in self.results
        ):
            raise RunScoringInputInvalid()
        if not all(
            _safe_reference(value)
            for value in (self.producer_id, self.producer_version, self.correlation_reference)
        ):
            raise RunScoringInputInvalid()
        ordered = tuple(
            sorted(
                self.results,
                key=lambda result: (*_case_key(result.case_reference), result.repetition),
            )
        )
        object.__setattr__(self, "results", ordered)

    def __repr__(self) -> str:
        return (
            "RunScoringInput("
            f"run_id={self.run_id!r}, decision_id={self.decision_id!r}, "
            f"result_count={len(self.results)!r})"
        )


def assess_run_scoring_eligibility(source: RunScoringInput) -> RunScoringEligibility:
    if not isinstance(source, RunScoringInput):
        raise RunScoringInputInvalid()
    expected = set(source.expected_matrix.slots)
    actual_slots = tuple(
        ExpectedResultSlot(result.case_reference, result.repetition)
        for result in source.results
    )
    actual = set(actual_slots)
    if len(actual_slots) != len(actual) or actual - expected:
        return RunScoringEligibility(RunScoringEligibilityStatus.INVALID)
    if any(result.run_id != source.run_id for result in source.results):
        return RunScoringEligibility(RunScoringEligibilityStatus.INVALID)
    missing = tuple(
        sorted(
            expected - actual,
            key=lambda slot: (*_case_key(slot.case_reference), slot.repetition),
        )
    )
    if missing:
        return RunScoringEligibility(RunScoringEligibilityStatus.INCOMPLETE, missing)
    return RunScoringEligibility(RunScoringEligibilityStatus.READY)


@dataclass(frozen=True)
class ScoringResultReference:
    result_id: EvalResultId
    case_reference: EvalCaseVersionRef
    repetition: int
    result_fingerprint: Fingerprint
    checksum: ContentChecksum

    def __post_init__(self) -> None:
        typed = (
            (self.result_id, EvalResultId),
            (self.case_reference, EvalCaseVersionRef),
            (self.result_fingerprint, Fingerprint),
            (self.checksum, ContentChecksum),
        )
        if any(not isinstance(value, expected) for value, expected in typed) or (
            isinstance(self.repetition, bool)
            or not isinstance(self.repetition, int)
            or self.repetition < 1
        ):
            raise RunScoringDecisionMismatch()


@dataclass(frozen=True)
class RunScoringDecision:
    decision_id: ScoringDecisionId
    run_id: EvalRunId
    manifest_id: EvalRunManifestId
    manifest_fingerprint: Fingerprint
    suite_id: EvalSuiteId
    suite_version: EvalVersion
    scoring_protocol_fingerprint: Fingerprint
    expected_matrix_fingerprint: Fingerprint
    expected_result_count: int
    result_references: tuple[ScoringResultReference, ...]
    result_set_fingerprint: Fingerprint
    observation_fingerprints: tuple[Fingerprint, ...]
    aggregate: ScoringDecision
    decision_fingerprint: Fingerprint
    producer_id: str
    producer_version: str
    created_at: UtcTimestamp
    checksum: ContentChecksum

    def __post_init__(self) -> None:
        typed = (
            (self.decision_id, ScoringDecisionId),
            (self.run_id, EvalRunId),
            (self.manifest_id, EvalRunManifestId),
            (self.manifest_fingerprint, Fingerprint),
            (self.suite_id, EvalSuiteId),
            (self.suite_version, EvalVersion),
            (self.scoring_protocol_fingerprint, Fingerprint),
            (self.expected_matrix_fingerprint, Fingerprint),
            (self.result_set_fingerprint, Fingerprint),
            (self.aggregate, ScoringDecision),
            (self.decision_fingerprint, Fingerprint),
            (self.created_at, UtcTimestamp),
            (self.checksum, ContentChecksum),
        )
        if any(not isinstance(value, expected) for value, expected in typed):
            raise RunScoringDecisionMismatch()
        if (
            not self.result_references
            or any(
                not isinstance(reference, ScoringResultReference)
                for reference in self.result_references
            )
            or len(self.result_references) != len(
                {
                    (reference.case_reference, reference.repetition)
                    for reference in self.result_references
                }
            )
            or isinstance(self.expected_result_count, bool)
            or not isinstance(self.expected_result_count, int)
            or self.expected_result_count < 1
            or len(self.result_references) != self.expected_result_count
            or len(self.observation_fingerprints) != len(self.result_references)
            or any(
                not isinstance(value, Fingerprint)
                for value in self.observation_fingerprints
            )
            or self.aggregate.run_id != self.run_id
            or not _safe_reference(self.producer_id)
            or not _safe_reference(self.producer_version)
        ):
            raise RunScoringDecisionMismatch()
        ordered = tuple(
            sorted(
                self.result_references,
                key=lambda reference: (
                    *_case_key(reference.case_reference),
                    reference.repetition,
                ),
            )
        )
        if self.result_references != ordered:
            raise RunScoringDecisionMismatch()

    @property
    def verdict(self) -> Verdict:
        return self.aggregate.verdict

    @property
    def coverage(self) -> tuple[int, int]:
        return len(self.result_references), self.expected_result_count

    def __repr__(self) -> str:
        return (
            "RunScoringDecision("
            f"decision_id={self.decision_id!r}, run_id={self.run_id!r}, "
            f"verdict={self.verdict!r}, decision_fingerprint={self.decision_fingerprint!r})"
        )


def scoring_observation_fingerprint(observation: ScoringObservation) -> Fingerprint:
    return fingerprint(
        {
            "run_id": observation.run_id,
            "case_reference": observation.case_reference,
            "repetition": observation.repetition,
            "result_status": observation.result_status,
            "scores": observation.scores,
            "result_fingerprint": observation.result_fingerprint,
        }
    )


def scoring_result_set_fingerprint(
    references: tuple[ScoringResultReference, ...],
) -> Fingerprint:
    return fingerprint(
        tuple(
            (
                reference.case_reference,
                reference.repetition,
                reference.result_fingerprint,
            )
            for reference in references
        )
    )


def run_scoring_decision_fingerprint(
    source: RunScoringInput,
    result_set_fingerprint: Fingerprint,
    observation_fingerprints: tuple[Fingerprint, ...],
    aggregate: ScoringDecision,
) -> Fingerprint:
    return fingerprint(
        {
            "run_id": source.run_id,
            "manifest_fingerprint": source.manifest_fingerprint,
            "suite": (source.suite_id, source.suite_version),
            "scoring_protocol_fingerprint": source.scoring_protocol_fingerprint,
            "expected_matrix_fingerprint": source.expected_matrix.fingerprint,
            "result_set_fingerprint": result_set_fingerprint,
            "observation_fingerprints": observation_fingerprints,
            "aggregation_configuration": ScoringEngine._protocol_identity(source.protocol),
            "aggregate": aggregate,
            "producer_version": source.producer_version,
        }
    )


def run_scoring_decision_checksum(decision: RunScoringDecision) -> ContentChecksum:
    return content_checksum(
        {
            "decision_id": decision.decision_id,
            "run_id": decision.run_id,
            "manifest": (decision.manifest_id, decision.manifest_fingerprint),
            "suite": (decision.suite_id, decision.suite_version),
            "scoring_protocol_fingerprint": decision.scoring_protocol_fingerprint,
            "expected_matrix_fingerprint": decision.expected_matrix_fingerprint,
            "expected_result_count": decision.expected_result_count,
            "result_references": decision.result_references,
            "result_set_fingerprint": decision.result_set_fingerprint,
            "observation_fingerprints": decision.observation_fingerprints,
            "aggregate": decision.aggregate,
            "decision_fingerprint": decision.decision_fingerprint,
            "producer_id": decision.producer_id,
            "producer_version": decision.producer_version,
            "created_at": decision.created_at,
        }
    )


@dataclass(frozen=True)
class ScoringDecisionFactory:
    engine: ScoringEngine = ScoringEngine()

    def create(self, source: RunScoringInput) -> RunScoringDecision:
        self._validate_input(source)
        results = self._validate_results(source)
        observations = tuple(project_scoring_observation(result) for result in results)
        self._validate_observations(source, observations)
        aggregate = self.engine.score(source.protocol, observations)
        self.engine.validate_decision(source.protocol, observations, aggregate)
        references = tuple(
            ScoringResultReference(
                result.result_id,
                result.case_reference,
                result.repetition,
                result.result_fingerprint,
                result.checksum,
            )
            for result in results
        )
        result_set_fingerprint = scoring_result_set_fingerprint(references)
        observation_fingerprints = tuple(
            scoring_observation_fingerprint(observation) for observation in observations
        )
        decision_fingerprint = run_scoring_decision_fingerprint(
            source,
            result_set_fingerprint,
            observation_fingerprints,
            aggregate,
        )
        matrix_fingerprint = source.expected_matrix.fingerprint
        assert matrix_fingerprint is not None
        candidate = RunScoringDecision(
            source.decision_id,
            source.run_id,
            source.manifest_id,
            source.manifest_fingerprint,
            source.suite_id,
            source.suite_version,
            source.scoring_protocol_fingerprint,
            matrix_fingerprint,
            len(source.expected_matrix.slots),
            references,
            result_set_fingerprint,
            observation_fingerprints,
            aggregate,
            decision_fingerprint,
            source.producer_id,
            source.producer_version,
            source.created_at,
            ContentChecksum("0" * 64),
        )
        return replace(candidate, checksum=run_scoring_decision_checksum(candidate))

    @staticmethod
    def _validate_input(source: RunScoringInput) -> None:
        if not isinstance(source, RunScoringInput):
            raise RunScoringInputInvalid()
        protocol = source.protocol
        matrix = source.expected_matrix
        if (
            source.manifest_id != matrix.manifest_id
            or source.manifest_fingerprint != matrix.manifest_fingerprint
            or source.suite_id != matrix.suite_id
            or source.suite_version != matrix.suite_version
            or protocol.run_id != source.run_id
            or protocol.suite_id != source.suite_id
            or protocol.suite_version != source.suite_version
            or source.scoring_protocol_fingerprint != fingerprint(protocol)
            or matrix.expected_repetitions != protocol.expected_repetitions
            or matrix.determinism_mode is not protocol.determinism_mode
            or any(target.evaluator != matrix.evaluator for target in protocol.targets)
            or {slot.case_reference for slot in matrix.slots}
            != {target.case_reference for target in protocol.targets}
        ):
            raise RunScoringProtocolMismatch()

    @staticmethod
    def _validate_results(source: RunScoringInput) -> tuple[EvalResult, ...]:
        eligibility = assess_run_scoring_eligibility(source)
        if eligibility.status is RunScoringEligibilityStatus.INCOMPLETE:
            raise ExpectedResultMissing()
        expected = set(source.expected_matrix.slots)
        seen: set[ExpectedResultSlot] = set()
        targets = {target.case_reference: target for target in source.protocol.targets}
        for result in source.results:
            slot = ExpectedResultSlot(result.case_reference, result.repetition)
            if slot in seen:
                raise DuplicateLogicalResult()
            seen.add(slot)
            if result.run_id != source.run_id:
                raise RunResultCorrespondenceMismatch()
            if slot not in expected:
                raise UnexpectedRunResult()
            if result.status is not ResultStatus.VALID or len(result.scores) != 1:
                raise RunResultCorrespondenceMismatch()
            if result.checksum != eval_result_checksum(result):
                raise RunResultFingerprintMismatch()
            if not _safe_reference(result.producer_id) or not _safe_reference(
                result.producer_version
            ):
                raise RunResultCorrespondenceMismatch()
            target = targets.get(result.case_reference)
            if target is None:
                raise RunScoringTargetMismatch()
            score = result.scores[0]
            if (
                score.metric_id.casefold() != target.metric_id
                or score.evaluator != target.evaluator
                or score.weight != target.weight
                or score.required != target.required
                or score.critical != target.critical
            ):
                raise RunScoringTargetMismatch()
            thresholds = tuple(
                threshold
                for threshold in source.protocol.thresholds
                if threshold.scope is ThresholdScope.CASE
                and threshold.case_reference == result.case_reference
                and threshold.metric_id == target.metric_id
            )
            local_threshold = thresholds[0] if thresholds else None
            if result.verdict is not derive_case_verdict(result.scores, local_threshold):
                raise RunResultCorrespondenceMismatch()
        if eligibility.status is RunScoringEligibilityStatus.INVALID:
            raise RunScoringInputInvalid()
        return source.results

    @staticmethod
    def _validate_observations(
        source: RunScoringInput,
        observations: tuple[ScoringObservation, ...],
    ) -> None:
        if len(observations) != len(source.results):
            raise RunScoringObservationMismatch()
        for result, observation in zip(source.results, observations, strict=True):
            if (
                observation.run_id != result.run_id
                or observation.case_reference != result.case_reference
                or observation.repetition != result.repetition
                or observation.result_status is not ResultStatus.VALID
                or observation.result_fingerprint != result.result_fingerprint
                or observation.scores != result.scores
            ):
                raise RunScoringObservationMismatch()


def validate_run_scoring_decision(
    source: RunScoringInput,
    decision: RunScoringDecision,
) -> None:
    expected = ScoringDecisionFactory().create(source)
    if decision != expected or decision.checksum != run_scoring_decision_checksum(decision):
        raise RunScoringDecisionMismatch()
