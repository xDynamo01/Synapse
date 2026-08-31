from __future__ import annotations

import hashlib
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

import synapse.skills as public_skills
from synapse.skills.phase2_models import (
    PublishedSkillManifest,
    PublishedSkillVersionId,
    SkillContentFingerprint,
    SkillContentKind,
    SkillContentRef,
    SkillId,
    SkillLogicalPath,
    SkillManifestFormatVersion,
    SkillProvenance,
    SkillPublicationScope,
    SkillSemanticReference,
    SkillVersion,
)
from synapse.skills.phase3_contracts import SkillCatalogStore, SkillStoreWriteOutcome
from synapse.skills.phase3_errors import (
    SkillStoreDivergentDuplicate,
    SkillStoreNotFound,
    SkillStoreUnavailable,
)
from synapse.skills.phase3_records import (
    PublishedSkillVersionRecord,
    SkillEvaluationBindingRecord,
)
from synapse.skills.phase3_values import (
    SkillStoreQueryLimit,
    SkillStoreRecordFingerprint,
    SkillStoreRecordId,
)
from synapse.skills.phase10_refs import ExternalBinderRef
from synapse.skills.phase11_bindings import SkillPrivateEvalBindingService
from synapse.skills.phase11_contracts import SkillPrivateEvalBindingStore
from synapse.skills.phase11_errors import (
    IncompleteSkillPrivateEvalBindingHistory,
    InvalidSkillPrivateEvalBindingHistory,
    InvalidSkillPrivateEvalBindingRequest,
    InvalidSkillPrivateEvalGranularity,
    InvalidSkillPrivateEvalReference,
    InvalidSkillPrivateEvalTemporalRelation,
    SkillPrivateEvalBindingCorrespondenceMismatch,
    SkillPrivateEvalBindingDivergentDuplicate,
    SkillPrivateEvalBindingStoreUnavailable,
    SkillPrivateEvalBindingSubjectNotPublished,
)
from synapse.skills.phase11_models import (
    BindSkillPrivateEvalResultRequest,
    SkillPrivateEvalBindingDiagnosticKind,
    SkillPrivateEvalBindingGranularity,
    SkillPrivateEvalBindingHistory,
    SkillPrivateEvalBindingOutcome,
    SkillPrivateEvalBindingRecord,
)
from synapse.skills.phase11_refs import (
    PrivateEvalBaselineRef,
    PrivateEvalBindingOccurrenceRef,
    PrivateEvalBindingRef,
    PrivateEvalCaseRef,
    PrivateEvalComparisonRef,
    PrivateEvalEvidenceRef,
    PrivateEvalProfileRef,
    PrivateEvalRegressionRef,
    PrivateEvalResultRef,
    PrivateEvalRunRef,
    PrivateEvalSuiteRef,
    PrivateEvalVerdictRef,
)

PUBLISHED_AT = datetime(2026, 7, 29, 12, 0, tzinfo=UTC)
EVALUATED_AT = PUBLISHED_AT + timedelta(minutes=1)
BOUND_AT = PUBLISHED_AT + timedelta(minutes=2)
LIMIT = SkillStoreQueryLimit(100)


class FakeCatalog:
    def __init__(self, record: PublishedSkillVersionRecord | None) -> None:
        self.record = record
        self.unavailable = False

    def save_version(self, record: PublishedSkillVersionRecord) -> SkillStoreWriteOutcome:
        raise AssertionError("Slice 11 must not publish")

    def get_version(self, identity: PublishedSkillVersionId) -> PublishedSkillVersionRecord:
        if self.unavailable:
            raise SkillStoreUnavailable()
        if self.record is None or self.record.identity != identity:
            raise SkillStoreNotFound()
        return self.record

    def list_versions(
        self, skill_id: SkillId, limit: SkillStoreQueryLimit
    ) -> tuple[PublishedSkillVersionRecord, ...]:
        raise AssertionError("Slice 11 requires exact lookup")


class FakePrivateEvalBindings:
    def __init__(self) -> None:
        self.records: dict[
            PrivateEvalBindingOccurrenceRef, SkillPrivateEvalBindingRecord
        ] = {}
        self.complete = True
        self.unavailable = False
        self.fail_after_append = False
        self.append_calls = 0
        self.corrupt_history: tuple[SkillPrivateEvalBindingRecord, ...] | None = None
        self.override_history: tuple[SkillPrivateEvalBindingRecord, ...] | None = None

    def append_private_eval(
        self, record: SkillPrivateEvalBindingRecord
    ) -> SkillStoreWriteOutcome:
        self.append_calls += 1
        if self.unavailable:
            raise SkillStoreUnavailable()
        existing = self.records.get(record.occurrence_ref)
        if existing is None:
            self.records[record.occurrence_ref] = record
            outcome = SkillStoreWriteOutcome.CREATED
        elif existing == record:
            outcome = SkillStoreWriteOutcome.IDEMPOTENT_REPLAY
        else:
            raise SkillStoreDivergentDuplicate()
        if self.fail_after_append:
            self.fail_after_append = False
            raise SkillStoreUnavailable()
        return outcome

    def list_private_evals_for_version(
        self,
        identity: PublishedSkillVersionId,
        limit: SkillStoreQueryLimit,
    ) -> SkillPrivateEvalBindingHistory:
        if self.unavailable:
            raise SkillStoreUnavailable()
        if self.corrupt_history is not None:
            return SkillPrivateEvalBindingHistory(self.corrupt_history, self.complete)
        if self.override_history is not None:
            return SkillPrivateEvalBindingHistory(self.override_history, self.complete)
        records = tuple(
            reversed(
                tuple(record for record in self.records.values() if record.identity == identity)
            )
        )[: limit.limit]
        return SkillPrivateEvalBindingHistory(records, self.complete)


def _published() -> PublishedSkillVersionRecord:
    content = b"# Evaluated skill"
    fingerprint = SkillContentFingerprint(hashlib.sha256(content).hexdigest())
    content_ref = SkillContentRef(
        SkillLogicalPath("SKILL.md"),
        fingerprint,
        SkillContentKind.INSTRUCTIONS,
        "text/markdown",
        len(content),
    )
    manifest = PublishedSkillManifest(
        format_version=SkillManifestFormatVersion(1),
        skill_id=SkillId("evaluated-skill"),
        version=SkillVersion.parse("1.0.0"),
        display_name="Evaluated skill",
        summary="Skill Private Evals binding test.",
        description="An exact published identity for Private Evals binding tests.",
        provenance=SkillProvenance(SkillSemanticReference("publisher:test")),
        scopes=(SkillPublicationScope.PROJECT,),
        content=(content_ref,),
    )
    identity = PublishedSkillVersionId.from_manifest(manifest, fingerprint)
    return PublishedSkillVersionRecord(
        identity,
        manifest,
        PUBLISHED_AT,
        SkillSemanticReference("actor:publisher"),
        SkillSemanticReference("publication:test"),
    )


def _request(
    identity: PublishedSkillVersionId,
    *,
    granularity: SkillPrivateEvalBindingGranularity = (
        SkillPrivateEvalBindingGranularity.SUITE_RESULT
    ),
    run: str = "private-eval-run:run-a",
    result: str = "private-eval-result:result-a",
    verdict: str | None = "private-eval-verdict:verdict-a",
    suite: str = "private-eval-suite:suite-a",
    case: str | None = None,
    profile: str = "private-eval-profile:profile-a",
    baseline: str | None = None,
    comparison: str | None = None,
    regression: str | None = None,
    evidence: tuple[str, ...] = (),
    binder: str = "external-binder:binder-a",
    evaluated_at: datetime = EVALUATED_AT,
    bound_at: datetime = BOUND_AT,
) -> BindSkillPrivateEvalResultRequest:
    return BindSkillPrivateEvalResultRequest(
        identity=identity,
        granularity=granularity,
        run_ref=PrivateEvalRunRef(run),
        result_ref=PrivateEvalResultRef(result),
        verdict_ref=PrivateEvalVerdictRef(verdict) if verdict is not None else None,
        suite_ref=PrivateEvalSuiteRef(suite),
        case_ref=PrivateEvalCaseRef(case) if case is not None else None,
        profile_ref=PrivateEvalProfileRef(profile),
        baseline_ref=PrivateEvalBaselineRef(baseline) if baseline is not None else None,
        comparison_ref=(
            PrivateEvalComparisonRef(comparison) if comparison is not None else None
        ),
        regression_ref=(
            PrivateEvalRegressionRef(regression) if regression is not None else None
        ),
        evidence_refs=tuple(PrivateEvalEvidenceRef(item) for item in evidence),
        binder_ref=ExternalBinderRef(binder),
        evaluated_at=evaluated_at,
        bound_at=bound_at,
    )


def _service() -> tuple[
    PublishedSkillVersionRecord,
    FakePrivateEvalBindings,
    SkillPrivateEvalBindingService,
]:
    publication = _published()
    catalog_port: SkillCatalogStore = FakeCatalog(publication)
    bindings = FakePrivateEvalBindings()
    binding_port: SkillPrivateEvalBindingStore = bindings
    return (
        publication,
        bindings,
        SkillPrivateEvalBindingService(catalog_port, binding_port, LIMIT),
    )


@pytest.mark.parametrize(
    ("reference_type", "value"),
    (
        (PrivateEvalRunRef, "private-eval-run:run-a"),
        (PrivateEvalResultRef, "private-eval-result:result-a"),
        (PrivateEvalVerdictRef, "private-eval-verdict:verdict-a"),
        (PrivateEvalEvidenceRef, "private-eval-evidence:evidence-a"),
        (PrivateEvalSuiteRef, "private-eval-suite:suite-a"),
        (PrivateEvalCaseRef, "private-eval-case:case-a"),
        (PrivateEvalProfileRef, "private-eval-profile:profile-a"),
        (PrivateEvalBaselineRef, "private-eval-baseline:baseline-a"),
        (PrivateEvalComparisonRef, "private-eval-comparison:comparison-a"),
        (PrivateEvalRegressionRef, "private-eval-regression:regression-a"),
        (PrivateEvalBindingRef, "private-eval-binding:" + "a" * 64),
        (
            PrivateEvalBindingOccurrenceRef,
            "private-eval-binding-occurrence:" + "a" * 64,
        ),
    ),
)
def test_private_eval_references_have_closed_families(
    reference_type: type, value: str
) -> None:
    assert str(reference_type(value)) == value


@pytest.mark.parametrize(
    "value",
    (
        "",
        "private-eval-result:",
        "private-eval-run:wrong-family",
        "private-eval-result:https://example.test",
        "private-eval-result:C:\\secret",
        "private-eval-result:/var/secret",
        "private-eval-result:user:password",
        "private-eval-result:value?token=secret",
        "private-eval-result:value#fragment",
        "private-eval-result:white space",
        "private-eval-result:\tcontrol",
        'private-eval-result:{"payload":"raw"}',
        "private-eval-result:Ã¡lpha",
        "private-eval-result:nul\x00value",
        "private-eval-result:" + "a" * 129,
    ),
)
def test_private_eval_references_reject_sensitive_or_unbounded_values(value: str) -> None:
    with pytest.raises(InvalidSkillPrivateEvalReference):
        PrivateEvalResultRef(value)


def test_reference_exact_local_limit_and_digest_validation() -> None:
    local = "a" * 128
    assert str(PrivateEvalResultRef(f"private-eval-result:{local}")).endswith(local)
    with pytest.raises(InvalidSkillPrivateEvalReference):
        PrivateEvalBindingRef("private-eval-binding:" + "a" * 63)


@pytest.mark.parametrize(
    ("granularity", "case", "baseline", "comparison", "regression"),
    (
        (SkillPrivateEvalBindingGranularity.SUITE_RESULT, None, None, None, None),
        (
            SkillPrivateEvalBindingGranularity.CASE_RESULT,
            "private-eval-case:case-a",
            None,
            None,
            None,
        ),
        (
            SkillPrivateEvalBindingGranularity.COMPARISON_RESULT,
            None,
            "private-eval-baseline:baseline-a",
            "private-eval-comparison:comparison-a",
            None,
        ),
        (
            SkillPrivateEvalBindingGranularity.REGRESSION_RESULT,
            None,
            "private-eval-baseline:baseline-a",
            "private-eval-comparison:comparison-a",
            "private-eval-regression:regression-a",
        ),
    ),
)
def test_explicit_granularities_accept_only_coherent_references(
    granularity: SkillPrivateEvalBindingGranularity,
    case: str | None,
    baseline: str | None,
    comparison: str | None,
    regression: str | None,
) -> None:
    request = _request(
        _published().identity,
        granularity=granularity,
        case=case,
        baseline=baseline,
        comparison=comparison,
        regression=regression,
    )
    assert request.granularity is granularity


@pytest.mark.parametrize(
    ("granularity", "case", "baseline", "comparison", "regression"),
    (
        (
            SkillPrivateEvalBindingGranularity.SUITE_RESULT,
            "private-eval-case:case-a",
            None,
            None,
            None,
        ),
        (SkillPrivateEvalBindingGranularity.CASE_RESULT, None, None, None, None),
        (
            SkillPrivateEvalBindingGranularity.COMPARISON_RESULT,
            None,
            None,
            "private-eval-comparison:comparison-a",
            None,
        ),
        (
            SkillPrivateEvalBindingGranularity.COMPARISON_RESULT,
            None,
            "private-eval-baseline:baseline-a",
            None,
            None,
        ),
        (
            SkillPrivateEvalBindingGranularity.REGRESSION_RESULT,
            None,
            "private-eval-baseline:baseline-a",
            "private-eval-comparison:comparison-a",
            None,
        ),
    ),
)
def test_incoherent_granularity_is_rejected(
    granularity: SkillPrivateEvalBindingGranularity,
    case: str | None,
    baseline: str | None,
    comparison: str | None,
    regression: str | None,
) -> None:
    with pytest.raises(InvalidSkillPrivateEvalGranularity):
        _request(
            _published().identity,
            granularity=granularity,
            case=case,
            baseline=baseline,
            comparison=comparison,
            regression=regression,
        )


@pytest.mark.parametrize(
    ("verdict", "evidence"),
    (
        (None, ()),
        ("private-eval-verdict:verdict-a", ()),
        (None, ("private-eval-evidence:evidence-a",)),
    ),
)
def test_run_verdict_or_evidence_without_result_is_rejected(
    verdict: str | None,
    evidence: tuple[str, ...],
) -> None:
    request = _request(_published().identity, verdict=verdict, evidence=evidence)
    with pytest.raises(InvalidSkillPrivateEvalBindingRequest):
        BindSkillPrivateEvalResultRequest(
            identity=request.identity,
            granularity=request.granularity,
            run_ref=request.run_ref,
            result_ref=None,  # type: ignore[arg-type]
            verdict_ref=request.verdict_ref,
            suite_ref=request.suite_ref,
            case_ref=request.case_ref,
            profile_ref=request.profile_ref,
            baseline_ref=request.baseline_ref,
            comparison_ref=request.comparison_ref,
            regression_ref=request.regression_ref,
            evidence_refs=request.evidence_refs,
            binder_ref=request.binder_ref,
            evaluated_at=request.evaluated_at,
            bound_at=request.bound_at,
        )


def test_evidence_is_canonical_identity_and_duplicates_are_rejected() -> None:
    identity = _published().identity
    request = _request(
        identity,
        evidence=(
            "private-eval-evidence:evidence-b",
            "private-eval-evidence:evidence-a",
        ),
    )
    assert tuple(map(str, request.evidence_refs)) == (
        "private-eval-evidence:evidence-a",
        "private-eval-evidence:evidence-b",
    )
    with pytest.raises(InvalidSkillPrivateEvalBindingRequest):
        _request(
            identity,
            evidence=(
                "private-eval-evidence:evidence-a",
                "private-eval-evidence:evidence-a",
            ),
        )


def test_temporal_relation_requires_utc_and_evaluation_not_after_binding() -> None:
    identity = _published().identity
    with pytest.raises(InvalidSkillPrivateEvalTemporalRelation):
        _request(identity, evaluated_at=BOUND_AT + timedelta(seconds=1))
    with pytest.raises(InvalidSkillPrivateEvalTemporalRelation):
        _request(identity, evaluated_at=EVALUATED_AT.replace(tzinfo=None))


def test_binding_requires_exact_publication_and_creates_structural_record() -> None:
    publication, bindings, service = _service()
    result = service.bind(_request(publication.identity))
    assert result.outcome is SkillPrivateEvalBindingOutcome.CREATED
    assert result.record.identity == publication.identity
    assert result.projection is not None
    assert result.projection.result_refs == (result.record.result_ref,)
    assert bindings.append_calls == 1


def test_unpublished_and_prepublication_binding_are_rejected() -> None:
    publication = _published()
    bindings = FakePrivateEvalBindings()
    missing = SkillPrivateEvalBindingService(FakeCatalog(None), bindings, LIMIT)
    with pytest.raises(SkillPrivateEvalBindingSubjectNotPublished):
        missing.bind(_request(publication.identity))
    service = SkillPrivateEvalBindingService(FakeCatalog(publication), bindings, LIMIT)
    with pytest.raises(SkillPrivateEvalBindingCorrespondenceMismatch):
        service.bind(
            _request(
                publication.identity,
                evaluated_at=PUBLISHED_AT - timedelta(minutes=2),
                bound_at=PUBLISHED_AT - timedelta(minutes=1),
            )
        )


def test_divergent_published_fingerprint_is_not_partial_correspondence() -> None:
    publication = _published()
    divergent_identity = replace(
        publication.identity,
        content_fingerprint=SkillContentFingerprint("f" * 64),
    )
    service = SkillPrivateEvalBindingService(
        FakeCatalog(publication),
        FakePrivateEvalBindings(),
        LIMIT,
    )
    with pytest.raises(SkillPrivateEvalBindingSubjectNotPublished):
        service.bind(_request(divergent_identity))


def test_candidate_evaluation_may_predate_exact_publication() -> None:
    publication, _, service = _service()
    result = service.bind(
        _request(
            publication.identity,
            evaluated_at=PUBLISHED_AT - timedelta(minutes=1),
            bound_at=PUBLISHED_AT,
        )
    )
    assert result.record.evaluated_at < publication.recorded_at


def test_identical_retry_replays_without_second_append() -> None:
    publication, bindings, service = _service()
    request = _request(publication.identity)
    first = service.bind(request)
    replay = service.bind(request)
    assert replay.record is first.record
    assert replay.outcome is SkillPrivateEvalBindingOutcome.IDEMPOTENT_REPLAY
    assert bindings.append_calls == 1


@pytest.mark.parametrize(
    "change",
    (
        {"binder": "external-binder:binder-b"},
        {"bound_at": BOUND_AT + timedelta(seconds=1)},
    ),
)
def test_binder_or_bound_time_creates_new_occurrence_same_binding(
    change: dict[str, object],
) -> None:
    publication, _, service = _service()
    first = service.bind(_request(publication.identity))
    second = service.bind(_request(publication.identity, **change))
    assert first.record.binding_ref == second.record.binding_ref
    assert first.record.occurrence_ref != second.record.occurrence_ref
    assert second.outcome is SkillPrivateEvalBindingOutcome.CREATED


def test_evidence_order_replays_but_additional_evidence_creates_new_binding() -> None:
    publication, bindings, service = _service()
    first = service.bind(
        _request(
            publication.identity,
            evidence=(
                "private-eval-evidence:evidence-a",
                "private-eval-evidence:evidence-b",
            ),
        )
    )
    replay = service.bind(
        _request(
            publication.identity,
            evidence=(
                "private-eval-evidence:evidence-b",
                "private-eval-evidence:evidence-a",
            ),
        )
    )
    assert replay.record is first.record
    additional = service.bind(
        _request(
            publication.identity,
            evidence=(
                "private-eval-evidence:evidence-a",
                "private-eval-evidence:evidence-b",
                "private-eval-evidence:evidence-c",
            ),
            bound_at=BOUND_AT + timedelta(seconds=1),
        )
    )
    assert additional.record.binding_ref != first.record.binding_ref
    assert bindings.append_calls == 2


@pytest.mark.parametrize(
    "change",
    (
        {"result": "private-eval-result:result-b"},
        {"verdict": "private-eval-verdict:verdict-b"},
        {"profile": "private-eval-profile:profile-b"},
    ),
)
def test_result_verdict_or_profile_change_creates_new_binding(
    change: dict[str, object],
) -> None:
    publication, _, service = _service()
    first = service.bind(_request(publication.identity))
    second = service.bind(
        _request(
            publication.identity,
            **change,
            bound_at=BOUND_AT + timedelta(seconds=1),
        )
    )
    assert first.record.binding_ref != second.record.binding_ref


def test_same_result_with_different_evaluated_at_is_divergent() -> None:
    publication, _, service = _service()
    service.bind(_request(publication.identity))
    with pytest.raises(SkillPrivateEvalBindingDivergentDuplicate):
        service.bind(
            _request(
                publication.identity,
                binder="external-binder:binder-b",
                evaluated_at=EVALUATED_AT + timedelta(seconds=1),
                bound_at=BOUND_AT + timedelta(seconds=1),
            )
        )


def test_same_run_other_case_and_comparison_regression_are_new_bindings() -> None:
    publication, _, service = _service()
    case_a = service.bind(
        _request(
            publication.identity,
            granularity=SkillPrivateEvalBindingGranularity.CASE_RESULT,
            case="private-eval-case:case-a",
        )
    )
    case_b = service.bind(
        _request(
            publication.identity,
            granularity=SkillPrivateEvalBindingGranularity.CASE_RESULT,
            case="private-eval-case:case-b",
            result="private-eval-result:result-b",
            bound_at=BOUND_AT + timedelta(seconds=1),
        )
    )
    comparison = service.bind(
        _request(
            publication.identity,
            granularity=SkillPrivateEvalBindingGranularity.COMPARISON_RESULT,
            baseline="private-eval-baseline:baseline-a",
            comparison="private-eval-comparison:comparison-a",
            result="private-eval-result:result-c",
            bound_at=BOUND_AT + timedelta(seconds=2),
        )
    )
    regression = service.bind(
        _request(
            publication.identity,
            granularity=SkillPrivateEvalBindingGranularity.REGRESSION_RESULT,
            baseline="private-eval-baseline:baseline-a",
            comparison="private-eval-comparison:comparison-a",
            regression="private-eval-regression:regression-a",
            result="private-eval-result:result-d",
            bound_at=BOUND_AT + timedelta(seconds=3),
        )
    )
    assert len(
        {
            case_a.record.binding_ref,
            case_b.record.binding_ref,
            comparison.record.binding_ref,
            regression.record.binding_ref,
        }
    ) == 4


def test_same_result_with_different_comparison_is_new_binding() -> None:
    publication, _, service = _service()
    first = service.bind(
        _request(
            publication.identity,
            granularity=SkillPrivateEvalBindingGranularity.COMPARISON_RESULT,
            baseline="private-eval-baseline:baseline-a",
            comparison="private-eval-comparison:comparison-a",
        )
    )
    second = service.bind(
        _request(
            publication.identity,
            granularity=SkillPrivateEvalBindingGranularity.COMPARISON_RESULT,
            baseline="private-eval-baseline:baseline-a",
            comparison="private-eval-comparison:comparison-b",
            bound_at=BOUND_AT + timedelta(seconds=1),
        )
    )
    assert first.record.binding_ref != second.record.binding_ref


@pytest.mark.parametrize(
    "request_kwargs",
    (
        {},
        {"evidence": ("private-eval-evidence:evidence-a",)},
        {
            "granularity": SkillPrivateEvalBindingGranularity.REGRESSION_RESULT,
            "baseline": "private-eval-baseline:baseline-a",
            "comparison": "private-eval-comparison:comparison-a",
            "regression": "private-eval-regression:regression-a",
            "evidence": ("private-eval-evidence:evidence-a",),
        },
    ),
)
def test_lost_response_is_reconciled_by_retry(
    request_kwargs: dict[str, object],
) -> None:
    publication, bindings, service = _service()
    request = _request(publication.identity, **request_kwargs)
    bindings.fail_after_append = True
    with pytest.raises(SkillPrivateEvalBindingStoreUnavailable):
        service.bind(request)
    replay = service.bind(request)
    assert replay.outcome is SkillPrivateEvalBindingOutcome.IDEMPOTENT_REPLAY
    assert bindings.append_calls == 1


def test_incomplete_history_is_visible_but_blocks_append() -> None:
    publication, bindings, service = _service()
    bindings.complete = False
    projection = service.projection(publication.identity)
    assert not projection.complete
    assert {item.kind for item in projection.diagnostics} == {
        SkillPrivateEvalBindingDiagnosticKind.INCOMPLETE_HISTORY
    }
    with pytest.raises(IncompleteSkillPrivateEvalBindingHistory):
        service.bind(_request(publication.identity))


def test_complete_empty_history_is_normal() -> None:
    publication, _, service = _service()
    projection = service.projection(publication.identity)
    assert projection.complete
    assert projection.history.records == ()
    assert projection.diagnostics == ()


def test_history_order_is_deterministic_and_input_independent() -> None:
    publication, _, service = _service()
    later = service.bind(
        _request(
            publication.identity,
            result="private-eval-result:result-b",
            evaluated_at=EVALUATED_AT + timedelta(seconds=1),
            bound_at=BOUND_AT + timedelta(seconds=1),
        )
    )
    earlier = service.bind(_request(publication.identity))
    assert service.history(publication.identity).records == (earlier.record, later.record)


def test_equal_timestamps_are_tied_by_occurrence_without_precedence() -> None:
    publication, _, service = _service()
    first = service.bind(_request(publication.identity))
    second = service.bind(
        _request(
            publication.identity,
            result="private-eval-result:result-b",
        )
    )
    history = service.history(publication.identity)
    assert set(history.records) == {first.record, second.record}
    assert history.records == tuple(
        sorted(history.records, key=lambda record: str(record.occurrence_ref))
    )


def test_projection_reports_only_structural_multiplicity() -> None:
    publication, _, service = _service()
    service.bind(_request(publication.identity))
    service.bind(
        _request(
            publication.identity,
            run="private-eval-run:run-b",
            result="private-eval-result:result-b",
            suite="private-eval-suite:suite-b",
            profile="private-eval-profile:profile-b",
            verdict="private-eval-verdict:verdict-b",
            bound_at=BOUND_AT + timedelta(seconds=1),
        )
    )
    kinds = {item.kind for item in service.projection(publication.identity).diagnostics}
    assert kinds == {
        SkillPrivateEvalBindingDiagnosticKind.MULTIPLE_RUN_REFERENCES,
        SkillPrivateEvalBindingDiagnosticKind.MULTIPLE_RESULT_REFERENCES,
        SkillPrivateEvalBindingDiagnosticKind.MULTIPLE_VERDICT_REFERENCES,
        SkillPrivateEvalBindingDiagnosticKind.MULTIPLE_SUITE_REFERENCES,
        SkillPrivateEvalBindingDiagnosticKind.MULTIPLE_PROFILE_REFERENCES,
    }


def test_forged_binding_or_occurrence_is_invalid_history() -> None:
    publication, bindings, service = _service()
    record = service.bind(_request(publication.identity)).record
    bindings.corrupt_history = (
        replace(
            record,
            binding_ref=PrivateEvalBindingRef("private-eval-binding:" + "f" * 64),
        ),
    )
    with pytest.raises(InvalidSkillPrivateEvalBindingHistory):
        service.history(publication.identity)


def test_store_divergent_duplicate_is_translated_safely() -> None:
    publication, bindings, service = _service()
    request = _request(publication.identity)
    record = service.bind(request).record
    bindings.records[record.occurrence_ref] = replace(
        record,
        evidence_refs=(PrivateEvalEvidenceRef("private-eval-evidence:divergent"),),
    )
    bindings.override_history = ()
    with pytest.raises(SkillPrivateEvalBindingDivergentDuplicate):
        service.bind(request)


def test_store_unavailability_is_translated_safely() -> None:
    publication, bindings, service = _service()
    bindings.unavailable = True
    with pytest.raises(SkillPrivateEvalBindingStoreUnavailable):
        service.projection(publication.identity)


def test_errors_do_not_echo_external_content() -> None:
    secret = "private-eval-result:secret-reference"
    assert secret not in str(InvalidSkillPrivateEvalReference(secret))
    assert secret not in str(SkillPrivateEvalBindingDivergentDuplicate(secret))


def test_requests_records_results_and_projections_are_frozen() -> None:
    publication, _, service = _service()
    request = _request(publication.identity)
    result = service.bind(request)
    with pytest.raises(FrozenInstanceError):
        request.bound_at = BOUND_AT  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        result.record.bound_at = BOUND_AT  # type: ignore[misc]
    assert result.projection is not None
    with pytest.raises(FrozenInstanceError):
        result.projection.complete = False  # type: ignore[misc]


def test_legacy_evaluation_record_remains_distinct() -> None:
    publication, _, service = _service()
    record = service.bind(_request(publication.identity)).record
    legacy = SkillEvaluationBindingRecord(
        SkillStoreRecordId("evaluation-binding:" + "a" * 64),
        publication.identity,
        SkillSemanticReference("evaluation:legacy"),
        SkillStoreRecordFingerprint("b" * 64),
        BOUND_AT,
        SkillSemanticReference("actor:legacy"),
    )
    assert type(record) is not type(legacy)


def test_store_contract_is_family_specific() -> None:
    methods = {name for name in SkillPrivateEvalBindingStore.__dict__ if not name.startswith("_")}
    assert methods == {
        "append_private_eval",
        "list_private_evals_for_version",
    }


def test_slice11_has_no_private_evals_runtime_or_progression_dependencies() -> None:
    paths = tuple(Path("backend/synapse/skills").glob("phase11_*.py"))
    source = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    forbidden = (
        "synapse.private_evals",
        "synapse.project_governance",
        "synapse.intelligence_boundary",
        "synapse.bootstrap",
        "synapse.api",
        "synapse.commands",
        "synapse.storage",
        "synapse.tools",
        "subprocess",
        "importlib",
        "sqlite3",
        "datetime.now",
        "uuid",
        "approved=",
        "trusted=",
        "promotable=",
        ".activate(",
        ".install(",
        ".execute(",
        ".revoke(",
    )
    assert not any(term in source for term in forbidden)


def test_public_surface_contains_only_stable_slice11_contracts() -> None:
    expected = {
        "PrivateEvalRunRef",
        "PrivateEvalResultRef",
        "PrivateEvalVerdictRef",
        "PrivateEvalEvidenceRef",
        "PrivateEvalSuiteRef",
        "PrivateEvalCaseRef",
        "PrivateEvalProfileRef",
        "PrivateEvalBaselineRef",
        "PrivateEvalComparisonRef",
        "PrivateEvalRegressionRef",
        "PrivateEvalBindingRef",
        "PrivateEvalBindingOccurrenceRef",
        "BindSkillPrivateEvalResultRequest",
        "SkillPrivateEvalBindingRecord",
        "SkillPrivateEvalBindingStore",
        "SkillPrivateEvalBindingService",
    }
    assert expected.issubset(public_skills.__all__)
    assert {
        "_private_eval_binding_ref",
        "_private_eval_occurrence_ref",
        "_canonical_private_eval_history",
        "_private_eval_projection",
        "FakePrivateEvalBindings",
    }.isdisjoint(public_skills.__all__)
