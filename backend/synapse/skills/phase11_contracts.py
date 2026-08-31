from __future__ import annotations

from typing import Protocol

from synapse.skills.phase2_models import PublishedSkillVersionId
from synapse.skills.phase3_contracts import SkillStoreWriteOutcome
from synapse.skills.phase3_values import SkillStoreQueryLimit
from synapse.skills.phase11_models import (
    SkillPrivateEvalBindingHistory,
    SkillPrivateEvalBindingRecord,
)


class SkillPrivateEvalBindingStore(Protocol):
    """Append-only Private Evals references with explicit history completeness."""

    def append_private_eval(
        self, record: SkillPrivateEvalBindingRecord
    ) -> SkillStoreWriteOutcome: ...

    def list_private_evals_for_version(
        self,
        identity: PublishedSkillVersionId,
        limit: SkillStoreQueryLimit,
    ) -> SkillPrivateEvalBindingHistory: ...
