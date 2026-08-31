"""Explicit projections from execution-owned provider contracts into discovery taxonomy."""

from __future__ import annotations

from typing import Any, cast

from synapse.providers.catalog import ProviderCatalog
from synapse.providers.taxonomy import (
    CanonicalProviderManifest,
    ProviderAvailability,
    ProviderCapability,
    ProviderConfigurationDescriptor,
    ProviderConfigurationField,
    ProviderDomain,
    ProviderLifecycleCapabilities,
)

_MODEL_EXECUTION_ALIASES = {
    "lmstudio_local": ("lmstudio",),
    "ollama_local": ("ollama",),
    "google_gemini": ("gemini",),
}
_SPEECH_DOMAINS: dict[str, ProviderDomain] = {
    "stt": "speech_to_text",
    "tts": "text_to_speech",
    "voice_analysis": "voice_analysis",
}


def register_model_provider_projections(
    catalog: ProviderCatalog,
    *,
    provider_settings: Any,
    speech_adapters: Any,
) -> None:
    """Register model and speech identities without transferring execution authority."""

    for setting in provider_settings.list_settings():
        requires_api_key = bool(setting.metadata.get("requires_api_key"))
        fields = (
            ProviderConfigurationField("enabled", default=False),
            ProviderConfigurationField("endpoint", required=True),
            ProviderConfigurationField("default_model"),
            ProviderConfigurationField("api_key", required=requires_api_key, sensitive=True),
        )
        catalog.register(
            CanonicalProviderManifest(
                provider_id=setting.provider_id,
                display_name=setting.display_name,
                domain="model",
                version="1.0.0",
                capabilities=(ProviderCapability("model.chat"),),
                availability=_canonical_availability(setting.status, enabled=setting.enabled),
                configuration=ProviderConfigurationDescriptor(fields=fields),
                lifecycle=ProviderLifecycleCapabilities(
                    lazy_load=True, streaming=True, cancel=False, reload=True
                ),
                implementation_id=setting.provider_id,
                health_reference="model_provider_health",
                local=setting.provider_kind == "local",
                aliases=_MODEL_EXECUTION_ALIASES.get(setting.provider_id, ()),
                metadata={"projection_source": "provider_settings"},
            )
        )

    for manifest in speech_adapters.registry.list_adapters():
        if manifest.metadata.get("mock"):
            continue
        capability_ids = {
            capability.capability_id
            for capability in speech_adapters.registry.list_capabilities(
                {
                    "stt": "speech_to_text",
                    "tts": "text_to_speech",
                    "voice_analysis": "voice_analysis",
                }[manifest.adapter_type]
            )
            if capability.adapter_id == manifest.adapter_id
        }
        catalog.register(
            CanonicalProviderManifest(
                provider_id=manifest.provider_id,
                display_name=manifest.name,
                domain=_SPEECH_DOMAINS[manifest.adapter_type],
                version=manifest.version,
                capabilities=tuple(ProviderCapability(item) for item in sorted(capability_ids)),
                availability="configured",
                configuration=ProviderConfigurationDescriptor(),
                lifecycle=ProviderLifecycleCapabilities(
                    lazy_load=manifest.adapter_type == "stt",
                    streaming=manifest.supports_streaming,
                ),
                implementation_id=manifest.adapter_id,
                health_reference="speech_adapter_health",
                local=not manifest.requires_network,
                metadata={
                    "projection_source": "speech_adapter_registry",
                    "adapter_id": manifest.adapter_id,
                },
            )
        )


def register_runtime_provider_projections(
    catalog: ProviderCatalog,
    *,
    platform: Any,
    models: Any,
    interaction: Any,
    agents: Any,
) -> None:
    """Complete discovery after all platform-specific factories have selected providers."""

    _register(
        catalog,
        "webrtcvad",
        "WebRTC VAD",
        "vad",
        ("voice.activity_detection",),
        availability="configured",
        lifecycle=ProviderLifecycleCapabilities(streaming=True),
        source="voice.vad",
    )
    vision_provider = interaction.vision.vision_provider
    _register(
        catalog,
        vision_provider.provider_id,
        "Local Image Metadata",
        "vision",
        tuple(vision_provider.capabilities()),
        availability="available",
        source="vision.runtime",
    )
    capture_provider = interaction.capture.provider
    _register(
        catalog,
        capture_provider.provider_id,
        "Local Screen Capture",
        "capture",
        ("screen.capture", "screen.sources"),
        availability="configured",
        source="vision.capture",
    )

    desktop = agents.desktop
    _register(
        catalog,
        desktop.provider.name,
        "Platform Accessibility",
        "desktop_automation",
        ("desktop.discovery", "desktop.semantic_actions", "clipboard"),
        availability="configured",
        source="desktop.factory",
    )
    _register(
        catalog,
        desktop.input.provider.name,
        "Platform Input",
        "desktop_automation",
        ("desktop.input",),
        availability="configured",
        source="desktop.input_factory",
    )
    for provider in desktop.ui_automation.providers[1:]:
        _register(
            catalog,
            provider.name,
            provider.name.replace("_", " ").title(),
            "desktop_automation",
            ("desktop.visual_fallback",),
            availability="configured",
            source="desktop.fallback",
        )

    insight_provider = models.system_insight.provider
    _register(
        catalog,
        insight_provider.name,
        f"{insight_provider.name.title()} System Insight",
        "system_insight",
        ("system.inspect", "hardware.inspect", "process.inspect"),
        availability="configured",
        source="system_insight.factory",
    )
    notification_providers = [
        platform.notifications.provider,
        *platform.notifications.extra_providers,
    ]
    for provider in notification_providers:
        _register(
            catalog,
            provider.name,
            f"{provider.name.title()} Notifications",
            "notification",
            ("notification.delivery",),
            availability="configured",
            source="notification.runtime",
        )


def _register(
    catalog: ProviderCatalog,
    provider_id: str,
    display_name: str,
    domain: ProviderDomain,
    capabilities: tuple[str, ...],
    *,
    availability: ProviderAvailability,
    source: str,
    lifecycle: ProviderLifecycleCapabilities | None = None,
) -> None:
    catalog.register(
        CanonicalProviderManifest(
            provider_id=provider_id,
            display_name=display_name,
            domain=domain,
            version="1.0.0",
            capabilities=tuple(ProviderCapability(item) for item in capabilities),
            availability=availability,
            implementation_id=provider_id,
            health_reference=f"{domain}_health",
            lifecycle=lifecycle or ProviderLifecycleCapabilities(),
            metadata={"projection_source": source},
        )
    )


def _canonical_availability(status: str, *, enabled: bool) -> ProviderAvailability:
    if not enabled or status in {"unconfigured", "disabled", "not_installed"}:
        return "not_configured"
    if status in {"available", "ready", "reachable", "authenticated"}:
        return "available"
    if status in {"degraded", "misconfigured", "unavailable"}:
        return cast(ProviderAvailability, status)
    return "configured"
