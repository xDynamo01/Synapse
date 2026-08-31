from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from synapse.skills.phase2_models import (
    PublishedSkillVersionId,
    SkillId,
    SkillSemanticReference,
)
from synapse.skills.phase8_models import (
    SkillCompatibilityStatus,
    SkillDependencyAnalysis,
    SkillDependencyCycleFact,
    SkillDependencyGraphSnapshot,
    SkillDependencyId,
    SkillDependencyLifecycleStatus,
)
from synapse.skills.phase9_errors import (
    InvalidSkillDependencyResolutionRequest,
    SkillDependencyResolutionInvariantError,
)
from synapse.skills.phase9_policy import (
    SkillDependencyResolutionPolicy,
    SkillDependencyResolutionPolicyVersion,
)


class SkillDependencyResolutionStatus(StrEnum):
    RESOLVED = "resolved"
    PARTIALLY_RESOLVED = "partially_resolved"
    UNRESOLVABLE = "unresolvable"
    INCOMPLETE = "incomplete"
    CONFLICTING = "conflicting"


class SkillDependencyRequirementResolutionStatus(StrEnum):
    RESOLVED = "resolved"
    OMITTED_NO_CANDIDATE = "omitted_no_candidate"
    OMITTED_CONFLICT = "omitted_conflict"
    OMITTED_POLICY = "omitted_policy"
    UNRESOLVED_INCOMPLETE = "unresolved_incomplete"
    UNRESOLVED_REQUIRED = "unresolved_required"


class SkillDependencyResolutionConflictKind(StrEnum):
    CONSTRAINT_INTERSECTION = "constraint_intersection"
    LIFECYCLE_ELIGIBILITY = "lifecycle_eligibility"
    COMPATIBILITY = "compatibility"
    SINGLE_VERSION = "single_version"
    GRAPH_CYCLE = "graph_cycle"
    INCOMPLETE_FACTS = "incomplete_facts"
    SEARCH_LIMIT_EXCEEDED = "search_limit_exceeded"
    NO_SELECTABLE_CANDIDATE = "no_selectable_candidate"


class SkillDependencyCandidateRejectionReason(StrEnum):
    CONSTRAINT_MISMATCH = "constraint_mismatch"
    PRERELEASE_DENIED = "prerelease_denied"
    REVOKED = "revoked"
    DEPRECATED_DENIED = "deprecated_denied"
    SUPERSEDED_DENIED = "superseded_denied"
    LIFECYCLE_INCOMPLETE = "lifecycle_incomplete"
    DECLARED_INCOMPATIBLE = "declared_incompatible"
    OBSERVED_INCOMPATIBLE = "observed_incompatible"
    CONFLICTING_COMPATIBILITY = "conflicting_compatibility"
    UNKNOWN_COMPATIBILITY = "unknown_compatibility"
    DECLARED_COMPATIBILITY_INSUFFICIENT = "declared_compatibility_insufficient"
class SkillDependencySelectionCriterion(StrEnum):
    REQUIRED_COVERAGE = "required_coverage"
    OPTIONAL_COVERAGE = "optional_coverage"
    REGULAR_LIFECYCLE = "regular_lifecycle"
    HIGHER_SEMVER = "higher_semver"
    LOWER_SEMVER = "lower_semver"
    CONCRETE_VERSION_TEXT = "concrete_version_text"
    EXACT_IDENTITY = "exact_identity"


class SkillDependencyTieBreak(StrEnum):
    NONE = "none"
    SEMVER_PRECEDENCE = "semver_precedence"
    CONCRETE_VERSION_TEXT = "concrete_version_text"
    EXACT_IDENTITY = "exact_identity"


class SkillDependencyResolutionDiagnosticCode(StrEnum):
    REQUIRED_UNRESOLVED = "required_unresolved"
    OPTIONAL_OMITTED_NO_CANDIDATE = "optional_omitted_no_candidate"
    OPTIONAL_OMITTED_CONFLICT = "optional_omitted_conflict"
    OPTIONAL_OMITTED_POLICY = "optional_omitted_policy"
    INCOMPLETE_REQUIREMENT = "incomplete_requirement"
    DEGRADED_SELECTION = "degraded_selection"
    CONSTRAINT_CONFLICT = "constraint_conflict"
    GRAPH_CYCLE = "graph_cycle"
    SEARCH_LIMIT_EXCEEDED = "search_limit_exceeded"


class SkillDependencyResolutionDiagnosticSeverity(StrEnum):
    BLOCKING = "blocking"
    WARNING = "warning"
    INCOMPLETE = "incomplete"


@dataclass(frozen=True)
class SkillDependencyCandidateDecision:
    dependency_id: SkillDependencyId
    candidate: PublishedSkillVersionId
    selectable: bool
    rejection_reasons: tuple[SkillDependencyCandidateRejectionReason, ...]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.dependency_id, SkillDependencyId)
            or not isinstance(self.candidate, PublishedSkillVersionId)
            or not isinstance(self.selectable, bool)
            or not _tuple_of(
                self.rejection_reasons,
                SkillDependencyCandidateRejectionReason,
            )
            or self.selectable == bool(self.rejection_reasons)
        ):
            raise SkillDependencyResolutionInvariantError()


@dataclass(frozen=True)
class SkillDependencySelectionRationale:
    criteria: tuple[SkillDependencySelectionCriterion, ...]
    considered: tuple[SkillDependencyCandidateDecision, ...]
    tie_break: SkillDependencyTieBreak

    def __post_init__(self) -> None:
        if (
            not _tuple_of(self.criteria, SkillDependencySelectionCriterion)
            or not self.criteria
            or not _tuple_of(self.considered, SkillDependencyCandidateDecision)
            or not isinstance(self.tie_break, SkillDependencyTieBreak)
        ):
            raise SkillDependencyResolutionInvariantError()


@dataclass(frozen=True)
class SkillResolvedDependency:
    target_skill_id: SkillId
    requirement_ids: tuple[SkillDependencyId, ...]
    selected: PublishedSkillVersionId
    policy_version: SkillDependencyResolutionPolicyVersion
    lifecycle_status: SkillDependencyLifecycleStatus
    compatibility_status: SkillCompatibilityStatus
    degraded: bool
    rationale: SkillDependencySelectionRationale

    def __post_init__(self) -> None:
        if (
            not isinstance(self.target_skill_id, SkillId)
            or not _tuple_of(self.requirement_ids, SkillDependencyId)
            or not self.requirement_ids
            or not isinstance(self.selected, PublishedSkillVersionId)
            or self.selected.skill_id != self.target_skill_id
            or not isinstance(
                self.policy_version, SkillDependencyResolutionPolicyVersion
            )
            or not isinstance(
                self.lifecycle_status, SkillDependencyLifecycleStatus
            )
            or not isinstance(self.compatibility_status, SkillCompatibilityStatus)
            or not isinstance(self.degraded, bool)
            or not isinstance(self.rationale, SkillDependencySelectionRationale)
        ):
            raise SkillDependencyResolutionInvariantError()


@dataclass(frozen=True)
class SkillDependencyRequirementResolution:
    dependency_id: SkillDependencyId
    status: SkillDependencyRequirementResolutionStatus
    selected: PublishedSkillVersionId | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.dependency_id, SkillDependencyId)
            or not isinstance(
                self.status, SkillDependencyRequirementResolutionStatus
            )
            or (
                self.selected is not None
                and not isinstance(self.selected, PublishedSkillVersionId)
            )
            or (
                (self.status is SkillDependencyRequirementResolutionStatus.RESOLVED)
                != (self.selected is not None)
            )
        ):
            raise SkillDependencyResolutionInvariantError()


@dataclass(frozen=True)
class SkillDependencyResolutionConflict:
    kind: SkillDependencyResolutionConflictKind
    requirement_ids: tuple[SkillDependencyId, ...]
    target_skill_id: SkillId | None
    blocking: bool

    def __post_init__(self) -> None:
        if (
            not isinstance(self.kind, SkillDependencyResolutionConflictKind)
            or not _tuple_of(self.requirement_ids, SkillDependencyId)
            or (
                self.target_skill_id is not None
                and not isinstance(self.target_skill_id, SkillId)
            )
            or not isinstance(self.blocking, bool)
        ):
            raise SkillDependencyResolutionInvariantError()


@dataclass(frozen=True)
class SkillDependencyResolutionDiagnostic:
    code: SkillDependencyResolutionDiagnosticCode
    severity: SkillDependencyResolutionDiagnosticSeverity
    dependency_id: SkillDependencyId | None = None
    target_skill_id: SkillId | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.code, SkillDependencyResolutionDiagnosticCode)
            or not isinstance(
                self.severity, SkillDependencyResolutionDiagnosticSeverity
            )
            or (
                self.dependency_id is not None
                and not isinstance(self.dependency_id, SkillDependencyId)
            )
            or (
                self.target_skill_id is not None
                and not isinstance(self.target_skill_id, SkillId)
            )
        ):
            raise SkillDependencyResolutionInvariantError()


@dataclass(frozen=True, kw_only=True)
class ResolveSkillDependenciesRequest:
    subject: PublishedSkillVersionId
    analysis: SkillDependencyAnalysis
    policy: SkillDependencyResolutionPolicy
    resolution_profile_ref: SkillSemanticReference
    graph: SkillDependencyGraphSnapshot | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.subject, PublishedSkillVersionId)
            or not isinstance(self.analysis, SkillDependencyAnalysis)
            or not isinstance(self.policy, SkillDependencyResolutionPolicy)
            or not isinstance(self.resolution_profile_ref, SkillSemanticReference)
            or not self.resolution_profile_ref.value.startswith(
                "resolution-profile:"
            )
            or (
                self.graph is not None
                and not isinstance(self.graph, SkillDependencyGraphSnapshot)
            )
        ):
            raise InvalidSkillDependencyResolutionRequest()


@dataclass(frozen=True)
class SkillDependencyResolutionPlan:
    subject: PublishedSkillVersionId
    resolution_profile_ref: SkillSemanticReference
    policy: SkillDependencyResolutionPolicy
    requirements: tuple[SkillDependencyRequirementResolution, ...]
    resolved: tuple[SkillResolvedDependency, ...]
    conflicts: tuple[SkillDependencyResolutionConflict, ...]
    diagnostics: tuple[SkillDependencyResolutionDiagnostic, ...]
    graph_cycles: tuple[SkillDependencyCycleFact, ...]
    status: SkillDependencyResolutionStatus
    complete: bool
    required_resolved: bool
    has_optional_omissions: bool
    has_degraded_selections: bool

    def __post_init__(self) -> None:
        if (
            not isinstance(self.subject, PublishedSkillVersionId)
            or not isinstance(self.resolution_profile_ref, SkillSemanticReference)
            or not self.resolution_profile_ref.value.startswith(
                "resolution-profile:"
            )
            or not isinstance(self.policy, SkillDependencyResolutionPolicy)
            or not _tuple_of(
                self.requirements, SkillDependencyRequirementResolution
            )
            or not _tuple_of(self.resolved, SkillResolvedDependency)
            or not _tuple_of(self.conflicts, SkillDependencyResolutionConflict)
            or not _tuple_of(
                self.diagnostics, SkillDependencyResolutionDiagnostic
            )
            or not _tuple_of(self.graph_cycles, SkillDependencyCycleFact)
            or not isinstance(self.status, SkillDependencyResolutionStatus)
            or not isinstance(self.complete, bool)
            or not isinstance(self.required_resolved, bool)
            or not isinstance(self.has_optional_omissions, bool)
            or not isinstance(self.has_degraded_selections, bool)
        ):
            raise SkillDependencyResolutionInvariantError()


def _tuple_of(value: object, expected: type[object]) -> bool:
    return isinstance(value, tuple) and all(
        isinstance(item, expected) for item in value
    )
