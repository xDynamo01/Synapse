from __future__ import annotations

import os
from dataclasses import dataclass

from synapse.bootstrap.adapters.provider_taxonomy import register_model_provider_projections
from synapse.bootstrap.adapters.speech_execution import LocalSpeechExecutionPort
from synapse.bootstrap.adapters.voicestudio import VoiceStudioHttpTransport
from synapse.bootstrap.feature import BuiltFeature, FeatureMetadata
from synapse.core.config import ConfigStore
from synapse.core.data_dir import DataDir
from synapse.core.events import EventBus
from synapse.model_hub.runtime import ModelHubRuntime
from synapse.model_providers.lmstudio import LMStudioModelAdapter, LMStudioProviderRuntime
from synapse.model_providers.synapse_local import SynapseLocalModelAdapter
from synapse.models.router import ModelRouter
from synapse.provider_plugins.registry import ProviderPluginRegistry
from synapse.provider_plugins.runtime import ProviderPluginRuntime
from synapse.providers.catalog import ProviderCatalog
from synapse.providers.registry import builtin_provider_registry
from synapse.providers.runtime import ProviderRuntime
from synapse.providers.settings import ProviderSettingsRuntime
from synapse.speech_adapters.registry import builtin_speech_adapter_registry
from synapse.speech_adapters.runtime import SpeechAdapterRuntime
from synapse.system_insight.runtime import SystemInsightRuntime


@dataclass(frozen=True)
class ModelFeatureDependencies:
    data_dir: DataDir
    config: ConfigStore
    events: EventBus


@dataclass(frozen=True)
class ModelFeature:
    models: ModelRouter
    providers: ProviderRuntime
    provider_settings: ProviderSettingsRuntime
    provider_plugins: ProviderPluginRuntime
    lmstudio: LMStudioProviderRuntime
    model_hub: ModelHubRuntime
    system_insight: SystemInsightRuntime
    speech_adapters: SpeechAdapterRuntime
    provider_catalog: ProviderCatalog


class ModelFeatureBuilder:
    metadata = FeatureMetadata("models-and-providers")

    def build(self, dependencies: ModelFeatureDependencies) -> BuiltFeature[ModelFeature]:
        data_dir = dependencies.data_dir
        events = dependencies.events
        models = ModelRouter(dependencies.config.load_system(), events=events)
        providers = ProviderRuntime(data_dir, builtin_provider_registry(), events)
        provider_settings = ProviderSettingsRuntime(data_dir, events)
        provider_plugins = ProviderPluginRuntime(ProviderPluginRegistry(data_dir), events, data_dir)
        lmstudio = LMStudioProviderRuntime(data_dir, events)
        models.adapters["lmstudio"] = LMStudioModelAdapter(lmstudio)
        models.adapters["lmstudio_local"] = LMStudioModelAdapter(lmstudio)
        models.adapters["synapse_local"] = SynapseLocalModelAdapter(
            data_dir, events,
            max_loaded_models=models.system_config.get("models", {}).get("providers", {}).get(
                "synapse_local", {}).get("max_loaded_models"),
        )
        model_hub = ModelHubRuntime(data_dir, events, lmstudio, providers, provider_plugins, models)
        def context_window(provider: str, model: str | None) -> int | None:
            # Read the existing snapshot only; do not load providers to budget a prompt.
            values = [entry.context_window for entry in model_hub.registry.list_models()
                      if entry.provider == provider and model in {entry.id, entry.name}
                      and entry.context_window is not None]
            return min(values) if values else None

        models.context_window_resolver = context_window
        system_insight = SystemInsightRuntime(data_dir, events, model_hub)
        models.model_capabilities = system_insight.model_capabilities
        provider_settings.model_hub = model_hub
        model_hub.provider_settings = provider_settings
        speech_adapters = SpeechAdapterRuntime(
            data_dir,
            builtin_speech_adapter_registry(),
            providers,
            events,
            execution=LocalSpeechExecutionPort(),
            voicestudio_transport=VoiceStudioHttpTransport(os.getenv("SYNAPSE_VOICESTUDIO_URL", "http://127.0.0.1:3900")),
        )
        provider_catalog = ProviderCatalog()
        register_model_provider_projections(
            provider_catalog,
            provider_settings=provider_settings,
            speech_adapters=speech_adapters,
        )
        model_hub.provider_catalog = provider_catalog
        system_insight.provider_catalog = provider_catalog
        return BuiltFeature(
            ModelFeature(
                models,
                providers,
                provider_settings,
                provider_plugins,
                lmstudio,
                model_hub,
                system_insight,
                speech_adapters,
                provider_catalog,
            ),
            self.metadata,
        )
