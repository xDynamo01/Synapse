from __future__ import annotations

from typing import Any

from synapse.health.contracts import HealthCheckContext, HealthContribution
from synapse.health.contributors.base import check, checks, component


class IntegrationHealthContributor:
    contributor_id = "context_fusion"

    def __init__(self, context_fusion: Any) -> None:
        self.context_fusion = context_fusion
        self.agent_multimodal_bridge_available = False

    def collect_health(self, context: HealthCheckContext) -> HealthContribution:
        active = 0
        if self.context_fusion is not None and self.context_fusion.conversations is not None:
            active = sum(
                getattr(item, "status", "active") not in {"archived", "deleted"}
                for item in self.context_fusion.conversations.list_conversations()
            )
        return HealthContribution(
            components=(
                component(1, "conversation", self.context_fusion, ["agents"]),
                component(2, "memory", self.context_fusion, []),
                component(11, "context_bridge", self.context_fusion, ["perception", "multimodal"]),
            ),
            summary={
                "context_fusion_runtime_available": self.context_fusion is not None,
                "agent_multimodal_bridge_available": self.agent_multimodal_bridge_available,
            },
            checks=checks(
                check(
                    46,
                    "context_fusion.unavailable_runtime",
                    self.context_fusion is None,
                    "warning",
                    "context fusion runtime unavailable",
                ),
            ),
            metrics={"active_conversations": active},
        )
