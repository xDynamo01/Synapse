from __future__ import annotations

from dataclasses import dataclass

from synapse.skills.phase2_models import PublishedSkillVersionId, SkillId
from synapse.skills.phase3_values import SkillStoreQueryLimit
from synapse.skills.phase8_models import (
    AnalyzeSkillDependenciesRequest,
    AnalyzeSkillDependencyGraphRequest,
)
from synapse.skills.phase9_models import ResolveSkillDependenciesRequest
from synapse.skills.phase12_models import BuildSkillExecutionHandoffRequest


@dataclass(frozen=True)
class GetPublishedSkillVersionQuery:
    identity: PublishedSkillVersionId


@dataclass(frozen=True)
class ListPublishedSkillVersionsQuery:
    skill_id: SkillId
    limit: SkillStoreQueryLimit


@dataclass(frozen=True)
class GetSkillLifecycleProjectionQuery:
    identity: PublishedSkillVersionId


@dataclass(frozen=True)
class GetSkillInstallationProjectionQuery:
    identity: PublishedSkillVersionId


@dataclass(frozen=True)
class AnalyzeSkillDependenciesQuery:
    request: AnalyzeSkillDependenciesRequest


@dataclass(frozen=True)
class AnalyzeSkillDependencyGraphQuery:
    request: AnalyzeSkillDependencyGraphRequest


@dataclass(frozen=True)
class ResolveSkillDependenciesQuery:
    request: ResolveSkillDependenciesRequest


@dataclass(frozen=True)
class GetSkillGovernanceBindingsQuery:
    identity: PublishedSkillVersionId


@dataclass(frozen=True)
class GetSkillIntelligenceBindingsQuery:
    identity: PublishedSkillVersionId


@dataclass(frozen=True)
class GetSkillPrivateEvalBindingsQuery:
    identity: PublishedSkillVersionId


@dataclass(frozen=True)
class BuildSkillExecutionHandoffQuery:
    request: BuildSkillExecutionHandoffRequest
