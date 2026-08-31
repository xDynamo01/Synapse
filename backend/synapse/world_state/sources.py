from __future__ import annotations

from typing import Any

from synapse.world_state.models import WorldStateUpdate
from synapse.world_state.runtime import WorldStateRuntime


def register_default_reconcilers(
    world_state: WorldStateRuntime,
    *,
    presence: Any,
    lifecycle: Any,
    missions: Any,
    daemon: Any,
    scheduler: Any,
) -> None:
    def reconcile_agents(snapshot):
        presences = {item.agent_id: item for item in presence.list_all()}
        lifecycles = {item.agent_id: item for item in lifecycle.list_all()}
        actual_ids = set(presences) | set(lifecycles)
        updates = []
        for agent_id in sorted(actual_ids):
            current_presence = presences.get(agent_id)
            current_lifecycle = lifecycles.get(agent_id)
            values = {
                "agent_id": agent_id,
                "presence": getattr(current_presence, "state", "unknown"),
                "lifecycle": getattr(current_lifecycle, "state", "unknown"),
                "busy": getattr(current_presence, "state", "unknown")
                in {"working", "thinking", "speaking"},
                "last_activity": getattr(current_presence, "updated_at", None),
            }
            if not _contains(snapshot.agents.get(agent_id), values):
                updates.append(_reconcile_update("agents", agent_id, values))
        for stale_id in sorted(set(snapshot.agents) - actual_ids):
            updates.append(_reconcile_update("agents", stale_id, {}, operation="remove"))
        return updates

    def reconcile_missions(snapshot):
        actual = {item.mission_id: item for item in missions.list_missions()}
        updates = []
        for mission_id, mission in sorted(actual.items()):
            values = {
                "mission_id": mission_id,
                "status": mission.status,
                "priority": mission.priority,
                "progress": mission.progress,
                "owner_agent_id": mission.owner_agent_id,
                "updated_at": mission.updated_at,
            }
            if not _contains(snapshot.missions.get(mission_id), values):
                updates.append(_reconcile_update("missions", mission_id, values))
        for stale_id in sorted(set(snapshot.missions) - set(actual)):
            updates.append(_reconcile_update("missions", stale_id, {}, operation="remove"))
        return updates

    def reconcile_operations(snapshot):
        daemon_status = daemon.status()
        lock = scheduler.lock_status()
        values = {
            "daemon_status": "running" if daemon_status.running else "stopped",
            "scheduler_status": "locked" if lock.get("locked", False) else "ready",
        }
        return (
            []
            if _contains(snapshot.system_state, values)
            else [_reconcile_update("system_state", None, values)]
        )

    world_state.register_reconciler("agents", reconcile_agents)
    world_state.register_reconciler("missions", reconcile_missions)
    world_state.register_reconciler("operations", reconcile_operations)


def _reconcile_update(
    entity_type: str,
    entity_id: str | None,
    values: dict[str, Any],
    operation: str = "merge",
) -> WorldStateUpdate:
    return WorldStateUpdate(
        source="world_state.reconciliation",
        entity_type=entity_type,
        entity_id=entity_id,
        operation=operation,
        values=values,
        provenance={"kind": "runtime_reconciliation"},
    )


def _contains(current: Any, expected: dict[str, Any]) -> bool:
    return isinstance(current, dict) and all(
        current.get(key) == value for key, value in expected.items()
    )
