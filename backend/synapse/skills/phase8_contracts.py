from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from synapse.skills.phase2_models import PublishedSkillVersionId, SkillId
from synapse.skills.phase3_records import PublishedSkillVersionRecord
from synapse.skills.phase3_values import SkillStoreQueryLimit
from synapse.skills.phase6_models import SkillLifecycleProjection
from synapse.skills.phase8_errors import InconsistentSkillDependencyCatalog


@dataclass(frozen=True)
class SkillDependencyCatalogPage:
    """Bounded catalog facts with provider-attested termination."""

    records: tuple[PublishedSkillVersionRecord, ...]
    complete: bool

    def __post_init__(self) -> None:
        if (
            not isinstance(self.records, tuple)
            or not all(
                isinstance(record, PublishedSkillVersionRecord)
                for record in self.records
            )
            or not isinstance(self.complete, bool)
        ):
            raise InconsistentSkillDependencyCatalog()


class SkillDependencyCatalogProvider(Protocol):
    """Read-only analysis view; completeness must be attested, never inferred."""

    def get_version(
        self, identity: PublishedSkillVersionId
    ) -> PublishedSkillVersionRecord: ...

    def list_dependency_candidates(
        self, skill_id: SkillId, limit: SkillStoreQueryLimit
    ) -> SkillDependencyCatalogPage: ...


class SkillLifecycleProjectionProvider(Protocol):
    """Read-only provider of the approved Slice 6 lifecycle projection."""

    def projection(
        self, identity: PublishedSkillVersionId
    ) -> SkillLifecycleProjection: ...
