from __future__ import annotations

from dataclasses import asdict
from typing import Any

from synapse.health.contracts import HealthCheckContext, HealthContribution
from synapse.health.contributors.base import check, checks, component
from synapse.health.models import ComponentHealth


class ModelsHealthContributor:
    contributor_id = "models"

    def __init__(
        self,
        providers: Any,
        plugins: Any,
        lmstudio: Any,
        model_hub: Any,
        settings: Any,
        insight: Any,
    ) -> None:
        self.providers = providers
        self.provider_plugins = plugins
        self.lmstudio = lmstudio
        self.model_hub = model_hub
        self.provider_settings = settings
        self.system_insight = insight
        self.chat: Any | None = None

    def collect_health(self, context: HealthCheckContext) -> HealthContribution:
        try:
            unavailable = (
                sum(item.status == "unavailable" for item in self.providers.list_provider_health())
                if self.providers
                else 0
            )
        except Exception:
            unavailable = 0
        try:
            plugin_unavailable = (
                self.provider_plugins.unavailable_count() if self.provider_plugins else 0
            )
            plugin_missing = (
                self.provider_plugins.not_installed_count() if self.provider_plugins else 0
            )
        except Exception:
            plugin_unavailable = plugin_missing = 0
        lmstudio = self._lmstudio_health()
        model_hub = self.model_hub.health_snapshot() if self.model_hub else {}
        local_policy = (
            self.chat.load_local_chat_policy()
            if self.chat
            else {"enabled": False, "provider_id": "lmstudio_local"}
        )
        configured_external = (
            self.provider_settings.configured_external_count() if self.provider_settings else 0
        )
        external = ComponentHealth(
            component_id="external_providers",
            module="synapse.providers",
            state="ready" if configured_external > 0 else "not_configured",
            configured=configured_external > 0,
            available=configured_external > 0,
            ready=configured_external > 0,
            degraded=False,
            recommendations=[]
            if configured_external > 0
            else ["Configure a provider only if needed."],
        )
        insight_components = []
        for order, component_id, dependencies in (
            (19, "insight", ["observability"]),
            (20, "hardware", ["insight"]),
            (21, "gpu", ["hardware"]),
            (22, "cpu", ["hardware"]),
            (23, "ram", ["hardware"]),
            (24, "disk", ["insight"]),
            (25, "drivers", ["hardware"]),
            (26, "model_availability", ["models", "insight"]),
        ):
            details = self.system_insight.health(component_id) if self.system_insight else {}
            insight_components.append(
                component(order, component_id, self.system_insight, dependencies, details=details)
            )
        return HealthContribution(
            components=(
                component(3, "models", self.model_hub, ["providers"]),
                *insight_components,
                (28, external),
            ),
            summary={
                "provider_runtime_available": self.providers is not None,
                "providers_unavailable_count": unavailable,
                "provider_plugin_runtime_available": self.provider_plugins is not None,
                "provider_plugins_unavailable_count": plugin_unavailable,
                "provider_plugins_not_installed_count": plugin_missing,
                "lmstudio_available": bool(lmstudio.get("available", False)),
                "lmstudio_model_count": int(lmstudio.get("model_count", 0)),
                "model_hub_available": bool(model_hub.get("available", False)),
                "model_catalog_size": int(model_hub.get("catalog_size", 0)),
                "model_provider_count": int(model_hub.get("provider_count", 0)),
                "provider_settings_available": self.provider_settings is not None,
                "configured_external_provider_count": configured_external,
                "local_chat_available": bool(local_policy.get("enabled", False))
                and bool(lmstudio.get("available", False)),
            },
            checks=checks(
                check(
                    24,
                    "providers.unavailable",
                    unavailable > 0,
                    "warning",
                    f"{unavailable} unavailable provider(s)",
                    {"providers_unavailable_count": unavailable},
                ),
                check(
                    25,
                    "providers.unavailable_runtime",
                    self.providers is None,
                    "warning",
                    "provider runtime unavailable",
                ),
                check(
                    26,
                    "provider_plugins.unavailable_runtime",
                    self.provider_plugins is None,
                    "warning",
                    "provider plugin runtime unavailable",
                ),
                check(
                    27,
                    "provider_plugins.unavailable",
                    plugin_unavailable > 0,
                    "warning",
                    f"{plugin_unavailable} provider plugin(s) unavailable",
                    {"provider_plugins_unavailable_count": plugin_unavailable},
                ),
                check(
                    28,
                    "provider_plugins.not_installed",
                    plugin_missing > 0,
                    "info",
                    f"{plugin_missing} provider plugin(s) not installed",
                    {"provider_plugins_not_installed_count": plugin_missing},
                ),
                check(
                    29,
                    "lmstudio.unavailable",
                    bool(lmstudio.get("enabled")) and not bool(lmstudio.get("available")),
                    "warning",
                    "LM Studio is enabled but unavailable",
                    {
                        "available": bool(lmstudio.get("available")),
                        "model_count": int(lmstudio.get("model_count", 0)),
                        "message": lmstudio.get("message"),
                    },
                ),
                check(
                    30,
                    "local_chat.unavailable",
                    bool(local_policy.get("enabled", False))
                    and not bool(lmstudio.get("available")),
                    "warning",
                    "local chat is enabled but provider is unavailable",
                    {
                        "provider_id": local_policy.get("provider_id"),
                        "lmstudio_available": bool(lmstudio.get("available")),
                    },
                ),
            ),
        )

    def _lmstudio_health(self) -> dict[str, Any]:
        if not self.lmstudio:
            return {"available": False, "model_count": 0, "enabled": False}
        try:
            return {
                **asdict(self.lmstudio.health()),
                "enabled": self.lmstudio.load_config().enabled,
            }
        except Exception as exc:
            return {"available": False, "model_count": 0, "enabled": False, "message": str(exc)}
