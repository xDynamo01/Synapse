from __future__ import annotations

import sys
from datetime import UTC, datetime
from typing import Any

from synapse.core.data_dir import DataDir
from synapse.core.events import EventBus
from synapse.core.exceptions import NotFound
from synapse.core.permissions import PermissionContext
from synapse.core.serialization import load_structured_file
from synapse.provider_plugins.models import (
    ProviderPluginHealth,
    ProviderPluginInstallState,
    ProviderPluginManifest,
    ProviderPluginSummary,
)
from synapse.provider_plugins.registry import ProviderPluginRegistry


class ProviderPluginRuntime:
    def __init__(
        self,
        registry: ProviderPluginRegistry,
        event_bus: EventBus,
        data_dir: DataDir,
    ):
        self.registry = registry
        self.event_bus = event_bus
        self.data_dir = data_dir
        for manifest in self.registry.list_plugins():
            self.event_bus.emit(
                "provider_plugin.registered",
                "provider_plugin",
                {
                    "plugin_id": manifest.plugin_id,
                    "plugin_type": manifest.plugin_type,
                    "version": manifest.version,
                },
            )

    def load_policy(self) -> dict[str, Any]:
        path = self.data_dir.resolve("config/provider_plugin_policy.yaml")
        if not path.exists():
            return {}
        raw = load_structured_file(path)
        return raw.get("provider_plugin_policy", raw)

    def list_plugins(self) -> list[ProviderPluginManifest]:
        return self.registry.list_plugins()

    def get_plugin(self, plugin_id: str) -> ProviderPluginManifest:
        plugin = self.registry.get_plugin(plugin_id)
        if not plugin:
            raise NotFound(f"Plugin {plugin_id} not found")
        return plugin

    def list_by_type(self, plugin_type: str) -> list[ProviderPluginManifest]:
        return self.registry.list_by_type(plugin_type)

    def plugin_health(
        self,
        plugin_id: str,
        context: PermissionContext | None = None,
    ) -> ProviderPluginHealth:
        manifest = self.get_plugin(plugin_id)
        policy = self.load_policy()
        policy_enabled = policy.get("enabled", True)
        disabled_plugins = policy.get("disabled_plugins", [])
        allow_network = policy.get("allow_network_plugins", False)
        allow_gpu = policy.get("allow_gpu_plugins", False)

        now_iso = datetime.now(UTC).isoformat()

        # Determine status
        if not policy_enabled:
            status = "disabled"
            message = "Provider plugin policy is globally disabled."
        elif plugin_id in disabled_plugins:
            status = "disabled"
            message = "Plugin is disabled in policy configuration."
        elif not manifest.installed:
            status = "not_installed"
            message = "Plugin is not installed."
        elif not manifest.enabled:
            status = "disabled"
            message = "Plugin is disabled."
        else:
            # Check platforms
            if manifest.supported_platforms:
                current_platform = (
                    "windows"
                    if sys.platform.startswith("win")
                    else ("darwin" if sys.platform.startswith("darwin") else "linux")
                )
                if current_platform not in manifest.supported_platforms:
                    status = "incompatible"
                    message = f"Platform {current_platform} is not supported."
                elif manifest.requires_network and not allow_network:
                    status = "unavailable"
                    message = "Network plugins are not allowed by policy."
                elif manifest.requires_gpu and not allow_gpu:
                    status = "unavailable"
                    message = "GPU plugins are not allowed by policy."
                else:
                    status = "available"
                    message = "Plugin is available and operational."
            else:
                if manifest.requires_network and not allow_network:
                    status = "unavailable"
                    message = "Network plugins are not allowed by policy."
                elif manifest.requires_gpu and not allow_gpu:
                    status = "unavailable"
                    message = "GPU plugins are not allowed by policy."
                else:
                    status = "available"
                    message = "Plugin is available and operational."

        health = ProviderPluginHealth(
            plugin_id=plugin_id,
            status=status,
            checked_at=now_iso,
            message=message,
            metadata={"policy": policy},
        )

        return health

    def list_plugin_health(
        self, context: PermissionContext | None = None
    ) -> list[ProviderPluginHealth]:
        plugins = self.list_plugins()
        return [self.plugin_health(p.plugin_id, context) for p in plugins]

    def summarize_plugins(self, context: PermissionContext | None = None) -> ProviderPluginSummary:
        plugins = self.list_plugins()
        total = len(plugins)
        installed = sum(1 for p in plugins if p.installed)
        enabled = sum(1 for p in plugins if p.enabled)

        # Count unavailable: plugins whose computed status is in incompatible, unavailable, degraded
        health_list = [self.plugin_health(p.plugin_id, context) for p in plugins]
        unavailable = sum(
            1 for h in health_list if h.status in {"unavailable", "degraded", "incompatible"}
        )

        by_type: dict[str, int] = {}
        for p in plugins:
            by_type[p.plugin_type] = by_type.get(p.plugin_type, 0) + 1

        summary = ProviderPluginSummary(
            total_plugins=total,
            installed_plugins=installed,
            enabled_plugins=enabled,
            unavailable_plugins=unavailable,
            by_type=by_type,
        )

        actor = context.actor_id if context else "system"
        self.event_bus.emit(
            "provider_plugin.summary_generated",
            actor,
            {
                "total_plugins": total,
                "installed_plugins": installed,
                "enabled_plugins": enabled,
                "unavailable_plugins": unavailable,
            },
        )

        return summary

    def unavailable_count(self) -> int:
        return len(
            [
                health
                for health in self.list_plugin_health()
                if health.status in {"unavailable", "degraded", "incompatible"}
            ]
        )

    def not_installed_count(self) -> int:
        return len(
            [health for health in self.list_plugin_health() if health.status == "not_installed"]
        )

    def enable_plugin(
        self,
        plugin_id: str,
        context: PermissionContext | None = None,
    ) -> ProviderPluginManifest:
        manifest = self.get_plugin(plugin_id)
        state = self.registry.get_install_state(plugin_id)
        now_iso = datetime.now(UTC).isoformat()
        installed_at = state.installed_at or now_iso

        new_state = ProviderPluginInstallState(
            plugin_id=plugin_id,
            installed=True,
            enabled=True,
            version=manifest.version,
            installed_at=installed_at,
            updated_at=now_iso,
        )
        self.registry.set_install_state(plugin_id, new_state)

        actor = context.actor_id if context else "system"
        self.event_bus.emit(
            "provider_plugin.enabled",
            actor,
            {"plugin_id": plugin_id, "version": manifest.version},
        )

        # Return updated manifest
        return self.get_plugin(plugin_id)

    def disable_plugin(
        self,
        plugin_id: str,
        context: PermissionContext | None = None,
    ) -> ProviderPluginManifest:
        manifest = self.get_plugin(plugin_id)
        state = self.registry.get_install_state(plugin_id)
        now_iso = datetime.now(UTC).isoformat()

        new_state = ProviderPluginInstallState(
            plugin_id=plugin_id,
            installed=state.installed,
            enabled=False,
            version=manifest.version,
            installed_at=state.installed_at,
            updated_at=now_iso,
        )
        self.registry.set_install_state(plugin_id, new_state)

        actor = context.actor_id if context else "system"
        self.event_bus.emit(
            "provider_plugin.disabled",
            actor,
            {"plugin_id": plugin_id, "version": manifest.version},
        )

        # Return updated manifest
        return self.get_plugin(plugin_id)

    def explain_plugin(self, plugin_id: str) -> str:
        manifest = self.get_plugin(plugin_id)
        health = self.plugin_health(plugin_id)

        lines = [
            f"Plugin ID: {manifest.plugin_id}",
            f"Name: {manifest.name}",
            f"Description: {manifest.description}",
            f"Version: {manifest.version}",
            f"Type: {manifest.plugin_type}",
            f"Installed: {'Yes' if manifest.installed else 'No'}",
            f"Enabled: {'Yes' if manifest.enabled else 'No'}",
            f"Requires Network: {'Yes' if manifest.requires_network else 'No'}",
            f"Requires GPU: {'Yes' if manifest.requires_gpu else 'No'}",
            f"Local Only: {'Yes' if manifest.local_only else 'No'}",
            f"Supported Platforms: {', '.join(manifest.supported_platforms) if manifest.supported_platforms else 'Any'}",
            f"Requirements: {', '.join(manifest.requirements) if manifest.requirements else 'None'}",
            f"Declared Providers: {', '.join(manifest.providers) if manifest.providers else 'None'}",
            f"Declared Capabilities: {', '.join(manifest.capabilities) if manifest.capabilities else 'None'}",
            f"Declared Adapters: {', '.join(manifest.adapters) if manifest.adapters else 'None'}",
            f"Health Status: {health.status.upper()}",
        ]
        if health.message:
            lines.append(f"Status Details: {health.message}")
        return "\n".join(lines)
