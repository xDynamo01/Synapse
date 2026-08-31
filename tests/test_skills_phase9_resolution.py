from __future__ import annotations

import hashlib
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

from synapse.skills.phase2_models import (
    PublishedSkillVersionId,
    SkillContentFingerprint,
    SkillDependencyDeclaration,
    SkillDependencyReason,
    SkillId,
    SkillManifestFingerprint,
    SkillSemanticReference,
    SkillVersion,
    SkillVersionConstraint,
)
from synapse.skills.phase8_models import (
    SkillCompatibilityStatus,
    SkillDependencyAnalysis,
    SkillDependencyAnalysisStatus,
    SkillDependencyCandidateFact,
    SkillDependencyCardinality,
    SkillDependencyConstraintStatus,
    SkillDependencyCycleFact,
    SkillDependencyCycleStatus,
    SkillDependencyGraphEdge,
    SkillDependencyGraphSnapshot,
    SkillDependencyId,
    SkillDependencyIncompleteReason,
    SkillDependencyLifecycleStatus,
    SkillDependencyRequirementFact,
    SkillDependencyRequirementStatus,
)
from synapse.skills.phase9_constraints import (
    intersect_dependency_declarations,
)
from synapse.skills.phase9_errors import (
    InconsistentSkillDependencyAnalysis,
    InvalidSkillDependencyResolutionPolicy,
    InvalidSkillDependencyResolutionRequest,
)
from synapse.skills.phase9_models import (
    ResolveSkillDependenciesRequest,
    SkillDependencyCandidateRejectionReason,
    SkillDependencyRequirementResolutionStatus,
    SkillDependencyResolutionConflictKind,
    SkillDependencyResolutionStatus,
    SkillDependencyTieBreak,
)
from synapse.skills.phase9_policy import (
    SkillDependencyCompatibilityPolicy,
    SkillDependencyCompletenessPolicy,
    SkillDependencyDegradedLifecyclePolicy,
    SkillDependencyResolutionLimits,
    SkillDependencyResolutionPolicy,
    SkillDependencyResolutionPolicyVersion,
    SkillDependencyVersionMode,
    SkillDependencyVersionPreference,
    SkillOptionalDependencyPolicy,
)
from synapse.skills.phase9_resolution import SkillDependencyResolutionService

PROFILE = SkillSemanticReference("analysis-profile:test")
RESOLUTION_PROFILE = SkillSemanticReference("resolution-profile:test")


def _identity(skill_id: str, version: str) -> PublishedSkillVersionId:
    manifest = hashlib.sha256(f"manifest:{skill_id}@{version}".encode()).hexdigest()
    content = hashlib.sha256(f"content:{skill_id}@{version}".encode()).hexdigest()
    return PublishedSkillVersionId(
        SkillId(skill_id),
        SkillVersion.parse(version),
        SkillManifestFingerprint(manifest),
        SkillContentFingerprint(content),
    )


def _dependency(
    skill_id: str,
    specification: str = "^1.0.0",
    *,
    optional: bool = False,
    exact: bool = False,
    reason: SkillDependencyReason | None = None,
) -> SkillDependencyDeclaration:
    return SkillDependencyDeclaration(
        SkillId(skill_id),
        reason
        or (
            SkillDependencyReason.OPTIONAL_ENHANCEMENT
            if optional
            else SkillDependencyReason.REQUIRED_WORKFLOW
        ),
        SkillVersion.parse(specification) if exact else None,
        None if exact else SkillVersionConstraint(specification),
        optional,
    )


def _limits(**changes: int) -> SkillDependencyResolutionLimits:
    values = {
        "max_requirements": 200,
        "max_candidates_per_requirement": 200,
        "max_groups": 200,
        "max_search_states": 10_000,
        "max_graph_nodes": 200,
        "max_graph_edges": 1_000,
        "max_diagnostics": 1_000,
    }
    values.update(changes)
    return SkillDependencyResolutionLimits(**values)


def _policy(
    *,
    mode: SkillDependencyVersionMode = SkillDependencyVersionMode.SINGLE_VERSION,
    preference: SkillDependencyVersionPreference = (
        SkillDependencyVersionPreference.HIGHER_SEMVER
    ),
    compatibility: SkillDependencyCompatibilityPolicy = (
        SkillDependencyCompatibilityPolicy.DECLARED_OR_OBSERVED
    ),
    degraded: SkillDependencyDegradedLifecyclePolicy = (
        SkillDependencyDegradedLifecyclePolicy.DENY
    ),
    optional: SkillOptionalDependencyPolicy = (
        SkillOptionalDependencyPolicy.RESOLVE_WHEN_POSSIBLE
    ),
    completeness: SkillDependencyCompletenessPolicy = (
        SkillDependencyCompletenessPolicy.ALLOW_OPTIONAL_INCOMPLETE
    ),
    prerelease: bool = False,
    limits: SkillDependencyResolutionLimits | None = None,
) -> SkillDependencyResolutionPolicy:
    return SkillDependencyResolutionPolicy(
        SkillDependencyResolutionPolicyVersion(1),
        mode,
        preference,
        compatibility,
        degraded,
        optional,
        completeness,
        prerelease,
        limits or _limits(),
    )


def _analysis(
    subject: PublishedSkillVersionId,
    declarations: tuple[SkillDependencyDeclaration, ...],
    available: dict[SkillDependencyId, tuple[PublishedSkillVersionId, ...]],
    *,
    lifecycle: dict[PublishedSkillVersionId, SkillDependencyLifecycleStatus]
    | None = None,
    compatibility: dict[PublishedSkillVersionId, SkillCompatibilityStatus]
    | None = None,
    incomplete: set[SkillDependencyId] | None = None,
) -> SkillDependencyAnalysis:
    lifecycle = lifecycle or {}
    compatibility = compatibility or {}
    incomplete = incomplete or set()
    requirements: list[SkillDependencyRequirementFact] = []
    candidates: list[SkillDependencyCandidateFact] = []
    for declaration in declarations:
        dependency_id = SkillDependencyId.from_declaration(subject, declaration)
        identities = available.get(dependency_id, ())
        matching = tuple(
            identity
            for identity in identities
            if declaration.version == identity.version
            or (
                declaration.constraint is not None
                and not identity.version.prerelease
                and _matches_for_fixture(declaration, identity.version)
            )
        )
        eligible: list[PublishedSkillVersionId] = []
        for identity in identities:
            match = identity in matching
            lifecycle_status = lifecycle.get(
                identity, SkillDependencyLifecycleStatus.ELIGIBLE
            )
            compatibility_status = compatibility.get(
                identity, SkillCompatibilityStatus.DECLARED_COMPATIBLE
            )
            if (
                match
                and lifecycle_status is SkillDependencyLifecycleStatus.ELIGIBLE
                and compatibility_status
                in {
                    SkillCompatibilityStatus.DECLARED_COMPATIBLE,
                    SkillCompatibilityStatus.OBSERVED_COMPATIBLE,
                }
            ):
                eligible.append(identity)
            candidates.append(
                SkillDependencyCandidateFact(
                    dependency_id,
                    identity,
                    (
                        SkillDependencyConstraintStatus.MATCH
                        if match
                        else SkillDependencyConstraintStatus.MISMATCH
                    ),
                    lifecycle_status if match else None,
                    (
                        compatibility_status
                        if match
                        else SkillCompatibilityStatus.UNKNOWN
                    ),
                    (),
                    (),
                )
            )
        status = (
            SkillDependencyRequirementStatus.INCOMPLETE
            if dependency_id in incomplete
            else (
                SkillDependencyRequirementStatus.SATISFIED
                if eligible
                else SkillDependencyRequirementStatus.UNSATISFIED
            )
        )
        requirements.append(
            SkillDependencyRequirementFact(
                dependency_id,
                subject,
                declaration,
                (
                    SkillDependencyCardinality.OPTIONAL
                    if declaration.optional
                    else SkillDependencyCardinality.REQUIRED
                ),
                matching,
                tuple(eligible),
                status,
            )
        )
    incomplete_reasons = (
        (SkillDependencyIncompleteReason.CATALOG_TRUNCATED,)
        if incomplete
        else ()
    )
    has_unsatisfied_required = any(
        requirement.cardinality is SkillDependencyCardinality.REQUIRED
        and requirement.status is SkillDependencyRequirementStatus.UNSATISFIED
        for requirement in requirements
    )
    has_conflicting_facts = any(
        candidate.compatibility_status
        is SkillCompatibilityStatus.CONFLICTING_INFORMATION
        for candidate in candidates
    )
    return SkillDependencyAnalysis(
        subject,
        tuple(requirements),
        tuple(candidates),
        (),
        (),
        (),
        incomplete_reasons,
        (
            SkillDependencyAnalysisStatus.CONFLICTING_FACTS
            if has_conflicting_facts
            else (
                SkillDependencyAnalysisStatus.INCOMPLETE
                if incomplete
                else (
                    SkillDependencyAnalysisStatus.UNSATISFIABLE
                    if has_unsatisfied_required
                    else SkillDependencyAnalysisStatus.SATISFIABLE
                )
            )
        ),
        not incomplete,
        has_unsatisfied_required,
        has_conflicting_facts,
        PROFILE,
    )


def _matches_for_fixture(
    declaration: SkillDependencyDeclaration, version: SkillVersion
) -> bool:
    from synapse.skills.phase8_matching import matches_declaration

    return matches_declaration(declaration, version)


def _request(
    analysis: SkillDependencyAnalysis,
    policy: SkillDependencyResolutionPolicy | None = None,
    graph: SkillDependencyGraphSnapshot | None = None,
) -> ResolveSkillDependenciesRequest:
    return ResolveSkillDependenciesRequest(
        subject=analysis.subject,
        analysis=analysis,
        policy=policy or _policy(),
        resolution_profile_ref=RESOLUTION_PROFILE,
        graph=graph,
    )


def _single_requirement_analysis(
    versions: tuple[str, ...],
    *,
    declaration: SkillDependencyDeclaration | None = None,
    lifecycle: dict[PublishedSkillVersionId, SkillDependencyLifecycleStatus]
    | None = None,
    compatibility: dict[PublishedSkillVersionId, SkillCompatibilityStatus]
    | None = None,
) -> SkillDependencyAnalysis:
    subject = _identity("subject-skill", "1.0.0")
    dependency = declaration or _dependency("base-skill")
    dependency_id = SkillDependencyId.from_declaration(subject, dependency)
    identities = tuple(_identity("base-skill", version) for version in versions)
    return _analysis(
        subject,
        (dependency,),
        {dependency_id: identities},
        lifecycle=lifecycle,
        compatibility=compatibility,
    )


def test_policy_is_required_explicit_and_deeply_frozen() -> None:
    with pytest.raises(TypeError):
        SkillDependencyResolutionPolicy()  # type: ignore[call-arg]
    policy = _policy()
    with pytest.raises(FrozenInstanceError):
        policy.allow_exact_prerelease = True  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        policy.limits.max_groups = 1  # type: ignore[misc]


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("max_requirements", 0),
        ("max_candidates_per_requirement", -1),
        ("max_groups", True),
        ("max_search_states", 100_001),
        ("max_graph_nodes", 201),
        ("max_graph_edges", 1_001),
        ("max_diagnostics", 5_001),
    ),
)
def test_policy_limits_reject_invalid_bounds(field: str, value: object) -> None:
    with pytest.raises(InvalidSkillDependencyResolutionPolicy):
        _limits(**{field: value})  # type: ignore[arg-type]


def test_policy_limits_accept_each_exact_maximum() -> None:
    limits = SkillDependencyResolutionLimits(500, 500, 500, 100_000, 200, 1_000, 5_000)
    assert limits.max_search_states == 100_000


@pytest.mark.parametrize(
    ("declarations", "version", "expected"),
    (
        (
            (_dependency("base-skill", "^1.0.0"), _dependency("base-skill", ">=1.5.0,<2.0.0")),
            "1.5.0",
            True,
        ),
        (
            (_dependency("base-skill", "^1.2.0"), _dependency("base-skill", "^1.5.0")),
            "1.8.0",
            True,
        ),
        (
            (_dependency("base-skill", "^0.2.3"), _dependency("base-skill", ">=0.2.5,<0.3.0")),
            "0.2.9",
            True,
        ),
        (
            (_dependency("base-skill", "1.2.0", exact=True), _dependency("base-skill", "^1.0.0")),
            "1.2.0",
            True,
        ),
        (
            (_dependency("base-skill", "1.2.0", exact=True), _dependency("base-skill", "1.2.0", exact=True)),
            "1.2.0",
            True,
        ),
        (
            (_dependency("base-skill", "1.2.0", exact=True), _dependency("base-skill", ">=1.0.0,<2.0.0")),
            "1.2.0",
            True,
        ),
        (
            (_dependency("base-skill", "1.2.0", exact=True), _dependency("base-skill", ">=2.0.0,<3.0.0")),
            "1.2.0",
            False,
        ),
        (
            (_dependency("base-skill", ">=1.0.0,<1.5.0"), _dependency("base-skill", ">=1.5.0,<2.0.0")),
            "1.5.0",
            False,
        ),
        (
            (_dependency("base-skill", ">=1.0.0,<=1.5.0"), _dependency("base-skill", ">=1.5.0,<2.0.0")),
            "1.5.0",
            True,
        ),
        (
            (_dependency("base-skill", "1.0.0+build1", exact=True), _dependency("base-skill", "1.0.0+build2", exact=True)),
            "1.0.0+build1",
            False,
        ),
        (
            (_dependency("base-skill", "1.0.0-rc.1", exact=True),),
            "1.0.0-rc.1",
            True,
        ),
    ),
)
def test_constraint_intersection(
    declarations: tuple[SkillDependencyDeclaration, ...],
    version: str,
    expected: bool,
) -> None:
    intersection = intersect_dependency_declarations(declarations)
    assert (intersection is not None and intersection.contains(SkillVersion.parse(version))) is expected


@pytest.mark.parametrize(
    ("preference", "expected"),
    (
        (SkillDependencyVersionPreference.HIGHER_SEMVER, "1.9.0"),
        (SkillDependencyVersionPreference.LOWER_SEMVER, "1.0.0"),
    ),
)
def test_selection_direction_is_explicit_policy(
    preference: SkillDependencyVersionPreference, expected: str
) -> None:
    analysis = _single_requirement_analysis(("1.0.0", "1.9.0"))
    plan = SkillDependencyResolutionService().resolve(
        _request(analysis, _policy(preference=preference))
    )
    assert str(plan.resolved[0].selected.version) == expected
    assert plan.status is SkillDependencyResolutionStatus.RESOLVED


def test_build_tie_is_deterministic_and_not_semver_superiority() -> None:
    analysis = _single_requirement_analysis(
        ("1.0.0+build2", "1.0.0", "1.0.0+build1")
    )
    plan = SkillDependencyResolutionService().resolve(_request(analysis))
    assert str(plan.resolved[0].selected.version) == "1.0.0"
    assert (
        plan.resolved[0].rationale.tie_break
        is SkillDependencyTieBreak.CONCRETE_VERSION_TEXT
    )


def test_exact_prerelease_requires_both_declaration_and_policy() -> None:
    declaration = _dependency(
        "base-skill", "1.0.0-rc.1", exact=True
    )
    analysis = _single_requirement_analysis(
        ("1.0.0-rc.1",), declaration=declaration
    )
    denied = SkillDependencyResolutionService().resolve(_request(analysis))
    allowed = SkillDependencyResolutionService().resolve(
        _request(analysis, _policy(prerelease=True))
    )
    assert denied.status is SkillDependencyResolutionStatus.UNRESOLVABLE
    assert allowed.status is SkillDependencyResolutionStatus.RESOLVED


@pytest.mark.parametrize(
    ("lifecycle_status", "degraded_policy", "resolved"),
    (
        (
            SkillDependencyLifecycleStatus.REVOKED,
            SkillDependencyDegradedLifecyclePolicy.ALLOW_DEPRECATED_AND_SUPERSEDED,
            False,
        ),
        (
            SkillDependencyLifecycleStatus.DEPRECATED,
            SkillDependencyDegradedLifecyclePolicy.DENY,
            False,
        ),
        (
            SkillDependencyLifecycleStatus.DEPRECATED,
            SkillDependencyDegradedLifecyclePolicy.ALLOW_DEPRECATED,
            True,
        ),
        (
            SkillDependencyLifecycleStatus.SUPERSEDED,
            SkillDependencyDegradedLifecyclePolicy.ALLOW_DEPRECATED,
            False,
        ),
        (
            SkillDependencyLifecycleStatus.SUPERSEDED,
            SkillDependencyDegradedLifecyclePolicy.ALLOW_DEPRECATED_AND_SUPERSEDED,
            True,
        ),
    ),
)
def test_lifecycle_filtering_is_explicit_and_revoked_never_selected(
    lifecycle_status: SkillDependencyLifecycleStatus,
    degraded_policy: SkillDependencyDegradedLifecyclePolicy,
    resolved: bool,
) -> None:
    identity = _identity("base-skill", "1.0.0")
    analysis = _single_requirement_analysis(
        (),
        lifecycle={identity: lifecycle_status},
    )
    declaration = analysis.requirements[0].declaration
    dependency_id = analysis.requirements[0].dependency_id
    analysis = _analysis(
        analysis.subject,
        (declaration,),
        {dependency_id: (identity,)},
        lifecycle={identity: lifecycle_status},
    )
    plan = SkillDependencyResolutionService().resolve(
        _request(analysis, _policy(degraded=degraded_policy))
    )
    assert bool(plan.resolved) is resolved
    if resolved:
        assert plan.has_degraded_selections


def test_regular_lifecycle_precedes_explicit_degraded_fallback() -> None:
    regular = _identity("base-skill", "1.0.0")
    deprecated = _identity("base-skill", "1.9.0")
    subject = _identity("subject-skill", "1.0.0")
    declaration = _dependency("base-skill")
    dependency_id = SkillDependencyId.from_declaration(subject, declaration)
    analysis = _analysis(
        subject,
        (declaration,),
        {dependency_id: (deprecated, regular)},
        lifecycle={deprecated: SkillDependencyLifecycleStatus.DEPRECATED},
    )
    plan = SkillDependencyResolutionService().resolve(
        _request(
            analysis,
            _policy(
                degraded=SkillDependencyDegradedLifecyclePolicy.ALLOW_DEPRECATED
            ),
        )
    )
    assert plan.resolved[0].selected == regular
    assert not plan.has_degraded_selections


@pytest.mark.parametrize(
    ("status", "policy", "resolved"),
    (
        (
            SkillCompatibilityStatus.DECLARED_COMPATIBLE,
            SkillDependencyCompatibilityPolicy.DECLARED_OR_OBSERVED,
            True,
        ),
        (
            SkillCompatibilityStatus.DECLARED_COMPATIBLE,
            SkillDependencyCompatibilityPolicy.OBSERVED_ONLY,
            False,
        ),
        (
            SkillCompatibilityStatus.OBSERVED_COMPATIBLE,
            SkillDependencyCompatibilityPolicy.OBSERVED_ONLY,
            True,
        ),
        (
            SkillCompatibilityStatus.UNKNOWN,
            SkillDependencyCompatibilityPolicy.ALLOW_UNKNOWN,
            True,
        ),
        (
            SkillCompatibilityStatus.UNKNOWN,
            SkillDependencyCompatibilityPolicy.DECLARED_OR_OBSERVED,
            False,
        ),
        (
            SkillCompatibilityStatus.DECLARED_INCOMPATIBLE,
            SkillDependencyCompatibilityPolicy.ALLOW_UNKNOWN,
            False,
        ),
        (
            SkillCompatibilityStatus.OBSERVED_INCOMPATIBLE,
            SkillDependencyCompatibilityPolicy.ALLOW_UNKNOWN,
            False,
        ),
        (
            SkillCompatibilityStatus.CONFLICTING_INFORMATION,
            SkillDependencyCompatibilityPolicy.ALLOW_UNKNOWN,
            False,
        ),
    ),
)
def test_compatibility_policy_never_turns_incompatibility_into_selection(
    status: SkillCompatibilityStatus,
    policy: SkillDependencyCompatibilityPolicy,
    resolved: bool,
) -> None:
    identity = _identity("base-skill", "1.0.0")
    subject = _identity("subject-skill", "1.0.0")
    declaration = _dependency("base-skill")
    dependency_id = SkillDependencyId.from_declaration(subject, declaration)
    analysis = _analysis(
        subject,
        (declaration,),
        {dependency_id: (identity,)},
        compatibility={identity: status},
    )
    plan = SkillDependencyResolutionService().resolve(
        _request(analysis, _policy(compatibility=policy))
    )
    assert bool(plan.resolved) is resolved


def test_single_version_shares_one_candidate_for_compatible_requirements() -> None:
    subject = _identity("subject-skill", "1.0.0")
    declarations = (
        _dependency("base-skill", "^1.0.0"),
        _dependency("base-skill", ">=1.5.0,<2.0.0", reason=SkillDependencyReason.SHARED_SCHEMA),
    )
    candidates = (_identity("base-skill", "1.5.0"), _identity("base-skill", "1.8.0"))
    available = {
        SkillDependencyId.from_declaration(subject, declaration): candidates
        for declaration in declarations
    }
    plan = SkillDependencyResolutionService().resolve(
        _request(_analysis(subject, declarations, available))
    )
    assert len(plan.resolved) == 1
    assert len(plan.resolved[0].requirement_ids) == 2
    assert str(plan.resolved[0].selected.version) == "1.8.0"


def test_duplicate_requirement_is_rejected_instead_of_silently_merged() -> None:
    subject = _identity("subject-skill", "1.0.0")
    declaration = _dependency("base-skill")
    dependency_id = SkillDependencyId.from_declaration(subject, declaration)
    candidate = _identity("base-skill", "1.0.0")
    analysis = _analysis(
        subject,
        (declaration, declaration),
        {dependency_id: (candidate,)},
    )
    with pytest.raises(InconsistentSkillDependencyAnalysis):
        SkillDependencyResolutionService().resolve(_request(analysis))


def test_single_version_conflict_and_multi_version_resolution_are_distinct() -> None:
    subject = _identity("subject-skill", "1.0.0")
    declarations = (
        _dependency("base-skill", "^1.0.0"),
        _dependency("base-skill", "^2.0.0", reason=SkillDependencyReason.SHARED_SCHEMA),
    )
    one = _identity("base-skill", "1.5.0")
    two = _identity("base-skill", "2.5.0")
    available = {
        SkillDependencyId.from_declaration(subject, declarations[0]): (one, two),
        SkillDependencyId.from_declaration(subject, declarations[1]): (one, two),
    }
    analysis = _analysis(subject, declarations, available)
    single = SkillDependencyResolutionService().resolve(_request(analysis))
    multi = SkillDependencyResolutionService().resolve(
        _request(
            analysis,
            _policy(mode=SkillDependencyVersionMode.MULTI_VERSION),
        )
    )
    assert single.status is SkillDependencyResolutionStatus.CONFLICTING
    assert (
        single.conflicts[0].kind
        is SkillDependencyResolutionConflictKind.CONSTRAINT_INTERSECTION
    )
    assert {str(item.selected.version) for item in multi.resolved} == {
        "1.5.0",
        "2.5.0",
    }


def test_required_and_optional_conflict_resolves_required_and_omits_optional() -> None:
    subject = _identity("subject-skill", "1.0.0")
    required = _dependency("base-skill", "^1.0.0")
    optional = _dependency("base-skill", "^2.0.0", optional=True)
    one = _identity("base-skill", "1.5.0")
    two = _identity("base-skill", "2.5.0")
    analysis = _analysis(
        subject,
        (required, optional),
        {
            SkillDependencyId.from_declaration(subject, required): (one, two),
            SkillDependencyId.from_declaration(subject, optional): (one, two),
        },
    )
    plan = SkillDependencyResolutionService().resolve(_request(analysis))
    assert plan.required_resolved
    assert plan.has_optional_omissions
    assert {
        item.status for item in plan.requirements
    } == {
        SkillDependencyRequirementResolutionStatus.RESOLVED,
        SkillDependencyRequirementResolutionStatus.OMITTED_CONFLICT,
    }


def test_optional_only_conflict_resolves_one_and_reports_other() -> None:
    subject = _identity("subject-skill", "1.0.0")
    one_requirement = _dependency("base-skill", "^1.0.0", optional=True)
    two_requirement = _dependency("base-skill", "^2.0.0", optional=True)
    one = _identity("base-skill", "1.5.0")
    two = _identity("base-skill", "2.5.0")
    analysis = _analysis(
        subject,
        (one_requirement, two_requirement),
        {
            SkillDependencyId.from_declaration(subject, one_requirement): (
                one,
                two,
            ),
            SkillDependencyId.from_declaration(subject, two_requirement): (
                one,
                two,
            ),
        },
    )
    plan = SkillDependencyResolutionService().resolve(_request(analysis))
    assert len(plan.resolved) == 1
    assert {
        item.status for item in plan.requirements
    } == {
        SkillDependencyRequirementResolutionStatus.RESOLVED,
        SkillDependencyRequirementResolutionStatus.OMITTED_CONFLICT,
    }


def test_optional_policy_omits_explicitly_even_when_candidate_exists() -> None:
    declaration = _dependency("base-skill", optional=True)
    analysis = _single_requirement_analysis(("1.0.0",), declaration=declaration)
    plan = SkillDependencyResolutionService().resolve(
        _request(
            analysis,
            _policy(optional=SkillOptionalDependencyPolicy.OMIT),
        )
    )
    assert (
        plan.requirements[0].status
        is SkillDependencyRequirementResolutionStatus.OMITTED_POLICY
    )
    assert plan.status is SkillDependencyResolutionStatus.PARTIALLY_RESOLVED


def test_optional_no_candidate_and_optional_incomplete_are_distinct() -> None:
    subject = _identity("subject-skill", "1.0.0")
    declaration = _dependency("base-skill", optional=True)
    dependency_id = SkillDependencyId.from_declaration(subject, declaration)
    missing = _analysis(subject, (declaration,), {dependency_id: ()})
    incomplete = _analysis(
        subject,
        (declaration,),
        {dependency_id: ()},
        incomplete={dependency_id},
    )
    service = SkillDependencyResolutionService()
    missing_plan = service.resolve(_request(missing))
    incomplete_plan = service.resolve(_request(incomplete))
    assert (
        missing_plan.requirements[0].status
        is SkillDependencyRequirementResolutionStatus.OMITTED_NO_CANDIDATE
    )
    assert (
        incomplete_plan.requirements[0].status
        is SkillDependencyRequirementResolutionStatus.UNRESOLVED_INCOMPLETE
    )


def test_complete_analysis_policy_blocks_optional_incomplete_globally() -> None:
    subject = _identity("subject-skill", "1.0.0")
    declaration = _dependency("base-skill", optional=True)
    dependency_id = SkillDependencyId.from_declaration(subject, declaration)
    analysis = _analysis(
        subject,
        (declaration,),
        {dependency_id: ()},
        incomplete={dependency_id},
    )
    plan = SkillDependencyResolutionService().resolve(
        _request(
            analysis,
            _policy(
                completeness=SkillDependencyCompletenessPolicy.REQUIRE_COMPLETE_ANALYSIS
            ),
        )
    )
    assert plan.status is SkillDependencyResolutionStatus.INCOMPLETE
    assert not plan.complete


def test_required_incomplete_never_produces_definitive_selection() -> None:
    subject = _identity("subject-skill", "1.0.0")
    declaration = _dependency("base-skill")
    dependency_id = SkillDependencyId.from_declaration(subject, declaration)
    candidate = _identity("base-skill", "1.0.0")
    analysis = _analysis(
        subject,
        (declaration,),
        {dependency_id: (candidate,)},
        incomplete={dependency_id},
    )
    plan = SkillDependencyResolutionService().resolve(_request(analysis))
    assert not plan.resolved
    assert plan.status is SkillDependencyResolutionStatus.INCOMPLETE


def test_rationale_preserves_considered_and_rejected_candidates() -> None:
    allowed = _identity("base-skill", "1.0.0")
    revoked = _identity("base-skill", "1.1.0")
    subject = _identity("subject-skill", "1.0.0")
    declaration = _dependency("base-skill")
    dependency_id = SkillDependencyId.from_declaration(subject, declaration)
    analysis = _analysis(
        subject,
        (declaration,),
        {dependency_id: (revoked, allowed)},
        lifecycle={revoked: SkillDependencyLifecycleStatus.REVOKED},
    )
    plan = SkillDependencyResolutionService().resolve(_request(analysis))
    decisions = plan.resolved[0].rationale.considered
    assert len(decisions) == 2
    assert any(
        SkillDependencyCandidateRejectionReason.REVOKED
        in decision.rejection_reasons
        for decision in decisions
    )


def test_rationale_does_not_misreport_semver_when_coverage_decides() -> None:
    subject = _identity("subject-skill", "1.0.0")
    required = _dependency("base-skill", ">=1.0.0,<3.0.0")
    optional = _dependency(
        "base-skill",
        ">=1.0.0,<2.0.0",
        optional=True,
    )
    low = _identity("base-skill", "1.0.0")
    high = _identity("base-skill", "2.0.0")
    available = {
        SkillDependencyId.from_declaration(subject, required): (low, high),
        SkillDependencyId.from_declaration(subject, optional): (low, high),
    }
    plan = SkillDependencyResolutionService().resolve(
        _request(_analysis(subject, (required, optional), available))
    )
    assert plan.resolved[0].selected == low
    assert plan.resolved[0].rationale.tie_break is SkillDependencyTieBreak.NONE


def test_candidate_requirement_and_diagnostic_order_do_not_change_plan() -> None:
    subject = _identity("subject-skill", "1.0.0")
    first = _dependency("base-skill", "^1.0.0")
    second = _dependency(
        "other-skill",
        "^1.0.0",
        reason=SkillDependencyReason.SHARED_SCHEMA,
    )
    first_candidates = (
        _identity("base-skill", "1.0.0"),
        _identity("base-skill", "1.9.0"),
    )
    second_candidates = (
        _identity("other-skill", "1.0.0"),
        _identity("other-skill", "1.5.0"),
    )
    analysis = _analysis(
        subject,
        (first, second),
        {
            SkillDependencyId.from_declaration(subject, first): first_candidates,
            SkillDependencyId.from_declaration(subject, second): second_candidates,
        },
    )
    reordered = replace(
        analysis,
        requirements=tuple(reversed(analysis.requirements)),
        candidates=tuple(reversed(analysis.candidates)),
        diagnostics=tuple(reversed(analysis.diagnostics)),
    )
    service = SkillDependencyResolutionService()
    assert service.resolve(_request(analysis)) == service.resolve(
        _request(reordered)
    )


def test_required_cycle_is_preserved_and_blocks_selected_exact_nodes() -> None:
    subject = _identity("subject-skill", "1.0.0")
    dependency = _identity("base-skill", "1.0.0")
    forward_declaration = _dependency("base-skill", "1.0.0", exact=True)
    reverse_declaration = _dependency("subject-skill", "1.0.0", exact=True)
    forward_id = SkillDependencyId.from_declaration(subject, forward_declaration)
    reverse_id = SkillDependencyId.from_declaration(dependency, reverse_declaration)
    analysis = _analysis(
        subject,
        (forward_declaration,),
        {forward_id: (dependency,)},
    )
    graph = SkillDependencyGraphSnapshot(
        (subject, dependency),
        (
            SkillDependencyGraphEdge(
                subject, dependency, forward_id, forward_declaration
            ),
            SkillDependencyGraphEdge(
                dependency, subject, reverse_id, reverse_declaration
            ),
        ),
        (
            SkillDependencyCycleFact(
                (subject, dependency),
                (forward_id, reverse_id),
                SkillDependencyCycleStatus.BLOCKING,
            ),
        ),
        True,
    )
    plan = SkillDependencyResolutionService().resolve(
        _request(analysis, graph=graph)
    )
    assert plan.status is SkillDependencyResolutionStatus.CONFLICTING
    assert plan.graph_cycles == graph.cycles


@pytest.mark.parametrize(
    ("forward_optional", "reverse_optional"),
    ((True, True), (False, True)),
)
def test_optional_or_mixed_graph_cycle_is_advisory_not_blocking(
    forward_optional: bool,
    reverse_optional: bool,
) -> None:
    subject = _identity("subject-skill", "1.0.0")
    dependency = _identity("base-skill", "1.0.0")
    forward_declaration = _dependency(
        "base-skill",
        "1.0.0",
        exact=True,
        optional=forward_optional,
    )
    reverse_declaration = _dependency(
        "subject-skill",
        "1.0.0",
        exact=True,
        optional=reverse_optional,
    )
    forward_id = SkillDependencyId.from_declaration(subject, forward_declaration)
    reverse_id = SkillDependencyId.from_declaration(
        dependency, reverse_declaration
    )
    analysis = _analysis(
        subject,
        (forward_declaration,),
        {forward_id: (dependency,)},
    )
    cycle = SkillDependencyCycleFact(
        (subject, dependency),
        (forward_id, reverse_id),
        SkillDependencyCycleStatus.ADVISORY,
    )
    graph = SkillDependencyGraphSnapshot(
        (subject, dependency),
        (
            SkillDependencyGraphEdge(
                subject, dependency, forward_id, forward_declaration
            ),
            SkillDependencyGraphEdge(
                dependency, subject, reverse_id, reverse_declaration
            ),
        ),
        (cycle,),
        True,
    )
    plan = SkillDependencyResolutionService().resolve(
        _request(analysis, graph=graph)
    )
    assert plan.status is SkillDependencyResolutionStatus.RESOLVED


def test_incomplete_graph_cannot_produce_complete_plan() -> None:
    analysis = _single_requirement_analysis(("1.0.0",))
    graph = SkillDependencyGraphSnapshot((), (), (), False)
    plan = SkillDependencyResolutionService().resolve(
        _request(analysis, graph=graph)
    )
    assert plan.status is SkillDependencyResolutionStatus.INCOMPLETE
    assert not plan.complete


def test_search_limit_exceeded_is_typed_incomplete_plan() -> None:
    analysis = _single_requirement_analysis(("1.0.0", "1.1.0"))
    plan = SkillDependencyResolutionService().resolve(
        _request(analysis, _policy(limits=_limits(max_search_states=1)))
    )
    assert plan.status is SkillDependencyResolutionStatus.INCOMPLETE
    assert (
        plan.conflicts[0].kind
        is SkillDependencyResolutionConflictKind.SEARCH_LIMIT_EXCEEDED
    )


def test_graph_policy_limit_exceeded_is_typed_incomplete_plan() -> None:
    analysis = _single_requirement_analysis(("1.0.0",))
    graph = SkillDependencyGraphSnapshot(
        (analysis.subject, analysis.candidates[0].candidate),
        (),
        (),
        True,
    )
    plan = SkillDependencyResolutionService().resolve(
        _request(
            analysis,
            _policy(limits=_limits(max_graph_nodes=1)),
            graph,
        )
    )
    assert plan.status is SkillDependencyResolutionStatus.INCOMPLETE
    assert (
        plan.conflicts[0].kind
        is SkillDependencyResolutionConflictKind.SEARCH_LIMIT_EXCEEDED
    )


def test_inconsistent_analysis_and_request_are_safe_errors() -> None:
    analysis = _single_requirement_analysis(("1.0.0",))
    other = _identity("other-subject", "1.0.0")
    with pytest.raises(InvalidSkillDependencyResolutionRequest):
        SkillDependencyResolutionService().resolve(
            replace(_request(analysis), subject=other)
        )
    corrupt = replace(
        analysis.candidates[0],
        dependency_id=SkillDependencyId(
            "dependency:" + "a" * 64
        ),
    )
    with pytest.raises(InconsistentSkillDependencyAnalysis):
        SkillDependencyResolutionService().resolve(
            _request(replace(analysis, candidates=(corrupt,)))
        )


@pytest.mark.parametrize(
    "corrupt",
    (
        lambda analysis: replace(
            analysis,
            requirements=(
                replace(analysis.requirements[0], eligible_candidates=()),
            ),
        ),
        lambda analysis: replace(
            analysis,
            has_unsatisfied_required=True,
        ),
        lambda analysis: replace(
            analysis,
            status=SkillDependencyAnalysisStatus.UNSATISFIABLE,
        ),
    ),
)
def test_inconsistent_analysis_summary_and_eligibility_are_safe_errors(
    corrupt: object,
) -> None:
    analysis = _single_requirement_analysis(("1.0.0",))
    corrupted = corrupt(analysis)  # type: ignore[operator]
    with pytest.raises(InconsistentSkillDependencyAnalysis):
        SkillDependencyResolutionService().resolve(_request(corrupted))


def test_inconsistent_shared_candidate_dimensions_are_a_safe_error() -> None:
    subject = _identity("subject-skill", "1.0.0")
    required = _dependency(
        "base-skill",
        reason=SkillDependencyReason.SHARED_SCHEMA,
    )
    optional = _dependency(
        "base-skill",
        optional=True,
    )
    candidate = _identity("base-skill", "1.0.0")
    available = {
        SkillDependencyId.from_declaration(subject, required): (candidate,),
        SkillDependencyId.from_declaration(subject, optional): (candidate,),
    }
    analysis = _analysis(subject, (required, optional), available)
    changed = replace(
        analysis.candidates[-1],
        compatibility_status=SkillCompatibilityStatus.OBSERVED_COMPATIBLE,
    )
    corrupted = replace(
        analysis,
        candidates=(*analysis.candidates[:-1], changed),
    )
    with pytest.raises(InconsistentSkillDependencyAnalysis):
        SkillDependencyResolutionService().resolve(_request(corrupted))


def test_request_plan_policy_and_nested_records_are_frozen() -> None:
    analysis = _single_requirement_analysis(("1.0.0",))
    request = _request(analysis)
    plan = SkillDependencyResolutionService().resolve(request)
    with pytest.raises(FrozenInstanceError):
        request.subject = analysis.subject  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        plan.complete = False  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        plan.resolved[0].degraded = True  # type: ignore[misc]
    assert not hasattr(plan, "plan_id")
    assert not hasattr(plan, "installation_order")
    assert not hasattr(plan, "activation_order")


def test_errors_are_fixed_and_do_not_leak_input() -> None:
    secret = "SECRET-RESOLUTION-DATA"
    error = InconsistentSkillDependencyAnalysis(secret)
    assert str(error) == "skill dependency analysis is inconsistent"
    assert secret not in str(error)
    assert secret not in repr(error)


def test_resolution_surface_has_no_runtime_progression_or_writes() -> None:
    forbidden = {
        "install",
        "activate",
        "execute",
        "save",
        "append",
        "publish",
        "download",
        "clone",
    }
    assert forbidden.isdisjoint(dir(SkillDependencyResolutionService))
    source = "\n".join(
        path.read_text(encoding="utf-8").lower()
        for path in Path("backend/synapse/skills").glob("phase9_*.py")
    )
    for term in (
        "subprocess",
        "importlib",
        "private_evals",
        "project_governance",
        "intelligence_boundary",
        "synapse.sandbox",
        "datetime.now",
        "uuid",
    ):
        assert term not in source


def test_public_surface_exports_contracts_but_not_resolution_internals() -> None:
    import synapse.skills as skills

    assert {
        "SkillDependencyResolutionPolicy",
        "ResolveSkillDependenciesRequest",
        "SkillResolvedDependency",
        "SkillDependencyRequirementResolution",
        "SkillDependencyResolutionConflict",
        "SkillDependencySelectionRationale",
        "SkillDependencyResolutionPlan",
        "SkillDependencyResolutionService",
        "SkillDependencyResolutionError",
    }.issubset(skills.__all__)
    assert {
        "DependencyConstraintIntersection",
        "intersect_dependency_declarations",
        "RequirementSelectionView",
        "ordered_candidates",
        "candidate_decision",
        "resolve_dependency_group",
    }.isdisjoint(skills.__all__)
