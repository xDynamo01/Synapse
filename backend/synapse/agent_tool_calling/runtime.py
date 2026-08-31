from __future__ import annotations

from dataclasses import asdict
from typing import Any

from synapse.agent_tool_calling.models import (
    AgentToolCallingParseResult,
    AgentToolCallingResult,
)
from synapse.agent_tool_calling.parser import parse_explicit_json_block
from synapse.core.data_dir import DataDir
from synapse.core.serialization import dump_structured_file, load_structured_file
from synapse.execution_router.runtime import ExecutionRouterRuntime
from synapse.tool_discovery.runtime import ToolDiscoveryRuntime
from synapse.tool_intents.runtime import ToolIntentRuntime

DEFAULT_POLICY: dict[str, Any] = {"enabled": False, "mode": "preview"}
POLICY_MODES = {"disabled", "preview", "create_intent"}


class AgentToolCallingRuntime:
    def __init__(
        self,
        data_dir: DataDir,
        intents: ToolIntentRuntime,
        discovery: ToolDiscoveryRuntime,
        execution_router: ExecutionRouterRuntime,
    ) -> None:
        self.data_dir = data_dir
        self.intents = intents
        self.discovery = discovery
        self.execution_router = execution_router
        self.policy_path = self.data_dir.resolve("config/agent_tool_calling_policy.yaml")
        if not self.policy_path.exists():
            dump_structured_file(self.policy_path, DEFAULT_POLICY)

    def parse_agent_output(self, text: str) -> AgentToolCallingParseResult:
        return parse_explicit_json_block(text)

    def create_intents_from_output(
        self,
        agent_id: str,
        text: str,
        conversation_id: str | None = None,
        mission_id: str | None = None,
    ) -> AgentToolCallingResult:
        parsed = self.parse_agent_output(text)
        created: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        errors = list(parsed.errors)
        catalog = self.discovery.catalog_for_agent(agent_id)
        views = {tool.tool_id: tool for tool in catalog.tools}
        for proposal in parsed.proposals:
            view = views.get(proposal.tool_id)
            if view is None:
                errors.append(f"Tool not found in agent catalog: {proposal.tool_id}")
                skipped.append({"proposal": asdict(proposal), "reason": "tool_not_found"})
                continue
            if not view.available:
                reason = view.reason_unavailable or "tool unavailable"
                errors.append(f"Tool unavailable for {agent_id}: {proposal.tool_id}: {reason}")
                skipped.append({"proposal": asdict(proposal), "reason": reason})
                continue
            plan = self.execution_router.route_tool(proposal.tool_id)
            intent = self.intents.create_intent(
                proposal.tool_id,
                proposal.arguments,
                source="agent",
                source_agent_id=agent_id,
                conversation_id=conversation_id,
                mission_id=mission_id,
                metadata={
                    "reason": proposal.reason,
                    "confidence": proposal.confidence,
                    "proposal_metadata": proposal.metadata,
                    "execution_plan": asdict(plan),
                    "created_by": "agent_tool_calling_bridge",
                },
            )
            created.append(asdict(intent))
        return AgentToolCallingResult(
            agent_id=agent_id,
            conversation_id=conversation_id,
            created_intents=created,
            skipped_proposals=skipped,
            errors=errors,
            metadata={"parse_found": parsed.found, "proposal_count": len(parsed.proposals)},
        )

    def preview_tool_calling(
        self,
        agent_id: str,
        text: str,
        conversation_id: str | None = None,
        mission_id: str | None = None,
    ) -> AgentToolCallingResult:
        parsed = self.parse_agent_output(text)
        catalog = self.discovery.catalog_for_agent(agent_id)
        views = {tool.tool_id: tool for tool in catalog.tools}
        previews: list[dict[str, Any]] = []
        errors = list(parsed.errors)
        for proposal in parsed.proposals:
            view = views.get(proposal.tool_id)
            if view is None:
                errors.append(f"Tool not found in agent catalog: {proposal.tool_id}")
                previews.append({"proposal": asdict(proposal), "reason": "tool_not_found"})
                continue
            plan = self.execution_router.route_tool(proposal.tool_id)
            previews.append(
                {
                    "proposal": asdict(proposal),
                    "tool": asdict(view),
                    "execution_plan": asdict(plan),
                }
            )
        return AgentToolCallingResult(
            agent_id=agent_id,
            conversation_id=conversation_id,
            errors=errors,
            metadata={
                "mode": "preview",
                "parse_found": parsed.found,
                "proposal_count": len(parsed.proposals),
                "proposals": previews,
                "mission_id": mission_id,
            },
        )

    def process_agent_output(
        self,
        agent_id: str,
        text: str,
        conversation_id: str | None = None,
        mission_id: str | None = None,
    ) -> AgentToolCallingResult:
        policy = self.load_policy()
        if not policy["enabled"] or policy["mode"] == "disabled":
            return AgentToolCallingResult(
                agent_id=agent_id,
                conversation_id=conversation_id,
                metadata={"mode": "disabled", "policy": policy},
            )
        if policy["mode"] == "create_intent":
            return self.create_intents_from_output(
                agent_id,
                text,
                conversation_id,
                mission_id,
            )
        return self.preview_tool_calling(agent_id, text, conversation_id, mission_id)

    def load_policy(self) -> dict[str, Any]:
        raw = load_structured_file(self.policy_path)
        policy = dict(DEFAULT_POLICY)
        policy.update(raw)
        mode = str(policy.get("mode", "preview"))
        if mode not in POLICY_MODES:
            mode = "disabled"
        policy["mode"] = mode
        policy["enabled"] = bool(policy.get("enabled", False))
        return policy
