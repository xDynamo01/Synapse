from __future__ import annotations

from synapse.core.events import EventBus
from synapse.system_insight.collection import CollectionRuntime
from synapse.system_insight.models import ProcessSnapshot
from synapse.system_insight.providers.base import PlatformInsightProvider


class ProcessRuntime(CollectionRuntime):
    def __init__(self, provider: PlatformInsightProvider, events: EventBus):
        super().__init__(provider, events)

    def inspect(self, limit: int = 100) -> ProcessSnapshot:
        return self._collect("processes", lambda: self.provider.collect_processes(limit))
