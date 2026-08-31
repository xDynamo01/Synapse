from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from synapse.intelligence_boundary.models import DataClassification
from synapse.project_governance.models import RFCImplementationBinding

from .analysis import CompatibilityStatus
from .canonical import content_checksum, fingerprint
from .evidence_errors import (
    GovernanceBindingMismatch,
    ProjectionChecksumMismatch,
    ProjectionFingerprintMismatch,
    RFCRevisionMissing,
    SensitiveEvidenceContent,
)
from .states import ComparisonResult, Verdict
from .values import (
    BaselineId,
    ComparisonId,
    ContentChecksum,
    EvalRunId,
    EvalSuiteId,
    EvalVersion,
    Fingerprint,
    RegressionReportId,
)

_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_SENSITIVE = re.compile(
    r"(?i)(?:token|secret|password|credential|authorization|bearer|api[_-]?key|sk-)"
)


def validate_evidence_reference(value: str, label: str) -> None:
    if isinstance(value, str) and _SENSITIVE.search(value):
        raise SensitiveEvidenceContent("evidence metadata contains forbidden content")
    if not isinstance(value, str) or not _SAFE_ID.fullmatch(value):
        raise SensitiveEvidenceContent(f"{label} is not a safe reference")


def _unique(values: tuple[object, ...], label: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"duplicate {label} reference")


class EvidenceProjectionKind(StrEnum):
    EVAL_RESULT = "eval_result"
    REGRESSION_RESULT = "regression_result"
    POLICY_BLOCK = "policy_block"
    REPRODUCIBILITY_FAILURE = "reproducibility_failure"
    COMPATIBILITY_FAILURE = "compatibility_failure"


class ProjectionReadinessStatus(StrEnum):
    READY = "ready"
    INCOMPLETE = "incomplete"
    INVALID = "invalid"
    NOT_APPLICABLE = "not_applicable"


class ProjectionReasonCode(StrEnum):
    EVAL_COMPLETED = "eval_completed"
    REGRESSION_EVALUATED = "regression_evaluated"
    POLICY_DENIED = "policy_denied"
    APPROVAL_PENDING = "approval_pending"
    INCOMPATIBLE_PROTOCOL = "incompatible_protocol"
    REPRODUCIBILITY_INVALID = "reproducibility_invalid"


@dataclass(frozen=True)
class GovernanceEvidenceBinding:
    implementation: RFCImplementationBinding
    implementation_binding_reference: str
    eval_requirement_id: str
    eval_id: str
    eval_version: str
    projection_kind: EvidenceProjectionKind
    producer_id: str
    producer_version: str
    correlation_id: str

    def __post_init__(self) -> None:
        if self.implementation.rfc_revision < 1:
            raise RFCRevisionMissing("explicit RFC revision is required")
        if self.implementation.plan_revision < 1:
            raise RFCRevisionMissing("explicit Plan revision is required")
        try:
            ContentChecksum(self.implementation.rfc_checksum)
            ContentChecksum(self.implementation.plan_checksum)
        except ValueError as exc:
            raise GovernanceBindingMismatch(
                "governance binding checksum is invalid"
            ) from exc
        for value, label in (
            (self.implementation.project_id, "project ID"),
            (self.implementation.rfc_id, "RFC ID"),
            (self.implementation.plan_id, "Plan ID"),
            (self.implementation_binding_reference, "implementation binding reference"),
            (self.eval_requirement_id, "eval requirement ID"),
            (self.eval_id, "eval ID"),
            (self.eval_version, "eval version"),
            (self.producer_id, "producer ID"),
            (self.producer_version, "producer version"),
            (self.correlation_id, "correlation ID"),
        ):
            validate_evidence_reference(value, label)

    def __repr__(self) -> str:
        return (
            "GovernanceEvidenceBinding("
            f"project_id={self.implementation.project_id!r}, "
            f"rfc_id={self.implementation.rfc_id!r}, "
            f"rfc_revision={self.implementation.rfc_revision!r}, "
            f"plan_id={self.implementation.plan_id!r}, "
            f"projection_kind={self.projection_kind!r})"
        )


@dataclass(frozen=True)
class EvidenceMetricAllowlist:
    allowlist_reference: str
    version: str
    allowed_metric_ids: tuple[str, ...]
    classification_reference: str
    classification: DataClassification
    fingerprint: Fingerprint | None = None

    def __post_init__(self) -> None:
        for value, label in (
            (self.allowlist_reference, "allowlist reference"),
            (self.version, "allowlist version"),
            (self.classification_reference, "classification reference"),
        ):
            validate_evidence_reference(value, label)
        if not self.allowed_metric_ids:
            raise ValueError("metric allowlist cannot be empty")
        _unique(self.allowed_metric_ids, "allowed metric")
        for metric_id in self.allowed_metric_ids:
            validate_evidence_reference(metric_id, "metric ID")
        expected = fingerprint(
            {
                "reference": self.allowlist_reference,
                "version": self.version,
                "metric_ids": tuple(sorted(self.allowed_metric_ids)),
                "classification_reference": self.classification_reference,
                "classification": self.classification,
            }
        )
        if self.fingerprint is None:
            object.__setattr__(self, "fingerprint", expected)
        elif self.fingerprint != expected:
            raise ProjectionFingerprintMismatch("metric allowlist fingerprint is inconsistent")


@dataclass(frozen=True, order=True)
class EvidenceMetric:
    metric_id: str
    value: Decimal

    def __post_init__(self) -> None:
        validate_evidence_reference(self.metric_id, "metric ID")
        if not isinstance(self.value, Decimal) or not self.value.is_finite():
            raise ValueError("evidence metric must be a finite Decimal")
        if self.value < Decimal(0) or self.value > Decimal(1):
            raise ValueError("evidence metric must use the normalized zero-to-one scale")


@dataclass(frozen=True)
class EvalEvidenceSource:
    applicable: bool
    run_id: EvalRunId | None = None
    suite_id: EvalSuiteId | None = None
    suite_version: EvalVersion | None = None
    run_manifest_reference: str | None = None
    run_manifest_fingerprint: Fingerprint | None = None
    finalization_reference: str | None = None
    finalization_fingerprint: Fingerprint | None = None
    scoring_decision_reference: str | None = None
    scoring_decision_fingerprint: Fingerprint | None = None
    verdict: Verdict | None = None
    baseline_id: BaselineId | None = None
    comparison_id: ComparisonId | None = None
    compatibility_status: CompatibilityStatus | None = None
    regression_rule_reference: str | None = None
    regression_rule_fingerprint: Fingerprint | None = None
    regression_report_id: RegressionReportId | None = None
    regression_report_fingerprint: Fingerprint | None = None
    regression_classification: ComparisonResult | None = None
    security_snapshot_reference: str | None = None
    security_snapshot_fingerprint: Fingerprint | None = None
    security_decision_reference: str | None = None
    security_decision_fingerprint: Fingerprint | None = None
    egress_manifest_reference: str | None = None
    egress_manifest_checksum: ContentChecksum | None = None
    provenance_references: tuple[str, ...] = ()
    reason_codes: tuple[ProjectionReasonCode, ...] = ()
    fingerprint: Fingerprint | None = None

    def __post_init__(self) -> None:
        for value, label in (
            (self.run_manifest_reference, "run manifest reference"),
            (self.finalization_reference, "finalization reference"),
            (self.scoring_decision_reference, "scoring decision reference"),
            (self.regression_rule_reference, "regression rule reference"),
            (self.security_snapshot_reference, "security snapshot reference"),
            (self.security_decision_reference, "security decision reference"),
            (self.egress_manifest_reference, "egress manifest reference"),
        ):
            if value is not None:
                validate_evidence_reference(value, label)
        _unique(self.provenance_references, "provenance")
        _unique(self.reason_codes, "projection reason")
        for reference in self.provenance_references:
            validate_evidence_reference(reference, "provenance reference")
        expected = evidence_source_fingerprint(self)
        if self.fingerprint is None:
            object.__setattr__(self, "fingerprint", expected)
        elif self.fingerprint != expected:
            raise ProjectionFingerprintMismatch("evidence source fingerprint is inconsistent")

    def __repr__(self) -> str:
        return (
            "EvalEvidenceSource("
            f"applicable={self.applicable!r}, run_id={self.run_id!r}, "
            f"fingerprint={self.fingerprint!r})"
        )


def evidence_source_fingerprint(source: EvalEvidenceSource) -> Fingerprint:
    return fingerprint(
        {
            "applicable": source.applicable,
            "run_id": source.run_id,
            "suite_id": source.suite_id,
            "suite_version": source.suite_version,
            "run_manifest": (
                source.run_manifest_reference,
                source.run_manifest_fingerprint,
            ),
            "finalization": (
                source.finalization_reference,
                source.finalization_fingerprint,
            ),
            "scoring_decision": (
                source.scoring_decision_reference,
                source.scoring_decision_fingerprint,
            ),
            "verdict": source.verdict,
            "baseline_id": source.baseline_id,
            "comparison_id": source.comparison_id,
            "compatibility_status": source.compatibility_status,
            "regression_rule": (
                source.regression_rule_reference,
                source.regression_rule_fingerprint,
            ),
            "regression_report": (
                source.regression_report_id,
                source.regression_report_fingerprint,
            ),
            "regression_classification": source.regression_classification,
            "security_snapshot": (
                source.security_snapshot_reference,
                source.security_snapshot_fingerprint,
            ),
            "security_decision": (
                source.security_decision_reference,
                source.security_decision_fingerprint,
            ),
            "egress_manifest": (
                source.egress_manifest_reference,
                source.egress_manifest_checksum,
            ),
            "provenance": tuple(sorted(source.provenance_references)),
            "reason_codes": tuple(sorted(source.reason_codes, key=lambda item: item.value)),
        }
    )


@dataclass(frozen=True)
class ProjectionReadiness:
    status: ProjectionReadinessStatus
    eligible: bool
    reason_codes: tuple[ProjectionReasonCode, ...]


@dataclass(frozen=True)
class EvalEvidenceProjection:
    binding: GovernanceEvidenceBinding
    source: EvalEvidenceSource
    readiness: ProjectionReadinessStatus
    metrics: tuple[EvidenceMetric, ...]
    metric_allowlist_fingerprint: Fingerprint
    classification: DataClassification
    summary: str
    checksum: ContentChecksum
    fingerprint: Fingerprint

    def __post_init__(self) -> None:
        if self.fingerprint != evidence_projection_fingerprint(self):
            raise ProjectionFingerprintMismatch("evidence projection fingerprint is inconsistent")
        if self.checksum != evidence_projection_checksum(self):
            raise ProjectionChecksumMismatch("evidence projection checksum is inconsistent")

    def __repr__(self) -> str:
        return (
            "EvalEvidenceProjection("
            f"projection_kind={self.binding.projection_kind!r}, "
            f"readiness={self.readiness!r}, fingerprint={self.fingerprint!r}, "
            f"checksum={self.checksum!r})"
        )


def _projection_semantic(projection: EvalEvidenceProjection) -> dict[str, object]:
    return {
        "binding": projection.binding,
        "source_fingerprint": projection.source.fingerprint,
        "readiness": projection.readiness,
        "metrics": tuple(sorted(projection.metrics)),
        "allowlist_fingerprint": projection.metric_allowlist_fingerprint,
        "classification": projection.classification,
        "summary": projection.summary,
    }


def evidence_projection_fingerprint(projection: EvalEvidenceProjection) -> Fingerprint:
    return fingerprint(_projection_semantic(projection))


def evidence_projection_checksum(projection: EvalEvidenceProjection) -> ContentChecksum:
    return content_checksum(
        {
            **_projection_semantic(projection),
            "fingerprint": projection.fingerprint,
        }
    )
