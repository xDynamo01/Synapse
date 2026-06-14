from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from synapse.agents.registry import AgentRegistry
from synapse.context.loader import LoadedContext
from synapse.core.events import EventBus
from synapse.core.model_router import ModelRouter
from synapse.core.permissions import PermissionContext
from synapse.models.types import ModelResponse
from synapse.tools.base import ToolRegistry


@dataclass(frozen=True)
class AgentRunResult:
    agent_id: str
    response: str
    model: dict[str, Any]
    tools: list[dict[str, Any]] = field(default_factory=list)
    tool_calling: str = "not_implemented"


class AgentRuntime:
    def __init__(
        self,
        agents: AgentRegistry,
        models: ModelRouter,
        tools: ToolRegistry,
        event_bus: EventBus,
    ):
        self.agents = agents
        self.models = models
        self.tools = tools
        self.event_bus = event_bus

    def run(
        self,
        context: PermissionContext,
        agent_id: str,
        loaded_context: LoadedContext,
        user_message: str,
    ) -> AgentRunResult:
        agent = self.agents.get(agent_id)
        allowed_tools = self._allowed_tools(agent.permissions)
        self.event_bus.emit(
            "agent.run.started",
            context.actor_id,
            {
                "agent_id": agent_id,
                "tool_calling": "not_implemented",
                "allowed_tools": [tool["name"] for tool in allowed_tools],
            },
        )
        model_response = self.models.generate(
            agent=agent,
            user_message=user_message,
            context=loaded_context.to_dict(),
            tools=allowed_tools,
        )
        result = AgentRunResult(
            agent_id=agent_id,
            response=model_response.content,
            model=self._model_metadata(model_response),
            tools=allowed_tools,
        )
        self.event_bus.emit(
            "agent.run.completed",
            context.actor_id,
            {
                "agent_id": agent_id,
                "model": result.model,
                "tool_calling": result.tool_calling,
            },
        )
        return result

    def _allowed_tools(self, permissions: list[str]) -> list[dict[str, Any]]:
        permission_set = set(permissions)
        specs = self.tools.list_specs()
        allowed = [
            asdict(spec)
            for spec in specs
            if "*" in permission_set or spec.permission in permission_set
        ]
        return allowed

    @staticmethod
    def _model_metadata(response: ModelResponse) -> dict[str, Any]:
        return {
            "provider": response.provider,
            "model": response.model,
            "metadata": response.metadata,
        }

