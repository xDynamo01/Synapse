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
from synapse.tools.calls import ToolCallPlan, ToolCallResult
from synapse.tools.router import ToolRouter


@dataclass(frozen=True)
class AgentRunResult:
    agent_id: str
    response: str
    model: dict[str, Any]
    tools: list[dict[str, Any]] = field(default_factory=list)
    tool_calling: str = "supported"
    tool_results: list[ToolCallResult] = field(default_factory=list)


class AgentRuntime:
    def __init__(
        self,
        agents: AgentRegistry,
        models: ModelRouter,
        tools: ToolRegistry,
        tool_router: ToolRouter,
        event_bus: EventBus,
    ):
        self.agents = agents
        self.models = models
        self.tools = tools
        self.tool_router = tool_router
        self.event_bus = event_bus

    def run(
        self,
        context: PermissionContext,
        agent_id: str,
        loaded_context: LoadedContext,
        user_message: str,
        session_id: str | None = None,
        project_id: str | None = None,
        original_message_id: str | None = None,
    ) -> AgentRunResult:
        agent = self.agents.get(agent_id)
        allowed_tools = self._allowed_tools(agent.permissions)
        self.event_bus.emit(
            "agent.run.started",
            context.actor_id,
            {
                "agent_id": agent_id,
                "tool_calling": "supported",
                "allowed_tools": [tool["name"] for tool in allowed_tools],
            },
        )
        model_response = self.models.generate(
            agent=agent,
            user_message=user_message,
            context=loaded_context.to_dict(),
            tools=allowed_tools,
        )
        tool_results: list[ToolCallResult] = []
        final_response = model_response.content
        if model_response.tool_calls:
            tool_context = PermissionContext(
                actor_id=agent.id,
                actor_type="agent",
                device_id=context.device_id,
                autonomy=context.autonomy,
            )
            plan = ToolCallPlan(calls=model_response.tool_calls)
            tool_results = self.tool_router.execute_plan(
                tool_context,
                plan,
                allowed_permissions=agent.permissions,
                session_id=session_id,
                project_id=project_id,
                original_message_id=original_message_id,
            )
            final_response = self._response_after_tools(model_response, tool_results)
        result = AgentRunResult(
            agent_id=agent_id,
            response=final_response,
            model=self._model_metadata(model_response),
            tools=allowed_tools,
            tool_results=tool_results,
        )
        self.event_bus.emit(
            "agent.run.completed",
            context.actor_id,
            {
                "agent_id": agent_id,
                "model": result.model,
                "tool_calling": result.tool_calling,
                "tool_results": [asdict(tool_result) for tool_result in tool_results],
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

    @staticmethod
    def _response_after_tools(
        response: ModelResponse,
        tool_results: list[ToolCallResult],
    ) -> str:
        summaries = []
        for item in tool_results:
            status = item.status
            summaries.append(f"{item.request.name}:{status}")
        return f"{response.content}\nTool results: {', '.join(summaries)}"
