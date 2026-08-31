from __future__ import annotations

import shlex
from dataclasses import asdict
from typing import Any

from synapse.commands.context import CommandContext, CommandInvocation, CommandResult
from synapse.commands.errors import UnknownCommandError
from synapse.commands.handlers.base import BaseCommandHandler
from synapse.commands.registry import CommandMetadata
from synapse.core.permissions import PermissionContext
from synapse.resources.models import ResourceRef
from synapse.tools.models import ToolExecutionRequest


class ToolsExecutionCommandHandler(BaseCommandHandler):
    metadata = (
        CommandMetadata(
            name="/tools",
            aliases=(),
            domain="tools_execution",
            handler="ToolsExecutionCommandHandler",
            argument_names=(),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="89bdf0280084bbdd29d4cafc11004b41b79ee27a2937cfbe6ed82a2182b8c49f",
        ),
        CommandMetadata(
            name="/tool",
            aliases=(),
            domain="tools_execution",
            handler="ToolsExecutionCommandHandler",
            argument_names=("tool_id",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="67065eae90929785459069141227b2dba867a5ee9e66137754e329bcb7ee6026",
        ),
        CommandMetadata(
            name="/tool-health",
            aliases=(),
            domain="tools_execution",
            handler="ToolsExecutionCommandHandler",
            argument_names=(),
            defaults=(),
            category="diagnostics",
            status="active",
            source_sha256="7146f33808a4244e8d294602a3f3a8623d0b7c428d2aab8d7d9d0b236b85bdf1",
        ),
        CommandMetadata(
            name="/run-tool",
            aliases=(),
            domain="tools_execution",
            handler="ToolsExecutionCommandHandler",
            argument_names=("context", "argument_text"),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="f9ac0c684aeb1feb6cdd308423e17128ba062a894d59b771bf61012450425485",
        ),
        CommandMetadata(
            name="/tool-decision",
            aliases=(),
            domain="tools_execution",
            handler="ToolsExecutionCommandHandler",
            argument_names=("context", "argument_text"),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="81f1b7d163fd2c9a71a33094253f7dd8516ca3355d856d75a81e39355dff7f42",
        ),
        CommandMetadata(
            name="/agent-tools",
            aliases=(),
            domain="tools_execution",
            handler="ToolsExecutionCommandHandler",
            argument_names=("agent_id",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="a74b4a2da215a3ba05c29edc8fcf0330150be2233d6e7fbaee248a6a2ddfba4c",
        ),
        CommandMetadata(
            name="/tool-catalog",
            aliases=(),
            domain="tools_execution",
            handler="ToolsExecutionCommandHandler",
            argument_names=(),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="a18eae35cdf481c3b6630f67341884fd6c157fcf8ed6f991d932fe7703f066c9",
        ),
        CommandMetadata(
            name="/tool-explain",
            aliases=(),
            domain="tools_execution",
            handler="ToolsExecutionCommandHandler",
            argument_names=("tool_id",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="5dce0cadff69b452304d0e74e521799b9cc3a4cbdc75bcbe646e455eacbba67f",
        ),
        CommandMetadata(
            name="/tool-intents",
            aliases=(),
            domain="tools_execution",
            handler="ToolsExecutionCommandHandler",
            argument_names=(),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="f50852078f810405970e93260d374219fef7a412d03e8c680916b2e1809fd11c",
        ),
        CommandMetadata(
            name="/tool-intent",
            aliases=(),
            domain="tools_execution",
            handler="ToolsExecutionCommandHandler",
            argument_names=("intent_id",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="042d11429820ad592acd8b970dcdefb9dc4725fc1d619b70378bb1e0ddcff0e8",
        ),
        CommandMetadata(
            name="/propose-tool",
            aliases=(),
            domain="tools_execution",
            handler="ToolsExecutionCommandHandler",
            argument_names=("context", "argument_text"),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="3b0a7ce5150d5e8e25cc7876ea3be5a156f6ddfeed7536b30821dc1db7923b4b",
        ),
        CommandMetadata(
            name="/approve-tool-intent",
            aliases=(),
            domain="tools_execution",
            handler="ToolsExecutionCommandHandler",
            argument_names=("context", "intent_id"),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="7d6eb2d2fee110ae20ba0c631751159b8a4d9ec9de0ce67a0c571a0fd8d6caac",
        ),
        CommandMetadata(
            name="/reject-tool-intent",
            aliases=(),
            domain="tools_execution",
            handler="ToolsExecutionCommandHandler",
            argument_names=("context", "intent_id"),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="d38d5984ebe20cfe3e3ae7c7f01df0bfb86b6868500bfa5ee861468061089c3b",
        ),
        CommandMetadata(
            name="/cancel-tool-intent",
            aliases=(),
            domain="tools_execution",
            handler="ToolsExecutionCommandHandler",
            argument_names=("context", "intent_id"),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="1c4a019455535bc844941841fee422a997afdd5dea173fb13e555848952f8c8b",
        ),
        CommandMetadata(
            name="/mcp-servers",
            aliases=(),
            domain="tools_execution",
            handler="ToolsExecutionCommandHandler",
            argument_names=(),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="c2f6b8cdb4d6a450763de0ecc4918610831e8880f29fa2a05c383ebe6c4bf6f0",
        ),
        CommandMetadata(
            name="/mcp-server",
            aliases=(),
            domain="tools_execution",
            handler="ToolsExecutionCommandHandler",
            argument_names=("server_id",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="ed0c7c13163f6399039a6cb79a2bdffd9b64f5e9dde3b97a7779b1a2324e1695",
        ),
        CommandMetadata(
            name="/mcp-tools",
            aliases=(),
            domain="tools_execution",
            handler="ToolsExecutionCommandHandler",
            argument_names=(),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="c4e04c87a7e8854ca5ed7bb811b3bca28578f56bffd648183bd604dace8cf124",
        ),
        CommandMetadata(
            name="/mcp-summary",
            aliases=(),
            domain="tools_execution",
            handler="ToolsExecutionCommandHandler",
            argument_names=(),
            defaults=(),
            category="diagnostics",
            status="active",
            source_sha256="3e83e986247de7bef799aed0ec854d2ff45591e640aef64359b4c56b4ab09be9",
        ),
        CommandMetadata(
            name="/mcp-bridge",
            aliases=(),
            domain="tools_execution",
            handler="ToolsExecutionCommandHandler",
            argument_names=(),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="e2c5ef82cee47ded35c22611a12c6a4d588328e43b334d79cf8537dff951c418",
        ),
        CommandMetadata(
            name="/mcp-bridge-sync",
            aliases=(),
            domain="tools_execution",
            handler="ToolsExecutionCommandHandler",
            argument_names=(),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="9950bd0cefba68b75ee8d0d6331abd399d153f457d69965f6b1ded351177660b",
        ),
        CommandMetadata(
            name="/mcp-bridge-tool",
            aliases=(),
            domain="tools_execution",
            handler="ToolsExecutionCommandHandler",
            argument_names=("bridge_tool_id",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="5f725dac073ce30e8f37f82f501c6be04dc78a5efaf2a4aa403910b7406c7a20",
        ),
        CommandMetadata(
            name="/execution-targets",
            aliases=(),
            domain="tools_execution",
            handler="ToolsExecutionCommandHandler",
            argument_names=(),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="42b82a3e8247ed581530c0239dad87aedb6ddb7b74d835051afdc497802491c7",
        ),
        CommandMetadata(
            name="/execution-plan",
            aliases=(),
            domain="tools_execution",
            handler="ToolsExecutionCommandHandler",
            argument_names=("tool_id",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="e27aa9f0f8ccd8bde46aa4fb3b18d1a704c1f889a5a8c005c4c0d9a276832786",
        ),
        CommandMetadata(
            name="/execution-summary",
            aliases=(),
            domain="tools_execution",
            handler="ToolsExecutionCommandHandler",
            argument_names=(),
            defaults=(),
            category="diagnostics",
            status="active",
            source_sha256="82f4e2ea4fa925e83d3380c656e396111fbe25ca35d862c1aa06364d5593eeee",
        ),
        CommandMetadata(
            name="/tool-call-preview",
            aliases=(),
            domain="tools_execution",
            handler="ToolsExecutionCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="internal/test",
            status="active",
            source_sha256="94090877878d91358cf14675666c7d5177372c80219ed6309452a2c7c05a216a",
        ),
        CommandMetadata(
            name="/tool-call-create",
            aliases=(),
            domain="tools_execution",
            handler="ToolsExecutionCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="f2194e6f91c7dacae28dd6749b1ac5f149f3dfabd4cb4d721cff38f6a3d8e8e1",
        ),
        CommandMetadata(
            name="/execute-tool-intent",
            aliases=(),
            domain="tools_execution",
            handler="ToolsExecutionCommandHandler",
            argument_names=("context", "intent_id"),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="adbf35de1f2b162f8e18195556d458f17593fe1cfd8dced89d89c4c9f17396df",
        ),
        CommandMetadata(
            name="/tool-intent-execution",
            aliases=(),
            domain="tools_execution",
            handler="ToolsExecutionCommandHandler",
            argument_names=("intent_id",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="da82b7eb7181ee2482a32b2ffde8e87ab9a0e515965c9e9b7af24f89ce071dfc",
        ),
    )

    def execute(
        self,
        command_context: CommandContext,
        invocation: CommandInvocation,
    ) -> CommandResult:
        command = invocation.command_name
        argument_text = invocation.argument_text
        context = command_context.permission
        if command == "/tools":
            return self._tools()
        if command == "/tool":
            return self._tool(argument_text)
        if command == "/tool-health":
            return self._tool_health()
        if command == "/run-tool":
            return self._run_tool(context, argument_text)
        if command == "/tool-decision":
            return self._tool_decision(context, argument_text)
        if command == "/agent-tools":
            return self._agent_tools(argument_text)
        if command == "/tool-catalog":
            return self._tool_catalog()
        if command == "/tool-explain":
            return self._tool_explain(argument_text)
        if command == "/tool-intents":
            return self._tool_intents()
        if command == "/tool-intent":
            return self._tool_intent(argument_text)
        if command == "/propose-tool":
            return self._propose_tool(context, argument_text)
        if command == "/approve-tool-intent":
            return self._approve_tool_intent(context, argument_text)
        if command == "/reject-tool-intent":
            return self._reject_tool_intent(context, argument_text)
        if command == "/cancel-tool-intent":
            return self._cancel_tool_intent(context, argument_text)
        if command == "/mcp-servers":
            return self._mcp_servers()
        if command == "/mcp-server":
            return self._mcp_server(argument_text)
        if command == "/mcp-tools":
            return self._mcp_tools()
        if command == "/mcp-summary":
            return self._mcp_summary()
        if command == "/mcp-bridge":
            return self._mcp_bridge()
        if command == "/mcp-bridge-sync":
            return self._mcp_bridge_sync()
        if command == "/mcp-bridge-tool":
            return self._mcp_bridge_tool(argument_text)
        if command == "/execution-targets":
            return self._execution_targets()
        if command == "/execution-plan":
            return self._execution_plan(argument_text)
        if command == "/execution-summary":
            return self._execution_summary()
        if command == "/tool-call-preview":
            return self._tool_call_preview(argument_text)
        if command == "/tool-call-create":
            return self._tool_call_create(argument_text)
        if command == "/execute-tool-intent":
            return self._execute_tool_intent(context, argument_text)
        if command == "/tool-intent-execution":
            return self._tool_intent_execution(argument_text)
        raise UnknownCommandError(command)

    def _tools(self) -> CommandResult:
        tools = [asdict(tool) for tool in self.tool_runtime.list_tools()]
        return CommandResult(
            command="/tools",
            status="ok",
            output=f"{len(tools)} runtime tool(s)",
            data={"tools": tools},
        )

    def _tool(self, tool_id: str) -> CommandResult:
        if not tool_id:
            return CommandResult(command="/tool", status="error", output="Usage: /tool <tool_id>")
        try:
            tool = self.tool_runtime.get_tool(tool_id)
        except Exception as exc:
            return CommandResult(command="/tool", status="error", output=str(exc))
        return CommandResult(
            command="/tool",
            status="ok",
            output=tool.display_name,
            data={"tool": asdict(tool)},
        )

    def _tool_health(self) -> CommandResult:
        health = {tool_id: asdict(item) for tool_id, item in self.tool_runtime.health().items()}
        return CommandResult(
            command="/tool-health",
            status="ok",
            output=f"{len(health)} runtime tool health record(s)",
            data={"health": health},
        )

    def _agent_tools(self, agent_id: str) -> CommandResult:
        if not agent_id:
            return CommandResult(
                command="/agent-tools",
                status="error",
                output="Usage: /agent-tools <agent_id>",
            )
        try:
            catalog = self.tool_discovery.catalog_for_agent(agent_id)
        except Exception as exc:
            return CommandResult(command="/agent-tools", status="error", output=str(exc))
        return CommandResult(
            command="/agent-tools",
            status="ok",
            output=f"{catalog.available_tools}/{catalog.total_tools} tool(s) available",
            data={"catalog": asdict(catalog)},
        )

    def _tool_catalog(self) -> CommandResult:
        catalog = self.tool_discovery.catalog_for_user()
        return CommandResult(
            command="/tool-catalog",
            status="ok",
            output=f"{catalog.available_tools}/{catalog.total_tools} tool(s) available",
            data={"catalog": asdict(catalog)},
        )

    def _tool_explain(self, tool_id: str) -> CommandResult:
        if not tool_id:
            return CommandResult(
                command="/tool-explain",
                status="error",
                output="Usage: /tool-explain <tool_id>",
            )
        try:
            explanation = self.tool_discovery.explain_tool(tool_id)
        except Exception as exc:
            return CommandResult(command="/tool-explain", status="error", output=str(exc))
        return CommandResult(
            command="/tool-explain",
            status="ok",
            output=explanation.tool.display_name,
            data={"tool": asdict(explanation)},
        )

    def _tool_intents(self) -> CommandResult:
        intents = [asdict(intent) for intent in self.tool_intents.list_intents()]
        return CommandResult(
            command="/tool-intents",
            status="ok",
            output=f"{len(intents)} tool intent(s)",
            data={"intents": intents},
        )

    def _tool_intent(self, intent_id: str) -> CommandResult:
        if not intent_id:
            return CommandResult(
                command="/tool-intent",
                status="error",
                output="Usage: /tool-intent <intent_id>",
            )
        try:
            intent = self.tool_intents.get_intent(intent_id)
        except Exception as exc:
            return CommandResult(command="/tool-intent", status="error", output=str(exc))
        return CommandResult(
            command="/tool-intent",
            status="ok",
            output=f"Tool intent {intent.intent_id}: {intent.status}",
            data={"intent": asdict(intent)},
        )

    def _propose_tool(self, context: PermissionContext, argument_text: str) -> CommandResult:
        parts = shlex.split(argument_text)
        if not parts:
            return CommandResult(
                command="/propose-tool",
                status="error",
                output="Usage: /propose-tool <tool_id> [key=value ...]",
            )
        tool_id = parts[0]
        _, arguments = self._parse_tool_arguments(parts[1:])
        try:
            intent = self.tool_intents.create_intent(
                tool_id,
                arguments,
                source="agent" if context.actor_type == "agent" else "user",
                source_agent_id=context.actor_id if context.actor_type == "agent" else None,
                metadata={"source": "command_runtime"},
            )
        except Exception as exc:
            return CommandResult(command="/propose-tool", status="error", output=str(exc))
        return CommandResult(
            command="/propose-tool",
            status="ok",
            output=f"Tool intent proposed: {intent.intent_id}",
            data={"intent": asdict(intent)},
        )

    def _approve_tool_intent(self, context: PermissionContext, intent_id: str) -> CommandResult:
        return self._review_tool_intent(context, intent_id, "approved")

    def _reject_tool_intent(self, context: PermissionContext, intent_id: str) -> CommandResult:
        return self._review_tool_intent(context, intent_id, "rejected")

    def _cancel_tool_intent(self, context: PermissionContext, intent_id: str) -> CommandResult:
        if not intent_id:
            return CommandResult(
                command="/cancel-tool-intent",
                status="error",
                output="Usage: /cancel-tool-intent <intent_id>",
            )
        try:
            intent = self.tool_intents.cancel_intent(intent_id, context.actor_id)
        except Exception as exc:
            return CommandResult(command="/cancel-tool-intent", status="error", output=str(exc))
        return CommandResult(
            command="/cancel-tool-intent",
            status="ok",
            output=f"Tool intent cancelled: {intent.intent_id}",
            data={"intent": asdict(intent)},
        )

    def _review_tool_intent(
        self,
        context: PermissionContext,
        intent_id: str,
        decision: str,
    ) -> CommandResult:
        command = {
            "approved": "/approve-tool-intent",
            "rejected": "/reject-tool-intent",
        }[decision]
        if not intent_id:
            return CommandResult(
                command=command,
                status="error",
                output=f"Usage: {command} <intent_id>",
            )
        try:
            intent = self.tool_intents.review_intent(
                intent_id,
                decision,
                reviewed_by=context.actor_id,
            )
        except Exception as exc:
            return CommandResult(command=command, status="error", output=str(exc))
        return CommandResult(
            command=command,
            status="ok",
            output=f"Tool intent {decision}: {intent.intent_id}",
            data={"intent": asdict(intent)},
        )

    def _mcp_servers(self) -> CommandResult:
        servers = [asdict(server) for server in self.mcp.list_servers()]
        return CommandResult(
            command="/mcp-servers",
            status="ok",
            output=f"{len(servers)} MCP server manifest(s)",
            data={"servers": servers},
        )

    def _mcp_server(self, server_id: str) -> CommandResult:
        if not server_id:
            return CommandResult(
                command="/mcp-server",
                status="error",
                output="Usage: /mcp-server <server_id>",
            )
        try:
            server = self.mcp.get_server(server_id)
        except Exception as exc:
            return CommandResult(command="/mcp-server", status="error", output=str(exc))
        return CommandResult(
            command="/mcp-server",
            status="ok",
            output=server.display_name,
            data={"server": asdict(server)},
        )

    def _mcp_tools(self) -> CommandResult:
        tools = [asdict(tool) for tool in self.mcp.list_tools()]
        return CommandResult(
            command="/mcp-tools",
            status="ok",
            output=f"{len(tools)} MCP tool reference(s)",
            data={"tools": tools},
        )

    def _mcp_summary(self) -> CommandResult:
        summary = asdict(self.mcp.summary())
        return CommandResult(
            command="/mcp-summary",
            status="ok",
            output=f"{summary['total_servers']} MCP server manifest(s)",
            data={"summary": summary},
        )

    def _mcp_bridge(self) -> CommandResult:
        status = asdict(self.mcp_bridge.bridge_status())
        tools = [asdict(tool) for tool in self.mcp_bridge.list_bridge_tools()]
        return CommandResult(
            command="/mcp-bridge",
            status="ok",
            output=f"{status['bridged_tools']} MCP tool(s) bridged",
            data={"status": status, "tools": tools},
        )

    def _mcp_bridge_sync(self) -> CommandResult:
        status = asdict(self.mcp_bridge.sync_from_mcp_registry())
        return CommandResult(
            command="/mcp-bridge-sync",
            status="ok",
            output=f"{status['bridged_tools']} MCP tool(s) bridged",
            data={"status": status},
        )

    def _mcp_bridge_tool(self, bridge_tool_id: str) -> CommandResult:
        if not bridge_tool_id:
            return CommandResult(
                command="/mcp-bridge-tool",
                status="error",
                output="Usage: /mcp-bridge-tool <bridge_tool_id>",
            )
        try:
            explanation = self.mcp_bridge.explain_bridge_tool(bridge_tool_id)
        except Exception as exc:
            return CommandResult(command="/mcp-bridge-tool", status="error", output=str(exc))
        return CommandResult(
            command="/mcp-bridge-tool",
            status="ok",
            output=bridge_tool_id,
            data=explanation,
        )

    def _execution_targets(self) -> CommandResult:
        targets = [asdict(target) for target in self.execution_router.registry.list_targets()]
        return CommandResult(
            command="/execution-targets",
            status="ok",
            output=f"{len(targets)} execution target(s)",
            data={"targets": targets},
        )

    def _execution_plan(self, tool_id: str) -> CommandResult:
        if not tool_id:
            return CommandResult(
                command="/execution-plan",
                status="error",
                output="Usage: /execution-plan <tool_id>",
            )
        try:
            plan = self.execution_router.route_tool(tool_id)
        except Exception as exc:
            return CommandResult(command="/execution-plan", status="error", output=str(exc))
        return CommandResult(
            command="/execution-plan",
            status="ok",
            output=f"Selected target: {plan.selected_target.target_id}",
            data={"plan": asdict(plan)},
        )

    def _execution_summary(self) -> CommandResult:
        summary = asdict(self.execution_router.execution_summary())
        return CommandResult(
            command="/execution-summary",
            status="ok",
            output=f"{summary['registered_targets']} execution target(s)",
            data={"summary": summary},
        )

    def _tool_call_preview(self, argument_text: str) -> CommandResult:
        return self._tool_call_bridge(argument_text, create=False)

    def _tool_call_create(self, argument_text: str) -> CommandResult:
        return self._tool_call_bridge(argument_text, create=True)

    def _tool_call_bridge(self, argument_text: str, *, create: bool) -> CommandResult:
        command = "/tool-call-create" if create else "/tool-call-preview"
        try:
            parts = shlex.split(argument_text)
        except ValueError as exc:
            return CommandResult(command=command, status="error", output=str(exc))
        if len(parts) < 2:
            return CommandResult(
                command=command,
                status="error",
                output=f'Usage: {command} <agent_id> "<text>"',
            )
        agent_id = parts[0]
        text = " ".join(parts[1:])
        try:
            result = (
                self.agent_tool_calling.create_intents_from_output(agent_id, text)
                if create
                else self.agent_tool_calling.preview_tool_calling(agent_id, text)
            )
        except Exception as exc:
            return CommandResult(command=command, status="error", output=str(exc))
        return CommandResult(
            command=command,
            status="ok" if not result.errors else "error",
            output=(
                f"Created {len(result.created_intents)} tool intent(s)"
                if create
                else f"Previewed {result.metadata.get('proposal_count', 0)} proposal(s)"
            ),
            data={"result": asdict(result)},
        )

    def _execute_tool_intent(
        self,
        context: PermissionContext,
        intent_id: str,
    ) -> CommandResult:
        if not intent_id:
            return CommandResult(
                command="/execute-tool-intent",
                status="error",
                output="Usage: /execute-tool-intent <intent_id>",
            )
        try:
            intent = self.tool_intents.execute_intent(intent_id, context.actor_id)
        except Exception as exc:
            return CommandResult(command="/execute-tool-intent", status="error", output=str(exc))
        return CommandResult(
            command="/execute-tool-intent",
            status="ok" if intent.status == "executed" else "error",
            output=f"Tool intent execution status: {intent.status}",
            data={"intent": asdict(intent)},
        )

    def _tool_intent_execution(self, intent_id: str) -> CommandResult:
        if not intent_id:
            return CommandResult(
                command="/tool-intent-execution",
                status="error",
                output="Usage: /tool-intent-execution <intent_id>",
            )
        try:
            summary = self.tool_intents.execution_summary(intent_id)
        except Exception as exc:
            return CommandResult(command="/tool-intent-execution", status="error", output=str(exc))
        return CommandResult(
            command="/tool-intent-execution",
            status="ok",
            output=f"Tool intent status: {summary['status']}",
            data={"execution": summary},
        )

    def _run_tool(self, context: PermissionContext, argument_text: str) -> CommandResult:
        parts = shlex.split(argument_text)
        if not parts:
            return CommandResult(
                command="/run-tool",
                status="error",
                output="Usage: /run-tool <tool_id> [key=value ...]",
            )
        tool_id = parts[0]
        options, arguments = self._parse_tool_arguments(parts[1:])
        result = self.tool_runtime.execute(
            ToolExecutionRequest(
                tool_id=tool_id,
                arguments=arguments,
                caller=context.actor_id,
                caller_type=context.actor_type,
                agent_id=options.get("agent"),
                resource_ref=self._resource_ref_from_text(options.get("resource")),
                dry_run=bool(options.get("dry_run")),
                metadata={"source": "command_runtime"},
            )
        )
        return CommandResult(
            command="/run-tool",
            status="ok" if result.success else "error",
            output=f"Tool {tool_id} {'executed' if result.success else 'failed'}.",
            data={"result": asdict(result)},
        )

    def _tool_decision(self, context: PermissionContext, argument_text: str) -> CommandResult:
        parts = shlex.split(argument_text)
        if not parts:
            return CommandResult(
                command="/tool-decision",
                status="error",
                output="Usage: /tool-decision <tool_id> [--agent <agent_id>] [--resource <type:id>]",
            )
        tool_id = parts[0]
        options, arguments = self._parse_tool_arguments(parts[1:])
        try:
            definition = self.tool_runtime.get_tool(tool_id)
            decision = self.tool_runtime.permission_bridge.evaluate(
                definition,
                ToolExecutionRequest(
                    tool_id=tool_id,
                    arguments=arguments,
                    caller=context.actor_id,
                    caller_type=context.actor_type,
                    agent_id=options.get("agent"),
                    resource_ref=self._resource_ref_from_text(options.get("resource")),
                    dry_run=True,
                    metadata={"source": "command_runtime"},
                ),
            )
        except Exception as exc:
            return CommandResult(command="/tool-decision", status="error", output=str(exc))
        return CommandResult(
            command="/tool-decision",
            status="ok",
            output=(
                "Tool decision: "
                + (
                    "allowed"
                    if decision.allowed
                    else "requires approval"
                    if decision.requires_approval
                    else "blocked"
                )
            ),
            data={"decision": asdict(decision)},
        )

    @staticmethod
    def _parse_tool_arguments(parts: list[str]) -> tuple[dict[str, Any], dict[str, Any]]:
        options: dict[str, Any] = {}
        arguments: dict[str, Any] = {}
        index = 0
        while index < len(parts):
            part = parts[index]
            if part == "--dry-run":
                options["dry_run"] = True
                index += 1
                continue
            if part in {"--agent", "--resource"} and index + 1 < len(parts):
                options[part.removeprefix("--").replace("-", "_")] = parts[index + 1]
                index += 2
                continue
            key, separator, value = part.partition("=")
            if separator:
                arguments[key] = value
            index += 1
        return options, arguments

    @staticmethod
    def _resource_ref_from_text(value: str | None) -> ResourceRef | None:
        if not value:
            return None
        resource_type, separator, identifier = value.partition(":")
        if not separator:
            return None
        if resource_type == "file":
            return ResourceRef(resource_type="file", path=identifier)
        return ResourceRef(resource_type=resource_type, resource_id=identifier)
