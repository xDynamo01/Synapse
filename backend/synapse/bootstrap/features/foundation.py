from __future__ import annotations

from dataclasses import dataclass

from synapse.bootstrap.feature import BuiltFeature, FeatureMetadata
from synapse.core.config import ConfigStore, Settings
from synapse.core.data_dir import DataDir
from synapse.core.events import EventBus
from synapse.core.permissions import PermissionManager


@dataclass(frozen=True)
class FoundationFeature:
    data_dir: DataDir
    config: ConfigStore
    events: EventBus
    permissions: PermissionManager


class FoundationFeatureBuilder:
    metadata = FeatureMetadata("foundation")

    def build(self, settings: Settings) -> BuiltFeature[FoundationFeature]:
        data_dir = DataDir(settings.data_dir)
        data_dir.bootstrap()
        config = ConfigStore(data_dir.root)
        events = EventBus(data_dir.root)
        permissions = PermissionManager(data_dir.root, events)
        return BuiltFeature(FoundationFeature(data_dir, config, events, permissions), self.metadata)
