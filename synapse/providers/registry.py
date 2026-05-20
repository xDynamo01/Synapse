from __future__ import annotations

from typing import Iterable

from synapse.config.models import AppConfig
from synapse.providers.anthropic import AnthropicProvider
from synapse.providers.base import BaseProvider, ChatRequest, ProviderError
from synapse.providers.ollama import OllamaProvider
from synapse.providers.openai_compatible import OpenAICompatibleProvider
from synapse.utils.logging import audit


class ProviderRegistry:
    def __init__(self, config: AppConfig):
        self.config = config

    def build(self, name: str | None = None) -> BaseProvider:
        cfg = self.config.provider(name)
        if cfg.type == "ollama":
            return OllamaProvider(cfg)
        if cfg.type == "anthropic":
            return AnthropicProvider(cfg)
        return OpenAICompatibleProvider(cfg)

    def provider_order(self, requested: str | None = None) -> list[str]:
        names = [requested or self.config.active_provider, *self.config.fallback_providers]
        seen: set[str] = set()
        return [name for name in names if not (name in seen or seen.add(name)) and name in self.config.providers]

    def chat_with_fallback(self, request: ChatRequest, provider_name: str | None = None) -> str:
        errors = []
        for name in self.provider_order(provider_name):
            cfg = self.config.provider(name)
            if not cfg.enabled:
                continue
            try:
                request.model = request.model or cfg.model
                return self.build(name).chat(request)
            except ProviderError as exc:
                audit("provider_failure", str(exc))
                errors.append(str(exc))
        raise ProviderError("; ".join(errors) or "No provider available")

    def stream_with_fallback(self, request: ChatRequest, provider_name: str | None = None) -> Iterable[str]:
        errors = []
        for name in self.provider_order(provider_name):
            cfg = self.config.provider(name)
            if not cfg.enabled:
                continue
            try:
                request.model = request.model or cfg.model
                yield from self.build(name).stream(request)
                return
            except ProviderError as exc:
                audit("provider_stream_failure", str(exc))
                errors.append(str(exc))
        raise ProviderError("; ".join(errors) or "No provider available")
