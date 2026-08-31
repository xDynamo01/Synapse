from __future__ import annotations

from typing import Any

from synapse.health.contracts import HealthCheckContext, HealthContribution
from synapse.health.contributors.base import check, checks, component


class ToolsHealthContributor:
    contributor_id = "tools_execution"

    def __init__(
        self,
        approvals: Any,
        tool_runtime: Any,
        tool_intents: Any,
        mcp: Any,
        mcp_bridge: Any,
        execution_router: Any,
    ) -> None:
        self.approvals = approvals
        self.tool_runtime = tool_runtime
        self.tool_intents = tool_intents
        self.mcp = mcp
        self.mcp_bridge = mcp_bridge
        self.execution_router = execution_router
        self.tool_discovery_runtime_available = True
        self.agent_tool_calling_runtime_available = True

    def collect_health(self, context: HealthCheckContext) -> HealthContribution:
        try:
            tool_count = len(self.tool_runtime.list_tools()) if self.tool_runtime else 0
        except Exception:
            tool_count = 0
        approval_count = sum(
            str(item.tool_name).startswith("danger.") or "." in str(item.tool_name)
            for item in self.approvals.list_pending()
        )
        pending = len(self.tool_intents.list_pending_intents()) if self.tool_intents else 0
        executable = len(self.tool_intents.list_intents("approved")) if self.tool_intents else 0
        failed = len(self.tool_intents.list_intents("failed")) if self.tool_intents else 0
        mcp_summary = self.mcp.summary() if self.mcp else None
        bridge = self.mcp_bridge.bridge_status() if self.mcp_bridge else None
        execution = self.execution_router.execution_summary() if self.execution_router else None
        permission_available = (
            self.tool_runtime is not None and self.tool_runtime.permission_bridge is not None
        )
        return HealthContribution(
            components=(component(4, "tools", self.tool_runtime, ["permissions"]),),
            summary={
                "tool_runtime_available": self.tool_runtime is not None,
                "tool_permission_bridge_available": permission_available,
                "tool_discovery_runtime_available": self.tool_discovery_runtime_available,
                "tool_intent_runtime_available": self.tool_intents is not None,
                "pending_tool_intents_count": pending,
                "mcp_runtime_available": self.mcp is not None,
                "mcp_registered_servers": mcp_summary.total_servers if mcp_summary else 0,
                "mcp_registered_tools": mcp_summary.total_tools if mcp_summary else 0,
                "mcp_bridge_runtime_available": self.mcp_bridge is not None,
                "mcp_bridged_tools_count": bridge.bridged_tools if bridge else 0,
                "execution_router_available": self.execution_router is not None,
                "execution_targets_registered": execution.registered_targets if execution else 0,
                "agent_tool_calling_runtime_available": self.agent_tool_calling_runtime_available,
                "executable_tool_intents_count": executable,
                "failed_tool_intents_count": failed,
                "tool_count": tool_count,
                "tool_approval_pending_count": approval_count,
            },
            checks=checks(
                check(
                    47,
                    "tool_runtime.unavailable",
                    self.tool_runtime is None,
                    "warning",
                    "tool runtime unavailable",
                ),
                check(
                    48,
                    "tool_runtime.empty",
                    self.tool_runtime is not None and tool_count == 0,
                    "warning",
                    "no runtime tools registered",
                ),
                check(
                    49,
                    "tool_permission_bridge.unavailable",
                    not permission_available,
                    "warning",
                    "tool permission bridge unavailable",
                ),
                check(
                    50,
                    "tool_discovery.unavailable",
                    not self.tool_discovery_runtime_available,
                    "warning",
                    "tool discovery runtime unavailable",
                ),
                check(
                    51,
                    "tool_intents.unavailable",
                    self.tool_intents is None,
                    "warning",
                    "tool intent runtime unavailable",
                ),
                check(
                    52,
                    "tool_intents.pending",
                    pending > 0,
                    "info",
                    f"{pending} tool intent(s) pending review",
                    {"pending_count": pending},
                ),
                check(53, "mcp.unavailable", self.mcp is None, "info", "MCP runtime unavailable"),
                check(
                    54,
                    "mcp_bridge.unavailable",
                    self.mcp_bridge is None,
                    "info",
                    "MCP tool bridge unavailable",
                ),
                check(
                    55,
                    "execution_router.unavailable",
                    self.execution_router is None,
                    "warning",
                    "execution router unavailable",
                ),
                check(
                    56,
                    "agent_tool_calling.unavailable",
                    not self.agent_tool_calling_runtime_available,
                    "warning",
                    "agent tool calling bridge unavailable",
                ),
                check(
                    57,
                    "tool_runtime.approvals_pending",
                    approval_count > 0,
                    "info",
                    f"{approval_count} tool approval request(s) pending",
                    {"pending_count": approval_count},
                ),
            ),
        )
