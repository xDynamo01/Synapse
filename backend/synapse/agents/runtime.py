from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING, Any

from synapse.agents.registry import AgentRegistry
from synapse.context.loader import LoadedContext
from synapse.core.events import EventBus
from synapse.core.permissions import PermissionContext
from synapse.models.router import ModelRouter
from synapse.models.types import ModelResponse
from synapse.policies.effective import EffectivePolicyRuntime
from synapse.presence.runtime import PresenceRuntime

if TYPE_CHECKING:
    from synapse.agent_tool_calling.runtime import AgentToolCallingRuntime
    from synapse.tool_discovery.models import AgentToolCatalog
    from synapse.tool_discovery.runtime import ToolDiscoveryRuntime
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
    tool_calling_result: dict[str, Any] | None = None


class AgentRuntime:
    def __init__(
        self,
        agents: AgentRegistry,
        policies: EffectivePolicyRuntime,
        models: ModelRouter,
        tool_router: ToolRouter,
        event_bus: EventBus,
        presence: PresenceRuntime | None = None,
        tool_discovery: ToolDiscoveryRuntime | None = None,
        agent_tool_calling: AgentToolCallingRuntime | None = None,
    ):
        self.agents = agents
        self.policies = policies
        self.models = models
        self.tool_router = tool_router
        self.event_bus = event_bus
        self.presence = presence
        self.tool_discovery = tool_discovery
        self.agent_tool_calling = agent_tool_calling

    def available_tools(self, agent_id: str) -> AgentToolCatalog:
        self.agents.get(agent_id)
        if self.tool_discovery is None:
            raise RuntimeError("Tool discovery runtime is unavailable")
        return self.tool_discovery.catalog_for_agent(agent_id)

    def run(
        self,
        context: PermissionContext,
        agent_id: str,
        loaded_context: LoadedContext,
        user_message: str,
        session_id: str | None = None,
        project_id: str | None = None,
        original_message_id: str | None = None,
        model_provider_override: str | None = None,
        model_override: str | None = None,
    ) -> AgentRunResult:
        try:
            self._set_presence(
                agent_id,
                "thinking",
                "Generating agent response",
                session_id=session_id,
                actor_id=context.actor_id,
            )
            agent = self.agents.get(agent_id)
            policy = self.policies.resolve(context, agent_id)
            allowed_tools = [
                tool
                for tool in policy.allowed_tool_specs
                if tool.get("name") not in {"agent.summary", "tool.summary"}
            ]
            self.event_bus.emit(
                "agent.run.started",
                context.actor_id,
                {
                    "agent_id": agent_id,
                    "tool_calling": "supported",
                    "allowed_tools": [tool["name"] for tool in allowed_tools],
                    "policy": policy.to_dict(),
                },
            )
            model_response = self.models.generate(
                agent=agent,
                user_message=user_message,
                context=loaded_context.to_dict(),
                tools=allowed_tools,
                provider_override=model_provider_override,
                model_override=model_override,
            )
            tool_results: list[ToolCallResult] = []
            final_response = model_response.content
            if model_response.tool_calls:
                self._set_presence(
                    agent_id,
                    "working",
                    "Executing tool calls",
                    session_id=session_id,
                    actor_id=context.actor_id,
                )
                tool_context = PermissionContext(
                    actor_id=agent.id,
                    actor_type="agent",
                    device_id=context.device_id,
                    autonomy=context.autonomy,
                )
                plan = ToolCallPlan(calls=model_response.tool_calls)
                blocked_results = []
                allowed_calls = []
                forbidden = set(policy.forbidden_tools)
                for call in plan.calls:
                    if call.name in forbidden:
                        error = f"Tool is forbidden by agent policy for {agent.id}: {call.name}"
                        blocked_results.append(
                            ToolCallResult(
                                request=call,
                                success=False,
                                status="blocked",
                                error=error,
                            )
                        )
                        self.event_bus.emit(
                            "tool.failed",
                            context.actor_id,
                            {
                                "tool_call_id": call.id,
                                "tool": call.name,
                                "success": False,
                                "error": error,
                                "error_type": "AgentEffectivePolicy",
                                "blocked_before_router": True,
                            },
                        )
                    else:
                        allowed_calls.append(call)
                plan = ToolCallPlan(calls=allowed_calls)
                tool_results = self.tool_router.execute_plan(
                    tool_context,
                    plan,
                    allowed_permissions=agent.permissions,
                    session_id=session_id,
                    project_id=project_id,
                    original_message_id=original_message_id,
                    policy=policy,
                )
                tool_results = [*blocked_results, *tool_results]
                final_response = self._response_after_tools(model_response, tool_results)
            tool_calling_result = None
            if self.agent_tool_calling:
                tool_calling_result = asdict(
                    self.agent_tool_calling.process_agent_output(
                        agent_id,
                        final_response,
                    )
                )
            result = AgentRunResult(
                agent_id=agent_id,
                response=final_response,
                model=self._model_metadata(model_response),
                tools=allowed_tools,
                tool_results=tool_results,
                tool_calling_result=tool_calling_result,
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
        except Exception:
            self._set_presence(
                agent_id,
                "error",
                "Agent run failed",
                session_id=session_id,
                actor_id=context.actor_id,
            )
            raise

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

    def _set_presence(
        self,
        agent_id: str,
        state: str,
        activity: str,
        session_id: str | None = None,
        actor_id: str | None = None,
    ) -> None:
        if not self.presence:
            return
        self.presence.set_state(
            agent_id,
            state,
            activity,
            {"current_session_id": session_id, "actor_id": actor_id or agent_id},
        )
