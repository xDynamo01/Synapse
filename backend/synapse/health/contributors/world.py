from __future__ import annotations

from typing import Any

from synapse.health.contracts import HealthCheckContext, HealthContribution
from synapse.health.contributors.base import component


class WorldHealthContributor:
    contributor_id = "world_and_desktop"

    def __init__(
        self, world_state: Any, attention: Any, agent_loop: Any, desktop_automation: Any
    ) -> None:
        self.world_state = world_state
        self.attention = attention
        self.agent_loop = agent_loop
        self.desktop_automation = desktop_automation

    def collect_health(self, context: HealthCheckContext) -> HealthContribution:
        return HealthContribution(
            components=(
                component(
                    15,
                    "world_state",
                    self.world_state,
                    ["observability"],
                    details=self.world_state.health() if self.world_state else {},
                ),
                component(
                    16,
                    "attention",
                    self.attention,
                    ["world_state", "observability"],
                    details=self.attention.health() if self.attention else {},
                ),
                component(
                    17,
                    "agent_loop",
                    self.agent_loop,
                    ["world_state", "attention", "policy"],
                    details=self.agent_loop.health() if self.agent_loop else {},
                ),
                component(
                    27,
                    "desktop_automation",
                    self.desktop_automation,
                    ["policy", "observability"],
                    details=self.desktop_automation.health() if self.desktop_automation else {},
                ),
            )
        )
