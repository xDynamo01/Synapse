from __future__ import annotations

import dataclasses
from pathlib import Path

from synapse.core.data_dir import DataDir
from synapse.core.serialization import dump_json, dump_structured_file, load_structured_file
from synapse.provider_plugins.models import ProviderPluginInstallState, ProviderPluginManifest


class ProviderPluginRegistry:
    def __init__(self, data_dir: DataDir):
        self.data_dir = data_dir

    def _manifest_path(self, plugin_id: str) -> Path:
        return self.data_dir.resolve(f"provider_plugins/manifests/{plugin_id}.yaml")

    def _state_path(self, plugin_id: str) -> Path:
        return self.data_dir.resolve(f"provider_plugins/states/{plugin_id}.json")

    def register_plugin(self, manifest: ProviderPluginManifest) -> None:
        path = self._manifest_path(manifest.plugin_id)
        # Convert dataclass to dict for dumping
        payload = dataclasses.asdict(manifest)
        dump_structured_file(path, payload)

    def get_plugin(self, plugin_id: str) -> ProviderPluginManifest | None:
        path = self._manifest_path(plugin_id)
        if not path.exists():
            return None
        raw = load_structured_file(path)
        if not raw:
            return None

        # Build raw dict into dataclass
        manifest = ProviderPluginManifest(
            plugin_id=raw["plugin_id"],
            name=raw["name"],
            description=raw["description"],
            version=raw["version"],
            plugin_type=raw["plugin_type"],
            providers=raw.get("providers", []),
            capabilities=raw.get("capabilities", []),
            adapters=raw.get("adapters", []),
            enabled=raw.get("enabled", False),
            installed=raw.get("installed", False),
            local_only=raw.get("local_only", True),
            requires_network=raw.get("requires_network", False),
            requires_gpu=raw.get("requires_gpu", False),
            supported_platforms=raw.get("supported_platforms", []),
            requirements=raw.get("requirements", []),
            entrypoint=raw.get("entrypoint"),
            metadata=raw.get("metadata"),
        )

        # Merge state
        state = self.get_install_state(plugin_id)
        return dataclasses.replace(
            manifest,
            enabled=state.enabled,
            installed=state.installed,
        )

    def list_plugins(self) -> list[ProviderPluginManifest]:
        manifest_dir = self.data_dir.resolve("provider_plugins/manifests")
        plugins = []
        for path in manifest_dir.glob("*.yaml"):
            plugin_id = path.stem
            plugin = self.get_plugin(plugin_id)
            if plugin:
                plugins.append(plugin)
        return plugins

    def list_by_type(self, plugin_type: str) -> list[ProviderPluginManifest]:
        return [p for p in self.list_plugins() if p.plugin_type == plugin_type]

    def get_install_state(self, plugin_id: str) -> ProviderPluginInstallState:
        path = self._state_path(plugin_id)
        if not path.exists():
            # Return a default state
            # Let's find version from manifest if available
            version = ""
            manifest_path = self._manifest_path(plugin_id)
            if manifest_path.exists():
                manifest_raw = load_structured_file(manifest_path)
                if manifest_raw:
                    version = manifest_raw.get("version", "")
            return ProviderPluginInstallState(
                plugin_id=plugin_id,
                installed=False,
                enabled=False,
                version=version,
            )

        raw = load_structured_file(path)
        return ProviderPluginInstallState(
            plugin_id=raw["plugin_id"],
            installed=raw["installed"],
            enabled=raw["enabled"],
            version=raw["version"],
            installed_at=raw.get("installed_at"),
            updated_at=raw.get("updated_at"),
            metadata=raw.get("metadata"),
        )

    def set_install_state(self, plugin_id: str, state: ProviderPluginInstallState) -> None:
        path = self._state_path(plugin_id)
        payload = dataclasses.asdict(state)
        dump_json(path, payload)
