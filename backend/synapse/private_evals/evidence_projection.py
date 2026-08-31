from __future__ import annotations

from dataclasses import dataclass

from synapse.project_governance.contracts import RFCEvidenceWritePort
from synapse.project_governance.models import (
    EvalReference,
    EvidenceRecord,
    RFCImplementationBinding,
)

from .analysis import CompatibilityStatus
from .canonical import content_checksum, fingerprint
from .evidence import (
    EvalEvidenceProjection,
    EvalEvidenceSource,
    EvidenceMetric,
    EvidenceMetricAllowlist,
    EvidenceProjectionKind,
    GovernanceEvidenceBinding,
    ProjectionReadiness,
    ProjectionReadinessStatus,
    ProjectionReasonCode,
    validate_evidence_reference,
)
from .evidence_errors import (
    EvalRequirementMismatch,
    GovernanceBindingMismatch,
    IncompatibleEvidenceSource,
    IncompleteEvidence,
    InvalidEvidenceSource,
    MetricNotAllowed,
)
from .states import Verdict
from .values import UtcTimestamp

_SOURCE_FIELDS = {
    "scoring": ("scoring_decision_reference", "scoring_decision_fingerprint"),
    "baseline": ("baseline_id",),
    "comparison": ("comparison_id",),
    "compatibility": ("compatibility_status",),
    "regression_rule": ("regression_rule_reference", "regression_rule_fingerprint"),
    "regression_report": ("regression_report_id", "regression_report_fingerprint"),
    "regression_classification": ("regression_classification",),
    "security_decision": ("security_decision_reference", "security_decision_fingerprint"),
}


@dataclass(frozen=True)
class EvalEvidenceProjectionFactory:
    """Pure selection, minimization and integrity factory for eval facts."""

    def assess(
        self,
        *,
        binding: GovernanceEvidenceBinding,
        expected_binding: RFCImplementationBinding,
        eval_reference: EvalReference,
        source: EvalEvidenceSource,
    ) -> ProjectionReadiness:
        self._validate_local_correlation(binding, expected_binding, eval_reference, source)
        if not source.applicable:
            return ProjectionReadiness(ProjectionReadinessStatus.NOT_APPLICABLE, False, ())
        kind = binding.projection_kind
        if self._missing_requirements(kind, source):
            return ProjectionReadiness(ProjectionReadinessStatus.INCOMPLETE, False, ())
        if self._has_forbidden_artifacts(kind, source):
            return ProjectionReadiness(
                ProjectionReadinessStatus.INVALID,
                False,
                source.reason_codes,
            )
        if kind is EvidenceProjectionKind.POLICY_BLOCK and source.verdict not in {
            Verdict.BLOCKED,
            Verdict.POLICY_DENIED,
        }:
            return ProjectionReadiness(
                ProjectionReadinessStatus.INVALID,
                False,
                source.reason_codes,
            )
        if kind is EvidenceProjectionKind.COMPATIBILITY_FAILURE and (
            source.compatibility_status is not CompatibilityStatus.INCOMPATIBLE
        ):
            return ProjectionReadiness(
                ProjectionReadinessStatus.INVALID,
                False,
                source.reason_codes,
            )
        if kind is EvidenceProjectionKind.REPRODUCIBILITY_FAILURE and (
            source.verdict is not Verdict.INVALID
            or ProjectionReasonCode.REPRODUCIBILITY_INVALID not in source.reason_codes
        ):
            return ProjectionReadiness(
                ProjectionReadinessStatus.INVALID,
                False,
                source.reason_codes,
            )
        return ProjectionReadiness(
            ProjectionReadinessStatus.READY,
            True,
            source.reason_codes,
        )

    def create(
        self,
        *,
        binding: GovernanceEvidenceBinding,
        expected_binding: RFCImplementationBinding,
        eval_reference: EvalReference,
        source: EvalEvidenceSource,
        allowlist: EvidenceMetricAllowlist,
        metrics: tuple[EvidenceMetric, ...],
    ) -> EvalEvidenceProjection:
        readiness = self.assess(
            binding=binding,
            expected_binding=expected_binding,
            eval_reference=eval_reference,
            source=source,
        )
        if readiness.status in {
            ProjectionReadinessStatus.INCOMPLETE,
            ProjectionReadinessStatus.NOT_APPLICABLE,
        }:
            raise IncompleteEvidence("evidence source is not ready for projection")
        if not readiness.eligible:
            if binding.projection_kind is EvidenceProjectionKind.COMPATIBILITY_FAILURE:
                raise IncompatibleEvidenceSource("compatibility projection source is inconsistent")
            raise InvalidEvidenceSource("evidence source contains incompatible artifacts")
        minimized = self._minimize_metrics(binding.projection_kind, allowlist, metrics)
        if (
            binding.projection_kind
            in {EvidenceProjectionKind.EVAL_RESULT, EvidenceProjectionKind.REGRESSION_RESULT}
            and eval_reference.required
            and eval_reference.metric not in {item.metric_id for item in minimized}
        ):
            raise EvalRequirementMismatch("required eval metric is absent from projection")
        allowlist_fingerprint = allowlist.fingerprint
        assert allowlist_fingerprint is not None
        summary = self._summary(binding.projection_kind, readiness)
        semantic = {
            "binding": binding,
            "source_fingerprint": source.fingerprint,
            "readiness": readiness.status,
            "metrics": minimized,
            "allowlist_fingerprint": allowlist_fingerprint,
            "classification": allowlist.classification,
            "summary": summary,
        }
        projection_fingerprint = fingerprint(semantic)
        projection_checksum = content_checksum(
            {**semantic, "fingerprint": projection_fingerprint}
        )
        return EvalEvidenceProjection(
            binding=binding,
            source=source,
            readiness=readiness.status,
            metrics=minimized,
            metric_allowlist_fingerprint=allowlist_fingerprint,
            classification=allowlist.classification,
            summary=summary,
            checksum=projection_checksum,
            fingerprint=projection_fingerprint,
        )

    @staticmethod
    def governance_record(
        projection: EvalEvidenceProjection,
        *,
        evidence_id: str,
        created_at: UtcTimestamp,
    ) -> EvidenceRecord:
        """Deterministically translate eval facts into the frozen record schema."""
        validate_evidence_reference(evidence_id, "institutional evidence ID")
        implementation = projection.binding.implementation
        return EvidenceRecord(
            project_id=implementation.project_id,
            rfc_id=implementation.rfc_id,
            rfc_revision=implementation.rfc_revision,
            plan_id=implementation.plan_id,
            evidence_type=projection.binding.projection_kind.value,
            summary=projection.summary,
            artifact_reference=EvalEvidenceProjectionFactory._artifact_reference(projection),
            checksum=projection.checksum.value,
            produced_by=(
                f"{projection.binding.producer_id}:{projection.binding.producer_version}"
            ),
            validation_status="projected",
            correlation_id=projection.binding.correlation_id,
            provenance=(),
            classification=projection.classification.value,
            evidence_id=evidence_id,
            created_at=created_at.value,
        )

    @staticmethod
    def _validate_local_correlation(
        binding: GovernanceEvidenceBinding,
        expected: RFCImplementationBinding,
        eval_reference: EvalReference,
        source: EvalEvidenceSource,
    ) -> None:
        if binding.implementation != expected:
            raise GovernanceBindingMismatch("governance implementation inputs are inconsistent")
        if binding.eval_id != eval_reference.eval_id or binding.eval_version != eval_reference.version:
            raise EvalRequirementMismatch("eval requirement inputs are inconsistent")
        if source.suite_id is not None and str(source.suite_id) != eval_reference.eval_id:
            raise EvalRequirementMismatch("evidence suite does not match eval requirement")
        if source.suite_version is not None and str(source.suite_version) != eval_reference.version:
            raise EvalRequirementMismatch("evidence suite version does not match eval requirement")

    @staticmethod
    def _missing_requirements(
        kind: EvidenceProjectionKind,
        source: EvalEvidenceSource,
    ) -> tuple[int, ...]:
        common = (source.suite_id, source.suite_version, source.provenance_references or None)
        requirements: dict[EvidenceProjectionKind, tuple[object | None, ...]] = {
            EvidenceProjectionKind.EVAL_RESULT: (
                *common,
                source.run_id,
                source.run_manifest_reference,
                source.run_manifest_fingerprint,
                source.finalization_reference,
                source.finalization_fingerprint,
                source.security_snapshot_reference,
                source.security_snapshot_fingerprint,
                source.scoring_decision_reference,
                source.scoring_decision_fingerprint,
                source.verdict,
            ),
            EvidenceProjectionKind.REGRESSION_RESULT: (
                *common,
                source.baseline_id,
                source.comparison_id,
                source.regression_rule_reference,
                source.regression_rule_fingerprint,
                source.regression_report_id,
                source.regression_report_fingerprint,
                source.regression_classification,
            ),
            EvidenceProjectionKind.POLICY_BLOCK: (
                *common,
                source.run_id,
                source.security_snapshot_reference,
                source.security_snapshot_fingerprint,
                source.security_decision_reference,
                source.security_decision_fingerprint,
                source.verdict,
            ),
            EvidenceProjectionKind.REPRODUCIBILITY_FAILURE: (
                *common,
                source.run_id,
                source.run_manifest_reference,
                source.reason_codes or None,
                source.verdict,
            ),
            EvidenceProjectionKind.COMPATIBILITY_FAILURE: (
                *common,
                source.comparison_id,
                source.compatibility_status,
                source.reason_codes or None,
            ),
        }
        return tuple(index for index, value in enumerate(requirements[kind]) if value is None)

    @staticmethod
    def _artifact_reference(projection: EvalEvidenceProjection) -> str:
        source = projection.source
        references: dict[EvidenceProjectionKind, object | None] = {
            EvidenceProjectionKind.EVAL_RESULT: source.finalization_reference,
            EvidenceProjectionKind.REGRESSION_RESULT: source.regression_report_id,
            EvidenceProjectionKind.POLICY_BLOCK: source.security_decision_reference,
            EvidenceProjectionKind.REPRODUCIBILITY_FAILURE: source.run_manifest_reference,
            EvidenceProjectionKind.COMPATIBILITY_FAILURE: source.comparison_id,
        }
        reference = references[projection.binding.projection_kind]
        assert reference is not None
        value = str(reference)
        validate_evidence_reference(value, "evidence artifact reference")
        return value

    @staticmethod
    def _has_forbidden_artifacts(
        kind: EvidenceProjectionKind,
        source: EvalEvidenceSource,
    ) -> bool:
        forbidden: dict[EvidenceProjectionKind, tuple[str, ...]] = {
            EvidenceProjectionKind.EVAL_RESULT: (
                "baseline",
                "comparison",
                "compatibility",
                "regression_rule",
                "regression_report",
                "regression_classification",
                "security_decision",
            ),
            EvidenceProjectionKind.REGRESSION_RESULT: (
                "scoring",
                "compatibility",
                "security_decision",
            ),
            EvidenceProjectionKind.POLICY_BLOCK: (
                "scoring",
                "baseline",
                "comparison",
                "compatibility",
                "regression_rule",
                "regression_report",
                "regression_classification",
            ),
            EvidenceProjectionKind.REPRODUCIBILITY_FAILURE: (
                "scoring",
                "baseline",
                "comparison",
                "regression_rule",
                "regression_report",
                "regression_classification",
            ),
            EvidenceProjectionKind.COMPATIBILITY_FAILURE: (
                "scoring",
                "baseline",
                "regression_rule",
                "regression_report",
                "regression_classification",
                "security_decision",
            ),
        }
        return any(
            any(getattr(source, field) is not None for field in _SOURCE_FIELDS[group])
            for group in forbidden[kind]
        )

    @staticmethod
    def _minimize_metrics(
        kind: EvidenceProjectionKind,
        allowlist: EvidenceMetricAllowlist,
        metrics: tuple[EvidenceMetric, ...],
    ) -> tuple[EvidenceMetric, ...]:
        if kind not in {
            EvidenceProjectionKind.EVAL_RESULT,
            EvidenceProjectionKind.REGRESSION_RESULT,
        }:
            if metrics:
                raise MetricNotAllowed("metrics are prohibited for this projection kind")
            return ()
        ids = tuple(item.metric_id for item in metrics)
        if len(ids) != len(set(ids)):
            raise MetricNotAllowed("duplicate evidence metric is prohibited")
        allowed = set(allowlist.allowed_metric_ids)
        if any(metric_id not in allowed for metric_id in ids):
            raise MetricNotAllowed("evidence metric is not allowlisted")
        return tuple(sorted(metrics))

    @staticmethod
    def _summary(
        kind: EvidenceProjectionKind,
        readiness: ProjectionReadiness,
    ) -> str:
        reasons = ",".join(sorted(item.value for item in readiness.reason_codes)) or "none"
        return f"private_evals:{kind.value};status:ready;reasons:{reasons}"


@dataclass(frozen=True)
class EvalEvidenceEmitter:
    governance: RFCEvidenceWritePort

    def emit(self, evidence: EvidenceRecord) -> EvidenceRecord:
        recorded = self.governance.record_evidence(evidence)
        if (
            recorded.evidence_id != evidence.evidence_id
            or recorded.checksum != evidence.checksum
            or recorded.project_id != evidence.project_id
            or recorded.rfc_id != evidence.rfc_id
            or recorded.rfc_revision != evidence.rfc_revision
            or recorded.plan_id != evidence.plan_id
        ):
            raise GovernanceBindingMismatch("recorded institutional evidence is inconsistent")
        return recorded
