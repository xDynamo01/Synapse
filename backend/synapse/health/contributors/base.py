from __future__ import annotations

from typing import Any

from synapse.health.models import ComponentHealth, HealthCheckItem


def component(
    order: int,
    component_id: str,
    runtime: Any,
    dependencies: list[str],
    *,
    details: dict[str, Any] | None = None,
    module: str | None = None,
) -> tuple[int, ComponentHealth]:
    available = runtime is not None
    metadata = details or {}
    state = str(metadata.get("status", "ready" if available else "unavailable"))
    state = {"healthy": "ready", "failed": "degraded"}.get(state, state)
    ready = available and state == "ready"
    return (
        order,
        ComponentHealth(
            component_id=component_id,
            module=module or f"synapse.{component_id}",
            state=state,
            configured=available,
            available=available,
            ready=ready,
            degraded=available and not ready,
            dependencies=dependencies,
            recommendations=[] if available else [f"Configure {component_id} runtime."],
            metadata=metadata,
        ),
    )


def check(
    order: int,
    check_id: str,
    condition: bool,
    severity: str,
    summary: str,
    metadata: dict[str, Any] | None = None,
) -> tuple[int, HealthCheckItem] | None:
    if not condition:
        return None
    return (
        order,
        HealthCheckItem(
            id=check_id,
            label=check_id.replace(".", " ").title(),
            severity=severity,
            summary=summary,
            metadata=metadata or {},
        ),
    )


def checks(*items: tuple[int, HealthCheckItem] | None) -> tuple[tuple[int, HealthCheckItem], ...]:
    return tuple(item for item in items if item is not None)
