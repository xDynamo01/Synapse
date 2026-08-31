from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from synapse.skills.phase2_models import PublishedSkillVersionId


class LegacyLookupOutcome(StrEnum):
    FOUND = "found"
    NOT_FOUND = "not_found"
    AMBIGUOUS = "ambiguous"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class LegacySkillLookup:
    skill_id: str
    version: str | None = None


@dataclass(frozen=True)
class LegacySkillView:
    identity: PublishedSkillVersionId
    skill_id: str
    version: str
    name: str
    summary: str
    description: str
    status: str
    capabilities: tuple[str, ...]
    exact_identity_retained: bool = True


@dataclass(frozen=True)
class LegacySkillLookupResult:
    outcome: LegacyLookupOutcome
    skill: LegacySkillView | None
    candidates: tuple[PublishedSkillVersionId, ...] = ()
    complete: bool = True


@dataclass(frozen=True)
class LegacySkillListResult:
    skills: tuple[LegacySkillView, ...]
    complete: bool


@dataclass(frozen=True)
class LegacyLifecycleView:
    identity: PublishedSkillVersionId
    activation_state: str
    selection_state: str
    active: bool
    deprecated: bool
    revoked: bool
    installation_id: str | None
    complete: bool
