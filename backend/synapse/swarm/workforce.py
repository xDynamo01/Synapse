from __future__ import annotations

from dataclasses import replace
from typing import Any

from synapse.ephemeral_agents.models import (
    AgentMemoryScope,
    EphemeralAgentSpec,
    EphemeralWorkforcePlan,
)


class EphemeralWorkforcePlanner:
    """Produces a bounded plan; only Mission/Swarm may apply it."""

    def __init__(
        self,
        agents: Any,
        resource_pressure: Any,
        model_capability: Any,
        ephemeral_runtime: Any,
    ) -> None:
        self.agents = agents
        self.resource_pressure = resource_pressure
        self.model_capability = model_capability
        self.ephemeral_runtime = ephemeral_runtime
        self.skill_resolution: Any | None = None

    def plan(
        self,
        mission: Any,
        mission_plan: Any,
        *,
        parent_agent_id: str,
        strategy: str,
    ) -> EphemeralWorkforcePlan:
        self.agents.get(parent_agent_id)
        tasks = [
            task for task in mission_plan.tasks if task.status not in {"completed", "cancelled"}
        ]
        explicit = [task for task in tasks if task.metadata.get("requires_ephemeral")]
        specialist = [task for task in tasks if task.required_capabilities or task.required_tools]
        needed = list(dict.fromkeys(task.task_id for task in [*explicit, *specialist]))
        selected = [task for task in tasks if task.task_id in needed]
        if len(tasks) <= 1 and not explicit and not specialist:
            return EphemeralWorkforcePlan(
                mission_id=mission.mission_id,
                required=False,
                reason="A simple task does not justify dynamic workforce creation.",
                agents=[],
                max_concurrency=0,
                execution_order=[],
                strategy="persistent_only",
                resource_estimate={"agents": 0},
            )
        if not selected:
            selected = tasks
        limits = self.ephemeral_runtime.limits()
        maximum = min(
            len(selected),
            int(limits["max_ephemeral_agents_per_mission"]),
            int(limits["max_ephemeral_agents_global"]),
        )
        warnings: list[str] = []
        capacity = self.resource_pressure.assess_capacity("ephemeral_swarm")
        if not capacity.sufficient:
            return EphemeralWorkforcePlan(
                mission_id=mission.mission_id,
                required=False,
                reason=capacity.reason,
                agents=[],
                max_concurrency=0,
                execution_order=[],
                strategy="deferred",
                resource_estimate={"pressure_level": capacity.pressure_level},
                warnings=["resource_capacity_unavailable"],
            )
        concurrency = min(maximum, int(limits["max_concurrent_ephemeral_agents"]))
        if capacity.recommended_concurrency:
            concurrency = min(concurrency, capacity.recommended_concurrency)
            warnings.append("resource_pressure_reduced_concurrency")
        agents: list[EphemeralAgentSpec] = []
        for task in selected[:maximum]:
            risk = str(task.metadata.get("risk_level", "low"))
            agents.append(
                EphemeralAgentSpec(
                    mission_id=mission.mission_id,
                    task_id=task.task_id,
                    parent_agent_id=parent_agent_id,
                    role=str(task.metadata.get("specialist_role") or task.title),
                    objective=task.objective,
                    required_capabilities=list(task.required_capabilities),
                    required_skills=list(task.metadata.get("required_skills", [])),
                    preferred_model_requirements={
                        "capability": str(task.metadata.get("model_capability", "swarm")),
                        "provider": task.metadata.get("provider"),
                        "model": task.metadata.get("model"),
                        "context": task.metadata.get("context_requirement"),
                        "latency": task.metadata.get("latency_requirement"),
                        "reasoning": task.metadata.get("reasoning_requirement"),
                        "tool_calling": bool(task.required_tools),
                    },
                    allowed_tools=list(task.metadata.get("authorized_tools", task.required_tools)),
                    denied_tools=list(task.metadata.get("denied_tools", [])),
                    context_scope={"mission_id": mission.mission_id, "task_id": task.task_id},
                    memory_scope=AgentMemoryScope.MISSION_SHARED
                    if len(tasks) > 1
                    else AgentMemoryScope.TASK,
                    autonomy_ceiling=str(task.metadata.get("autonomy_ceiling", "manual")),
                    risk_ceiling=risk,
                    max_context_tokens=min(
                        int(task.metadata.get("max_context_tokens", 8192)),
                        int(limits["max_context_budget"]),
                    ),
                    max_execution_time=min(task.timeout_seconds, int(limits["max_agent_lifetime"])),
                    max_retries=min(task.max_attempts - 1, int(limits["max_retries"])),
                    lease_duration=min(task.timeout_seconds, int(limits["max_agent_lifetime"])),
                    created_by="swarm",
                    correlation_id=task.correlation_id or mission.mission_id,
                    provenance=[{"mission_id": mission.mission_id, "task_id": task.task_id}],
                    metadata={"spawn_depth": 1, "strategy": strategy},
                    project_id=mission.project_id,
                    rfc_id=mission.rfc_id,
                    rfc_revision=mission.rfc_revision,
                    rfc_checksum=mission.rfc_checksum,
                    implementation_plan_id=mission.implementation_plan_id,
                    implementation_plan_revision=mission.implementation_plan_revision,
                    implementation_plan_checksum=mission.implementation_plan_checksum,
                    information_classification=mission.information_classification,
                    information_categories=mission.information_categories,
                    allowed_processing_boundaries=mission.allowed_processing_boundaries,
                    allowed_provider_profiles=mission.allowed_provider_profiles,
                    external_processing_policy=mission.external_processing_policy,
                    training_use_policy=mission.training_use_policy,
                    can_approve_egress=False,
                )
            )
        order = [
            [spec.spec_id for spec in agents[index : index + max(1, concurrency)]]
            for index in range(0, len(agents), max(1, concurrency))
        ]
        approval = any(spec.risk_ceiling in {"high", "critical"} for spec in agents)
        return EphemeralWorkforcePlan(
            mission_id=mission.mission_id,
            required=bool(agents),
            reason="Specialized or parallel mission work requires bounded temporary identities.",
            agents=agents,
            max_concurrency=concurrency,
            execution_order=order,
            strategy="sequential" if concurrency == 1 else strategy,
            resource_estimate={
                "agents": len(agents),
                "concurrency": concurrency,
                "pressure_level": capacity.pressure_level,
                "model_resource_budget": limits["max_model_resource_budget"],
            },
            warnings=warnings,
            approval_required=approval,
        )

    def reduce(self, plan: EphemeralWorkforcePlan, maximum: int) -> EphemeralWorkforcePlan:
        agents = plan.agents[: max(0, maximum)]
        concurrency = min(plan.max_concurrency, len(agents))
        return replace(
            plan,
            required=bool(agents),
            agents=agents,
            max_concurrency=concurrency,
            execution_order=[[spec.spec_id] for spec in agents],
            strategy="sequential" if agents else "deferred",
            warnings=[*plan.warnings, "workforce_reduced"],
        )
