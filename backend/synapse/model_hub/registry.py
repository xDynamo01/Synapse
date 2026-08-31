from __future__ import annotations

from synapse.model_hub.models import ModelCatalogEntry, ModelProviderInfo


class ModelHubRegistry:
    def __init__(self) -> None:
        self._models: dict[str, ModelCatalogEntry] = {}
        self._providers: dict[str, ModelProviderInfo] = {}

    def replace_models(self, models: list[ModelCatalogEntry]) -> None:
        self._models = {model.id: model for model in models}

    def replace_providers(self, providers: list[ModelProviderInfo]) -> None:
        self._providers = {provider.provider_id: provider for provider in providers}

    def list_models(self) -> list[ModelCatalogEntry]:
        return sorted(self._models.values(), key=lambda item: (item.provider, item.name.lower()))

    def list_providers(self) -> list[ModelProviderInfo]:
        return sorted(self._providers.values(), key=lambda item: item.display_name.lower())

    def get_provider(self, provider_id: str) -> ModelProviderInfo | None:
        return self._providers.get(provider_id)
