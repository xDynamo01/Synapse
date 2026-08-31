from __future__ import annotations

from synapse.core.events import EventBus
from synapse.system_insight.collection import CollectionRuntime
from synapse.system_insight.models import HardwareSnapshot
from synapse.system_insight.providers.base import PlatformInsightProvider


class HardwareRuntime(CollectionRuntime):
    def __init__(self, provider: PlatformInsightProvider, events: EventBus):
        super().__init__(provider, events)

    def inspect(self) -> HardwareSnapshot:
        return self._collect("hardware", self.provider.collect_hardware)
