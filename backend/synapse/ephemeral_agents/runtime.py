from __future__ import annotations

import builtins
from collections.abc import Callable, Mapping
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from synapse.core.serialization import load_structured_file
from synapse.ephemeral_agents.errors import (
    EphemeralAgentError,
    EphemeralAgentInvalidTransition,
    EphemeralAgentLimitExceeded,
    EphemeralAgentNotFound,
    EphemeralAgentResourceUnavailable,
)
from synapse.ephemeral_agents.models import (
    AgentMemoryScope,
    EphemeralAgentInstance,
    EphemeralAgentResult,
    EphemeralAgentSpec,
    EphemeralAgentState,
    EphemeralCleanupResult,
    now_iso,
)
from synapse.health.contracts import HealthContribution
from synapse.health.contributors.base import check, checks, component
from synapse.skills.contracts import SkillLeasePort
from synapse.storage.collection import FileCollection
from synapse.storage.errors import StorageRecordNotFound

TERMINAL_STATES = {
    EphemeralAgentState.COMPLETED,
    EphemeralAgentState.FAILED,
    EphemeralAgentState.CANCELLED,
    EphemeralAgentState.EXPIRED,
    EphemeralAgentState.DESTROYED,
}

TRANSITIONS: dict[EphemeralAgentState, set[EphemeralAgentState]] = {
    EphemeralAgentState.PLANNED: {EphemeralAgentState.PROVISIONING, EphemeralAgentState.CANCELLED},
    EphemeralAgentState.PROVISIONING: {
        EphemeralAgentState.READY,
        EphemeralAgentState.FAILED,
        EphemeralAgentState.CANCELLED,
    },
    EphemeralAgentState.READY: {
        EphemeralAgentState.ASSIGNED,
        EphemeralAgentState.CANCELLED,
        EphemeralAgentState.EXPIRED,
    },
    EphemeralAgentState.ASSIGNED: {
        EphemeralAgentState.RUNNING,
        EphemeralAgentState.CANCELLED,
        EphemeralAgentState.EXPIRED,
    },
    EphemeralAgentState.RUNNING: {
        EphemeralAgentState.WAITING,
        EphemeralAgentState.COMPLETED,
        EphemeralAgentState.FAILED,
        EphemeralAgentState.CANCELLED,
        EphemeralAgentState.EXPIRED,
    },
    EphemeralAgentState.WAITING: {
        EphemeralAgentState.RUNNING,
        EphemeralAgentState.COMPLETED,
        EphemeralAgentState.FAILED,
        EphemeralAgentState.CANCELLED,
        EphemeralAgentState.EXPIRED,
    },
    EphemeralAgentState.COMPLETED: {EphemeralAgentState.DESTROYING},
    EphemeralAgentState.FAILED: {EphemeralAgentState.DESTROYING},
    EphemeralAgentState.CANCELLED: {EphemeralAgentState.DESTROYING},
    EphemeralAgentState.EXPIRED: {EphemeralAgentState.DESTROYING},
    EphemeralAgentState.DESTROYING: {EphemeralAgentState.DESTROYED},
    EphemeralAgentState.DESTROYED: set(),
}

DEFAULT_LIMITS = {
    "max_ephemeral_agents_per_mission": 8,
    "max_concurrent_ephemeral_agents": 4,
    "max_ephemeral_agents_global": 16,
    "max_agent_lifetime": 3600,
    "max_context_budget": 32768,
    "max_model_resource_budget": 4,
    "max_tool_risk": "medium",
    "max_retries": 2,
    "max_spawn_depth": 1,
    "max_child_agents_per_agent": 4,
}


class EphemeralAgentRuntime:
    """Mission-owned temporary identity lifecycle; it never executes work itself."""

    def __init__(
        self,
        data_dir: Any,
        events: Any,
        *,
        agents: Any,
        identities: Any | None = None,
        resource_pressure: Any | None = None,
        model_capability: Any | None = None,
        workers: Any | None = None,
        attempts: Any | None = None,
        skill_leases: SkillLeasePort | None = None,
        authorized_tools: Callable[[str], builtins.list[str]] | None = None,
    ) -> None:
        self.data_dir = data_dir
        self.events = events
        self.agents = agents
        self.identities = identities
        self.resource_pressure = resource_pressure
        self.model_capability = model_capability
        self.workers = workers
        self.attempts = attempts
        self.skill_leases = skill_leases
        self.authorized_tools = authorized_tools
        self.instances = FileCollection(
            collection_id="ephemeral_agent_instances",
            root=data_dir.resolve("ephemeral_agents/instances"),
            current_schema_version=1,
            validator=_validate_instance,
            revision=lambda payload: int(payload.get("revision", 1)),
            recovery_policy="quarantine_record",
            events=events,
        )
        self.results = FileCollection(
            collection_id="ephemeral_agent_results",
            root=data_dir.resolve("ephemeral_agents/results"),
            current_schema_version=1,
            validator=_validate_result,
            revision=lambda payload: int(payload.get("revision", 1)),
            recovery_policy="quarantine_record",
            events=events,
        )
        self.contexts = FileCollection(
            collection_id="ephemeral_agent_contexts",
            root=data_dir.resolve("ephemeral_agents/contexts"),
            current_schema_version=1,
            recovery_policy="quarantine_record",
            events=events,
            sensitive_record_ids=True,
        )

    def limits(self) -> dict[str, Any]:
        path = self.data_dir.resolve("config/ephemeral_agent_policy.yaml")
        if not path.exists():
            return dict(DEFAULT_LIMITS)
        raw = load_structured_file(path).get("limits", {})
        return {**DEFAULT_LIMITS, **raw}

    def create_instance(
        self, spec: EphemeralAgentSpec, *, authority: str
    ) -> EphemeralAgentInstance:
        if authority not in {"mission", "swarm"}:
            raise EphemeralAgentError("Only Mission or Swarm may create ephemeral agents")
        self._validate_spec(spec)
        self._check_limits(spec)
        capacity = (
            self.resource_pressure.assess_capacity("ephemeral_agent")
            if self.resource_pressure
            else None
        )
        if capacity is not None and not capacity.sufficient:
            raise EphemeralAgentResourceUnavailable(capacity.reason)
        model_selection = self._select_model(spec)
        tool_scope = self._tool_scope(spec)
        now = datetime.now(UTC)
        lifetime = min(spec.lease_duration, int(self.limits()["max_agent_lifetime"]))
        ephemeral_id = f"ephemeral:{spec.mission_id}:{uuid4().hex[:12]}"
        context_id = uuid4().hex
        self.contexts.put(
            context_id,
            {
                "schema_version": 1,
                "revision": 1,
                "mission_id": spec.mission_id,
                "task_id": spec.task_id,
                "memory_scope": spec.memory_scope.value,
                "context_scope": _redact_mapping(spec.context_scope),
                "created_at": now.isoformat(),
                "updated_at": now.isoformat(),
            },
            create_only=True,
        )
        instance = EphemeralAgentInstance(
            ephemeral_agent_id=ephemeral_id,
            spec_id=spec.spec_id,
            mission_id=spec.mission_id,
            task_id=spec.task_id,
            parent_agent_id=spec.parent_agent_id,
            state=EphemeralAgentState.PLANNED,
            created_at=now.isoformat(),
            expires_at=(now + timedelta(seconds=lifetime)).isoformat(),
            correlation_id=spec.correlation_id,
            model_selection=model_selection,
            tool_scope=tool_scope,
            context_reference=f"ephemeral-context:{context_id}",
            scratchpad_reference=f"ephemeral-context:{context_id}",
        )
        self.instances.put(_storage_id(ephemeral_id), asdict(instance), create_only=True)
        self._emit("ephemeral_agent.planned", instance)
        self._emit("ephemeral_agent.created", instance)
        instance = self._transition(instance, EphemeralAgentState.PROVISIONING)
        instance = replace(instance, ready_at=now_iso())
        instance = self._transition(instance, EphemeralAgentState.READY)
        if self.skill_leases and spec.required_skills:
            self.skill_leases.grant_for_ephemeral(
                instance.ephemeral_agent_id,
                tuple(spec.required_skills),
                mission_id=instance.mission_id,
                task_id=instance.task_id,
                expires_at=instance.expires_at,
                context_budget=spec.max_context_tokens,
                allowed_tools=tuple(instance.tool_scope),
                correlation_id=instance.correlation_id,
            )
        return instance

    def get(self, ephemeral_agent_id: str) -> EphemeralAgentInstance:
        try:
            return _instance_from_payload(
                self.instances.get(_storage_id(ephemeral_agent_id)).payload
            )
        except StorageRecordNotFound as exc:
            raise EphemeralAgentNotFound(
                f"Ephemeral agent not found: {ephemeral_agent_id}"
            ) from exc

    def list(self, mission_id: str | None = None) -> list[EphemeralAgentInstance]:
        items = [_instance_from_payload(item.payload) for item in self.instances.list_all()]
        return [item for item in items if mission_id is None or item.mission_id == mission_id]

    def assign_worker(self, ephemeral_agent_id: str, worker_id: str) -> EphemeralAgentInstance:
        current = self.get(ephemeral_agent_id)
        concurrent = sum(
            item.state in {EphemeralAgentState.ASSIGNED, EphemeralAgentState.RUNNING}
            for item in self.list()
        )
        if concurrent >= int(self.limits()["max_concurrent_ephemeral_agents"]):
            raise EphemeralAgentLimitExceeded("concurrent ephemeral agent limit reached")
        if self.workers:
            worker = self.workers.get(worker_id)
            if worker.status not in {"idle", "online"} or worker.workload > 0:
                raise EphemeralAgentResourceUnavailable("Worker is not available")
        updated = replace(current, worker_id=worker_id)
        return self._transition(updated, EphemeralAgentState.ASSIGNED)

    def start(
        self, ephemeral_agent_id: str, attempt_id: str | None = None
    ) -> EphemeralAgentInstance:
        current = self.get(ephemeral_agent_id)
        updated = replace(
            current,
            started_at=current.started_at or now_iso(),
            current_attempt_id=attempt_id or current.current_attempt_id,
            last_heartbeat=now_iso(),
        )
        return self._transition(updated, EphemeralAgentState.RUNNING)

    def heartbeat(
        self, ephemeral_agent_id: str, extend_seconds: int = 60
    ) -> EphemeralAgentInstance:
        current = self.get(ephemeral_agent_id)
        if current.state not in {
            EphemeralAgentState.ASSIGNED,
            EphemeralAgentState.RUNNING,
            EphemeralAgentState.WAITING,
        }:
            raise EphemeralAgentInvalidTransition("Heartbeat requires an active lease")
        maximum = datetime.fromisoformat(current.created_at) + timedelta(
            seconds=int(self.limits()["max_agent_lifetime"])
        )
        expires = min(
            maximum,
            datetime.fromisoformat(current.expires_at) + timedelta(seconds=extend_seconds),
        )
        return self._save(
            replace(
                current,
                expires_at=expires.isoformat(),
                last_heartbeat=now_iso(),
                revision=current.revision + 1,
            ),
            expected_revision=current.revision,
        )

    def wait(self, ephemeral_agent_id: str) -> EphemeralAgentInstance:
        return self._transition(self.get(ephemeral_agent_id), EphemeralAgentState.WAITING)

    def complete(
        self,
        ephemeral_agent_id: str,
        *,
        output_reference: str | None,
        attempt_ids: builtins.list[str],
        verification: dict[str, Any] | None = None,
        evidence: builtins.list[dict[str, Any]] | None = None,
        artifacts: builtins.list[dict[str, Any]] | None = None,
        provenance: builtins.list[dict[str, Any]] | None = None,
    ) -> EphemeralAgentResult:
        current = self.get(ephemeral_agent_id)
        completed = self._transition(
            replace(current, completed_at=now_iso()), EphemeralAgentState.COMPLETED
        )
        result = EphemeralAgentResult(
            ephemeral_agent_id=completed.ephemeral_agent_id,
            mission_id=completed.mission_id,
            task_id=completed.task_id,
            attempt_ids=list(attempt_ids),
            status="completed",
            output_reference=output_reference,
            started_at=completed.started_at,
            completed_at=completed.completed_at or now_iso(),
            trace_id=completed.correlation_id,
            evidence=evidence or [],
            artifacts=artifacts or [],
            verification=verification,
            provenance=provenance or [],
        )
        self.results.put(_storage_id(ephemeral_agent_id), asdict(result))
        self._save(
            replace(
                completed,
                result_reference=f"ephemeral-result:{ephemeral_agent_id}",
                revision=completed.revision + 1,
            ),
            expected_revision=completed.revision,
        )
        return result

    def fail(self, ephemeral_agent_id: str, failure: dict[str, Any]) -> EphemeralAgentInstance:
        current = self.get(ephemeral_agent_id)
        return self._transition(
            replace(current, failure=_redact_mapping(failure), completed_at=now_iso()),
            EphemeralAgentState.FAILED,
        )

    def cancel(self, ephemeral_agent_id: str) -> EphemeralAgentInstance:
        current = self.get(ephemeral_agent_id)
        if current.state is EphemeralAgentState.DESTROYED:
            return current
        return self._transition(
            replace(current, completed_at=now_iso()), EphemeralAgentState.CANCELLED
        )

    def get_result(self, ephemeral_agent_id: str) -> EphemeralAgentResult:
        try:
            return EphemeralAgentResult(**self.results.get(_storage_id(ephemeral_agent_id)).payload)
        except StorageRecordNotFound as exc:
            raise EphemeralAgentNotFound(
                f"Ephemeral result not found: {ephemeral_agent_id}"
            ) from exc

    def destroy(self, ephemeral_agent_id: str) -> EphemeralAgentInstance:
        current = self.get(ephemeral_agent_id)
        if current.state is EphemeralAgentState.DESTROYED:
            return current
        if (
            current.state not in TERMINAL_STATES
            and current.state is not EphemeralAgentState.DESTROYING
        ):
            raise EphemeralAgentInvalidTransition("Only terminal ephemeral agents can be destroyed")
        if current.state is not EphemeralAgentState.DESTROYING:
            current = self._transition(current, EphemeralAgentState.DESTROYING)
        if current.worker_id and self.workers:
            try:
                self.workers.set_workload(current.worker_id, 0.0, None, None)
                if self.workers.get(current.worker_id).agent_id == ephemeral_agent_id:
                    self.workers.disable(current.worker_id)
            except Exception as exc:
                self.events.emit(
                    "ephemeral_agent.cleanup_failed",
                    current.parent_agent_id,
                    {
                        "ephemeral_agent_id": current.ephemeral_agent_id,
                        "error_type": type(exc).__name__,
                    },
                )
                raise
        context_id = _reference_id(current.context_reference)
        if context_id:
            try:
                self.contexts.delete(context_id)
            except StorageRecordNotFound:
                pass
        destroyed = self._transition(
            replace(current, context_reference=None, scratchpad_reference=None),
            EphemeralAgentState.DESTROYED,
        )
        if self.skill_leases:
            self.skill_leases.cleanup_leases(ephemeral_agent_id)
        return destroyed

    def reconcile(self, now: datetime | None = None) -> builtins.list[EphemeralAgentInstance]:
        now = now or datetime.now(UTC)
        reconciled: builtins.list[EphemeralAgentInstance] = []
        for current in self.list():
            if current.state is EphemeralAgentState.DESTROYED:
                continue
            if (
                datetime.fromisoformat(current.expires_at) <= now
                and current.state not in TERMINAL_STATES
            ):
                current = self._transition(current, EphemeralAgentState.EXPIRED)
            elif current.state in {EphemeralAgentState.PLANNED, EphemeralAgentState.PROVISIONING}:
                current = self.cancel(current.ephemeral_agent_id)
            elif (
                current.state is EphemeralAgentState.RUNNING
                and current.current_attempt_id
                and self.attempts
            ):
                try:
                    attempt = self.attempts.get(current.current_attempt_id)
                    status = str(attempt.status)
                    if status == "completed":
                        current = self._transition(
                            replace(current, completed_at=attempt.completed_at or now_iso()),
                            EphemeralAgentState.COMPLETED,
                        )
                    elif status in {"failed", "cancelled", "timed_out"}:
                        current = self._transition(
                            replace(
                                current, failure={"attempt_status": status}, completed_at=now_iso()
                            ),
                            EphemeralAgentState.FAILED,
                        )
                except Exception:
                    current = self._transition(
                        replace(
                            current,
                            failure={"reason": "attempt_unavailable"},
                            completed_at=now_iso(),
                        ),
                        EphemeralAgentState.FAILED,
                    )
            if current.state in TERMINAL_STATES:
                current = self.destroy(current.ephemeral_agent_id)
            reconciled.append(current)
        return reconciled

    def cleanup(self, *, dry_run: bool = True) -> EphemeralCleanupResult:
        items = self.list()
        eligible = [
            item
            for item in items
            if item.state in TERMINAL_STATES or item.state is EphemeralAgentState.DESTROYING
        ]
        destroyed = 0
        errors: list[dict[str, str]] = []
        if not dry_run:
            for item in eligible:
                try:
                    self.destroy(item.ephemeral_agent_id)
                    destroyed += 1
                except Exception as exc:
                    errors.append(
                        {
                            "ephemeral_agent_id": item.ephemeral_agent_id,
                            "error_type": type(exc).__name__,
                        }
                    )
        return EphemeralCleanupResult(
            dry_run=dry_run,
            scanned=len(items),
            eligible=len(eligible),
            destroyed=destroyed,
            preserved=len(items) - destroyed,
            agent_ids=[item.ephemeral_agent_id for item in eligible],
            errors=errors,
        )

    def health_snapshot(self) -> dict[str, Any]:
        items = self.list()
        return {
            "ready": True,
            "active_count": sum(item.state not in TERMINAL_STATES for item in items),
            "expired_count": sum(item.state is EphemeralAgentState.EXPIRED for item in items),
            "cleanup_pending": sum(
                item.state in TERMINAL_STATES - {EphemeralAgentState.DESTROYED} for item in items
            ),
            "resource_limits": self.limits(),
            "last_error": None,
        }

    def collect_health(self, context: Any) -> HealthContribution:
        snapshot = self.health_snapshot()
        return HealthContribution(
            components=(component(0, "ephemeral_agents", self, []),),
            summary={"ephemeral_agents": snapshot},
            checks=checks(
                check(
                    0,
                    "ephemeral_agents.cleanup_pending",
                    snapshot["cleanup_pending"] > 0,
                    "info",
                    f"{snapshot['cleanup_pending']} ephemeral cleanup(s) pending.",
                    snapshot,
                ),
            ),
        )

    def _validate_spec(self, spec: EphemeralAgentSpec) -> None:
        self.agents.get(spec.parent_agent_id)
        if not spec.mission_id or not spec.role.strip() or not spec.objective.strip():
            raise EphemeralAgentError("mission_id, role and objective are required")
        if spec.memory_scope not in set(AgentMemoryScope):
            raise EphemeralAgentError("long-term agent memory is not allowed")
        if spec.max_execution_time <= 0 or spec.lease_duration <= 0:
            raise EphemeralAgentError("execution and lease durations must be positive")
        if spec.max_retries > int(self.limits()["max_retries"]):
            raise EphemeralAgentLimitExceeded("max_retries exceeds policy")
        if spec.max_context_tokens > int(self.limits()["max_context_budget"]):
            raise EphemeralAgentLimitExceeded("context budget exceeds policy")
        if int(spec.metadata.get("spawn_depth", 0)) > int(self.limits()["max_spawn_depth"]):
            raise EphemeralAgentLimitExceeded("spawn depth exceeds policy")
        if spec.created_by.startswith("ephemeral:"):
            raise EphemeralAgentError("Ephemeral agents cannot create child agents directly")
        parent = self.agents.get(spec.parent_agent_id)
        autonomy = {"manual": 0, "assisted": 1, "autonomous": 2}
        if autonomy.get(spec.autonomy_ceiling, 99) > autonomy.get(parent.autonomy, 0):
            raise EphemeralAgentError("Ephemeral autonomy cannot exceed parent autonomy")
        risk = {"low": 0, "medium": 1, "high": 2, "critical": 3}
        maximum_risk = str(self.limits()["max_tool_risk"])
        if risk.get(spec.risk_ceiling, 99) > risk.get(maximum_risk, 0):
            raise EphemeralAgentError("Ephemeral risk ceiling exceeds system policy")
        if spec.risk_ceiling in {"high", "critical"} and not spec.metadata.get("approval_id"):
            raise EphemeralAgentError("High-risk ephemeral agent requires bound approval")

    def _check_limits(self, spec: EphemeralAgentSpec) -> None:
        limits = self.limits()
        active = [item for item in self.list() if item.state not in TERMINAL_STATES]
        mission_active = [item for item in active if item.mission_id == spec.mission_id]
        parent_active = [
            item for item in mission_active if item.parent_agent_id == spec.parent_agent_id
        ]
        if len(active) >= int(limits["max_ephemeral_agents_global"]):
            raise EphemeralAgentLimitExceeded("global ephemeral agent limit reached")
        if len(mission_active) >= int(limits["max_ephemeral_agents_per_mission"]):
            raise EphemeralAgentLimitExceeded("mission ephemeral agent limit reached")
        if len(parent_active) >= int(limits["max_child_agents_per_agent"]):
            raise EphemeralAgentLimitExceeded("parent child-agent limit reached")

    def _select_model(self, spec: EphemeralAgentSpec) -> dict[str, Any]:
        req = spec.preferred_model_requirements
        if req.get("provider") and req.get("model"):
            return {"provider": req["provider"], "model": req["model"],
                    "status": "selected", "reason": "explicit_mission_route"}
        if not self.model_capability:
            return {"status": "deferred", "reason": "model_router_selection_required"}
        recommendation = self.model_capability.recommend_route(
            str(req.get("capability", "swarm")),
            req.get("provider"),
            req.get("model"),
        )
        return {
            "provider": recommendation.provider_id,
            "model": recommendation.model_id,
            "status": recommendation.status,
            "reason": recommendation.reason,
            "fallback": None,
            "estimated_ram_gb": recommendation.estimated_ram_gb,
            "estimated_vram_gb": recommendation.estimated_vram_gb,
        }

    def _tool_scope(self, spec: EphemeralAgentSpec) -> builtins.list[str]:
        requested = set(spec.allowed_tools) - set(spec.denied_tools)
        if self.authorized_tools is not None:
            ceiling = set(self.authorized_tools(spec.parent_agent_id))
            return sorted((requested if spec.allowed_tools else ceiling) & ceiling - set(spec.denied_tools))
        if not self.identities:
            return sorted(requested)
        parent = self.identities.load_identity(spec.parent_agent_id)
        parent_tools = set(parent.preferred_tools) - set(parent.forbidden_tools)
        return sorted(requested & parent_tools) if parent_tools else []

    def _transition(
        self, current: EphemeralAgentInstance, target: EphemeralAgentState
    ) -> EphemeralAgentInstance:
        if current.state is target:
            return current
        if target not in TRANSITIONS[current.state]:
            raise EphemeralAgentInvalidTransition(f"{current.state} -> {target} is not allowed")
        updated = replace(current, state=target, revision=current.revision + 1)
        updated = self._save(updated, expected_revision=current.revision)
        event_type = (
            "ephemeral_agent.started"
            if target is EphemeralAgentState.RUNNING
            and current.state is EphemeralAgentState.ASSIGNED
            else f"ephemeral_agent.{target.value}"
        )
        self._emit(event_type, updated)
        return updated

    def _save(
        self, instance: EphemeralAgentInstance, *, expected_revision: int
    ) -> EphemeralAgentInstance:
        self.instances.put(
            _storage_id(instance.ephemeral_agent_id),
            asdict(instance),
            expected_revision=expected_revision,
        )
        return instance

    def _emit(self, event_type: str, instance: EphemeralAgentInstance) -> None:
        self.events.emit(
            event_type,
            instance.parent_agent_id,
            {
                "ephemeral_agent_id": instance.ephemeral_agent_id,
                "mission_id": instance.mission_id,
                "task_id": instance.task_id,
                "state": instance.state.value,
                "correlation_id": instance.correlation_id,
            },
        )


def _instance_from_payload(payload: Mapping[str, Any]) -> EphemeralAgentInstance:
    return EphemeralAgentInstance(**{**payload, "state": EphemeralAgentState(payload["state"])})


def _reference_id(reference: str | None) -> str | None:
    if not reference or not reference.startswith("ephemeral-context:"):
        return None
    return reference.split(":", 1)[1]


def _storage_id(ephemeral_agent_id: str) -> str:
    return ephemeral_agent_id.replace(":", "--")


def _redact_mapping(value: dict[str, Any]) -> dict[str, Any]:
    blocked = {"prompt", "system_prompt", "scratchpad", "secret", "token", "password"}
    return {key: item for key, item in value.items() if key.lower() not in blocked}


def _validate_instance(payload: Mapping[str, Any]) -> None:
    required = {"ephemeral_agent_id", "mission_id", "state", "expires_at", "revision"}
    if not required <= payload.keys():
        raise ValueError("ephemeral agent instance is incomplete")
    EphemeralAgentState(payload["state"])


def _validate_result(payload: Mapping[str, Any]) -> None:
    required = {"ephemeral_agent_id", "mission_id", "status", "completed_at"}
    if not required <= payload.keys():
        raise ValueError("ephemeral agent result is incomplete")
