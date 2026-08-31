from __future__ import annotations

from typing import Protocol

from synapse.skills.application.errors import SkillApplicationError
from synapse.skills.application.queries import GetSkillLifecycleProjectionQuery
from synapse.skills.application.results import (
    SkillApplicationCompleteness,
    SkillLifecycleQueryResult,
)
from synapse.skills.phase2_models import PublishedSkillVersionId

from .catalog import _translate
from .errors import SkillLegacyCompatibilityIncomplete
from .models import LegacyLifecycleView


class _StateQueries(Protocol):
    def lifecycle(
        self, query: GetSkillLifecycleProjectionQuery
    ) -> SkillLifecycleQueryResult: ...


class LegacyLifecycleAdapter:
    def __init__(self, states: _StateQueries) -> None:
        self._states = states

    def state(self, identity: PublishedSkillVersionId) -> LegacyLifecycleView:
        try:
            result = self._states.lifecycle(GetSkillLifecycleProjectionQuery(identity))
        except SkillApplicationError as exc:
            raise _translate(exc) from exc
        if result.completeness is not SkillApplicationCompleteness.COMPLETE:
            raise SkillLegacyCompatibilityIncomplete()
        value = result.projection
        return LegacyLifecycleView(
            identity=value.identity,
            activation_state=value.activation_state.value,
            selection_state=value.selection_state.value,
            active=value.active,
            deprecated=value.deprecated,
            revoked=value.revoked,
            installation_id=(
                str(value.active_installation_id)
                if value.active_installation_id is not None
                else None
            ),
            complete=True,
        )
