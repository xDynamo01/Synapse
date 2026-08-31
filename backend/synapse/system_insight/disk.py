from __future__ import annotations

from synapse.core.events import EventBus
from synapse.system_insight.collection import CollectionRuntime
from synapse.system_insight.models import DiskSnapshot
from synapse.system_insight.providers.base import PlatformInsightProvider


class DiskRuntime(CollectionRuntime):
    def __init__(self, provider: PlatformInsightProvider, events: EventBus):
        super().__init__(provider, events)

    def inspect(self) -> DiskSnapshot:
        return self._collect("storage", self.provider.collect_storage)
