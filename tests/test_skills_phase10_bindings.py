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
from synapse.skills.phase10_contracts import SkillExternalBindingStore
from synapse.skills.phase10_errors import (
    IncompleteSkillExternalBindingHistory,
    InvalidSkillExternalBindingHistory,
    InvalidSkillExternalBindingRequest,
    InvalidSkillExternalReference,
    SkillExternalBindingCorrespondenceMismatch,
    SkillExternalBindingDivergentDuplicate,
    SkillExternalBindingStoreUnavailable,
    SkillExternalBindingSubjectNotPublished,
)
from synapse.skills.phase10_governance import SkillGovernanceBindingService
from synapse.skills.phase10_intelligence import SkillIntelligenceBindingService
from synapse.skills.phase10_models import (
    BindSkillGovernanceDecisionRequest,
    BindSkillIntelligenceFactRequest,
    SkillExternalBindingDiagnosticKind,
    SkillExternalBindingOutcome,
    SkillGovernanceBindingHistory,
    SkillGovernanceBindingRecord,
    SkillIntelligenceBindingHistory,
    SkillIntelligenceBindingRecord,
)
from synapse.skills.phase10_refs import (
    ExternalAuthorityRef,
    ExternalBinderRef,
    ExternalBindingOccurrenceRef,
    ExternalBindingRef,
    GovernanceDecisionKindRef,
    GovernanceDecisionRef,
    GovernancePolicyRef,
    IntelligenceAnalysisRef,
    IntelligenceFactKindRef,
    IntelligenceFactRef,
    IntelligenceProfileRef,
)

PUBLISHED_AT = datetime(2026, 7, 28, 12, 0, tzinfo=UTC)
BOUND_AT = PUBLISHED_AT + timedelta(minutes=5)
OBSERVED_AT = PUBLISHED_AT + timedelta(minutes=2)
LIMIT = SkillStoreQueryLimit(100)


class FakeCatalog:
    def __init__(self, record: PublishedSkillVersionRecord | None) -> None:
        self.record = record
        self.unavailable = False

    def save_version(self, record: PublishedSkillVersionRecord) -> SkillStoreWriteOutcome:
        raise AssertionError("Slice 10 must not publish")

    def get_version(self, identity: PublishedSkillVersionId) -> PublishedSkillVersionRecord:
        if self.unavailable:
            raise SkillStoreUnavailable()
        if self.record is None or self.record.identity != identity:
            raise SkillStoreNotFound()
        return self.record

    def list_versions(
        self, skill_id: SkillId, limit: SkillStoreQueryLimit
    ) -> tuple[PublishedSkillVersionRecord, ...]:
        raise AssertionError("Slice 10 requires exact lookup")


class FakeExternalBindings:
    def __init__(self) -> None:
        self.governance: dict[ExternalBindingOccurrenceRef, SkillGovernanceBindingRecord] = {}
        self.intelligence: dict[ExternalBindingOccurrenceRef, SkillIntelligenceBindingRecord] = {}
        self.complete = True
        self.unavailable = False
        self.fail_after_governance = False
        self.fail_after_intelligence = False
        self.append_governance_calls = 0
        self.append_intelligence_calls = 0
        self.corrupt_governance_history: tuple[SkillGovernanceBindingRecord, ...] | None = None

    def append_governance(self, record: SkillGovernanceBindingRecord) -> SkillStoreWriteOutcome:
        self.append_governance_calls += 1
        outcome = self._append(self.governance, record)
        if self.fail_after_governance:
            self.fail_after_governance = False
            raise SkillStoreUnavailable()
        return outcome

    def append_intelligence(self, record: SkillIntelligenceBindingRecord) -> SkillStoreWriteOutcome:
        self.append_intelligence_calls += 1
        outcome = self._append(self.intelligence, record)
        if self.fail_after_intelligence:
            self.fail_after_intelligence = False
            raise SkillStoreUnavailable()
        return outcome

    def list_governance_for_version(
        self,
        identity: PublishedSkillVersionId,
        limit: SkillStoreQueryLimit,
    ) -> SkillGovernanceBindingHistory:
        if self.unavailable:
            raise SkillStoreUnavailable()
        if self.corrupt_governance_history is not None:
            return SkillGovernanceBindingHistory(self.corrupt_governance_history, self.complete)
        records = tuple(
            reversed(
                tuple(record for record in self.governance.values() if record.identity == identity)
            )
        )[: limit.limit]
        return SkillGovernanceBindingHistory(records, self.complete)

    def list_intelligence_for_version(
        self,
        identity: PublishedSkillVersionId,
        limit: SkillStoreQueryLimit,
    ) -> SkillIntelligenceBindingHistory:
        if self.unavailable:
            raise SkillStoreUnavailable()
        records = tuple(
            reversed(
                tuple(
                    record for record in self.intelligence.values() if record.identity == identity
                )
            )
        )[: limit.limit]
        return SkillIntelligenceBindingHistory(records, self.complete)

    def _append(self, target: dict, record: object) -> SkillStoreWriteOutcome:
        if self.unavailable:
            raise SkillStoreUnavailable()
        occurrence_ref = record.occurrence_ref  # type: ignore[attr-defined]
        existing = target.get(occurrence_ref)
        if existing is None:
            target[occurrence_ref] = record
            return SkillStoreWriteOutcome.CREATED
        if existing == record:
            return SkillStoreWriteOutcome.IDEMPOTENT_REPLAY
        raise SkillStoreDivergentDuplicate()


def _published() -> PublishedSkillVersionRecord:
    content = b"# Bound skill"
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
        skill_id=SkillId("bound-skill"),
        version=SkillVersion.parse("1.0.0"),
        display_name="Bound skill",
        summary="Skill external binding test.",
        description="An exact published identity for external binding tests.",
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


def _governance_request(
    identity: PublishedSkillVersionId,
    *,
    decision: str = "governance-decision:decision-a",
    policy: str = "governance-policy:policy-a",
    authority: str = "external-authority:governance-a",
    binder: str = "external-binder:binder-a",
    bound_at: datetime = BOUND_AT,
) -> BindSkillGovernanceDecisionRequest:
    return BindSkillGovernanceDecisionRequest(
        identity=identity,
        decision_ref=GovernanceDecisionRef(decision),
        decision_kind_ref=GovernanceDecisionKindRef("governance-decision-kind:review-outcome"),
        policy_ref=GovernancePolicyRef(policy),
        authority_ref=ExternalAuthorityRef(authority),
        binder_ref=ExternalBinderRef(binder),
        bound_at=bound_at,
    )


def _intelligence_request(
    identity: PublishedSkillVersionId,
    *,
    fact: str = "intelligence-fact:fact-a",
    profile: str = "intelligence-profile:profile-a",
    authority: str = "external-authority:intelligence-a",
    binder: str = "external-binder:binder-a",
    observed_at: datetime = OBSERVED_AT,
    bound_at: datetime = BOUND_AT,
) -> BindSkillIntelligenceFactRequest:
    return BindSkillIntelligenceFactRequest(
        identity=identity,
        fact_ref=IntelligenceFactRef(fact),
        analysis_ref=IntelligenceAnalysisRef("intelligence-analysis:analysis-a"),
        fact_kind_ref=IntelligenceFactKindRef("intelligence-fact-kind:compatibility"),
        profile_ref=IntelligenceProfileRef(profile),
        authority_ref=ExternalAuthorityRef(authority),
        binder_ref=ExternalBinderRef(binder),
        observed_at=observed_at,
        bound_at=bound_at,
    )


def _services() -> tuple[
    PublishedSkillVersionRecord,
    FakeExternalBindings,
    SkillGovernanceBindingService,
    SkillIntelligenceBindingService,
]:
    publication = _published()
    catalog = FakeCatalog(publication)
    bindings = FakeExternalBindings()
    catalog_port: SkillCatalogStore = catalog
    binding_port: SkillExternalBindingStore = bindings
    return (
        publication,
        bindings,
        SkillGovernanceBindingService(catalog_port, binding_port, LIMIT),
        SkillIntelligenceBindingService(catalog_port, binding_port, LIMIT),
    )


@pytest.mark.parametrize(
    ("reference_type", "value"),
    (
        (ExternalAuthorityRef, "external-authority:authority-a"),
        (ExternalBinderRef, "external-binder:binder-a"),
        (GovernanceDecisionRef, "governance-decision:decision-a"),
        (
            GovernanceDecisionKindRef,
            "governance-decision-kind:review-outcome",
        ),
        (GovernancePolicyRef, "governance-policy:policy-a"),
        (IntelligenceFactRef, "intelligence-fact:fact-a"),
        (IntelligenceAnalysisRef, "intelligence-analysis:analysis-a"),
        (
            IntelligenceFactKindRef,
            "intelligence-fact-kind:compatibility",
        ),
        (IntelligenceProfileRef, "intelligence-profile:profile-a"),
    ),
)
def test_neutral_references_accept_only_their_closed_namespace(
    reference_type: type, value: str
) -> None:
    assert str(reference_type(value)) == value


@pytest.mark.parametrize(
    "value",
    (
        "",
        "governance-decision:",
        "governance-policy:wrong-family",
        "governance-decision:https://example.test",
        "governance-decision:C:\\secret",
        "governance-decision:/var/secret",
        "governance-decision:user:password",
        "governance-decision:value?token=secret",
        "governance-decision:value#fragment",
        "governance-decision:white space",
        "governance-decision:\tcontrol",
        'governance-decision:{"payload":"raw"}',
        "governance-decision:álpha",
        "governance-decision:nul\x00value",
        "governance-decision:" + "a" * 129,
    ),
)
def test_neutral_references_reject_malformed_sensitive_or_wrong_family(
    value: str,
) -> None:
    with pytest.raises(InvalidSkillExternalReference):
        GovernanceDecisionRef(value)


def test_external_reference_exact_local_length_boundary_is_preserved() -> None:
    local = "a" * 128
    assert str(GovernanceDecisionRef(f"governance-decision:{local}")).endswith(local)


def test_binding_reference_is_family_specific_semantic_digest() -> None:
    valid = "a" * 64
    assert ExternalBindingRef(f"governance-binding:{valid}").family == ("governance-binding")
    assert (
        ExternalBindingOccurrenceRef(f"governance-binding-occurrence:{valid}").family
        == "governance-binding-occurrence"
    )
    with pytest.raises(InvalidSkillExternalReference):
        ExternalBindingRef(f"evaluation-binding:{valid}")


def test_governance_binding_requires_publication_and_appends_local_fact() -> None:
    publication, bindings, service, _ = _services()
    result = service.bind(_governance_request(publication.identity))
    assert result.outcome is SkillExternalBindingOutcome.CREATED
    assert result.record.identity == publication.identity
    assert result.projection is not None
    assert result.projection.decision_refs == (result.record.decision_ref,)
    assert bindings.append_governance_calls == 1


def test_governance_equivalent_replay_returns_existing_without_second_append() -> None:
    publication, bindings, service, _ = _services()
    request = _governance_request(publication.identity)
    first = service.bind(request)
    replay = service.bind(request)
    assert replay.record is first.record
    assert replay.outcome is SkillExternalBindingOutcome.IDEMPOTENT_REPLAY
    assert bindings.append_governance_calls == 1


def test_governance_lost_append_response_is_reconciled_by_exact_retry() -> None:
    publication, bindings, service, _ = _services()
    request = _governance_request(publication.identity)
    bindings.fail_after_governance = True
    with pytest.raises(SkillExternalBindingStoreUnavailable):
        service.bind(request)
    replay = service.bind(request)
    assert replay.outcome is SkillExternalBindingOutcome.IDEMPOTENT_REPLAY
    assert replay.projection is not None
    assert len(replay.projection.history.records) == 1
    assert bindings.append_governance_calls == 1


def test_governance_binding_identity_is_separate_from_occurrence_identity() -> None:
    publication, bindings, service, _ = _services()
    first = service.bind(_governance_request(publication.identity))
    second = service.bind(
        _governance_request(
            publication.identity,
            binder="external-binder:binder-b",
            bound_at=BOUND_AT + timedelta(seconds=1),
        )
    )
    assert first.record.binding_ref == second.record.binding_ref
    assert first.record.occurrence_ref != second.record.occurrence_ref
    assert bindings.append_governance_calls == 2
    assert second.projection is not None
    assert len(second.projection.history.records) == 2


def test_governance_rejects_unpublished_or_prepublication_binding() -> None:
    publication = _published()
    empty = FakeCatalog(None)
    bindings = FakeExternalBindings()
    missing = SkillGovernanceBindingService(empty, bindings, LIMIT)
    with pytest.raises(SkillExternalBindingSubjectNotPublished):
        missing.bind(_governance_request(publication.identity))
    service = SkillGovernanceBindingService(FakeCatalog(publication), bindings, LIMIT)
    with pytest.raises(SkillExternalBindingCorrespondenceMismatch):
        service.bind(
            _governance_request(
                publication.identity,
                bound_at=PUBLISHED_AT - timedelta(seconds=1),
            )
        )
    assert bindings.append_governance_calls == 0


def test_governance_projection_preserves_conflicts_without_resolving() -> None:
    publication, _, service, _ = _services()
    service.bind(_governance_request(publication.identity))
    service.bind(
        _governance_request(
            publication.identity,
            decision="governance-decision:decision-b",
            policy="governance-policy:policy-b",
            authority="external-authority:governance-b",
            bound_at=BOUND_AT + timedelta(seconds=1),
        )
    )
    projection = service.projection(publication.identity)
    kinds = {diagnostic.kind for diagnostic in projection.diagnostics}
    assert kinds == {
        SkillExternalBindingDiagnosticKind.MULTIPLE_AUTHORITY_REFERENCES,
        SkillExternalBindingDiagnosticKind.MULTIPLE_DECISION_REFERENCES,
        SkillExternalBindingDiagnosticKind.MULTIPLE_POLICY_REFERENCES,
    }
    assert not hasattr(projection, "approved")
    assert not hasattr(projection, "trusted")


def test_governance_history_is_complete_and_canonically_ordered() -> None:
    publication, _, service, _ = _services()
    later = service.bind(
        _governance_request(
            publication.identity,
            decision="governance-decision:decision-b",
            bound_at=BOUND_AT + timedelta(seconds=1),
        )
    )
    earlier = service.bind(_governance_request(publication.identity))
    history = service.history(publication.identity)
    assert history.complete
    assert history.records == (earlier.record, later.record)


def test_incomplete_history_is_visible_but_blocks_append_reconciliation() -> None:
    publication, bindings, service, _ = _services()
    bindings.complete = False
    projection = service.projection(publication.identity)
    assert not projection.complete
    assert {diagnostic.kind for diagnostic in projection.diagnostics} == {
        SkillExternalBindingDiagnosticKind.INCOMPLETE_HISTORY,
    }
    with pytest.raises(IncompleteSkillExternalBindingHistory):
        service.bind(_governance_request(publication.identity))


def test_complete_empty_histories_are_normal_without_missing_diagnostic() -> None:
    publication, _, governance, intelligence = _services()
    governance_projection = governance.projection(publication.identity)
    intelligence_projection = intelligence.projection(publication.identity)
    assert governance_projection.complete
    assert intelligence_projection.complete
    assert governance_projection.diagnostics == ()
    assert intelligence_projection.diagnostics == ()


@pytest.mark.parametrize(
    ("change", "same_binding"),
    (
        ({"policy": "governance-policy:policy-b"}, False),
        ({"authority": "external-authority:governance-b"}, False),
        ({"binder": "external-binder:binder-b"}, True),
        ({"bound_at": BOUND_AT + timedelta(seconds=1)}, True),
    ),
)
def test_governance_additional_facts_preserve_binding_and_occurrence_semantics(
    change: dict[str, object],
    same_binding: bool,
) -> None:
    publication, _, service, _ = _services()
    first = service.bind(_governance_request(publication.identity))
    second = service.bind(_governance_request(publication.identity, **change))
    assert (first.record.binding_ref == second.record.binding_ref) is same_binding
    assert first.record.occurrence_ref != second.record.occurrence_ref
    assert second.outcome is SkillExternalBindingOutcome.CREATED


def test_intelligence_binding_requires_exact_subject_and_preserves_fact() -> None:
    publication, bindings, _, service = _services()
    result = service.bind(_intelligence_request(publication.identity))
    assert result.outcome is SkillExternalBindingOutcome.CREATED
    assert result.projection is not None
    assert result.projection.fact_refs == (result.record.fact_ref,)
    assert result.projection.profile_refs == (result.record.profile_ref,)
    assert bindings.append_intelligence_calls == 1
    assert not hasattr(result.projection, "safe")


def test_intelligence_retry_replays_but_new_binder_is_additional_occurrence() -> None:
    publication, bindings, _, service = _services()
    request = _intelligence_request(publication.identity)
    service.bind(request)
    replay = service.bind(request)
    assert replay.outcome is SkillExternalBindingOutcome.IDEMPOTENT_REPLAY
    assert bindings.append_intelligence_calls == 1
    additional = service.bind(
        _intelligence_request(
            publication.identity,
            binder="external-binder:binder-b",
        )
    )
    assert additional.record.binding_ref == replay.record.binding_ref
    assert additional.record.occurrence_ref != replay.record.occurrence_ref
    assert bindings.append_intelligence_calls == 2


def test_intelligence_lost_append_response_is_reconciled_by_exact_retry() -> None:
    publication, bindings, _, service = _services()
    request = _intelligence_request(publication.identity)
    bindings.fail_after_intelligence = True
    with pytest.raises(SkillExternalBindingStoreUnavailable):
        service.bind(request)
    replay = service.bind(request)
    assert replay.outcome is SkillExternalBindingOutcome.IDEMPOTENT_REPLAY
    assert replay.projection is not None
    assert len(replay.projection.history.records) == 1
    assert bindings.append_intelligence_calls == 1


def test_intelligence_same_occurrence_with_divergent_observed_at_conflicts() -> None:
    publication, _, _, service = _services()
    service.bind(_intelligence_request(publication.identity))
    with pytest.raises(SkillExternalBindingDivergentDuplicate):
        service.bind(
            _intelligence_request(
                publication.identity,
                observed_at=OBSERVED_AT + timedelta(seconds=1),
            )
        )


def test_intelligence_same_external_fact_keeps_observed_at_across_occurrences() -> None:
    publication, _, _, service = _services()
    service.bind(_intelligence_request(publication.identity))
    with pytest.raises(SkillExternalBindingDivergentDuplicate):
        service.bind(
            _intelligence_request(
                publication.identity,
                binder="external-binder:binder-b",
                observed_at=OBSERVED_AT + timedelta(seconds=1),
                bound_at=BOUND_AT + timedelta(seconds=1),
            )
        )


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("fact", "intelligence-fact:fact-b"),
        ("profile", "intelligence-profile:profile-b"),
        ("authority", "external-authority:intelligence-b"),
    ),
)
def test_intelligence_scope_or_fact_change_is_legitimate_additional_binding(
    field: str,
    value: str,
) -> None:
    publication, _, _, service = _services()
    first = service.bind(_intelligence_request(publication.identity))
    second = service.bind(
        _intelligence_request(
            publication.identity,
            **{field: value},
            bound_at=BOUND_AT + timedelta(seconds=1),
        )
    )
    assert first.record.binding_ref != second.record.binding_ref
    assert first.record.occurrence_ref != second.record.occurrence_ref


def test_intelligence_analysis_change_is_additional_binding_not_semantic_conflict() -> None:
    publication, _, _, service = _services()
    first_request = _intelligence_request(publication.identity)
    first = service.bind(first_request)
    second = service.bind(
        replace(
            first_request,
            analysis_ref=IntelligenceAnalysisRef("intelligence-analysis:analysis-b"),
            bound_at=BOUND_AT + timedelta(seconds=1),
        )
    )
    assert first.record.binding_ref != second.record.binding_ref
    assert SkillExternalBindingDiagnosticKind.MULTIPLE_ANALYSIS_REFERENCES in {
        diagnostic.kind for diagnostic in service.projection(publication.identity).diagnostics
    }


def test_intelligence_observation_may_predate_publication_but_binding_may_not() -> None:
    publication, bindings, _, service = _services()
    result = service.bind(
        _intelligence_request(
            publication.identity,
            observed_at=PUBLISHED_AT - timedelta(seconds=1),
        )
    )
    assert result.record.observed_at < PUBLISHED_AT
    with pytest.raises(SkillExternalBindingCorrespondenceMismatch):
        service.bind(
            _intelligence_request(
                publication.identity,
                observed_at=PUBLISHED_AT - timedelta(seconds=2),
                bound_at=PUBLISHED_AT - timedelta(seconds=1),
            )
        )
    with pytest.raises(InvalidSkillExternalBindingRequest):
        _intelligence_request(
            publication.identity,
            observed_at=BOUND_AT + timedelta(seconds=1),
        )
    assert bindings.append_intelligence_calls == 1


def test_intelligence_projection_reports_only_structural_multiplicity() -> None:
    publication, _, _, service = _services()
    service.bind(_intelligence_request(publication.identity))
    service.bind(
        _intelligence_request(
            publication.identity,
            fact="intelligence-fact:fact-b",
            bound_at=BOUND_AT + timedelta(seconds=1),
        )
    )
    service.bind(
        _intelligence_request(
            publication.identity,
            profile="intelligence-profile:profile-b",
            bound_at=BOUND_AT + timedelta(seconds=2),
        )
    )
    kinds = {diagnostic.kind for diagnostic in service.projection(publication.identity).diagnostics}
    assert SkillExternalBindingDiagnosticKind.MULTIPLE_FACT_REFERENCES in kinds
    assert SkillExternalBindingDiagnosticKind.MULTIPLE_PROFILE_REFERENCES in kinds


def test_governance_intelligence_and_evaluation_records_are_distinct() -> None:
    publication, _, governance, intelligence = _services()
    governance_record = governance.bind(_governance_request(publication.identity)).record
    intelligence_record = intelligence.bind(_intelligence_request(publication.identity)).record
    legacy_evaluation = SkillEvaluationBindingRecord(
        SkillStoreRecordId("evaluation-binding:" + "a" * 64),
        publication.identity,
        SkillSemanticReference("evaluation:legacy"),
        SkillStoreRecordFingerprint("b" * 64),
        BOUND_AT,
        SkillSemanticReference("actor:legacy"),
    )
    assert type(governance_record) is not type(intelligence_record)
    assert type(intelligence_record) is not type(legacy_evaluation)


def test_store_unavailability_and_corrupt_history_are_safe_errors() -> None:
    publication, bindings, service, _ = _services()
    bindings.unavailable = True
    with pytest.raises(SkillExternalBindingStoreUnavailable):
        service.projection(publication.identity)
    bindings.unavailable = False
    other = _published()
    wrong_identity = replace(
        other.identity,
        version=SkillVersion.parse("2.0.0"),
    )
    record = service.bind(_governance_request(publication.identity)).record
    bindings.corrupt_governance_history = (replace(record, identity=wrong_identity),)
    with pytest.raises(InvalidSkillExternalBindingHistory):
        service.history(publication.identity)


def test_history_rejects_forged_binding_or_occurrence_identity() -> None:
    publication, bindings, service, _ = _services()
    record = service.bind(_governance_request(publication.identity)).record
    bindings.corrupt_governance_history = (
        replace(
            record,
            binding_ref=ExternalBindingRef("governance-binding:" + "f" * 64),
        ),
    )
    with pytest.raises(InvalidSkillExternalBindingHistory):
        service.history(publication.identity)


def test_requests_records_results_and_projections_are_frozen() -> None:
    publication, _, service, _ = _services()
    request = _governance_request(publication.identity)
    result = service.bind(request)
    with pytest.raises(FrozenInstanceError):
        request.bound_at = BOUND_AT  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        result.record.bound_at = BOUND_AT  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        assert result.projection is not None
        result.projection.complete = False  # type: ignore[misc]


def test_fixed_errors_do_not_leak_external_reference() -> None:
    secret = "governance-decision:secret-reference"
    assert secret not in str(SkillExternalBindingDivergentDuplicate(secret))
    assert secret not in str(InvalidSkillExternalReference(secret))


def test_services_have_no_external_runtime_or_progression_dependencies() -> None:
    paths = tuple(Path("backend/synapse/skills").glob("phase10_*.py"))
    source = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    forbidden = (
        "synapse.project_governance",
        "synapse.intelligence_boundary",
        "synapse.private_evals",
        "synapse.bootstrap",
        "synapse.api",
        "synapse.commands",
        "synapse.storage",
        "subprocess",
        "importlib",
        "sqlite3",
        "requests",
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


def test_public_surface_exports_only_stable_slice10_contracts() -> None:
    expected = {
        "ExternalAuthorityRef",
        "ExternalBinderRef",
        "ExternalBindingRef",
        "ExternalBindingOccurrenceRef",
        "GovernanceDecisionRef",
        "GovernanceDecisionKindRef",
        "GovernancePolicyRef",
        "IntelligenceFactRef",
        "IntelligenceAnalysisRef",
        "IntelligenceFactKindRef",
        "IntelligenceProfileRef",
        "BindSkillGovernanceDecisionRequest",
        "BindSkillIntelligenceFactRequest",
        "SkillGovernanceBindingRecord",
        "SkillIntelligenceBindingRecord",
        "SkillGovernanceBindingService",
        "SkillIntelligenceBindingService",
        "SkillExternalBindingStore",
    }
    assert expected.issubset(public_skills.__all__)
    assert {
        "_canonical_governance_history",
        "_canonical_intelligence_history",
        "_governance_projection",
        "_intelligence_projection",
        "_governance_binding_ref",
        "_governance_occurrence_ref",
        "_intelligence_binding_ref",
        "_intelligence_occurrence_ref",
        "FakeExternalBindings",
    }.isdisjoint(public_skills.__all__)


def test_store_contract_has_no_generic_or_evaluation_method() -> None:
    methods = {name for name in SkillExternalBindingStore.__dict__ if not name.startswith("_")}
    assert methods == {
        "append_governance",
        "append_intelligence",
        "list_governance_for_version",
        "list_intelligence_for_version",
    }
