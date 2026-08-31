from __future__ import annotations

from dataclasses import dataclass

from synapse.skills.phase5_models import PublishVerifiedSkillVersionRequest
from synapse.skills.phase6_models import (
    DeactivateSkillVersionRequest,
    DeprecateSkillVersionRequest,
    ReenableSkillVersionRequest,
    RevokeSkillVersionRequest,
    RollbackSkillVersionRequest,
    SupersedeSkillVersionRequest,
)
from synapse.skills.phase7_models import (
    ActivateInstalledSkillVersionRequest,
    DeactivateInstalledSkillVersionRequest,
    InstallVerifiedSkillVersionRequest,
    TerminateSkillInstallationRequest,
)
from synapse.skills.phase10_models import (
    BindSkillGovernanceDecisionRequest,
    BindSkillIntelligenceFactRequest,
)
from synapse.skills.phase11_models import BindSkillPrivateEvalResultRequest

_LifecycleTransitionRequest = (
    DeactivateSkillVersionRequest
    | DeprecateSkillVersionRequest
    | ReenableSkillVersionRequest
    | SupersedeSkillVersionRequest
    | RollbackSkillVersionRequest
    | RevokeSkillVersionRequest
)


@dataclass(frozen=True)
class PublishSkillVersionCommand:
    request: PublishVerifiedSkillVersionRequest


@dataclass(frozen=True)
class ApplySkillLifecycleTransitionCommand:
    request: _LifecycleTransitionRequest


@dataclass(frozen=True)
class InstallSkillVersionCommand:
    request: InstallVerifiedSkillVersionRequest


@dataclass(frozen=True)
class TerminateSkillInstallationCommand:
    request: TerminateSkillInstallationRequest


@dataclass(frozen=True)
class ActivateSkillVersionCommand:
    request: ActivateInstalledSkillVersionRequest


@dataclass(frozen=True)
class DeactivateSkillVersionCommand:
    request: DeactivateInstalledSkillVersionRequest


@dataclass(frozen=True)
class BindSkillGovernanceDecisionCommand:
    request: BindSkillGovernanceDecisionRequest


@dataclass(frozen=True)
class BindSkillIntelligenceFactCommand:
    request: BindSkillIntelligenceFactRequest


@dataclass(frozen=True)
class BindSkillPrivateEvalResultCommand:
    request: BindSkillPrivateEvalResultRequest
