from __future__ import annotations

from typing import Any

from synapse.health.contracts import HealthCheckContext, HealthContribution
from synapse.health.contributors.base import check, checks, component


class AgentsHealthContributor:
    contributor_id = "agents"

    def __init__(
        self, agents: Any, presence: Any, provisioning: Any, admin: Any, model_hub: Any
    ) -> None:
        self.agents = agents
        self.presence = presence
        self.provisioning = provisioning
        self.admin = admin
        self.model_hub = model_hub
        self.tool_discovery_runtime_available = False

    def collect_health(self, context: HealthCheckContext) -> HealthContribution:
        presences = {item.agent_id: item for item in self.presence.list_all()}
        attention: list[dict[str, Any]] = []
        for agent in self.agents.list_agents():
            current = presences.get(agent.id)
            if not current:
                attention.append({"agent_id": agent.id, "state": "offline", "source": "presence"})
            elif current.state in {"error", "offline"}:
                attention.append(
                    {
                        "agent_id": agent.id,
                        "state": current.state,
                        "activity": current.activity,
                        "source": "presence",
                    }
                )
        pending_provisioning = (
            sum(
                item.status == "awaiting_approval"
                for item in self.provisioning.list_provisioning_requests()
            )
            if self.provisioning
            else 0
        )
        pending_admin = (
            sum(
                item.status == "awaiting_approval"
                for item in self.admin.list_admin_action_requests()
            )
            if self.admin
            else 0
        )
        entries = self.admin.list_agents(include_archived=True) if self.admin else []
        archived = sum(item.is_archived for item in entries)
        inactive = sum(item.status != "active" for item in entries)
        user_agents = sum(not item.is_seed_agent for item in entries)
        return HealthContribution(
            components=(component(0, "agents", self.agents, []),),
            summary={
                "agents_attention": attention,
                "pending_agent_provisioning_requests": pending_provisioning,
                "pending_admin_action_requests": pending_admin,
                "archived_agents": archived,
                "inactive_agents": inactive,
                "user_agent_count": user_agents,
            },
            checks=checks(
                check(
                    3,
                    "provisioning.pending",
                    pending_provisioning > 0,
                    "warning",
                    f"{pending_provisioning} pending provisioning request(s)",
                ),
                check(
                    4,
                    "admin_actions.pending",
                    pending_admin > 0,
                    "warning",
                    f"{pending_admin} pending admin action request(s)",
                ),
                check(
                    5,
                    "agents.error",
                    any(item["state"] == "error" for item in attention),
                    "warning",
                    "agent(s) in error state",
                    {"agents": attention},
                ),
                check(
                    6,
                    "agents.offline",
                    any(item["state"] == "offline" for item in attention),
                    "info",
                    "agent(s) offline",
                    {"agents": attention},
                ),
                check(
                    12,
                    "agents.archived_or_inactive",
                    archived > 0 or inactive > 0,
                    "info",
                    f"{archived} archived, {inactive} inactive agent(s)",
                ),
            ),
        )
