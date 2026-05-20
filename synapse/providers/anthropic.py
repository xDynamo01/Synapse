from __future__ import annotations

from typing import Iterable

from synapse.providers.base import BaseProvider, ChatRequest, ProviderError


class AnthropicProvider(BaseProvider):
    def chat(self, request: ChatRequest) -> str:
        raise ProviderError("AnthropicProvider is scaffolded; use an OpenAI-compatible proxy or implement native messages.")

    def stream(self, request: ChatRequest) -> Iterable[str]:
        raise ProviderError("AnthropicProvider is scaffolded; use an OpenAI-compatible proxy or implement native messages.")
