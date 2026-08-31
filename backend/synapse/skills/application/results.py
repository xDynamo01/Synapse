from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from synapse.skills.phase2_models import PublishedSkillVersionId
from synapse.skills.phase3_records import PublishedSkillVersionRecord
from synapse.skills.phase6_models import SkillLifecycleProjection
from synapse.skills.phase7_models import SkillInstallationProjection
from synapse.skills.phase8_models import (
    SkillDependencyAnalysis,
    SkillDependencyGraphSnapshot,
)
from synapse.skills.phase9_models import SkillDependencyResolutionPlan
from synapse.skills.phase10_models import (
    SkillGovernanceBindingProjection,
    SkillIntelligenceBindingProjection,
)
from synapse.skills.phase11_models import SkillPrivateEvalBindingProjection
from synapse.skills.phase12_models import SkillExecutionHandoffBuildResult


class SkillApplicationMutationOutcome(StrEnum):
    CREATED = "created"
    REPLAYED = "replayed"


class SkillApplicationCompleteness(StrEnum):
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"
    UNKNOWN = "unknown"


class SkillApplicationBindingFamily(StrEnum):
    GOVERNANCE = "governance"
    INTELLIGENCE = "intelligence"
    PRIVATE_EVALS = "private_evals"


@dataclass(frozen=True)
class SkillCommandResult:
    identity: PublishedSkillVersionId
    outcome: SkillApplicationMutationOutcome


@dataclass(frozen=True)
class PublishedSkillVersionView:
    record: PublishedSkillVersionRecord


@dataclass(frozen=True)
class PublishedSkillVersionListResult:
    versions: tuple[PublishedSkillVersionView, ...]
    completeness: SkillApplicationCompleteness


@dataclass(frozen=True)
class SkillLifecycleQueryResult:
    projection: SkillLifecycleProjection
    completeness: SkillApplicationCompleteness


@dataclass(frozen=True)
class SkillInstallationQueryResult:
    projection: SkillInstallationProjection
    completeness: SkillApplicationCompleteness


_BindingProjection = (
    SkillGovernanceBindingProjection
    | SkillIntelligenceBindingProjection
    | SkillPrivateEvalBindingProjection
)


@dataclass(frozen=True)
class SkillBindingQueryResult:
    family: SkillApplicationBindingFamily
    projection: _BindingProjection
    completeness: SkillApplicationCompleteness


@dataclass(frozen=True)
class SkillDependencyAnalysisQueryResult:
    analysis: SkillDependencyAnalysis


@dataclass(frozen=True)
class SkillDependencyGraphQueryResult:
    graph: SkillDependencyGraphSnapshot


@dataclass(frozen=True)
class SkillDependencyResolutionQueryResult:
    plan: SkillDependencyResolutionPlan


@dataclass(frozen=True)
class SkillExecutionHandoffQueryResult:
    result: SkillExecutionHandoffBuildResult
