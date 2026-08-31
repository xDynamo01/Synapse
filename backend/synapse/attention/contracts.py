from __future__ import annotations

from typing import Protocol

from synapse.world_state.models import WorldStateSnapshot


class WorldStateReadPort(Protocol):
    def snapshot(self) -> WorldStateSnapshot: ...
