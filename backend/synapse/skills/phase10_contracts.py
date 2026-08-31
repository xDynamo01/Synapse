from __future__ import annotations

from typing import Protocol

from synapse.skills.phase2_models import PublishedSkillVersionId
from synapse.skills.phase3_contracts import SkillStoreWriteOutcome
from synapse.skills.phase3_values import SkillStoreQueryLimit
from synapse.skills.phase10_models import (
    SkillGovernanceBindingHistory,
    SkillGovernanceBindingRecord,
    SkillIntelligenceBindingHistory,
    SkillIntelligenceBindingRecord,
)


class SkillExternalBindingStore(Protocol):
    """Append-only local binding facts; adapters must report history completeness."""

    def append_governance(self, record: SkillGovernanceBindingRecord) -> SkillStoreWriteOutcome: ...

    def append_intelligence(
        self, record: SkillIntelligenceBindingRecord
    ) -> SkillStoreWriteOutcome: ...

    def list_governance_for_version(
        self,
        identity: PublishedSkillVersionId,
        limit: SkillStoreQueryLimit,
    ) -> SkillGovernanceBindingHistory: ...

    def list_intelligence_for_version(
        self,
        identity: PublishedSkillVersionId,
        limit: SkillStoreQueryLimit,
    ) -> SkillIntelligenceBindingHistory: ...
