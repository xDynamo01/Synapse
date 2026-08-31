from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from synapse.skills.phase9_errors import InvalidSkillDependencyResolutionPolicy


@dataclass(frozen=True, order=True)
class SkillDependencyResolutionPolicyVersion:
    value: int

    def __post_init__(self) -> None:
        if isinstance(self.value, bool) or self.value != 1:
            raise InvalidSkillDependencyResolutionPolicy()

    def __str__(self) -> str:
        return str(self.value)


class SkillDependencyVersionMode(StrEnum):
    SINGLE_VERSION = "single_version"
    MULTI_VERSION = "multi_version"


class SkillDependencyVersionPreference(StrEnum):
    HIGHER_SEMVER = "higher_semver"
    LOWER_SEMVER = "lower_semver"


class SkillDependencyCompatibilityPolicy(StrEnum):
    OBSERVED_ONLY = "observed_only"
    DECLARED_OR_OBSERVED = "declared_or_observed"
    ALLOW_UNKNOWN = "allow_unknown"


class SkillDependencyDegradedLifecyclePolicy(StrEnum):
    DENY = "deny"
    ALLOW_DEPRECATED = "allow_deprecated"
    ALLOW_DEPRECATED_AND_SUPERSEDED = "allow_deprecated_and_superseded"


class SkillOptionalDependencyPolicy(StrEnum):
    RESOLVE_WHEN_POSSIBLE = "resolve_when_possible"
    OMIT = "omit"


class SkillDependencyCompletenessPolicy(StrEnum):
    REQUIRE_COMPLETE_ANALYSIS = "require_complete_analysis"
    ALLOW_OPTIONAL_INCOMPLETE = "allow_optional_incomplete"


@dataclass(frozen=True)
class SkillDependencyResolutionLimits:
    max_requirements: int
    max_candidates_per_requirement: int
    max_groups: int
    max_search_states: int
    max_graph_nodes: int
    max_graph_edges: int
    max_diagnostics: int

    def __post_init__(self) -> None:
        values = (
            (self.max_requirements, 500),
            (self.max_candidates_per_requirement, 500),
            (self.max_groups, 500),
            (self.max_search_states, 100_000),
            (self.max_graph_nodes, 200),
            (self.max_graph_edges, 1_000),
            (self.max_diagnostics, 5_000),
        )
        if any(
            isinstance(value, bool)
            or not isinstance(value, int)
            or not 1 <= value <= maximum
            for value, maximum in values
        ):
            raise InvalidSkillDependencyResolutionPolicy()


@dataclass(frozen=True)
class SkillDependencyResolutionPolicy:
    version: SkillDependencyResolutionPolicyVersion
    version_mode: SkillDependencyVersionMode
    version_preference: SkillDependencyVersionPreference
    compatibility: SkillDependencyCompatibilityPolicy
    degraded_lifecycle: SkillDependencyDegradedLifecyclePolicy
    optional_dependencies: SkillOptionalDependencyPolicy
    completeness: SkillDependencyCompletenessPolicy
    allow_exact_prerelease: bool
    limits: SkillDependencyResolutionLimits

    def __post_init__(self) -> None:
        if (
            not isinstance(self.version, SkillDependencyResolutionPolicyVersion)
            or not isinstance(self.version_mode, SkillDependencyVersionMode)
            or not isinstance(
                self.version_preference, SkillDependencyVersionPreference
            )
            or not isinstance(
                self.compatibility, SkillDependencyCompatibilityPolicy
            )
            or not isinstance(
                self.degraded_lifecycle,
                SkillDependencyDegradedLifecyclePolicy,
            )
            or not isinstance(
                self.optional_dependencies, SkillOptionalDependencyPolicy
            )
            or not isinstance(
                self.completeness, SkillDependencyCompletenessPolicy
            )
            or not isinstance(self.allow_exact_prerelease, bool)
            or not isinstance(self.limits, SkillDependencyResolutionLimits)
        ):
            raise InvalidSkillDependencyResolutionPolicy()
