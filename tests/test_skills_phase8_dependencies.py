from __future__ import annotations

import hashlib
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from synapse.skills.phase2_models import (
    FilesystemRequirement,
    PublishedSkillManifest,
    PublishedSkillVersionId,
    SkillCompatibilityDeclaration,
    SkillConflictDeclaration,
    SkillContentFingerprint,
    SkillContentKind,
    SkillContentRef,
    SkillDependencyDeclaration,
    SkillDependencyReason,
    SkillId,
    SkillLogicalPath,
    SkillManifestFingerprint,
    SkillManifestFormatVersion,
    SkillProvenance,
    SkillPublicationScope,
    SkillRequirementId,
    SkillSecurityDeclaration,
    SkillSemanticReference,
    SkillVersion,
    SkillVersionConstraint,
)
from synapse.skills.phase3_errors import SkillStoreNotFound, SkillStoreUnavailable
from synapse.skills.phase3_records import PublishedSkillVersionRecord
from synapse.skills.phase3_values import SkillStoreQueryLimit
from synapse.skills.phase6_errors import (
    CorruptedSkillLifecycleHistory,
    IncompleteSkillLifecycleHistory,
    SkillLifecycleStoreUnavailable,
)
from synapse.skills.phase6_models import (
    SkillActivationState,
    SkillLifecycleProjection,
    SkillSelectionState,
)
from synapse.skills.phase8_analysis import SkillDependencyAnalysisService
from synapse.skills.phase8_contracts import SkillDependencyCatalogPage
from synapse.skills.phase8_errors import (
    InconsistentSkillDependencyCatalog,
    InconsistentSkillDependencyGraph,
    InvalidSkillCompatibilityObservation,
    InvalidSkillDependencyDeclaration,
    InvalidSkillDependencyGraphInput,
    SkillDependencyCatalogUnavailable,
    SkillDependencySubjectNotPublished,
)
from synapse.skills.phase8_graph import SkillDependencyGraphAnalysisService
from synapse.skills.phase8_models import (
    AnalyzeSkillDependenciesRequest,
    AnalyzeSkillDependencyGraphRequest,
    SkillCompatibilityObservation,
    SkillCompatibilityObservationStatus,
    SkillCompatibilityRequirementId,
    SkillCompatibilityStatus,
    SkillDependencyAnalysisStatus,
    SkillDependencyConstraintStatus,
    SkillDependencyCycleStatus,
    SkillDependencyDiagnosticCode,
    SkillDependencyGraphEdge,
    SkillDependencyGraphInput,
    SkillDependencyId,
    SkillDependencyIncompleteReason,
    SkillDependencyLifecycleStatus,
    SkillDependencyRequirementStatus,
)

NOW = datetime(2026, 7, 27, 16, 0, tzinfo=UTC)
ACTOR = SkillSemanticReference("actor:publisher")
PROFILE = SkillSemanticReference("analysis-profile:test")


def _dependency(
    skill_id: str,
    specification: str = "^1.0.0",
    *,
    optional: bool = False,
    exact: bool = False,
) -> SkillDependencyDeclaration:
    return SkillDependencyDeclaration(
        skill_id=SkillId(skill_id),
        reason=(
            SkillDependencyReason.OPTIONAL_ENHANCEMENT
            if optional
            else SkillDependencyReason.REQUIRED_WORKFLOW
        ),
        version=SkillVersion.parse(specification) if exact else None,
        constraint=None if exact else SkillVersionConstraint(specification),
        optional=optional,
    )


def _record(
    skill_id: str,
    version: str,
    *,
    dependencies: tuple[SkillDependencyDeclaration, ...] = (),
    conflicts: tuple[SkillConflictDeclaration, ...] = (),
    compatibility: SkillCompatibilityDeclaration | None = None,
    security: SkillSecurityDeclaration | None = None,
) -> PublishedSkillVersionRecord:
    digest = hashlib.sha256(f"{skill_id}@{version}".encode()).hexdigest()
    content = SkillContentRef(
        SkillLogicalPath("SKILL.md"),
        SkillContentFingerprint(digest),
        SkillContentKind.INSTRUCTIONS,
        "text/markdown",
        1,
    )
    manifest = PublishedSkillManifest(
        format_version=SkillManifestFormatVersion(1),
        skill_id=SkillId(skill_id),
        version=SkillVersion.parse(version),
        display_name=skill_id,
        summary=f"{skill_id} summary.",
        description=f"{skill_id} dependency analysis fixture.",
        provenance=SkillProvenance(SkillSemanticReference("publisher:synapse")),
        scopes=(SkillPublicationScope.PROJECT,),
        content=(content,),
        dependencies=dependencies,
        conflicts=conflicts,
        compatibility=compatibility or SkillCompatibilityDeclaration(),
        security=security or SkillSecurityDeclaration(),
    )
    identity = PublishedSkillVersionId.from_manifest(
        manifest, SkillContentFingerprint(digest)
    )
    return PublishedSkillVersionRecord(
        identity,
        manifest,
        NOW,
        ACTOR,
        SkillSemanticReference(f"publication:{skill_id}-{version.replace('+', '-')}"),
    )


def _eligible(identity: PublishedSkillVersionId) -> SkillLifecycleProjection:
    return SkillLifecycleProjection(
        identity=identity,
        activation_state=SkillActivationState.NEVER_ACTIVATED,
        selection_state=SkillSelectionState.ELIGIBLE,
        deprecated=False,
        revoked=False,
        superseded=False,
        resolvable=True,
        activatable=True,
        active=False,
        active_selection_eligible=False,
        active_installation_id=None,
        superseded_by=None,
        rollback_target=None,
        rollback_decision_ref=None,
        last_record_id=None,
    )


def _lifecycle_state(
    identity: PublishedSkillVersionId, state: str
) -> SkillLifecycleProjection:
    base = _eligible(identity)
    if state == "deprecated":
        return replace(base, deprecated=True, activatable=False)
    if state == "superseded":
        return replace(
            base,
            selection_state=SkillSelectionState.SUPERSEDED,
            superseded=True,
            resolvable=False,
            activatable=False,
        )
    if state == "revoked":
        return replace(
            base,
            selection_state=SkillSelectionState.REVOKED,
            revoked=True,
            resolvable=False,
            activatable=False,
        )
    return base


class FakeCatalog:
    def __init__(self, *records: PublishedSkillVersionRecord) -> None:
        self.records = {record.identity: record for record in records}
        self.unavailable_skills: set[SkillId] = set()
        self.subject_unavailable = False
        self.malformed = False
        self.incomplete_skills: set[SkillId] = set()

    def save_version(self, record):
        raise AssertionError("analysis is read-only")

    def get_version(self, identity):
        if self.subject_unavailable:
            raise SkillStoreUnavailable()
        try:
            return self.records[identity]
        except KeyError as exc:
            raise SkillStoreNotFound() from exc

    def list_dependency_candidates(self, skill_id, limit):
        if skill_id in self.unavailable_skills:
            raise SkillStoreUnavailable()
        if self.malformed:
            return ("invalid",)
        records = sorted(
            (
                record
                for record in self.records.values()
                if record.identity.skill_id == skill_id
            ),
            key=lambda record: (
                record.identity.version.precedence_key(),
                str(record.identity.version),
                record.identity.to_canonical_text(),
            ),
        )
        return SkillDependencyCatalogPage(
            tuple(records[: limit.limit]),
            skill_id not in self.incomplete_skills,
        )


class FakeLifecycle:
    def __init__(self, *records: PublishedSkillVersionRecord) -> None:
        self.projections = {
            record.identity: _eligible(record.identity) for record in records
        }
        self.failures: dict[PublishedSkillVersionId, Exception] = {}
        self.calls: list[PublishedSkillVersionId] = []

    def projection(self, identity):
        self.calls.append(identity)
        failure = self.failures.get(identity)
        if failure is not None:
            raise failure
        return self.projections[identity]


def _harness(*records: PublishedSkillVersionRecord):
    catalog = FakeCatalog(*records)
    lifecycle = FakeLifecycle(*records)
    return SkillDependencyAnalysisService(catalog, lifecycle), catalog, lifecycle


def _request(
    subject: PublishedSkillVersionRecord,
    *,
    observations: tuple[SkillCompatibilityObservation, ...] = (),
    limit: int = 100,
) -> AnalyzeSkillDependenciesRequest:
    return AnalyzeSkillDependenciesRequest(
        subject=subject.identity,
        analysis_profile_ref=PROFILE,
        observations=observations,
        candidate_limit=SkillStoreQueryLimit(limit),
    )


def _observations_for(
    analysis,
    *,
    status: SkillCompatibilityObservationStatus,
    only_first: bool = False,
) -> tuple[SkillCompatibilityObservation, ...]:
    observations: list[SkillCompatibilityObservation] = []
    index = 0
    for candidate in analysis.candidates:
        if (
            candidate.constraint_status
            is SkillDependencyConstraintStatus.MISMATCH
        ):
            continue
        requirement_ids = candidate.compatibility_requirement_ids
        if only_first:
            requirement_ids = requirement_ids[:1]
        for requirement_id in requirement_ids:
            observations.append(
                SkillCompatibilityObservation(
                    subject=analysis.subject,
                    dependency=candidate.candidate,
                    analysis_profile_ref=PROFILE,
                    requirement_id=requirement_id,
                    status=status,
                    observer_ref=SkillSemanticReference("observer:compatibility"),
                    observed_at=NOW + timedelta(minutes=index + 1),
                    observation_ref=SkillSemanticReference(
                        f"compatibility-observation:o{index}"
                    ),
                )
            )
            index += 1
    return tuple(observations)


def _edge(
    owner: PublishedSkillVersionRecord,
    dependency: PublishedSkillVersionRecord,
    *,
    optional: bool = False,
) -> SkillDependencyGraphEdge:
    declaration = _dependency(
        str(dependency.identity.skill_id),
        str(dependency.identity.version),
        optional=optional,
        exact=True,
    )
    return SkillDependencyGraphEdge(
        owner=owner.identity,
        dependency=dependency.identity,
        dependency_id=SkillDependencyId.from_declaration(
            owner.identity, declaration
        ),
        declaration=declaration,
    )


def test_required_dependency_preserves_all_matching_candidates() -> None:
    subject = _record(
        "subject-skill", "1.0.0", dependencies=(_dependency("base-skill"),)
    )
    one = _record("base-skill", "1.0.0")
    two = _record("base-skill", "1.8.0")
    mismatch = _record("base-skill", "2.0.0")
    service, *_ = _harness(subject, mismatch, two, one)
    result = service.analyze(_request(subject))
    assert result.status is SkillDependencyAnalysisStatus.SATISFIABLE
    assert result.requirements[0].matching_candidates == (
        one.identity,
        two.identity,
    )
    assert result.requirements[0].eligible_candidates == (
        one.identity,
        two.identity,
    )
    assert len(result.candidates) == 3
    assert not hasattr(result, "resolved_version")
    assert not hasattr(result, "recommended_version")


def test_optional_dependency_absence_is_explicit_and_nonblocking() -> None:
    subject = _record(
        "subject-skill",
        "1.0.0",
        dependencies=(_dependency("optional-skill", optional=True),),
    )
    service, *_ = _harness(subject)
    result = service.analyze(_request(subject))
    assert result.status is SkillDependencyAnalysisStatus.SATISFIABLE
    assert result.requirements[0].status is SkillDependencyRequirementStatus.UNSATISFIED
    assert {
        diagnostic.code for diagnostic in result.diagnostics
    } == {SkillDependencyDiagnosticCode.OPTIONAL_DEPENDENCY_UNAVAILABLE}


def test_required_missing_and_unmatched_are_distinct() -> None:
    subject = _record(
        "subject-skill", "1.0.0", dependencies=(_dependency("base-skill"),)
    )
    service, *_ = _harness(subject)
    missing = service.analyze(_request(subject))
    assert missing.status is SkillDependencyAnalysisStatus.UNSATISFIABLE
    assert missing.diagnostics[0].code is SkillDependencyDiagnosticCode.NO_PUBLISHED_VERSION

    mismatch = _record("base-skill", "2.0.0")
    service, *_ = _harness(subject, mismatch)
    unmatched = service.analyze(_request(subject))
    assert unmatched.diagnostics[0].code is SkillDependencyDiagnosticCode.NO_CONSTRAINT_MATCH


def test_distinct_requirements_for_same_skill_coexist_without_merging() -> None:
    declarations = (
        _dependency("base-skill", "^1.0.0"),
        _dependency("base-skill", "^2.0.0"),
        _dependency("base-skill", "^3.0.0", optional=True),
    )
    subject = _record("subject-skill", "1.0.0", dependencies=declarations)
    one = _record("base-skill", "1.1.0")
    two = _record("base-skill", "2.1.0")
    service, *_ = _harness(subject, one, two)
    result = service.analyze(_request(subject))
    assert len(result.requirements) == 3
    assert len({fact.dependency_id for fact in result.requirements}) == 3
    assert result.has_unsatisfied_required is False
    assert result.status is SkillDependencyAnalysisStatus.SATISFIABLE


def test_self_malformed_and_impossible_declarations_are_rejected() -> None:
    with pytest.raises(ValueError):
        _record(
            "subject-skill",
            "1.0.0",
            dependencies=(_dependency("subject-skill"),),
        )

    subject = _record("subject-skill", "1.0.0")
    object.__setattr__(subject.manifest, "dependencies", ("invalid",))
    service, *_ = _harness(subject)
    with pytest.raises(InvalidSkillDependencyDeclaration):
        service.analyze(_request(subject))

    impossible = _record(
        "impossible-subject",
        "1.0.0",
        dependencies=(
            _dependency("base-skill", ">1.0.0,<1.0.1"),
        ),
    )
    service, *_ = _harness(impossible)
    with pytest.raises(InvalidSkillDependencyDeclaration):
        service.analyze(_request(impossible))


def test_dependency_identity_is_order_time_actor_and_request_independent() -> None:
    owner = _record("subject-skill", "1.0.0")
    declaration = _dependency("base-skill", "^1.2.3")
    first = SkillDependencyId.from_declaration(owner.identity, declaration)
    second = SkillDependencyId.from_declaration(owner.identity, replace(declaration))
    assert first == second
    assert str(first).startswith("dependency:")
    changed = SkillDependencyId.from_declaration(
        owner.identity, _dependency("base-skill", "^2.0.0")
    )
    assert changed != first
    other_version = _record("subject-skill", "1.0.1")
    assert (
        SkillDependencyId.from_declaration(other_version.identity, declaration)
        != first
    )
    rebuilt_identity = replace(
        owner.identity,
        manifest_fingerprint=SkillManifestFingerprint("f" * 64),
    )
    assert (
        SkillDependencyId.from_declaration(rebuilt_identity, declaration)
        != first
    )


@pytest.mark.parametrize(
    ("constraint", "versions", "matching"),
    (
        ("^0.2.3", ("0.2.3", "0.2.9", "0.3.0"), ("0.2.3", "0.2.9")),
        ("^0.0.3", ("0.0.3", "0.0.4"), ("0.0.3",)),
        (">=1.0.0,<2.0.0", ("1.0.0", "1.9.9", "2.0.0"), ("1.0.0", "1.9.9")),
        (">1.0.0,<=2.0.0", ("1.0.0", "1.0.1", "2.0.0"), ("1.0.1", "2.0.0")),
    ),
)
def test_semver_constraint_matching(
    constraint: str, versions: tuple[str, ...], matching: tuple[str, ...]
) -> None:
    subject = _record(
        "subject-skill",
        "1.0.0",
        dependencies=(_dependency("base-skill", constraint),),
    )
    candidates = tuple(_record("base-skill", version) for version in versions)
    service, *_ = _harness(subject, *candidates)
    result = service.analyze(_request(subject))
    assert tuple(
        str(identity.version)
        for identity in result.requirements[0].matching_candidates
    ) == matching


def test_prerelease_is_excluded_from_ranges_and_exact_version_is_structural() -> None:
    ranged = _record(
        "range-subject",
        "1.0.0",
        dependencies=(_dependency("base-skill", "^1.0.0"),),
    )
    prerelease = _record("base-skill", "1.1.0-rc.1")
    service, *_ = _harness(ranged, prerelease)
    result = service.analyze(_request(ranged))
    assert result.requirements[0].matching_candidates == ()

    exact = _record(
        "exact-subject",
        "1.0.0",
        dependencies=(_dependency("base-skill", "1.1.0-rc.1", exact=True),),
    )
    service, *_ = _harness(exact, prerelease)
    result = service.analyze(_request(exact))
    assert result.requirements[0].matching_candidates == (prerelease.identity,)


def test_build_metadata_is_preserved_while_range_precedence_is_equal() -> None:
    subject = _record(
        "subject-skill",
        "1.0.0",
        dependencies=(_dependency("base-skill", "^1.0.0"),),
    )
    one = _record("base-skill", "1.2.0+build.1")
    two = _record("base-skill", "1.2.0+build.2")
    service, *_ = _harness(subject, two, one)
    result = service.analyze(_request(subject))
    assert result.requirements[0].matching_candidates == (
        one.identity,
        two.identity,
    )


def test_exact_version_preserves_build_metadata_structurally() -> None:
    subject = _record(
        "subject-skill",
        "1.0.0",
        dependencies=(
            _dependency("base-skill", "1.2.0+build.1", exact=True),
        ),
    )
    one = _record("base-skill", "1.2.0+build.1")
    two = _record("base-skill", "1.2.0+build.2")
    service, *_ = _harness(subject, two, one)
    result = service.analyze(_request(subject))
    assert result.requirements[0].matching_candidates == (one.identity,)


def test_catalog_completeness_is_provider_attested_not_length_inferred() -> None:
    subject = _record(
        "subject-skill", "1.0.0", dependencies=(_dependency("base-skill"),)
    )
    candidate = _record("base-skill", "1.0.0")
    service, catalog, _ = _harness(subject, candidate)
    complete = service.analyze(_request(subject, limit=1))
    assert complete.complete
    catalog.incomplete_skills.add(SkillId("base-skill"))
    result = service.analyze(_request(subject, limit=1))
    assert not result.complete
    assert SkillDependencyIncompleteReason.CATALOG_TRUNCATED in result.incomplete_reasons


@pytest.mark.parametrize(
    ("available", "provider_complete", "expected_complete"),
    ((199, True, True), (200, True, True), (201, False, False)),
)
def test_catalog_boundary_counts_do_not_define_completeness(
    available: int,
    provider_complete: bool,
    expected_complete: bool,
) -> None:
    subject = _record(
        "subject-skill", "1.0.0", dependencies=(_dependency("base-skill"),)
    )
    candidates = tuple(
        _record("base-skill", f"1.0.{index}") for index in range(available)
    )
    service, catalog, _ = _harness(subject, *candidates)
    if not provider_complete:
        catalog.incomplete_skills.add(SkillId("base-skill"))
    result = service.analyze(_request(subject, limit=200))
    assert result.complete is expected_complete
    assert len(result.candidates) == min(available, 200)


def test_catalog_unavailability_and_malformed_results_are_distinct() -> None:
    subject = _record(
        "subject-skill", "1.0.0", dependencies=(_dependency("base-skill"),)
    )
    service, catalog, _ = _harness(subject)
    catalog.unavailable_skills.add(SkillId("base-skill"))
    result = service.analyze(_request(subject))
    assert result.status is SkillDependencyAnalysisStatus.INCOMPLETE
    assert result.diagnostics[0].code is SkillDependencyDiagnosticCode.CATALOG_UNAVAILABLE

    catalog.unavailable_skills.clear()
    catalog.malformed = True
    with pytest.raises(InconsistentSkillDependencyCatalog):
        service.analyze(_request(subject))


def test_subject_lookup_errors_are_typed() -> None:
    subject = _record("subject-skill", "1.0.0")
    service, catalog, _ = _harness()
    with pytest.raises(SkillDependencySubjectNotPublished):
        service.analyze(_request(subject))
    catalog.subject_unavailable = True
    with pytest.raises(SkillDependencyCatalogUnavailable):
        service.analyze(_request(subject))


@pytest.mark.parametrize(
    ("state", "expected"),
    (
        ("eligible", SkillDependencyLifecycleStatus.ELIGIBLE),
        ("deprecated", SkillDependencyLifecycleStatus.DEPRECATED),
        ("superseded", SkillDependencyLifecycleStatus.SUPERSEDED),
        ("revoked", SkillDependencyLifecycleStatus.REVOKED),
    ),
)
def test_lifecycle_projection_is_consumed_without_transition_policy(
    state: str, expected: SkillDependencyLifecycleStatus
) -> None:
    subject = _record(
        "subject-skill", "1.0.0", dependencies=(_dependency("base-skill"),)
    )
    candidate = _record("base-skill", "1.0.0")
    service, _, lifecycle = _harness(subject, candidate)
    lifecycle.projections[candidate.identity] = _lifecycle_state(
        candidate.identity, state
    )
    result = service.analyze(_request(subject))
    assert result.candidates[0].constraint_status is SkillDependencyConstraintStatus.MATCH
    assert result.candidates[0].lifecycle_status is expected
    assert candidate.identity in lifecycle.calls


@pytest.mark.parametrize(
    ("failure", "expected"),
    (
        (
            IncompleteSkillLifecycleHistory(),
            SkillDependencyLifecycleStatus.INCOMPLETE,
        ),
        (
            SkillLifecycleStoreUnavailable(),
            SkillDependencyLifecycleStatus.UNAVAILABLE,
        ),
        (
            CorruptedSkillLifecycleHistory(),
            SkillDependencyLifecycleStatus.INCONSISTENT,
        ),
    ),
)
def test_lifecycle_missing_information_remains_incomplete(
    failure: Exception, expected: SkillDependencyLifecycleStatus
) -> None:
    subject = _record(
        "subject-skill", "1.0.0", dependencies=(_dependency("base-skill"),)
    )
    candidate = _record("base-skill", "1.0.0")
    service, _, lifecycle = _harness(subject, candidate)
    lifecycle.failures[candidate.identity] = failure
    result = service.analyze(_request(subject))
    assert result.candidates[0].lifecycle_status is expected
    assert result.status is SkillDependencyAnalysisStatus.INCOMPLETE


def test_declared_conflict_is_structural_incompatibility() -> None:
    conflict = SkillConflictDeclaration(
        SkillId("base-skill"),
        SkillVersionConstraint("^1.0.0"),
        SkillSemanticReference("reason:declared-conflict"),
    )
    subject = _record(
        "subject-skill",
        "1.0.0",
        dependencies=(_dependency("base-skill"),),
        conflicts=(conflict,),
    )
    candidate = _record("base-skill", "1.0.0")
    service, *_ = _harness(subject, candidate)
    result = service.analyze(_request(subject))
    assert (
        result.candidates[0].compatibility_status
        is SkillCompatibilityStatus.DECLARED_INCOMPATIBLE
    )
    assert result.status is SkillDependencyAnalysisStatus.UNSATISFIABLE


def test_observed_compatibility_is_profile_scoped_and_complete() -> None:
    subject = _record(
        "subject-skill",
        "1.0.0",
        dependencies=(_dependency("base-skill"),),
        compatibility=SkillCompatibilityDeclaration(
            platforms=(SkillRequirementId("linux"),)
        ),
    )
    candidate = _record("base-skill", "1.0.0")
    service, *_ = _harness(subject, candidate)
    initial = service.analyze(_request(subject))
    assert initial.status is SkillDependencyAnalysisStatus.INCOMPLETE
    observations = _observations_for(
        initial, status=SkillCompatibilityObservationStatus.COMPATIBLE
    )
    complete = service.analyze(_request(subject, observations=observations))
    assert complete.status is SkillDependencyAnalysisStatus.SATISFIABLE
    assert (
        complete.candidates[0].compatibility_status
        is SkillCompatibilityStatus.OBSERVED_COMPATIBLE
    )


def test_negative_observation_overrides_declared_requirements() -> None:
    subject = _record(
        "subject-skill",
        "1.0.0",
        dependencies=(_dependency("base-skill"),),
        compatibility=SkillCompatibilityDeclaration(
            platforms=(SkillRequirementId("linux"),)
        ),
    )
    candidate = _record("base-skill", "1.0.0")
    service, *_ = _harness(subject, candidate)
    initial = service.analyze(_request(subject))
    observations = _observations_for(
        initial, status=SkillCompatibilityObservationStatus.INCOMPATIBLE
    )
    result = service.analyze(_request(subject, observations=observations))
    assert (
        result.candidates[0].compatibility_status
        is SkillCompatibilityStatus.OBSERVED_INCOMPATIBLE
    )
    assert result.status is SkillDependencyAnalysisStatus.UNSATISFIABLE


def test_partial_positive_observation_does_not_prove_universal_compatibility() -> None:
    subject = _record(
        "subject-skill",
        "1.0.0",
        dependencies=(_dependency("base-skill"),),
        compatibility=SkillCompatibilityDeclaration(
            platforms=(SkillRequirementId("linux"),),
            operating_profiles=(SkillRequirementId("local-first"),),
        ),
    )
    candidate = _record("base-skill", "1.0.0")
    service, *_ = _harness(subject, candidate)
    initial = service.analyze(_request(subject))
    observations = _observations_for(
        initial,
        status=SkillCompatibilityObservationStatus.COMPATIBLE,
        only_first=True,
    )
    result = service.analyze(_request(subject, observations=observations))
    assert result.candidates[0].compatibility_status is SkillCompatibilityStatus.UNKNOWN
    assert not result.complete


def test_conflicting_observations_are_explicit() -> None:
    subject = _record(
        "subject-skill",
        "1.0.0",
        dependencies=(_dependency("base-skill"),),
        compatibility=SkillCompatibilityDeclaration(
            platforms=(SkillRequirementId("linux"),)
        ),
    )
    candidate = _record("base-skill", "1.0.0")
    service, *_ = _harness(subject, candidate)
    initial = service.analyze(_request(subject))
    positive = _observations_for(
        initial, status=SkillCompatibilityObservationStatus.COMPATIBLE
    )[0]
    negative = replace(
        positive,
        status=SkillCompatibilityObservationStatus.INCOMPATIBLE,
        observed_at=positive.observed_at + timedelta(minutes=1),
        observation_ref=SkillSemanticReference("compatibility-observation:negative"),
    )
    result = service.analyze(
        _request(subject, observations=(negative, positive))
    )
    assert result.status is SkillDependencyAnalysisStatus.CONFLICTING_FACTS
    assert (
        result.candidates[0].compatibility_status
        is SkillCompatibilityStatus.CONFLICTING_INFORMATION
    )
    assert result.has_conflicting_facts


def test_global_dimensions_preserve_conflict_and_incompleteness_together() -> None:
    conflict = SkillConflictDeclaration(
        SkillId("base-skill"),
        None,
        SkillSemanticReference("reason:declared-conflict"),
    )
    subject = _record(
        "subject-skill",
        "1.0.0",
        dependencies=(_dependency("base-skill"),),
        conflicts=(conflict,),
        compatibility=SkillCompatibilityDeclaration(
            platforms=(SkillRequirementId("linux"),)
        ),
    )
    candidate = _record("base-skill", "1.0.0")
    service, catalog, _ = _harness(subject, candidate)
    initial = service.analyze(_request(subject))
    positive = _observations_for(
        initial, status=SkillCompatibilityObservationStatus.COMPATIBLE
    )
    catalog.incomplete_skills.add(SkillId("base-skill"))
    result = service.analyze(_request(subject, observations=positive))
    assert result.status is SkillDependencyAnalysisStatus.CONFLICTING_FACTS
    assert result.has_conflicting_facts
    assert not result.complete
    assert SkillDependencyIncompleteReason.CATALOG_TRUNCATED in result.incomplete_reasons


def test_positive_observation_cannot_override_declared_conflict() -> None:
    conflict = SkillConflictDeclaration(
        SkillId("base-skill"),
        None,
        SkillSemanticReference("reason:declared-conflict"),
    )
    subject = _record(
        "subject-skill",
        "1.0.0",
        dependencies=(_dependency("base-skill"),),
        conflicts=(conflict,),
        compatibility=SkillCompatibilityDeclaration(
            platforms=(SkillRequirementId("linux"),)
        ),
    )
    candidate = _record("base-skill", "1.0.0")
    service, *_ = _harness(subject, candidate)
    initial = service.analyze(_request(subject))
    positive = _observations_for(
        initial, status=SkillCompatibilityObservationStatus.COMPATIBLE
    )
    result = service.analyze(_request(subject, observations=positive))
    assert result.status is SkillDependencyAnalysisStatus.CONFLICTING_FACTS
    assert (
        result.candidates[0].compatibility_status
        is SkillCompatibilityStatus.CONFLICTING_INFORMATION
    )


def test_security_requirement_can_be_observed_incompatible_without_safety_claim() -> None:
    subject = _record(
        "subject-skill",
        "1.0.0",
        dependencies=(_dependency("base-skill"),),
        security=SkillSecurityDeclaration(
            filesystem_requirement=FilesystemRequirement.READ_ONLY
        ),
    )
    candidate = _record("base-skill", "1.0.0")
    service, *_ = _harness(subject, candidate)
    initial = service.analyze(_request(subject))
    observations = _observations_for(
        initial, status=SkillCompatibilityObservationStatus.INCOMPATIBLE
    )
    result = service.analyze(_request(subject, observations=observations))
    assert result.status is SkillDependencyAnalysisStatus.UNSATISFIABLE
    assert not hasattr(result, "safe")
    assert not hasattr(result, "trusted")


def test_invalid_or_unrelated_observations_are_rejected() -> None:
    subject = _record(
        "subject-skill", "1.0.0", dependencies=(_dependency("base-skill"),)
    )
    candidate = _record("base-skill", "1.0.0")
    service, *_ = _harness(subject, candidate)
    bogus = SkillCompatibilityObservation(
        subject=subject.identity,
        dependency=candidate.identity,
        analysis_profile_ref=PROFILE,
        requirement_id=SkillCompatibilityRequirementId(
            "compatibility-requirement:" + "a" * 64
        ),
        status=SkillCompatibilityObservationStatus.COMPATIBLE,
        observer_ref=SkillSemanticReference("observer:test"),
        observed_at=NOW,
        observation_ref=SkillSemanticReference("compatibility-observation:bogus"),
    )
    with pytest.raises(InvalidSkillCompatibilityObservation):
        service.analyze(_request(subject, observations=(bogus,)))


def test_acyclic_graph_is_canonical_and_contains_no_order_plan() -> None:
    one = _record(
        "graph-one",
        "1.0.0",
        dependencies=(_dependency("graph-two", "1.0.0", exact=True),),
    )
    two = _record("graph-two", "1.0.0")
    edge = _edge(one, two)
    graph = SkillDependencyGraphInput((two, one), (edge,), True)
    result = SkillDependencyGraphAnalysisService().analyze(
        AnalyzeSkillDependencyGraphRequest(graph)
    )
    assert result.nodes == (one.identity, two.identity)
    assert result.cycles == ()
    assert not hasattr(result, "installation_order")
    assert not hasattr(result, "execution_order")


def test_required_direct_and_long_cycles_are_blocking() -> None:
    one = _record(
        "graph-one",
        "1.0.0",
        dependencies=(_dependency("graph-two", "1.0.0", exact=True),),
    )
    two = _record(
        "graph-two",
        "1.0.0",
        dependencies=(
            _dependency("graph-one", "1.0.0", exact=True),
            _dependency("graph-three", "1.0.0", exact=True),
        ),
    )
    three = _record(
        "graph-three",
        "1.0.0",
        dependencies=(_dependency("graph-one", "1.0.0", exact=True),),
    )
    service = SkillDependencyGraphAnalysisService()
    cases = (
        ((one, two), (_edge(one, two), _edge(two, one))),
        (
            (one, two, three),
            (_edge(one, two), _edge(two, three), _edge(three, one)),
        ),
    )
    for nodes, edges in cases:
        result = service.analyze(
            AnalyzeSkillDependencyGraphRequest(
                SkillDependencyGraphInput(nodes, edges, True)
            )
        )
        assert result.cycles[0].status is SkillDependencyCycleStatus.BLOCKING


def test_optional_and_mixed_cycles_are_advisory() -> None:
    one = _record(
        "graph-one",
        "1.0.0",
        dependencies=(
            _dependency("graph-two", "1.0.0", optional=True, exact=True),
            _dependency("graph-two", "1.0.0", exact=True),
        ),
    )
    two = _record(
        "graph-two",
        "1.0.0",
        dependencies=(
            _dependency("graph-one", "1.0.0", optional=True, exact=True),
            _dependency("graph-one", "1.0.0", exact=True),
        ),
    )
    service = SkillDependencyGraphAnalysisService()
    optional_graph = SkillDependencyGraphInput(
        (one, two),
        (_edge(one, two, optional=True), _edge(two, one, optional=True)),
        True,
    )
    optional = service.analyze(AnalyzeSkillDependencyGraphRequest(optional_graph))
    assert optional.cycles[0].status is SkillDependencyCycleStatus.ADVISORY

    mixed_graph = SkillDependencyGraphInput(
        (one, two),
        (_edge(one, two, optional=True), _edge(two, one)),
        True,
    )
    mixed = service.analyze(AnalyzeSkillDependencyGraphRequest(mixed_graph))
    assert mixed.cycles[0].status is SkillDependencyCycleStatus.ADVISORY


def test_graph_duplicate_input_and_incomplete_boundary_are_explicit() -> None:
    one = _record(
        "graph-one",
        "1.0.0",
        dependencies=(_dependency("graph-two", "1.0.0", exact=True),),
    )
    two = _record("graph-two", "1.0.0")
    edge = _edge(one, two)
    service = SkillDependencyGraphAnalysisService()
    with pytest.raises(InvalidSkillDependencyGraphInput):
        service.analyze(
            AnalyzeSkillDependencyGraphRequest(
                SkillDependencyGraphInput(
                    (one, one, two),
                    (edge,),
                    True,
                )
            )
        )
    with pytest.raises(InvalidSkillDependencyGraphInput):
        service.analyze(
            AnalyzeSkillDependencyGraphRequest(
                SkillDependencyGraphInput(
                    (one, two),
                    (edge, edge),
                    True,
                )
            )
        )
    incomplete = service.analyze(
        AnalyzeSkillDependencyGraphRequest(
            SkillDependencyGraphInput((one, two), (edge,), False)
        )
    )
    assert not incomplete.complete


def test_graph_and_analysis_are_input_order_independent() -> None:
    subject = _record(
        "subject-skill",
        "1.0.0",
        dependencies=(
            _dependency("base-skill"),
            _dependency("base-skill", "1.0.0+build.1", exact=True),
        ),
    )
    one = _record("base-skill", "1.0.0+build.1")
    two = _record("base-skill", "1.0.0+build.2")
    edge_one = _edge(subject, one)
    graph_one = SkillDependencyGraphInput(
        (two, subject, one), (edge_one,), True
    )
    graph_two = SkillDependencyGraphInput(
        tuple(reversed(graph_one.nodes)), tuple(reversed(graph_one.edges)), True
    )
    first_service, *_ = _harness(subject, two, one)
    second_service, *_ = _harness(one, subject, two)
    assert first_service.analyze(_request(subject)) == second_service.analyze(
        _request(subject)
    )
    graph_service = SkillDependencyGraphAnalysisService()
    assert graph_service.analyze(
        AnalyzeSkillDependencyGraphRequest(graph_one)
    ) == graph_service.analyze(AnalyzeSkillDependencyGraphRequest(graph_two))


@pytest.mark.parametrize("count", (0, 1, 200))
def test_graph_node_limits_accept_zero_one_and_exact_max(count: int) -> None:
    records = tuple(
        _record(f"graph-node-{index}", "1.0.0") for index in range(count)
    )
    snapshot = SkillDependencyGraphAnalysisService().analyze(
        AnalyzeSkillDependencyGraphRequest(
            SkillDependencyGraphInput(records, (), True)
        )
    )
    assert len(snapshot.nodes) == count


def test_graph_rejects_max_plus_one_and_edges_not_attested_by_owner() -> None:
    records = tuple(
        _record(f"graph-node-{index}", "1.0.0") for index in range(201)
    )
    with pytest.raises(InvalidSkillDependencyGraphInput):
        SkillDependencyGraphInput(records, (), True)

    owner = _record("graph-owner", "1.0.0")
    dependency = _record("graph-dependency", "1.0.0")
    invented = _edge(owner, dependency)
    with pytest.raises(InvalidSkillDependencyGraphInput):
        SkillDependencyGraphAnalysisService().analyze(
            AnalyzeSkillDependencyGraphRequest(
                SkillDependencyGraphInput(
                    (owner, dependency), (invented,), True
                )
            )
        )


def test_exact_edge_limit_is_accepted_and_dense_cycles_remain_bounded() -> None:
    size = 50
    records = tuple(
        _record(
            f"dense-{owner}",
            "1.0.0",
            dependencies=tuple(
                _dependency(
                    f"dense-{(owner + offset) % size}",
                    "1.0.0",
                    exact=True,
                )
                for offset in range(1, 21)
            ),
        )
        for owner in range(size)
    )
    edges = tuple(
        _edge(owner, dependency)
        for owner_index, owner in enumerate(records)
        for dependency in (
            records[(owner_index + offset) % size]
            for offset in range(1, 21)
        )
    )
    assert len(edges) == 1000
    assert isinstance(
        SkillDependencyGraphInput(records, edges, True),
        SkillDependencyGraphInput,
    )
    with pytest.raises(InvalidSkillDependencyGraphInput):
        SkillDependencyGraphInput(records, (*edges, edges[0]), True)

    dense_records = tuple(
        _record(
            f"bounded-dense-{owner}",
            "1.0.0",
            dependencies=tuple(
                _dependency(
                    f"bounded-dense-{dependency}",
                    "1.0.0",
                    exact=True,
                )
                for dependency in range(10)
                if dependency != owner
            ),
        )
        for owner in range(10)
    )
    dense_edges = tuple(
        _edge(owner, dependency)
        for owner in dense_records
        for dependency in dense_records
        if dependency is not owner
    )
    with pytest.raises(InconsistentSkillDependencyGraph):
        SkillDependencyGraphAnalysisService().analyze(
            AnalyzeSkillDependencyGraphRequest(
                SkillDependencyGraphInput(dense_records, dense_edges, True)
            )
        )


def test_requests_results_graphs_and_observations_are_frozen() -> None:
    subject = _record("subject-skill", "1.0.0")
    service, *_ = _harness(subject)
    request = _request(subject)
    result = service.analyze(request)
    with pytest.raises(FrozenInstanceError):
        request.subject = subject.identity  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        result.complete = False  # type: ignore[misc]
    assert isinstance(result.requirements, tuple)
    assert isinstance(result.candidates, tuple)
    assert not hasattr(request, "graph")
    assert not hasattr(result, "graph")


def test_observation_order_and_timestamp_metadata_do_not_change_analysis() -> None:
    subject = _record(
        "subject-skill",
        "1.0.0",
        dependencies=(_dependency("base-skill"),),
        compatibility=SkillCompatibilityDeclaration(
            platforms=(SkillRequirementId("linux"),)
        ),
    )
    candidate = _record("base-skill", "1.0.0")
    service, *_ = _harness(subject, candidate)
    initial = service.analyze(_request(subject))
    observation = _observations_for(
        initial, status=SkillCompatibilityObservationStatus.COMPATIBLE
    )[0]
    changed_metadata = replace(
        observation, observed_at=observation.observed_at + timedelta(days=1)
    )
    assert service.analyze(
        _request(subject, observations=(observation,))
    ) == service.analyze(
        _request(subject, observations=(changed_metadata,))
    )


def test_errors_are_fixed_and_analysis_does_not_leak_inputs() -> None:
    secret = "SECRET-MANIFEST-OBSERVATION"
    error = InvalidSkillCompatibilityObservation(secret)
    assert str(error) == "skill compatibility observation is invalid"
    assert secret not in str(error)
    assert secret not in repr(error)


def test_analysis_has_no_write_or_runtime_progression_surface() -> None:
    forbidden = {
        "resolve",
        "install",
        "activate",
        "publish",
        "execute",
        "save",
        "append",
        "delete",
    }
    assert forbidden.isdisjoint(dir(SkillDependencyAnalysisService))
    source = (
        Path("backend/synapse/skills/phase8_analysis.py")
        .read_text(encoding="utf-8")
        .lower()
    )
    for term in (
        "subprocess",
        "importlib",
        "private_evals",
        "project_governance",
        "intelligence_boundary",
        "synapse.sandbox",
    ):
        assert term not in source


def test_public_surface_contains_only_stable_slice8_contracts() -> None:
    import synapse.skills as skills

    assert {
        "SkillDependencyId",
        "SkillDependencyCandidateFact",
        "SkillCompatibilityObservation",
        "SkillDependencyGraphSnapshot",
        "AnalyzeSkillDependenciesRequest",
        "SkillDependencyAnalysis",
        "SkillLifecycleProjectionProvider",
        "SkillDependencyAnalysisService",
        "SkillDependencyAnalysisError",
        "SkillDependencyCatalogPage",
        "SkillDependencyCatalogProvider",
        "SkillDependencyGraphAnalysisService",
    }.issubset(skills.__all__)
    assert {
        "_matches_constraint",
        "_cycles",
        "_canonical_cycle",
        "FakeCatalog",
        "FakeLifecycle",
        "SkillDependencyCandidateStatus",
        "ConflictingSkillDependencyDeclarations",
    }.isdisjoint(skills.__all__)
