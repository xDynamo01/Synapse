from __future__ import annotations

from dataclasses import dataclass

from synapse.skills.phase2_models import SkillId
from synapse.skills.phase8_models import (
    SkillDependencyCardinality,
    SkillDependencyLifecycleStatus,
    SkillDependencyRequirementFact,
    SkillDependencyRequirementStatus,
)
from synapse.skills.phase9_constraints import (
    intersect_dependency_declarations,
)
from synapse.skills.phase9_models import (
    SkillDependencyCandidateRejectionReason,
    SkillDependencyRequirementResolution,
    SkillDependencyRequirementResolutionStatus,
    SkillDependencyResolutionConflict,
    SkillDependencyResolutionConflictKind,
    SkillDependencyResolutionDiagnostic,
    SkillDependencyResolutionDiagnosticCode,
    SkillDependencyResolutionDiagnosticSeverity,
    SkillResolvedDependency,
)
from synapse.skills.phase9_policy import (
    SkillDependencyCompletenessPolicy,
    SkillDependencyResolutionPolicy,
    SkillDependencyVersionMode,
    SkillOptionalDependencyPolicy,
)
from synapse.skills.phase9_selection import (
    RequirementSelectionView,
    candidate_fact_for,
    ordered_candidates,
    required_lifecycle,
    selection_rationale,
)


@dataclass(frozen=True)
class SkillDependencyGroupResolution:
    requirements: tuple[SkillDependencyRequirementResolution, ...]
    resolved: tuple[SkillResolvedDependency, ...]
    conflicts: tuple[SkillDependencyResolutionConflict, ...]
    diagnostics: tuple[SkillDependencyResolutionDiagnostic, ...]


def resolve_dependency_group(
    target: SkillId,
    views: tuple[RequirementSelectionView, ...],
    policy: SkillDependencyResolutionPolicy,
) -> SkillDependencyGroupResolution:
    outcomes: list[SkillDependencyRequirementResolution] = []
    resolved: list[SkillResolvedDependency] = []
    conflicts: list[SkillDependencyResolutionConflict] = []
    diagnostics: list[SkillDependencyResolutionDiagnostic] = []
    if policy.version_mode is SkillDependencyVersionMode.SINGLE_VERSION:
        _resolve_single(
            target,
            views,
            policy,
            outcomes,
            resolved,
            conflicts,
            diagnostics,
        )
    else:
        _resolve_multi(
            target,
            views,
            policy,
            outcomes,
            resolved,
            conflicts,
            diagnostics,
        )
    return SkillDependencyGroupResolution(
        tuple(outcomes),
        tuple(resolved),
        tuple(conflicts),
        tuple(diagnostics),
    )


def _resolve_single(
    target: SkillId,
    views: tuple[RequirementSelectionView, ...],
    policy: SkillDependencyResolutionPolicy,
    outcomes: list[SkillDependencyRequirementResolution],
    resolved: list[SkillResolvedDependency],
    conflicts: list[SkillDependencyResolutionConflict],
    diagnostics: list[SkillDependencyResolutionDiagnostic],
) -> None:
    incomplete_optional = tuple(
        view
        for view in views
        if view.fact.cardinality is SkillDependencyCardinality.OPTIONAL
        and view.fact.status is SkillDependencyRequirementStatus.INCOMPLETE
    )
    for view in incomplete_optional:
        _record_optional_incomplete(view.fact, outcomes, diagnostics)
    views = tuple(view for view in views if view not in incomplete_optional)
    if not views:
        return
    required = tuple(
        view
        for view in views
        if view.fact.cardinality is SkillDependencyCardinality.REQUIRED
    )
    optional = tuple(view for view in views if view not in required)
    if _requirements_incomplete(views, policy):
        _record_incomplete_group(
            target, views, outcomes, conflicts, diagnostics
        )
        return
    if required and intersect_dependency_declarations(
        tuple(view.fact.declaration for view in required)
    ) is None:
        ids = tuple(view.fact.dependency_id for view in required)
        conflicts.append(
            SkillDependencyResolutionConflict(
                SkillDependencyResolutionConflictKind.CONSTRAINT_INTERSECTION,
                ids,
                target,
                True,
            )
        )
        diagnostics.append(
            SkillDependencyResolutionDiagnostic(
                SkillDependencyResolutionDiagnosticCode.CONSTRAINT_CONFLICT,
                SkillDependencyResolutionDiagnosticSeverity.BLOCKING,
                target_skill_id=target,
            )
        )
        _record_group_failure(views, outcomes, diagnostics)
        return
    if (
        policy.optional_dependencies is SkillOptionalDependencyPolicy.OMIT
        and not required
    ):
        for view in optional:
            _omit_policy(view.fact, outcomes, diagnostics)
        return

    selectable_by_requirement = {
        view.fact.dependency_id: {
            decision.candidate
            for decision in view.decisions
            if decision.selectable
        }
        for view in views
    }
    all_candidates = {
        decision.candidate for view in views for decision in view.decisions
    }
    required_ids = {view.fact.dependency_id for view in required}
    optional_ids = {
        view.fact.dependency_id
        for view in optional
        if policy.optional_dependencies
        is SkillOptionalDependencyPolicy.RESOLVE_WHEN_POSSIBLE
    }
    coverage = {
        candidate: {
            dependency_id
            for dependency_id, selectable in selectable_by_requirement.items()
            if candidate in selectable
        }
        for candidate in all_candidates
    }
    possible = tuple(
        candidate
        for candidate in all_candidates
        if required_ids.issubset(coverage[candidate])
        and (required_ids or coverage[candidate] & optional_ids)
    )
    if not possible:
        if required:
            conflicts.append(
                SkillDependencyResolutionConflict(
                    _group_failure_kind(views),
                    tuple(view.fact.dependency_id for view in views),
                    target,
                    True,
                )
            )
        _record_group_failure(views, outcomes, diagnostics)
        return
    selected = ordered_candidates(
        possible, coverage, required_ids, optional_ids, views, policy
    )[0]
    resolved_ids = tuple(
        sorted(
            (
                dependency_id
                for dependency_id in coverage[selected]
                if dependency_id in required_ids or dependency_id in optional_ids
            ),
            key=str,
        )
    )
    for view in views:
        if view.fact.dependency_id in resolved_ids:
            outcomes.append(
                SkillDependencyRequirementResolution(
                    view.fact.dependency_id,
                    SkillDependencyRequirementResolutionStatus.RESOLVED,
                    selected,
                )
            )
        elif (
            view.fact.cardinality is SkillDependencyCardinality.OPTIONAL
            and policy.optional_dependencies is SkillOptionalDependencyPolicy.OMIT
        ):
            _omit_policy(view.fact, outcomes, diagnostics)
        elif view.fact.cardinality is SkillDependencyCardinality.OPTIONAL:
            _omit_conflict(view.fact, outcomes, diagnostics)
        else:
            outcomes.append(
                SkillDependencyRequirementResolution(
                    view.fact.dependency_id,
                    SkillDependencyRequirementResolutionStatus.UNRESOLVED_REQUIRED,
                )
            )
    selected_fact = candidate_fact_for(selected, resolved_ids, views)
    degraded = selected_fact.lifecycle_status in {
        SkillDependencyLifecycleStatus.DEPRECATED,
        SkillDependencyLifecycleStatus.SUPERSEDED,
    }
    if degraded:
        diagnostics.append(
            SkillDependencyResolutionDiagnostic(
                SkillDependencyResolutionDiagnosticCode.DEGRADED_SELECTION,
                SkillDependencyResolutionDiagnosticSeverity.WARNING,
                target_skill_id=target,
            )
        )
    resolved.append(
        SkillResolvedDependency(
            target,
            resolved_ids,
            selected,
            policy.version,
            required_lifecycle(selected_fact),
            selected_fact.compatibility_status,
            degraded,
            selection_rationale(
                views,
                policy,
                possible,
                coverage,
                required_ids,
                optional_ids,
            ),
        )
    )


def _resolve_multi(
    target: SkillId,
    views: tuple[RequirementSelectionView, ...],
    policy: SkillDependencyResolutionPolicy,
    outcomes: list[SkillDependencyRequirementResolution],
    resolved: list[SkillResolvedDependency],
    conflicts: list[SkillDependencyResolutionConflict],
    diagnostics: list[SkillDependencyResolutionDiagnostic],
) -> None:
    for view in views:
        fact = view.fact
        if (
            fact.cardinality is SkillDependencyCardinality.OPTIONAL
            and fact.status is SkillDependencyRequirementStatus.INCOMPLETE
        ):
            _record_optional_incomplete(fact, outcomes, diagnostics)
            continue
        if (
            fact.cardinality is SkillDependencyCardinality.OPTIONAL
            and policy.optional_dependencies is SkillOptionalDependencyPolicy.OMIT
        ):
            _omit_policy(fact, outcomes, diagnostics)
            continue
        if _requirements_incomplete((view,), policy):
            _record_incomplete_group(
                target, (view,), outcomes, conflicts, diagnostics
            )
            continue
        selectable = tuple(
            decision.candidate
            for decision in view.decisions
            if decision.selectable
        )
        if not selectable:
            if fact.cardinality is SkillDependencyCardinality.REQUIRED:
                conflicts.append(
                    SkillDependencyResolutionConflict(
                        _group_failure_kind((view,)),
                        (fact.dependency_id,),
                        target,
                        True,
                    )
                )
                outcomes.append(
                    SkillDependencyRequirementResolution(
                        fact.dependency_id,
                        SkillDependencyRequirementResolutionStatus.UNRESOLVED_REQUIRED,
                    )
                )
                diagnostics.append(
                    SkillDependencyResolutionDiagnostic(
                        SkillDependencyResolutionDiagnosticCode.REQUIRED_UNRESOLVED,
                        SkillDependencyResolutionDiagnosticSeverity.BLOCKING,
                        fact.dependency_id,
                        target,
                    )
                )
            else:
                _omit_no_candidate(fact, outcomes, diagnostics)
            continue
        coverage = {candidate: {fact.dependency_id} for candidate in selectable}
        required_ids = (
            {fact.dependency_id}
            if fact.cardinality is SkillDependencyCardinality.REQUIRED
            else set()
        )
        optional_ids = (
            {fact.dependency_id}
            if fact.cardinality is SkillDependencyCardinality.OPTIONAL
            else set()
        )
        selected = ordered_candidates(
            selectable,
            coverage,
            required_ids,
            optional_ids,
            (view,),
            policy,
        )[0]
        selected_fact = candidate_fact_for(
            selected, (fact.dependency_id,), (view,)
        )
        degraded = selected_fact.lifecycle_status in {
            SkillDependencyLifecycleStatus.DEPRECATED,
            SkillDependencyLifecycleStatus.SUPERSEDED,
        }
        if degraded:
            diagnostics.append(
                SkillDependencyResolutionDiagnostic(
                    SkillDependencyResolutionDiagnosticCode.DEGRADED_SELECTION,
                    SkillDependencyResolutionDiagnosticSeverity.WARNING,
                    fact.dependency_id,
                    target,
                )
            )
        outcomes.append(
            SkillDependencyRequirementResolution(
                fact.dependency_id,
                SkillDependencyRequirementResolutionStatus.RESOLVED,
                selected,
            )
        )
        resolved.append(
            SkillResolvedDependency(
                target,
                (fact.dependency_id,),
                selected,
                policy.version,
                required_lifecycle(selected_fact),
                selected_fact.compatibility_status,
                degraded,
                selection_rationale(
                    (view,),
                    policy,
                    selectable,
                    coverage,
                    required_ids,
                    optional_ids,
                ),
            )
        )


def _requirements_incomplete(
    views: tuple[RequirementSelectionView, ...],
    policy: SkillDependencyResolutionPolicy,
) -> bool:
    incomplete = tuple(
        view
        for view in views
        if view.fact.status is SkillDependencyRequirementStatus.INCOMPLETE
    )
    if not incomplete:
        return False
    if (
        policy.completeness
        is SkillDependencyCompletenessPolicy.REQUIRE_COMPLETE_ANALYSIS
    ):
        return True
    return any(
        view.fact.cardinality is SkillDependencyCardinality.REQUIRED
        for view in incomplete
    )


def _group_failure_kind(
    views: tuple[RequirementSelectionView, ...],
) -> SkillDependencyResolutionConflictKind:
    reasons = {
        reason
        for view in views
        for decision in view.decisions
        for reason in decision.rejection_reasons
    }
    if reasons & {
        SkillDependencyCandidateRejectionReason.DECLARED_INCOMPATIBLE,
        SkillDependencyCandidateRejectionReason.OBSERVED_INCOMPATIBLE,
        SkillDependencyCandidateRejectionReason.CONFLICTING_COMPATIBILITY,
        SkillDependencyCandidateRejectionReason.UNKNOWN_COMPATIBILITY,
        SkillDependencyCandidateRejectionReason.DECLARED_COMPATIBILITY_INSUFFICIENT,
    }:
        return SkillDependencyResolutionConflictKind.COMPATIBILITY
    if reasons & {
        SkillDependencyCandidateRejectionReason.REVOKED,
        SkillDependencyCandidateRejectionReason.DEPRECATED_DENIED,
        SkillDependencyCandidateRejectionReason.SUPERSEDED_DENIED,
        SkillDependencyCandidateRejectionReason.LIFECYCLE_INCOMPLETE,
    }:
        return SkillDependencyResolutionConflictKind.LIFECYCLE_ELIGIBILITY
    if len(views) > 1:
        return SkillDependencyResolutionConflictKind.SINGLE_VERSION
    return SkillDependencyResolutionConflictKind.NO_SELECTABLE_CANDIDATE


def _record_incomplete_group(
    target: SkillId,
    views: tuple[RequirementSelectionView, ...],
    outcomes: list[SkillDependencyRequirementResolution],
    conflicts: list[SkillDependencyResolutionConflict],
    diagnostics: list[SkillDependencyResolutionDiagnostic],
) -> None:
    required_ids = tuple(
        view.fact.dependency_id
        for view in views
        if view.fact.cardinality is SkillDependencyCardinality.REQUIRED
    )
    if required_ids:
        conflicts.append(
            SkillDependencyResolutionConflict(
                SkillDependencyResolutionConflictKind.INCOMPLETE_FACTS,
                required_ids,
                target,
                True,
            )
        )
    for view in views:
        status = (
            SkillDependencyRequirementResolutionStatus.UNRESOLVED_INCOMPLETE
        )
        outcomes.append(
            SkillDependencyRequirementResolution(view.fact.dependency_id, status)
        )
        diagnostics.append(
            SkillDependencyResolutionDiagnostic(
                SkillDependencyResolutionDiagnosticCode.INCOMPLETE_REQUIREMENT,
                SkillDependencyResolutionDiagnosticSeverity.INCOMPLETE,
                view.fact.dependency_id,
                target,
            )
        )


def _record_group_failure(
    views: tuple[RequirementSelectionView, ...],
    outcomes: list[SkillDependencyRequirementResolution],
    diagnostics: list[SkillDependencyResolutionDiagnostic],
) -> None:
    for view in views:
        if view.fact.cardinality is SkillDependencyCardinality.REQUIRED:
            outcomes.append(
                SkillDependencyRequirementResolution(
                    view.fact.dependency_id,
                    SkillDependencyRequirementResolutionStatus.UNRESOLVED_REQUIRED,
                )
            )
            diagnostics.append(
                SkillDependencyResolutionDiagnostic(
                    SkillDependencyResolutionDiagnosticCode.REQUIRED_UNRESOLVED,
                    SkillDependencyResolutionDiagnosticSeverity.BLOCKING,
                    view.fact.dependency_id,
                    view.fact.declaration.skill_id,
                )
            )
        elif view.fact.matching_candidates:
            _omit_conflict(view.fact, outcomes, diagnostics)
        else:
            _omit_no_candidate(view.fact, outcomes, diagnostics)


def _omit_no_candidate(
    fact: SkillDependencyRequirementFact,
    outcomes: list[SkillDependencyRequirementResolution],
    diagnostics: list[SkillDependencyResolutionDiagnostic],
) -> None:
    outcomes.append(
        SkillDependencyRequirementResolution(
            fact.dependency_id,
            SkillDependencyRequirementResolutionStatus.OMITTED_NO_CANDIDATE,
        )
    )
    diagnostics.append(
        SkillDependencyResolutionDiagnostic(
            SkillDependencyResolutionDiagnosticCode.OPTIONAL_OMITTED_NO_CANDIDATE,
            SkillDependencyResolutionDiagnosticSeverity.WARNING,
            fact.dependency_id,
            fact.declaration.skill_id,
        )
    )


def _omit_conflict(
    fact: SkillDependencyRequirementFact,
    outcomes: list[SkillDependencyRequirementResolution],
    diagnostics: list[SkillDependencyResolutionDiagnostic],
) -> None:
    outcomes.append(
        SkillDependencyRequirementResolution(
            fact.dependency_id,
            SkillDependencyRequirementResolutionStatus.OMITTED_CONFLICT,
        )
    )
    diagnostics.append(
        SkillDependencyResolutionDiagnostic(
            SkillDependencyResolutionDiagnosticCode.OPTIONAL_OMITTED_CONFLICT,
            SkillDependencyResolutionDiagnosticSeverity.WARNING,
            fact.dependency_id,
            fact.declaration.skill_id,
        )
    )


def _omit_policy(
    fact: SkillDependencyRequirementFact,
    outcomes: list[SkillDependencyRequirementResolution],
    diagnostics: list[SkillDependencyResolutionDiagnostic],
) -> None:
    outcomes.append(
        SkillDependencyRequirementResolution(
            fact.dependency_id,
            SkillDependencyRequirementResolutionStatus.OMITTED_POLICY,
        )
    )
    diagnostics.append(
        SkillDependencyResolutionDiagnostic(
            SkillDependencyResolutionDiagnosticCode.OPTIONAL_OMITTED_POLICY,
            SkillDependencyResolutionDiagnosticSeverity.WARNING,
            fact.dependency_id,
            fact.declaration.skill_id,
        )
    )


def _record_optional_incomplete(
    fact: SkillDependencyRequirementFact,
    outcomes: list[SkillDependencyRequirementResolution],
    diagnostics: list[SkillDependencyResolutionDiagnostic],
) -> None:
    outcomes.append(
        SkillDependencyRequirementResolution(
            fact.dependency_id,
            SkillDependencyRequirementResolutionStatus.UNRESOLVED_INCOMPLETE,
        )
    )
    diagnostics.append(
        SkillDependencyResolutionDiagnostic(
            SkillDependencyResolutionDiagnosticCode.INCOMPLETE_REQUIREMENT,
            SkillDependencyResolutionDiagnosticSeverity.INCOMPLETE,
            fact.dependency_id,
            fact.declaration.skill_id,
        )
    )
