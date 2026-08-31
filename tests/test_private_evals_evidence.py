from __future__ import annotations

from dataclasses import fields, replace
from decimal import Decimal

import pytest

from synapse.intelligence_boundary.models import DataClassification
from synapse.private_evals.analysis import CompatibilityStatus
from synapse.private_evals.evidence import (
    EvalEvidenceProjection,
    EvalEvidenceSource,
    EvidenceMetric,
    EvidenceMetricAllowlist,
    EvidenceProjectionKind,
    GovernanceEvidenceBinding,
    ProjectionReadinessStatus,
    ProjectionReasonCode,
)
from synapse.private_evals.evidence_errors import (
    EvalRequirementMismatch,
    GovernanceBindingMismatch,
    IncompatibleEvidenceSource,
    IncompleteEvidence,
    InvalidEvidenceSource,
    MetricNotAllowed,
    ProjectionChecksumMismatch,
    ProjectionFingerprintMismatch,
    RFCRevisionMissing,
    SensitiveEvidenceContent,
)
from synapse.private_evals.evidence_projection import (
    EvalEvidenceEmitter,
    EvalEvidenceProjectionFactory,
)
from synapse.private_evals.states import ComparisonResult, Verdict
from synapse.private_evals.values import (
    BaselineId,
    ComparisonId,
    ContentChecksum,
    EvalRunId,
    EvalSuiteId,
    EvalVersion,
    Fingerprint,
    RegressionReportId,
    UtcTimestamp,
)
from synapse.project_governance.models import (
    EvalReference,
    EvidenceRecord,
    RFCImplementationBinding,
)

FP_A = Fingerprint("1" * 64)
FP_B = Fingerprint("2" * 64)
SHA_A = ContentChecksum("a" * 64)
NOW = UtcTimestamp("2026-07-18T12:00:00Z")
LATER = UtcTimestamp("2026-07-18T13:00:00Z")
FACTORY = EvalEvidenceProjectionFactory()


def implementation(**changes: object) -> RFCImplementationBinding:
    return replace(
        RFCImplementationBinding(
            project_id="project-1",
            rfc_id="rfc-1",
            rfc_revision=7,
            rfc_checksum="a" * 64,
            plan_id="plan-1",
            plan_revision=3,
            plan_checksum="b" * 64,
        ),
        **changes,
    )


def eval_reference(**changes: object) -> EvalReference:
    return replace(
        EvalReference(
            eval_id="suite-1",
            version="1.2.0",
            required=True,
            dataset_reference="asset://private-dataset-reference",
            metric="quality.score",
            threshold="0.80",
        ),
        **changes,
    )


def binding(
    kind: EvidenceProjectionKind = EvidenceProjectionKind.EVAL_RESULT,
    **changes: object,
) -> GovernanceEvidenceBinding:
    return replace(
        GovernanceEvidenceBinding(
            implementation=implementation(),
            implementation_binding_reference="implementation-binding-1",
            eval_requirement_id="eval-requirement-1",
            eval_id="suite-1",
            eval_version="1.2.0",
            projection_kind=kind,
            producer_id="private-evals",
            producer_version="8.0.0",
            correlation_id="correlation-1",
        ),
        **changes,
    )


def common_source(**changes: object) -> EvalEvidenceSource:
    values: dict[str, object] = {
        "applicable": True,
        "suite_id": EvalSuiteId("suite-1"),
        "suite_version": EvalVersion("1.2.0"),
        "provenance_references": ("provenance-1",),
    }
    values.update(changes)
    return EvalEvidenceSource(**values)  # type: ignore[arg-type]


def eval_source(**changes: object) -> EvalEvidenceSource:
    values: dict[str, object] = {
        "run_id": EvalRunId("run-1"),
        "run_manifest_reference": "run-manifest-1",
        "run_manifest_fingerprint": FP_A,
        "finalization_reference": "finalization-1",
        "finalization_fingerprint": FP_B,
        "scoring_decision_reference": "scoring-decision-1",
        "scoring_decision_fingerprint": FP_B,
        "verdict": Verdict.PASSED,
        "security_snapshot_reference": "security-snapshot-1",
        "security_snapshot_fingerprint": FP_A,
        "egress_manifest_reference": "egress-manifest-1",
        "egress_manifest_checksum": SHA_A,
        "reason_codes": (ProjectionReasonCode.EVAL_COMPLETED,),
    }
    values.update(changes)
    return common_source(**values)


def regression_source(**changes: object) -> EvalEvidenceSource:
    values: dict[str, object] = {
        "baseline_id": BaselineId("baseline-1"),
        "comparison_id": ComparisonId("comparison-1"),
        "regression_rule_reference": "regression-rule-1",
        "regression_rule_fingerprint": FP_A,
        "regression_report_id": RegressionReportId("report-1"),
        "regression_report_fingerprint": FP_B,
        "regression_classification": ComparisonResult.REGRESSED,
        "reason_codes": (ProjectionReasonCode.REGRESSION_EVALUATED,),
    }
    values.update(changes)
    return common_source(**values)


def policy_source(**changes: object) -> EvalEvidenceSource:
    values: dict[str, object] = {
        "run_id": EvalRunId("run-1"),
        "verdict": Verdict.POLICY_DENIED,
        "security_snapshot_reference": "security-snapshot-1",
        "security_snapshot_fingerprint": FP_A,
        "security_decision_reference": "security-decision-1",
        "security_decision_fingerprint": FP_B,
        "reason_codes": (ProjectionReasonCode.POLICY_DENIED,),
    }
    values.update(changes)
    return common_source(**values)


def compatibility_source(**changes: object) -> EvalEvidenceSource:
    values: dict[str, object] = {
        "comparison_id": ComparisonId("comparison-1"),
        "compatibility_status": CompatibilityStatus.INCOMPATIBLE,
        "reason_codes": (ProjectionReasonCode.INCOMPATIBLE_PROTOCOL,),
    }
    values.update(changes)
    return common_source(**values)


def reproducibility_source(**changes: object) -> EvalEvidenceSource:
    values: dict[str, object] = {
        "run_id": EvalRunId("run-1"),
        "run_manifest_reference": "run-manifest-1",
        "run_manifest_fingerprint": FP_A,
        "verdict": Verdict.INVALID,
        "reason_codes": (ProjectionReasonCode.REPRODUCIBILITY_INVALID,),
    }
    values.update(changes)
    return common_source(**values)


def allowlist(**changes: object) -> EvidenceMetricAllowlist:
    return replace(
        EvidenceMetricAllowlist(
            allowlist_reference="evidence-metrics-1",
            version="1.0.0",
            allowed_metric_ids=("quality.score", "latency.score"),
            classification_reference="classification-policy-1",
            classification=DataClassification.INTERNAL,
        ),
        **changes,
    )


def create_projection(
    kind: EvidenceProjectionKind = EvidenceProjectionKind.EVAL_RESULT,
    *,
    source: EvalEvidenceSource | None = None,
    metrics: tuple[EvidenceMetric, ...] | None = None,
) -> EvalEvidenceProjection:
    sources = {
        EvidenceProjectionKind.EVAL_RESULT: eval_source(),
        EvidenceProjectionKind.REGRESSION_RESULT: regression_source(),
        EvidenceProjectionKind.POLICY_BLOCK: policy_source(),
        EvidenceProjectionKind.REPRODUCIBILITY_FAILURE: reproducibility_source(),
        EvidenceProjectionKind.COMPATIBILITY_FAILURE: compatibility_source(),
    }
    selected_metrics = metrics
    if selected_metrics is None:
        selected_metrics = (
            (EvidenceMetric("quality.score", Decimal("0.9")),)
            if kind in {EvidenceProjectionKind.EVAL_RESULT, EvidenceProjectionKind.REGRESSION_RESULT}
            else ()
        )
    return FACTORY.create(
        binding=binding(kind),
        expected_binding=implementation(),
        eval_reference=eval_reference(),
        source=source or sources[kind],
        allowlist=allowlist(),
        metrics=selected_metrics,
    )


@pytest.mark.parametrize(
    ("kind", "source"),
    [
        (EvidenceProjectionKind.EVAL_RESULT, eval_source()),
        (EvidenceProjectionKind.REGRESSION_RESULT, regression_source()),
        (EvidenceProjectionKind.POLICY_BLOCK, policy_source()),
        (EvidenceProjectionKind.REPRODUCIBILITY_FAILURE, reproducibility_source()),
        (EvidenceProjectionKind.COMPATIBILITY_FAILURE, compatibility_source()),
    ],
)
def test_all_projection_kinds_are_ready_when_structurally_valid(
    kind: EvidenceProjectionKind, source: EvalEvidenceSource
) -> None:
    readiness = FACTORY.assess(
        binding=binding(kind),
        expected_binding=implementation(),
        eval_reference=eval_reference(),
        source=source,
    )
    assert readiness.status is ProjectionReadinessStatus.READY
    assert readiness.eligible


def test_readiness_states_are_structural_not_governance_submission_states() -> None:
    not_applicable = FACTORY.assess(
        binding=binding(),
        expected_binding=implementation(),
        eval_reference=eval_reference(),
        source=EvalEvidenceSource(applicable=False),
    )
    incomplete = FACTORY.assess(
        binding=binding(),
        expected_binding=implementation(),
        eval_reference=eval_reference(),
        source=common_source(),
    )
    invalid = FACTORY.assess(
        binding=binding(EvidenceProjectionKind.POLICY_BLOCK),
        expected_binding=implementation(),
        eval_reference=eval_reference(),
        source=policy_source(verdict=Verdict.PASSED),
    )
    assert (not_applicable.status, incomplete.status, invalid.status) == (
        ProjectionReadinessStatus.NOT_APPLICABLE,
        ProjectionReadinessStatus.INCOMPLETE,
        ProjectionReadinessStatus.INVALID,
    )


def test_create_rejects_incomplete_invalid_and_incompatible_sources() -> None:
    with pytest.raises(IncompleteEvidence):
        create_projection(source=common_source())
    with pytest.raises(InvalidEvidenceSource):
        create_projection(
            EvidenceProjectionKind.POLICY_BLOCK,
            source=policy_source(verdict=Verdict.PASSED),
        )
    with pytest.raises(IncompatibleEvidenceSource):
        create_projection(
            EvidenceProjectionKind.COMPATIBILITY_FAILURE,
            source=compatibility_source(compatibility_status=CompatibilityStatus.COMPATIBLE),
        )


def test_metric_minimization_is_allowlisted_sorted_and_label_free() -> None:
    projection = create_projection(
        metrics=(
            EvidenceMetric("quality.score", Decimal("0.90")),
            EvidenceMetric("latency.score", Decimal("0.70")),
        )[::-1]
    )
    assert tuple(item.metric_id for item in projection.metrics) == (
        "latency.score",
        "quality.score",
    )
    assert {item.name for item in fields(EvidenceMetric)} == {"metric_id", "value"}
    with pytest.raises(TypeError):
        EvidenceMetric("quality.score", Decimal("0.9"), labels={"secret": "x"})  # type: ignore[call-arg]


def test_metric_allowlist_classification_is_external_and_fingerprint_bound() -> None:
    internal = allowlist()
    restricted = allowlist(classification=DataClassification.RESTRICTED, fingerprint=None)
    assert internal.classification is DataClassification.INTERNAL
    assert internal.fingerprint != restricted.fingerprint
    with pytest.raises(ProjectionFingerprintMismatch):
        allowlist(fingerprint=FP_A)


def test_metrics_must_be_allowed_unique_and_include_required_eval_metric() -> None:
    with pytest.raises(MetricNotAllowed):
        create_projection(metrics=(EvidenceMetric("unknown", Decimal("0.2")),))
    duplicate = EvidenceMetric("quality.score", Decimal("0.9"))
    with pytest.raises(MetricNotAllowed):
        create_projection(metrics=(duplicate, duplicate))
    with pytest.raises(EvalRequirementMismatch):
        create_projection(metrics=(EvidenceMetric("latency.score", Decimal("0.9")),))
    with pytest.raises(MetricNotAllowed):
        create_projection(
            EvidenceProjectionKind.POLICY_BLOCK,
            metrics=(EvidenceMetric("quality.score", Decimal("0.9")),),
        )


def test_projection_integrity_is_semantic_deterministic_and_time_free() -> None:
    first = create_projection()
    second = create_projection()
    changed = create_projection(metrics=(EvidenceMetric("quality.score", Decimal("0.8")),))
    assert first == second
    assert first.fingerprint == second.fingerprint
    assert first.checksum == second.checksum
    assert first.fingerprint != changed.fingerprint
    assert first.checksum != changed.checksum
    assert "created_at" not in {item.name for item in fields(EvalEvidenceProjection)}
    assert "evidence_id" not in {item.name for item in fields(EvalEvidenceProjection)}


def test_projection_detects_fingerprint_and_checksum_tampering_independently() -> None:
    projection = create_projection()
    with pytest.raises(ProjectionFingerprintMismatch):
        replace(projection, fingerprint=FP_A)
    with pytest.raises(ProjectionChecksumMismatch):
        replace(projection, checksum=SHA_A)


def test_governance_record_adds_only_institutional_identity_and_timestamp() -> None:
    projection = create_projection()
    first = FACTORY.governance_record(projection, evidence_id="evidence-1", created_at=NOW)
    second = FACTORY.governance_record(projection, evidence_id="evidence-2", created_at=LATER)
    assert first.checksum == second.checksum == projection.checksum.value
    assert first.evidence_type == projection.binding.projection_kind.value
    assert first.created_at == NOW.value and second.created_at == LATER.value
    assert first.evidence_id != second.evidence_id
    assert first.project_id == projection.binding.implementation.project_id
    assert first.artifact_reference == "finalization-1"


def test_governance_record_is_minimal_and_compatible_with_frozen_schema() -> None:
    record = FACTORY.governance_record(create_projection(), evidence_id="evidence-1", created_at=NOW)
    assert isinstance(record, EvidenceRecord)
    assert record.validation_status == "projected"
    assert record.classification == DataClassification.INTERNAL.value
    assert record.provenance == ()
    assert record.summary == "private_evals:eval_result;status:ready;reasons:eval_completed"


@pytest.mark.parametrize(
    ("kind", "artifact_reference"),
    [
        (EvidenceProjectionKind.EVAL_RESULT, "finalization-1"),
        (EvidenceProjectionKind.REGRESSION_RESULT, "report-1"),
        (EvidenceProjectionKind.POLICY_BLOCK, "security-decision-1"),
        (EvidenceProjectionKind.REPRODUCIBILITY_FAILURE, "run-manifest-1"),
        (EvidenceProjectionKind.COMPATIBILITY_FAILURE, "comparison-1"),
    ],
)
def test_each_projection_kind_references_a_real_source_artifact(
    kind: EvidenceProjectionKind, artifact_reference: str
) -> None:
    record = FACTORY.governance_record(
        create_projection(kind), evidence_id="evidence-1", created_at=NOW
    )
    assert record.artifact_reference == artifact_reference


def test_local_binding_checks_exact_revision_and_eval_reference_without_claiming_freshness() -> None:
    with pytest.raises(GovernanceBindingMismatch):
        FACTORY.assess(
            binding=binding(),
            expected_binding=implementation(rfc_revision=8),
            eval_reference=eval_reference(),
            source=eval_source(),
        )
    with pytest.raises(EvalRequirementMismatch):
        FACTORY.assess(
            binding=binding(),
            expected_binding=implementation(),
            eval_reference=eval_reference(version="2.0.0"),
            source=eval_source(),
        )
    with pytest.raises(RFCRevisionMissing):
        binding(implementation=implementation(rfc_revision=0))


def test_sensitive_metadata_is_rejected_without_inspecting_artifact_payloads() -> None:
    with pytest.raises(SensitiveEvidenceContent):
        binding(correlation_id="Bearer-secret-token")
    with pytest.raises(SensitiveEvidenceContent):
        FACTORY.governance_record(create_projection(), evidence_id="../evidence", created_at=NOW)


class RecordingGovernance:
    def __init__(self) -> None:
        self.records: list[EvidenceRecord] = []

    def record_evidence(self, evidence: EvidenceRecord) -> EvidenceRecord:
        self.records.append(evidence)
        return evidence


def test_emitter_uses_frozen_governance_port_directly() -> None:
    governance = RecordingGovernance()
    record = FACTORY.governance_record(create_projection(), evidence_id="evidence-1", created_at=NOW)
    assert EvalEvidenceEmitter(governance).emit(record) is record
    assert governance.records == [record]


def test_emitter_rejects_malformed_returned_record() -> None:
    class MalformedGovernance:
        def record_evidence(self, evidence: EvidenceRecord) -> EvidenceRecord:
            return replace(evidence, evidence_id="other-evidence")

    record = FACTORY.governance_record(create_projection(), evidence_id="evidence-1", created_at=NOW)
    with pytest.raises(GovernanceBindingMismatch):
        EvalEvidenceEmitter(MalformedGovernance()).emit(record)


def test_governance_rejection_and_conflict_semantics_are_propagated_unchanged() -> None:
    class GovernanceDecision(Exception):
        pass

    class RejectingGovernance:
        def record_evidence(self, evidence: EvidenceRecord) -> EvidenceRecord:
            raise GovernanceDecision("owned by governance")

    record = FACTORY.governance_record(create_projection(), evidence_id="evidence-1", created_at=NOW)
    with pytest.raises(GovernanceDecision, match="owned by governance"):
        EvalEvidenceEmitter(RejectingGovernance()).emit(record)


def test_no_local_submission_or_idempotency_contract_is_exposed() -> None:
    import synapse.private_evals.evidence as evidence
    import synapse.private_evals.evidence_projection as projection

    forbidden = {
        "EvalEvidenceSubmissionPort",
        "EvalEvidenceSubmissionCoordinator",
        "EvidenceSubmissionRequest",
        "EvidenceSubmissionResult",
        "EvidenceSubmissionStatus",
    }
    assert not forbidden & set(dir(evidence))
    assert not forbidden & set(dir(projection))
