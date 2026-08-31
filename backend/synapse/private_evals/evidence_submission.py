from __future__ import annotations

from dataclasses import dataclass

from synapse.project_governance.models import EvalReference, RFCImplementationBinding

from .evidence import (
    EvalEvidenceProjection,
    EvalEvidenceSource,
    EvidenceMetric,
    EvidenceMetricAllowlist,
    EvidenceProjectionKind,
    GovernanceEvidenceBinding,
    ProjectionReadinessStatus,
    ProjectionReasonCode,
)
from .evidence_errors import EvalEvidenceError
from .evidence_projection import EvalEvidenceProjectionFactory
from .evidence_submission_errors import (
    EvidenceImplementationBindingMismatch,
    EvidencePlanIncomplete,
    EvidencePlanInvalid,
    EvidenceProjectionFingerprintMismatch,
    EvidenceProjectionKindInvalid,
    EvidenceSourceMismatch,
)
from .evidence_submission_models import (
    EvalEvidenceSubmissionPlan,
    EvidenceProjectionSpecification,
)
from .run_finalization_models import (
    EvalRunFinalizationRecord,
    RunFinalizationPath,
    RunTerminalCause,
    validate_finalization_record,
)
from .run_scoring import RunScoringDecision, run_scoring_decision_checksum
from .states import Verdict
from .store_models import IdempotencyKey
from .values import UtcTimestamp


@dataclass(frozen=True)
class EvidenceProjectionCandidate:
    binding: GovernanceEvidenceBinding
    eval_reference: EvalReference
    source_record_reference: str
    source: EvalEvidenceSource
    allowlist: EvidenceMetricAllowlist
    metrics: tuple[EvidenceMetric, ...] = ()


@dataclass(frozen=True)
class EvalEvidencePlanningInput:
    finalization: EvalRunFinalizationRecord
    implementation: RFCImplementationBinding
    implementation_binding_reference: str
    candidates: tuple[EvidenceProjectionCandidate, ...]
    scoring_decision: RunScoringDecision | None
    idempotency_key: IdempotencyKey
    correlation_reference: str
    producer_id: str
    producer_version: str
    created_at: UtcTimestamp

    def __repr__(self) -> str:
        return (
            "EvalEvidencePlanningInput("
            f"run_id={self.finalization.run_id!r}, candidate_count={len(self.candidates)!r})"
        )


@dataclass(frozen=True)
class EvidencePlanReadiness:
    status: ProjectionReadinessStatus
    plan: EvalEvidenceSubmissionPlan | None = None


@dataclass(frozen=True)
class EvalEvidenceSubmissionPlanner:
    projection_factory: EvalEvidenceProjectionFactory = EvalEvidenceProjectionFactory()

    def assess(self, source: EvalEvidencePlanningInput) -> EvidencePlanReadiness:
        try:
            plan = self._build(source)
        except EvidencePlanIncomplete:
            return EvidencePlanReadiness(ProjectionReadinessStatus.INCOMPLETE)
        except (
            EvidencePlanInvalid,
            EvidenceImplementationBindingMismatch,
            EvidenceProjectionFingerprintMismatch,
            EvidenceProjectionKindInvalid,
            EvidenceSourceMismatch,
            EvalEvidenceError,
            ValueError,
        ):
            return EvidencePlanReadiness(ProjectionReadinessStatus.INVALID)
        if not plan.specifications:
            return EvidencePlanReadiness(ProjectionReadinessStatus.NOT_APPLICABLE, plan)
        return EvidencePlanReadiness(ProjectionReadinessStatus.READY, plan)

    def create(self, source: EvalEvidencePlanningInput) -> EvalEvidenceSubmissionPlan:
        readiness = self.assess(source)
        if readiness.status is ProjectionReadinessStatus.INCOMPLETE:
            raise EvidencePlanIncomplete()
        if readiness.status is ProjectionReadinessStatus.INVALID or readiness.plan is None:
            raise EvidencePlanInvalid()
        return readiness.plan

    def construct_projections(
        self,
        source: EvalEvidencePlanningInput,
        plan: EvalEvidenceSubmissionPlan,
    ) -> tuple[EvalEvidenceProjection, ...]:
        candidates = {item.binding.projection_kind: item for item in source.candidates}
        projections: list[EvalEvidenceProjection] = []
        for specification in plan.specifications:
            candidate = candidates[specification.projection_kind]
            try:
                projection = self.projection_factory.create(
                    binding=candidate.binding,
                    expected_binding=source.implementation,
                    eval_reference=candidate.eval_reference,
                    source=candidate.source,
                    allowlist=candidate.allowlist,
                    metrics=candidate.metrics,
                )
            except EvalEvidenceError as exc:
                raise EvidencePlanInvalid() from exc
            if projection.fingerprint != specification.expected_projection_fingerprint:
                raise EvidenceProjectionFingerprintMismatch()
            projections.append(projection)
        return tuple(projections)

    def _build(self, source: EvalEvidencePlanningInput) -> EvalEvidenceSubmissionPlan:
        self._validate_finalization(source)
        kinds = tuple(item.binding.projection_kind for item in source.candidates)
        if len(kinds) != len(set(kinds)):
            raise EvidencePlanInvalid()
        allowed, required = self._selected_kinds(source)
        if any(kind not in allowed for kind in kinds):
            raise EvidenceProjectionKindInvalid()
        if any(kind not in kinds for kind in required):
            raise EvidencePlanIncomplete()
        projections: list[tuple[EvidenceProjectionCandidate, EvalEvidenceProjection]] = []
        for candidate in source.candidates:
            self._validate_candidate(source, candidate)
            readiness = self.projection_factory.assess(
                binding=candidate.binding,
                expected_binding=source.implementation,
                eval_reference=candidate.eval_reference,
                source=candidate.source,
            )
            if readiness.status is ProjectionReadinessStatus.INCOMPLETE:
                raise EvidencePlanIncomplete()
            if readiness.status is not ProjectionReadinessStatus.READY:
                raise EvidencePlanInvalid()
            projection = self.projection_factory.create(
                binding=candidate.binding,
                expected_binding=source.implementation,
                eval_reference=candidate.eval_reference,
                source=candidate.source,
                allowlist=candidate.allowlist,
                metrics=candidate.metrics,
            )
            projections.append((candidate, projection))
        projections.sort(key=lambda item: item[0].binding.projection_kind.value)
        finalization = source.finalization
        assert finalization.fingerprint is not None
        finalization_reference = f"private-evals-finalization:{finalization.finalization_id.value}"
        specification_items: list[EvidenceProjectionSpecification] = []
        for candidate, projection in projections:
            source_fingerprint = candidate.source.fingerprint
            if source_fingerprint is None:
                raise EvidenceSourceMismatch()
            specification_items.append(
                EvidenceProjectionSpecification(
                    projection_kind=candidate.binding.projection_kind,
                    source_record_reference=candidate.source_record_reference,
                    source_fingerprint=source_fingerprint,
                    finalization_reference=finalization_reference,
                    finalization_fingerprint=finalization.fingerprint,
                    scoring_decision_reference=finalization.scoring_decision_reference,
                    terminal_failure_set_reference=finalization.terminal_failure_set_fingerprint,
                    reproducibility_fingerprint=finalization.reproducibility_fingerprint,
                    security_snapshot_reference=finalization.security_snapshot_reference,
                    security_snapshot_fingerprint=finalization.security_snapshot_fingerprint,
                    implementation_binding_reference=source.implementation_binding_reference,
                    expected_projection_fingerprint=projection.fingerprint,
                )
            )
        specifications = tuple(specification_items)
        return EvalEvidenceSubmissionPlan(
            run_id=finalization.run_id,
            finalization_reference=finalization_reference,
            finalization_fingerprint=finalization.fingerprint,
            implementation=source.implementation,
            implementation_binding_reference=source.implementation_binding_reference,
            specifications=specifications,
            idempotency_key=source.idempotency_key,
            correlation_reference=source.correlation_reference,
            producer_id=source.producer_id,
            producer_version=source.producer_version,
            created_at=source.created_at,
        )

    @staticmethod
    def _selected_kinds(
        source: EvalEvidencePlanningInput,
    ) -> tuple[set[EvidenceProjectionKind], set[EvidenceProjectionKind]]:
        finalization = source.finalization
        if finalization.path is RunFinalizationPath.SCORABLE:
            return {EvidenceProjectionKind.EVAL_RESULT}, {EvidenceProjectionKind.EVAL_RESULT}
        allowed: set[EvidenceProjectionKind] = set()
        required: set[EvidenceProjectionKind] = set()
        if RunTerminalCause.POLICY_DENIAL in finalization.terminal_causes:
            allowed.add(EvidenceProjectionKind.POLICY_BLOCK)
            required.add(EvidenceProjectionKind.POLICY_BLOCK)
        reproducibility_proven = any(
            candidate.binding.projection_kind is EvidenceProjectionKind.REPRODUCIBILITY_FAILURE
            and ProjectionReasonCode.REPRODUCIBILITY_INVALID in candidate.source.reason_codes
            for candidate in source.candidates
        )
        if (
            RunTerminalCause.INVALID_RESPONSE in finalization.terminal_causes
            and reproducibility_proven
        ):
            allowed.add(EvidenceProjectionKind.REPRODUCIBILITY_FAILURE)
            required.add(EvidenceProjectionKind.REPRODUCIBILITY_FAILURE)
        return allowed, required

    @staticmethod
    def _validate_finalization(source: EvalEvidencePlanningInput) -> None:
        try:
            validate_finalization_record(source.finalization)
        except Exception as exc:
            raise EvidencePlanInvalid() from exc
        finalization = source.finalization
        decision = source.scoring_decision
        if finalization.path is RunFinalizationPath.SCORABLE:
            if decision is None:
                raise EvidencePlanIncomplete()
            if (
                decision.checksum != run_scoring_decision_checksum(decision)
                or decision.run_id != finalization.run_id
                or decision.manifest_fingerprint != finalization.manifest_fingerprint
                or decision.suite_id != finalization.suite_id
                or decision.suite_version != finalization.suite_version
                or decision.decision_fingerprint != finalization.scoring_decision_reference
            ):
                raise EvidenceSourceMismatch()
        elif decision is not None:
            raise EvidenceSourceMismatch()

    @staticmethod
    def _validate_candidate(
        source: EvalEvidencePlanningInput,
        candidate: EvidenceProjectionCandidate,
    ) -> None:
        finalization = source.finalization
        projection_source = candidate.source
        binding = candidate.binding
        if binding.implementation != source.implementation:
            raise EvidenceImplementationBindingMismatch()
        if binding.implementation_binding_reference != source.implementation_binding_reference:
            raise EvidenceImplementationBindingMismatch()
        if (
            projection_source.run_id != finalization.run_id
            or projection_source.suite_id != finalization.suite_id
            or projection_source.suite_version != finalization.suite_version
            or projection_source.finalization_reference is None
            or projection_source.finalization_fingerprint != finalization.fingerprint
            or projection_source.security_snapshot_reference
            != finalization.security_snapshot_reference
            or projection_source.security_snapshot_fingerprint
            != finalization.security_snapshot_fingerprint
        ):
            raise EvidenceSourceMismatch()
        kind = binding.projection_kind
        if kind is EvidenceProjectionKind.EVAL_RESULT:
            decision = source.scoring_decision
            assert decision is not None
            if (
                projection_source.finalization_fingerprint != finalization.fingerprint
                or projection_source.scoring_decision_fingerprint != decision.decision_fingerprint
                or projection_source.verdict is not decision.verdict
            ):
                raise EvidenceSourceMismatch()
        elif kind is EvidenceProjectionKind.POLICY_BLOCK:
            if (
                RunTerminalCause.POLICY_DENIAL not in finalization.terminal_causes
                or projection_source.verdict not in {Verdict.BLOCKED, Verdict.POLICY_DENIED}
            ):
                raise EvidenceSourceMismatch()
        elif kind is EvidenceProjectionKind.REPRODUCIBILITY_FAILURE:
            if (
                RunTerminalCause.INVALID_RESPONSE not in finalization.terminal_causes
                or projection_source.run_manifest_fingerprint != finalization.manifest_fingerprint
                or ProjectionReasonCode.REPRODUCIBILITY_INVALID
                not in projection_source.reason_codes
            ):
                raise EvidenceSourceMismatch()
        else:
            raise EvidenceProjectionKindInvalid()
