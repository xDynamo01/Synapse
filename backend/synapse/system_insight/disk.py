from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path

from synapse.core.events import EventBus
from synapse.system_insight.collection import CollectionRuntime
from synapse.system_insight.models import DiskSnapshot, DiskVolume
from synapse.system_insight.providers.base import PlatformInsightProvider


class DiskRuntime(CollectionRuntime):
    def __init__(self, provider: PlatformInsightProvider, events: EventBus):
        super().__init__(provider, events)

    def inspect(self) -> DiskSnapshot:
        return self._collect("storage", self.provider.collect_storage)

    def inspect_path(self, path: Path) -> DiskSnapshot:
        usage = shutil.disk_usage(path)
        return DiskSnapshot(
            provider="filesystem", collected_at=datetime.now(UTC).isoformat(),
            volumes=[DiskVolume("execution-data", "unknown", usage.total, usage.used,
                                usage.free, usage.used / usage.total * 100)],
        )
