from __future__ import annotations

from datetime import UTC, datetime

from synapse.tool_discovery.models import AgentToolCatalog, AgentToolView, ToolExplanation
from synapse.tools.contracts import ToolExecutionPort
from synapse.tools.models import ToolDefinition, ToolExecutionRequest


class ToolDiscoveryRuntime:
    def __init__(self, tools: ToolExecutionPort, default_actor_id: str = "local_owner") -> None:
        self.tools = tools
        self.default_actor_id = default_actor_id

    def catalog_for_agent(self, agent_id: str) -> AgentToolCatalog:
        return self._catalog(agent_id=agent_id, caller=agent_id, caller_type="agent")

    def catalog_for_user(self) -> AgentToolCatalog:
        return self._catalog(
            agent_id=self.default_actor_id,
            caller=self.default_actor_id,
            caller_type="user",
        )

    def summarize(self, agent_id: str) -> dict[str, int | str]:
        catalog = self.catalog_for_agent(agent_id)
        return {
            "agent_id": catalog.agent_id,
            "total_tools": catalog.total_tools,
            "available_tools": catalog.available_tools,
            "unavailable_tools": catalog.unavailable_tools,
            "approval_required_tools": catalog.approval_required_tools,
        }

    def explain_tool(self, tool_id: str) -> ToolExplanation:
        definition = self.tools.get_tool(tool_id)
        view = self._view(
            definition,
            ToolExecutionRequest(
                tool_id=tool_id,
                caller=self.default_actor_id,
                caller_type="user",
                dry_run=True,
                metadata={"source": "tool_discovery"},
            ),
        )
        return ToolExplanation(
            tool=view,
            required_capability=definition.required_capability,
            required_permission=definition.required_permission,
            resource_scope_required=definition.resource_scope_required,
            input_schema=definition.input_schema,
            output_schema=definition.output_schema,
            metadata=definition.metadata,
        )

    def _catalog(self, *, agent_id: str, caller: str, caller_type: str) -> AgentToolCatalog:
        views = [
            self._view(
                definition,
                ToolExecutionRequest(
                    tool_id=definition.tool_id,
                    caller=caller,
                    caller_type=caller_type,
                    agent_id=agent_id if caller_type == "agent" else None,
                    dry_run=True,
                    metadata={"source": "tool_discovery"},
                ),
            )
            for definition in (
                self.tools.registry.list_registered_tools()
                if caller_type == "agent"
                else self.tools.list_tools()
            )
        ]
        available = sum(view.available for view in views)
        approval_required = sum(view.requires_approval for view in views)
        return AgentToolCatalog(
            agent_id=agent_id,
            total_tools=len(views),
            available_tools=available,
            unavailable_tools=len(views) - available,
            approval_required_tools=approval_required,
            generated_at=datetime.now(UTC).isoformat(),
            tools=views,
        )

    def _view(
        self,
        definition: ToolDefinition,
        request: ToolExecutionRequest,
    ) -> AgentToolView:
        if not definition.enabled:
            reason = definition.metadata.get("unavailable_reason", "Tool is disabled")
            return self._unavailable(definition, str(reason))
        if self.tools.permission_bridge is None:
            return self._unavailable(definition, "Tool permission bridge is unavailable")

        try:
            decision = self.tools.permission_bridge.evaluate(definition, request)
        except Exception as exc:
            return self._unavailable(definition, str(exc) or type(exc).__name__)
        available = decision.allowed and not decision.requires_approval
        reason = None
        if decision.requires_approval:
            reason = "Approval required"
        elif decision.blocked:
            reason = "; ".join(decision.blocked_reasons) or "Access blocked"
        return AgentToolView(
            tool_id=definition.tool_id,
            display_name=definition.display_name,
            description=definition.description,
            category=definition.category,
            available=available,
            requires_approval=decision.requires_approval,
            risk_level=definition.risk_level,
            reason_unavailable=reason,
        )

    @staticmethod
    def _unavailable(definition: ToolDefinition, reason: str) -> AgentToolView:
        return AgentToolView(
            tool_id=definition.tool_id,
            display_name=definition.display_name,
            description=definition.description,
            category=definition.category,
            available=False,
            requires_approval=definition.approval_required,
            risk_level=definition.risk_level,
            reason_unavailable=reason,
        )
