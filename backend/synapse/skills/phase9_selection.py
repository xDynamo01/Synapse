from __future__ import annotations

from dataclasses import dataclass

from synapse.skills.phase2_models import PublishedSkillVersionId
from synapse.skills.phase8_models import (
    SkillCompatibilityStatus,
    SkillDependencyCandidateFact,
    SkillDependencyConstraintStatus,
    SkillDependencyId,
    SkillDependencyLifecycleStatus,
    SkillDependencyRequirementFact,
)
from synapse.skills.phase9_errors import InconsistentSkillDependencyAnalysis
from synapse.skills.phase9_models import (
    SkillDependencyCandidateDecision,
    SkillDependencyCandidateRejectionReason,
    SkillDependencySelectionCriterion,
    SkillDependencySelectionRationale,
    SkillDependencyTieBreak,
)
from synapse.skills.phase9_policy import (
    SkillDependencyCompatibilityPolicy,
    SkillDependencyDegradedLifecyclePolicy,
    SkillDependencyResolutionPolicy,
    SkillDependencyVersionPreference,
)


@dataclass(frozen=True)
class RequirementSelectionView:
    fact: SkillDependencyRequirementFact
    candidates: tuple[SkillDependencyCandidateFact, ...]
    decisions: tuple[SkillDependencyCandidateDecision, ...]


def requirement_selection_view(
    fact: SkillDependencyRequirementFact,
    candidates: tuple[SkillDependencyCandidateFact, ...],
    policy: SkillDependencyResolutionPolicy,
) -> RequirementSelectionView:
    return RequirementSelectionView(
        fact,
        candidates,
        tuple(candidate_decision(candidate, policy) for candidate in candidates),
    )


def candidate_decision(
    candidate: SkillDependencyCandidateFact,
    policy: SkillDependencyResolutionPolicy,
) -> SkillDependencyCandidateDecision:
    reasons: set[SkillDependencyCandidateRejectionReason] = set()
    if candidate.constraint_status is SkillDependencyConstraintStatus.MISMATCH:
        reasons.add(SkillDependencyCandidateRejectionReason.CONSTRAINT_MISMATCH)
    if candidate.candidate.version.prerelease and not policy.allow_exact_prerelease:
        reasons.add(SkillDependencyCandidateRejectionReason.PRERELEASE_DENIED)
    lifecycle = candidate.lifecycle_status
    if lifecycle is SkillDependencyLifecycleStatus.REVOKED:
        reasons.add(SkillDependencyCandidateRejectionReason.REVOKED)
    elif lifecycle is SkillDependencyLifecycleStatus.DEPRECATED:
        if policy.degraded_lifecycle not in {
            SkillDependencyDegradedLifecyclePolicy.ALLOW_DEPRECATED,
            SkillDependencyDegradedLifecyclePolicy.ALLOW_DEPRECATED_AND_SUPERSEDED,
        }:
            reasons.add(
                SkillDependencyCandidateRejectionReason.DEPRECATED_DENIED
            )
    elif lifecycle is SkillDependencyLifecycleStatus.SUPERSEDED:
        if (
            policy.degraded_lifecycle
            is not SkillDependencyDegradedLifecyclePolicy.ALLOW_DEPRECATED_AND_SUPERSEDED
        ):
            reasons.add(
                SkillDependencyCandidateRejectionReason.SUPERSEDED_DENIED
            )
    elif lifecycle is not SkillDependencyLifecycleStatus.ELIGIBLE:
        reasons.add(
            SkillDependencyCandidateRejectionReason.LIFECYCLE_INCOMPLETE
        )

    compatibility = candidate.compatibility_status
    if compatibility is SkillCompatibilityStatus.DECLARED_INCOMPATIBLE:
        reasons.add(
            SkillDependencyCandidateRejectionReason.DECLARED_INCOMPATIBLE
        )
    elif compatibility is SkillCompatibilityStatus.OBSERVED_INCOMPATIBLE:
        reasons.add(
            SkillDependencyCandidateRejectionReason.OBSERVED_INCOMPATIBLE
        )
    elif compatibility is SkillCompatibilityStatus.CONFLICTING_INFORMATION:
        reasons.add(
            SkillDependencyCandidateRejectionReason.CONFLICTING_COMPATIBILITY
        )
    elif compatibility is SkillCompatibilityStatus.UNKNOWN:
        if (
            policy.compatibility
            is not SkillDependencyCompatibilityPolicy.ALLOW_UNKNOWN
        ):
            reasons.add(
                SkillDependencyCandidateRejectionReason.UNKNOWN_COMPATIBILITY
            )
    elif (
        compatibility is SkillCompatibilityStatus.DECLARED_COMPATIBLE
        and policy.compatibility
        is SkillDependencyCompatibilityPolicy.OBSERVED_ONLY
    ):
        reasons.add(
            SkillDependencyCandidateRejectionReason.DECLARED_COMPATIBILITY_INSUFFICIENT
        )
    ordered = tuple(sorted(reasons, key=lambda item: item.value))
    return SkillDependencyCandidateDecision(
        candidate.dependency_id,
        candidate.candidate,
        not ordered,
        ordered,
    )


def ordered_candidates(
    candidates: tuple[PublishedSkillVersionId, ...],
    coverage: dict[PublishedSkillVersionId, set[SkillDependencyId]],
    required_ids: set[SkillDependencyId],
    optional_ids: set[SkillDependencyId],
    views: tuple[RequirementSelectionView, ...],
    policy: SkillDependencyResolutionPolicy,
) -> tuple[PublishedSkillVersionId, ...]:
    lifecycle = {
        candidate.candidate: candidate.lifecycle_status
        for view in views
        for candidate in view.candidates
    }
    ordered = sorted(candidates, key=lambda item: item.to_canonical_text())
    ordered.sort(key=lambda item: str(item.version))
    ordered.sort(
        key=lambda item: item.version.precedence_key(),
        reverse=(
            policy.version_preference
            is SkillDependencyVersionPreference.HIGHER_SEMVER
        ),
    )
    ordered.sort(
        key=lambda item: lifecycle.get(item)
        is SkillDependencyLifecycleStatus.ELIGIBLE,
        reverse=True,
    )
    ordered.sort(
        key=lambda item: len(coverage[item] & optional_ids),
        reverse=True,
    )
    ordered.sort(
        key=lambda item: len(coverage[item] & required_ids),
        reverse=True,
    )
    return tuple(ordered)


def selection_rationale(
    views: tuple[RequirementSelectionView, ...],
    policy: SkillDependencyResolutionPolicy,
    possible: tuple[PublishedSkillVersionId, ...],
    coverage: dict[PublishedSkillVersionId, set[SkillDependencyId]],
    required_ids: set[SkillDependencyId],
    optional_ids: set[SkillDependencyId],
) -> SkillDependencySelectionRationale:
    considered = tuple(
        sorted(
            (decision for view in views for decision in view.decisions),
            key=lambda item: (
                str(item.dependency_id),
                item.candidate.to_canonical_text(),
            ),
        )
    )
    criteria = (
        SkillDependencySelectionCriterion.REQUIRED_COVERAGE,
        SkillDependencySelectionCriterion.OPTIONAL_COVERAGE,
        SkillDependencySelectionCriterion.REGULAR_LIFECYCLE,
        (
            SkillDependencySelectionCriterion.HIGHER_SEMVER
            if policy.version_preference
            is SkillDependencyVersionPreference.HIGHER_SEMVER
            else SkillDependencySelectionCriterion.LOWER_SEMVER
        ),
        SkillDependencySelectionCriterion.CONCRETE_VERSION_TEXT,
        SkillDependencySelectionCriterion.EXACT_IDENTITY,
    )
    ordered = ordered_candidates(
        possible, coverage, required_ids, optional_ids, views, policy
    )
    lifecycle = {
        candidate.candidate: candidate.lifecycle_status
        for view in views
        for candidate in view.candidates
    }
    tie_break = SkillDependencyTieBreak.NONE
    if len(ordered) > 1:
        winner, runner_up = ordered[:2]
        primary_tied = (
            len(coverage[winner] & required_ids)
            == len(coverage[runner_up] & required_ids)
            and len(coverage[winner] & optional_ids)
            == len(coverage[runner_up] & optional_ids)
            and (
                lifecycle.get(winner)
                is SkillDependencyLifecycleStatus.ELIGIBLE
            )
            == (
                lifecycle.get(runner_up)
                is SkillDependencyLifecycleStatus.ELIGIBLE
            )
        )
        if primary_tied and not winner.version.has_same_precedence(
            runner_up.version
        ):
            tie_break = SkillDependencyTieBreak.SEMVER_PRECEDENCE
        elif primary_tied and str(winner.version) != str(runner_up.version):
            tie_break = SkillDependencyTieBreak.CONCRETE_VERSION_TEXT
        elif primary_tied:
            tie_break = SkillDependencyTieBreak.EXACT_IDENTITY
    return SkillDependencySelectionRationale(criteria, considered, tie_break)


def candidate_fact_for(
    selected: PublishedSkillVersionId,
    dependency_ids: tuple[SkillDependencyId, ...],
    views: tuple[RequirementSelectionView, ...],
) -> SkillDependencyCandidateFact:
    facts = tuple(
        candidate
        for view in views
        if view.fact.dependency_id in dependency_ids
        for candidate in view.candidates
        if candidate.candidate == selected
    )
    if not facts:
        raise InconsistentSkillDependencyAnalysis()
    first = facts[0]
    if any(
        candidate.lifecycle_status != first.lifecycle_status
        or candidate.compatibility_status != first.compatibility_status
        for candidate in facts[1:]
    ):
        raise InconsistentSkillDependencyAnalysis()
    return first


def required_lifecycle(
    candidate: SkillDependencyCandidateFact,
) -> SkillDependencyLifecycleStatus:
    if candidate.lifecycle_status is None:
        raise InconsistentSkillDependencyAnalysis()
    return candidate.lifecycle_status
