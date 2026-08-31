from __future__ import annotations

from synapse.core.events import EventBus
from synapse.system_insight.collection import CollectionRuntime
from synapse.system_insight.models import SystemSnapshot
from synapse.system_insight.providers.base import PlatformInsightProvider


class SystemRuntime(CollectionRuntime):
    def __init__(self, provider: PlatformInsightProvider, events: EventBus):
        super().__init__(provider, events)

    def inspect(self) -> SystemSnapshot:
        return self._collect("system", self.provider.collect_system)
