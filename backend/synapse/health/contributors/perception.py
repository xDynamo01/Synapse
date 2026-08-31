from __future__ import annotations

from typing import Any

from synapse.health.contracts import HealthCheckContext, HealthContribution
from synapse.health.contributors.base import check, checks, component
from synapse.health.models import ComponentHealth


class PerceptionHealthContributor:
    contributor_id = "perception"

    def __init__(self, perception: Any, vision: Any) -> None:
        self.perception = perception
        self.vision = vision

    def collect_health(self, context: HealthCheckContext) -> HealthContribution:
        try:
            signals = len(self.perception.list_signals()) if self.perception else 0
        except Exception:
            signals = 0
        vision_health = self.vision.health() if self.vision else {}
        try:
            vision_unavailable = (
                sum(
                    1
                    for key in ("vision", "ocr", "camera")
                    if vision_health.get(key, {}).get("configured")
                    and vision_health.get(key, {}).get("state") not in {"ready", "healthy"}
                )
                if self.vision
                else 0
            )
        except Exception:
            vision_unavailable = 1
        extras = []
        for order, component_id in ((29, "screen_capture"), (30, "camera"), (31, "ocr")):
            details = vision_health.get(component_id, {})
            state = str(details.get("state", "not_configured"))
            configured = state != "not_configured"
            ready = state in {"ready", "healthy"}
            extras.append(
                (
                    order,
                    ComponentHealth(
                        component_id,
                        "synapse.vision",
                        state,
                        configured,
                        ready,
                        ready,
                        configured and not ready,
                        dependencies=["vision"],
                        recommendations=[]
                        if configured
                        else [f"Configure {component_id} only if needed."],
                        metadata=details,
                    ),
                )
            )
        return HealthContribution(
            components=(
                component(7, "perception", self.perception, []),
                component(8, "signal_storage", self.perception, ["perception"]),
                component(10, "vision", self.vision, ["perception"]),
                component(12, "perception_retention", self.perception, ["perception"]),
                *extras,
            ),
            summary={
                "vision_runtime_available": self.vision is not None,
                "vision_provider_unavailable_count": vision_unavailable,
                "perception_runtime_available": self.perception is not None,
                "perception_signal_count": signals,
            },
            checks=checks(
                check(
                    43,
                    "vision.unavailable_runtime",
                    self.vision is None,
                    "warning",
                    "vision runtime unavailable",
                ),
                check(
                    44,
                    "vision.providers_unavailable",
                    vision_unavailable > 0,
                    "warning",
                    f"{vision_unavailable} vision provider(s) unavailable",
                    {"vision_provider_unavailable_count": vision_unavailable},
                ),
                check(
                    45,
                    "perception.unavailable_runtime",
                    self.perception is None,
                    "warning",
                    "perception runtime unavailable",
                ),
            ),
        )
