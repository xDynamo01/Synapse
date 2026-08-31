from __future__ import annotations

from dataclasses import FrozenInstanceError, dataclass, replace
from decimal import Decimal

import pytest

from synapse.intelligence_boundary.models import (
    DataClassification,
    InformationOwnership,
    OperatingProfile,
    ProcessingBoundary,
)
from synapse.private_evals import (
    BaselineId,
    BaselineStatus,
    ComparisonId,
    ComparisonResult,
    ComparisonScope,
    ContentBinding,
    ContentChecksum,
    DatasetBinding,
    DatasetBindingId,
    DatasetBindingRef,
    DatasetCustodyKind,
    DecodingParameters,
    DefinitionStatus,
    DeterminismMode,
    EnvironmentSnapshot,
    EvalBaseline,
    EvalCaseId,
    EvalCaseVersion,
    EvalCaseVersionRef,
    EvalComparison,
    EvalResult,
    EvalResultId,
    EvalRun,
    EvalRunId,
    EvalRunManifest,
    EvalRunManifestId,
    EvalSuite,
    EvalSuiteId,
    EvalSuiteVersion,
    EvaluatorId,
    EvaluatorIdentity,
    EvalVersion,
    ExecutionProtocol,
    Fingerprint,
    InputKind,
    MetricDelta,
    MetricThreshold,
    ModelProviderSnapshot,
    RegressionOutcome,
    RegressionReport,
    RegressionReportId,
    RegressionRule,
    RegressionRuleId,
    ResourceUsage,
    ResultStatus,
    Revision,
    RunProvenance,
    RunStatus,
    Score,
    ScoreKind,
    ScoreStatus,
    SecuritySnapshotRef,
    SideEffectPolicy,
    SuiteStatus,
    UtcTimestamp,
    Verdict,
    canonical_json,
    content_checksum,
    fingerprint,
)
from synapse.private_evals.errors import (
    DuplicateReference,
    IncompatibleReference,
    InvalidBaseline,
    InvalidCase,
    InvalidChecksum,
    InvalidComparison,
    InvalidDatasetBinding,
    InvalidFingerprint,
    InvalidIdentity,
    InvalidRegressionRule,
    InvalidResult,
    InvalidRun,
    InvalidRunManifest,
    InvalidScore,
    InvalidSuite,
    InvalidTimestamp,
    InvalidVersion,
    SensitivePayloadViolation,
)

SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
SHA_D = "d" * 64
SHA_E = "e" * 64
NOW = UtcTimestamp("2026-07-17T18:00:00+00:00")
SUITE_ID = EvalSuiteId("suite.private-evals")
CASE_ID = EvalCaseId("case.exact-match")
VERSION = EvalVersion("1.0.0")
CHECKSUM = ContentChecksum(SHA_A)


def evaluator() -> EvaluatorIdentity:
    return EvaluatorIdentity(
        evaluator_id=EvaluatorId("evaluator.exact-match"),
        version=VERSION,
        implementation_checksum=CHECKSUM,
        kind="exact_match",
        configuration_checksum=ContentChecksum(SHA_B),
    )


def case_reference() -> EvalCaseVersionRef:
    return EvalCaseVersionRef(SUITE_ID, CASE_ID, VERSION, CHECKSUM)


def content() -> ContentBinding:
    return ContentBinding(
        kind=InputKind.INLINE,
        classification=DataClassification.PUBLIC,
        inline_value="bounded non-sensitive fixture",
    )


def score(**changes: object) -> Score:
    model = Score(
        metric_id="accuracy",
        evaluator=evaluator(),
        kind=ScoreKind.NUMERIC,
        status=ScoreStatus.VALID,
        raw_value=Decimal("8"),
        scale_minimum=Decimal("0"),
        scale_maximum=Decimal("10"),
        normalized_value=Decimal("0.8"),
        weight=Decimal("1"),
        sample_count=3,
        confidence=Decimal("0.95"),
        variance=Decimal("0.02"),
        confidence_method="bootstrap",
        critical=False,
        required=True,
        reason_code=None,
        checksum=CHECKSUM,
    )
    return replace(model, **changes)


def dataset_reference() -> DatasetBindingRef:
    return DatasetBindingRef(DatasetBindingId("dataset.binding-1"), Revision(1), CHECKSUM)


def execution_protocol(**changes: object) -> ExecutionProtocol:
    model = ExecutionProtocol(
        determinism_mode=DeterminismMode.DETERMINISTIC,
        repetitions=2,
        concurrency=1,
        retry_count=0,
        logical_timeout_seconds=Decimal("60"),
        call_timeout_seconds=Decimal("30"),
        seeds=(41, 42),
        aggregation_protocol="mean-v1",
    )
    return replace(model, **changes)


def manifest(**changes: object) -> EvalRunManifest:
    model = EvalRunManifest(
        manifest_id=EvalRunManifestId("manifest-1"),
        suite_id=SUITE_ID,
        suite_version=VERSION,
        suite_checksum=CHECKSUM,
        case_references=(case_reference(),),
        dataset_binding=dataset_reference(),
        evaluator=evaluator(),
        subject_kind="model",
        source_fingerprint=Fingerprint(SHA_A),
        model_provider=ModelProviderSnapshot(
            provider_id="local-provider",
            processing_boundary=ProcessingBoundary.LOCAL_MODEL,
            model_id="model-1",
            model_version="2026-07",
            configuration_checksum=ContentChecksum(SHA_B),
            decoding=DecodingParameters(Decimal("0"), Decimal("1"), 512, seed=41),
        ),
        component_references=(),
        security=SecuritySnapshotRef(
            operating_profile=OperatingProfile.LOCAL_SOVEREIGN,
            policy_references=("policy-1",),
            policy_checksums=(ContentChecksum(SHA_C),),
        ),
        execution=execution_protocol(),
        environment=EnvironmentSnapshot("Windows", "x86_64", "3.12", "synapse-v3"),
        provenance=RunProvenance("actor-1", "project-1", "caller-checksum"),
        protocol_fingerprint=Fingerprint(SHA_B),
        subject_fingerprint=Fingerprint(SHA_C),
        run_fingerprint=Fingerprint(SHA_D),
        environment_fingerprint=Fingerprint(SHA_E),
        checksum=CHECKSUM,
    )
    return replace(model, **changes)


def scope() -> ComparisonScope:
    return ComparisonScope(SUITE_ID, VERSION, "default", ("subject",))


def baseline(**changes: object) -> EvalBaseline:
    model = EvalBaseline(
        baseline_id=BaselineId("baseline-1"),
        scope=scope(),
        source_run_id=EvalRunId("run-baseline"),
        source_run_verdict=Verdict.PASSED,
        run_fingerprint=Fingerprint(SHA_D),
        finalization_checksum=CHECKSUM,
        protocol_fingerprint=Fingerprint(SHA_B),
        subject_fingerprint=Fingerprint(SHA_C),
        compatibility_signature=Fingerprint(SHA_E),
        summary_checksum=ContentChecksum(SHA_B),
        status=BaselineStatus.CANDIDATE,
        content_checksum=CHECKSUM,
        revision=Revision(1),
        governance_binding_reference=None,
        created_at=NOW,
    )
    return replace(model, **changes)


@pytest.mark.parametrize(
    ("identity_type", "valid"),
    [
        (EvalSuiteId, "suite-1"),
        (EvalCaseId, "case:1"),
        (EvalRunId, "run.1"),
        (EvalResultId, "result_1"),
        (BaselineId, "baseline-1"),
        (ComparisonId, "comparison-1"),
        (RegressionRuleId, "rule-1"),
        (RegressionReportId, "report-1"),
    ],
)
def test_typed_identities_have_stable_representation(identity_type: type, valid: str) -> None:
    identity = identity_type(valid)
    assert str(identity) == valid
    with pytest.raises(InvalidIdentity):
        identity_type("")
    with pytest.raises(InvalidIdentity):
        identity_type(" invalid ")


def test_identity_types_do_not_mix() -> None:
    assert EvalSuiteId("same") != EvalCaseId("same")


def test_versions_checksums_fingerprints_and_timestamps_validate_canonical_forms() -> None:
    assert EvalVersion("1.2.3-rc.1+build.5") < EvalVersion("2.0.0")
    assert EvalVersion("1.10.0") > EvalVersion("1.2.0")
    assert EvalVersion("1.0.0-rc.1") < EvalVersion("1.0.0")
    with pytest.raises(InvalidVersion):
        EvalVersion("01.2.3")
    with pytest.raises(InvalidVersion):
        EvalVersion("1.0.0-rc.01")
    with pytest.raises(InvalidChecksum):
        ContentChecksum("A" * 64)
    with pytest.raises(InvalidFingerprint):
        Fingerprint("")
    with pytest.raises(InvalidTimestamp):
        UtcTimestamp("2026-07-17T18:00:00")


def test_canonical_hashing_is_deterministic_ordered_and_secret_safe() -> None:
    assert canonical_json({"b": 2, "a": 1}) == '{"a":1,"b":2}'
    assert content_checksum({"a": 1, "b": 2}) == content_checksum({"b": 2, "a": 1})
    assert fingerprint({"state": "one"}) != fingerprint({"state": "two"})
    with pytest.raises(SensitivePayloadViolation) as caught:
        canonical_json({"api_key": "must-not-appear"})
    assert "must-not-appear" not in str(caught.value)

    @dataclass(frozen=True)
    class SecretFixture:
        access_token: str

    with pytest.raises(SensitivePayloadViolation) as dataclass_error:
        canonical_json(SecretFixture("also-must-not-appear"))
    assert "also-must-not-appear" not in str(dataclass_error.value)
    assert canonical_json({"credential_binding_id": "safe-reference"})
    assert canonical_json({"value": Decimal("-0")}) == '{"value":"0"}'


def test_suite_is_validated_and_immutable() -> None:
    suite = EvalSuite(
        SUITE_ID,
        "Private quality",
        "",
        InformationOwnership.PROJECT,
        "project-1",
        DataClassification.INTERNAL,
        SuiteStatus.ACTIVE,
        Revision(1),
        NOW,
        NOW,
    )
    with pytest.raises(FrozenInstanceError):
        suite.name = "silently changed"  # type: ignore[misc]
    with pytest.raises(InvalidSuite):
        replace(suite, name=" ")
    with pytest.raises(InvalidSuite):
        replace(suite, status="active")
    with pytest.raises(InvalidSuite):
        replace(suite, suite_id=EvalCaseId("wrong-id-type"))
    with pytest.raises(InvalidSuite):
        replace(suite, owner="project-owned")
    with pytest.raises(InvalidSuite):
        replace(suite, classification="internal")


def test_suite_version_rejects_duplicate_and_cross_suite_cases() -> None:
    base = dict(
        suite_id=SUITE_ID,
        version=VERSION,
        case_references=(case_reference(),),
        dataset_references=(dataset_reference(),),
        scoring_protocol_version=VERSION,
        default_repetitions=1,
        default_concurrency=1,
        default_timeout_seconds=Decimal("30"),
        default_retry_count=0,
        compatible_versions=(),
        required_case_ids=(CASE_ID,),
        classification=DataClassification.INTERNAL,
        owner=InformationOwnership.PROJECT,
        status=DefinitionStatus.FROZEN,
        checksum=CHECKSUM,
    )
    assert EvalSuiteVersion(**base).case_references == (case_reference(),)
    with pytest.raises(DuplicateReference):
        EvalSuiteVersion(**{**base, "case_references": (case_reference(), case_reference())})
    foreign = replace(case_reference(), suite_id=EvalSuiteId("other-suite"))
    with pytest.raises(IncompatibleReference):
        EvalSuiteVersion(**{**base, "case_references": (foreign,)})


def test_case_normalizes_tags_and_enforces_weight_timeout_and_sensitive_references() -> None:
    model = EvalCaseVersion(
        SUITE_ID,
        CASE_ID,
        VERSION,
        content(),
        content(),
        evaluator(),
        Decimal("1"),
        (" Accuracy ", "REQUIRED"),
        InformationOwnership.PROJECT,
        DataClassification.PUBLIC,
        Decimal("30"),
        SideEffectPolicy.NONE,
        True,
        False,
        DefinitionStatus.FROZEN,
        CHECKSUM,
    )
    assert model.tags == ("accuracy", "required")
    with pytest.raises(DuplicateReference):
        replace(model, tags=("Tag", " tag "))
    with pytest.raises(InvalidCase):
        replace(model, weight=Decimal("0"))
    with pytest.raises(InvalidCase):
        replace(model, timeout_seconds=Decimal("-1"))
    with pytest.raises(InvalidCase):
        replace(model, side_effect_policy="none")
    with pytest.raises(SensitivePayloadViolation):
        ContentBinding(
            InputKind.INLINE,
            DataClassification.CONFIDENTIAL,
            inline_value="private prompt",
        )
    with pytest.raises(SensitivePayloadViolation):
        ContentBinding(
            InputKind.INLINE,
            DataClassification.INTERNAL,
            inline_value="internal prompt without a policy decision",
        )
    assert "bounded non-sensitive fixture" not in repr(model)


def test_dataset_binding_is_reference_only_and_rejects_desktop_custody() -> None:
    binding = DatasetBinding(
        DatasetBindingId("binding-1"),
        "asset-1",
        "custody://dataset/revision/1",
        Revision(1),
        CHECKSUM,
        ContentChecksum(SHA_B),
        100,
        DataClassification.CONFIDENTIAL,
        InformationOwnership.PROJECT,
        "classification-snapshot-1",
        "ownership-snapshot-1",
        "retention-1",
        Fingerprint(SHA_C),
        DatasetCustodyKind.GOVERNED_LOCAL,
        NOW,
        ContentChecksum(SHA_D),
    )
    assert "custody://dataset/revision/1" not in repr(binding)
    assert not hasattr(binding, "payload")
    with pytest.raises(InvalidDatasetBinding):
        replace(binding, custody_kind="desktop_ui_upload")
    with pytest.raises(InvalidDatasetBinding):
        replace(binding, content_reference="private dataset payload")
    with pytest.raises(InvalidDatasetBinding):
        replace(binding, asset_id="")
    with pytest.raises(InvalidDatasetBinding):
        replace(binding, dataset_revision="1")
    with pytest.raises(InvalidDatasetBinding):
        replace(binding, content_checksum=None)


def test_manifest_is_complete_versioned_and_rejects_duplicates_and_secret_environment() -> None:
    assert manifest().execution.determinism_mode is DeterminismMode.DETERMINISTIC
    with pytest.raises(DuplicateReference):
        manifest(case_references=(case_reference(), case_reference()))
    with pytest.raises(InvalidRunManifest):
        manifest(execution=execution_protocol(seeds=(41,)))
    with pytest.raises(InvalidRunManifest):
        manifest(protocol_fingerprint=None)
    with pytest.raises(SensitivePayloadViolation):
        EnvironmentSnapshot(
            "Windows",
            "x86_64",
            "3.12",
            "v3",
            capability_versions=(("hostname", "private-host"),),
        )
    with pytest.raises(InvalidRunManifest):
        DecodingParameters(0.0, Decimal("1"), 128)  # type: ignore[arg-type]


def test_run_model_validates_prepared_and_terminal_state_references_without_transitions() -> None:
    created = EvalRun(
        EvalRunId("run-1"),
        SUITE_ID,
        VERSION,
        RunStatus.CREATED,
        Revision(1),
        NOW,
        NOW,
    )
    assert created.manifest_id is None
    with pytest.raises(InvalidRun):
        replace(created, status=RunStatus.READY)
    ready = replace(
        created,
        status=RunStatus.READY,
        manifest_id=EvalRunManifestId("manifest-1"),
    )
    assert ready.status is RunStatus.READY
    with pytest.raises(InvalidRun):
        replace(ready, status=RunStatus.COMPLETED)
    completed = replace(
        ready,
        status=RunStatus.COMPLETED,
        finalization_reference="finalization-1",
    )
    assert completed.finalization_reference == "finalization-1"


@pytest.mark.parametrize(
    "changes",
    [
        {"raw_value": Decimal("11")},
        {"confidence": Decimal("1.1")},
        {"variance": Decimal("-0.01")},
        {"scale_minimum": Decimal("1"), "scale_maximum": Decimal("1")},
    ],
)
def test_score_rejects_invalid_scales_values_confidence_and_variance(changes: dict) -> None:
    with pytest.raises(InvalidScore):
        score(**changes)


def test_binary_score_uses_canonical_scale_and_invalid_score_has_no_verdict_value() -> None:
    binary = score(
        kind=ScoreKind.BINARY,
        raw_value=Decimal("1"),
        scale_maximum=Decimal("1"),
        normalized_value=Decimal("1"),
    )
    assert binary.raw_value == Decimal("1")
    with pytest.raises(InvalidScore):
        replace(binary, raw_value=Decimal("0.5"), normalized_value=Decimal("0.5"))
    invalid = score(
        status=ScoreStatus.INVALID,
        raw_value=None,
        normalized_value=None,
        sample_count=0,
        confidence=None,
        confidence_method=None,
        reason_code="shape_invalid",
    )
    assert invalid.normalized_value is None


def test_result_enforces_status_score_verdict_and_hides_output_reference() -> None:
    result = EvalResult(
        EvalResultId("result-1"),
        EvalRunId("run-1"),
        case_reference(),
        1,
        "execution-1",
        ResultStatus.VALID,
        "output-asset-1",
        "custody://private-output",
        CHECKSUM,
        "safe result summary",
        (score(),),
        Verdict.PASSED,
        None,
        ResourceUsage(20, cpu_ms=10),
        "evaluator-artifact-1",
        "evaluator-provenance-1",
        Fingerprint(SHA_E),
        "private-evals",
        "11.0.0",
        NOW,
        ContentChecksum(SHA_B),
    )
    assert "custody://private-output" not in repr(result)
    with pytest.raises(InvalidResult):
        replace(result, error_code="provider_timeout")
    with pytest.raises(InvalidResult):
        replace(result, output_reference="private raw output")
    with pytest.raises(SensitivePayloadViolation) as caught:
        replace(result, safe_summary="token=must-not-appear")
    assert "must-not-appear" not in str(caught.value)
    with pytest.raises(InvalidResult):
        replace(result, scores=(replace(score(), status=ScoreStatus.INVALID, raw_value=None,
                                        normalized_value=None, sample_count=0, confidence=None,
                                        confidence_method=None, reason_code="invalid"),))
    with pytest.raises(InvalidResult):
        ResourceUsage(-1)


def test_baseline_requires_eligible_run_and_external_authority_for_non_candidate_state() -> None:
    assert baseline().status is BaselineStatus.CANDIDATE
    with pytest.raises(InvalidBaseline):
        baseline(source_run_verdict=Verdict.FAILED)
    with pytest.raises(InvalidBaseline):
        baseline(status=BaselineStatus.ACTIVE)
    active = baseline(
        status=BaselineStatus.ACTIVE,
        governance_binding_reference="governance-binding-1",
    )
    assert active.governance_binding_reference == "governance-binding-1"


def test_comparison_rejects_self_comparison_and_represents_incompatibility() -> None:
    incompatible = EvalComparison(
        ComparisonId("comparison-1"),
        EvalRunId("run-current"),
        BaselineId("baseline-1"),
        EvalRunId("run-baseline"),
        scope(),
        Fingerprint(SHA_B),
        Fingerprint(SHA_C),
        (),
        ComparisonResult.INCOMPATIBLE,
        (),
        ("protocol_mismatch",),
        CHECKSUM,
        NOW,
    )
    assert incompatible.result is ComparisonResult.INCOMPATIBLE
    with pytest.raises(InvalidComparison):
        replace(incompatible, current_run_id=EvalRunId("run-baseline"))
    with pytest.raises(InvalidComparison):
        replace(
            incompatible,
            metric_deltas=(MetricDelta("accuracy", Decimal("0.8"), Decimal("0.7"), Decimal("-0.1")),),
        )
    with pytest.raises(InvalidComparison):
        MetricDelta("accuracy", 0.8, Decimal("0.7"), Decimal("-0.1"))  # type: ignore[arg-type]


def test_regression_rule_enforces_thresholds_unique_critical_cases_and_failure_budget() -> None:
    rule = RegressionRule(
        RegressionRuleId("rule-1"),
        VERSION,
        DefinitionStatus.FROZEN,
        Decimal("0.8"),
        Decimal("0.05"),
        (MetricThreshold("accuracy", minimum=Decimal("0.75")),),
        (case_reference(),),
        (case_reference(),),
        0,
        None,
        2,
        Decimal("0.1"),
        Decimal("0.9"),
        CHECKSUM,
    )
    assert rule.critical_cases == rule.mandatory_cases
    with pytest.raises(DuplicateReference):
        replace(rule, critical_cases=(case_reference(), case_reference()))
    with pytest.raises(InvalidRegressionRule):
        replace(rule, failure_budget_count=-1)
    with pytest.raises(InvalidRegressionRule):
        RegressionRule(
            RegressionRuleId("global-only"), VERSION, DefinitionStatus.FROZEN,
            Decimal("0.8"), None, (), (), (), None, None, 1, None, None, CHECKSUM,
        )


def test_regression_report_has_typed_result_and_no_private_payload_field() -> None:
    report = RegressionReport(
        RegressionReportId("report-1"),
        ComparisonId("comparison-1"),
        RegressionRuleId("rule-1"),
        VERSION,
        CHECKSUM,
        ComparisonResult.REGRESSED,
        (RegressionOutcome("critical_case_failed", ComparisonResult.REGRESSED,
                           case_reference=case_reference()),),
        ("critical_case_failed",),
        ContentChecksum(SHA_B),
        NOW,
    )
    assert report.result is ComparisonResult.REGRESSED
    assert not hasattr(report, "payload")
