from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from synapse.agents.models import AgentConfig
from synapse.core.exceptions import ToolExecutionError
from synapse.models.adapters import (
    BaseModelAdapter,
    MockModelAdapter,
    OllamaModelAdapter,
    OpenAICompatibleAdapter,
)
from synapse.models.types import ModelRequest, ModelResponse


@dataclass(frozen=True)
class ModelRoute:
    provider: str
    model: str | None
    base_url: str | None


class ModelRouter:
    def __init__(
        self,
        system_config: dict[str, Any],
        adapters: dict[str, BaseModelAdapter] | None = None,
    ):
        self.system_config = system_config
        self.adapters = adapters or {
            "mock": MockModelAdapter(),
            "ollama": OllamaModelAdapter(),
            "openai_compatible": OpenAICompatibleAdapter(),
        }

    def default_route(self) -> ModelRoute:
        models = self.system_config.get("models", {})
        default_provider = models.get("default_provider", "ollama")
        provider_config = models.get("providers", {}).get(default_provider, {})
        return ModelRoute(
            provider=default_provider,
            model=provider_config.get("model"),
            base_url=provider_config.get("base_url"),
        )

    def route_for_agent(self, agent: AgentConfig) -> ModelRoute:
        if agent.preferred_model:
            provider, model = self._parse_preferred_model(agent.preferred_model)
            provider_config = self.system_config.get("models", {}).get("providers", {}).get(provider, {})
            return ModelRoute(
                provider=provider,
                model=model or provider_config.get("model"),
                base_url=provider_config.get("base_url"),
            )
        return self.default_route()

    def generate(
        self,
        agent: AgentConfig,
        user_message: str,
        context: dict[str, Any],
        tools: list[dict[str, Any]],
    ) -> ModelResponse:
        route = self.route_for_agent(agent)
        if self._should_use_mock(route):
            route = ModelRoute(provider="mock", model=route.model or "mock", base_url=None)

        adapter = self.adapters.get(route.provider)
        if not adapter:
            raise ToolExecutionError(f"No model adapter registered for provider: {route.provider}")

        return adapter.generate(
            ModelRequest(
                agent_id=agent.id,
                provider=route.provider,
                model=route.model,
                base_url=route.base_url,
                user_message=user_message,
                context=context,
                tools=tools,
            )
        )

    def _should_use_mock(self, route: ModelRoute) -> bool:
        if route.provider == "mock":
            return False
        environment = os.environ.get("SYNAPSE_ENV", "").lower()
        mode = str(self.system_config.get("system", {}).get("mode", "")).lower()
        return environment in {"test", "dev"} or mode in {"test", "dev"}

    @staticmethod
    def _parse_preferred_model(preferred_model: str) -> tuple[str, str | None]:
        if "/" not in preferred_model:
            return preferred_model, None
        provider, _, model = preferred_model.partition("/")
        return provider, model or None
