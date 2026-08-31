from __future__ import annotations

from dataclasses import replace

from synapse.execution_router.models import ExecutionPlan, ExecutionSummary, ExecutionTarget
from synapse.execution_router.registry import ExecutionTargetRegistry
from synapse.mcp_bridge.runtime import MCPToolBridgeRuntime
from synapse.provider_plugins.runtime import ProviderPluginRuntime
from synapse.providers.runtime import ProviderRuntime
from synapse.tool_intents.runtime import ToolIntentRuntime
from synapse.tools.contracts import ToolExecutionPort


class ExecutionRouterRuntime:
    def __init__(
        self,
        tools: ToolExecutionPort,
        intents: ToolIntentRuntime,
        mcp_bridge: MCPToolBridgeRuntime,
        providers: ProviderRuntime,
        plugins: ProviderPluginRuntime,
        registry: ExecutionTargetRegistry | None = None,
    ) -> None:
        self.tools = tools
        self.intents = intents
        self.mcp_bridge = mcp_bridge
        self.providers = providers
        self.plugins = plugins
        self.registry = registry or ExecutionTargetRegistry()
        self._register_defaults()

    def route_tool(self, tool_id: str) -> ExecutionPlan:
        definition = self.tools.get_tool(tool_id)
        if definition.category == "mcp" or definition.metadata.get("mcp_bridge"):
            return self.route_mcp(tool_id)
        selected = self.registry.get("tool_runtime")
        return ExecutionPlan(
            selected_target=selected,
            fallback_targets=self._fallbacks(exclude={selected.target_id}),
            routing_reason=f"Tool {tool_id} is registered in Tool Runtime.",
        )

    def route_intent(self, intent_id: str) -> ExecutionPlan:
        intent = self.intents.get_intent(intent_id)
        plan = self.route_tool(intent.tool_id)
        return replace(
            plan,
            request_id=intent.intent_id,
            routing_reason=f"Tool intent {intent.intent_id} references {intent.tool_id}. {plan.routing_reason}",
        )

    def route_mcp(self, bridge_tool_id: str) -> ExecutionPlan:
        bridged = self.mcp_bridge.get_bridge_tool(bridge_tool_id)
        base = self.registry.get("mcp_bridge")
        selected = replace(
            base,
            available=bridged.available and base.available,
            metadata={
                **base.metadata,
                "bridge_tool_id": bridge_tool_id,
                "server_id": bridged.server_id,
            },
        )
        return ExecutionPlan(
            selected_target=selected,
            fallback_targets=[self.registry.get("tool_runtime")],
            routing_reason=(
                f"Tool {bridge_tool_id} is an MCP bridge reference; MCP execution is unavailable."
            ),
        )

    def route_provider(self, provider_id: str) -> ExecutionPlan:
        manifest = self.providers.get_provider(provider_id)
        health = self.providers.provider_health(provider_id)
        base = self.registry.get("provider_runtime")
        selected = replace(
            base,
            available=base.available and health.status == "available",
            metadata={
                **base.metadata,
                "provider_id": provider_id,
                "provider_type": manifest.provider_type,
                "provider_status": health.status,
            },
        )
        return ExecutionPlan(
            selected_target=selected,
            fallback_targets=[self.registry.get("plugin_runtime")],
            routing_reason=f"Provider {provider_id} is registered with status {health.status}.",
        )

    def execution_summary(self) -> ExecutionSummary:
        targets = self.registry.list_targets()
        return ExecutionSummary(
            available_targets=sum(target.available for target in targets),
            registered_targets=len(targets),
            routing_table={
                "internal_tool": ["tool_runtime", "provider_runtime", "plugin_runtime"],
                "mcp_tool": ["mcp_bridge", "tool_runtime"],
                "provider": ["provider_runtime", "plugin_runtime"],
                "intent": ["tool_runtime", "mcp_bridge", "provider_runtime", "plugin_runtime"],
            },
        )

    def _fallbacks(self, exclude: set[str]) -> list[ExecutionTarget]:
        return [
            target
            for target in self.registry.list_targets(available=True)
            if target.target_id not in exclude
        ]

    def _register_defaults(self) -> None:
        self.registry.register(
            ExecutionTarget(
                target_type="tool_runtime",
                target_id="tool_runtime",
                available=True,
                priority=100,
                metadata={"executes_in_this_stage": False},
            )
        )
        self.registry.register(
            ExecutionTarget(
                target_type="mcp",
                target_id="mcp_bridge",
                available=False,
                priority=90,
                metadata={"structural_only": True},
            )
        )
        self.registry.register(
            ExecutionTarget(
                target_type="provider",
                target_id="provider_runtime",
                available=True,
                priority=80,
                metadata={"executes_in_this_stage": False},
            )
        )
        self.registry.register(
            ExecutionTarget(
                target_type="plugin",
                target_id="plugin_runtime",
                available=True,
                priority=70,
                metadata={"executes_in_this_stage": False},
            )
        )
