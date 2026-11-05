"""Model proposals enter the existing Planner and mission governance."""
from __future__ import annotations

import json
import re
from dataclasses import replace
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from synapse.bootstrap.adapters.mom import PrimaryInference
from synapse.chat.routing import PlannedMission
from synapse.conversations.errors import ConversationError
from synapse.core.exceptions import ValidationError
from synapse.core.permissions import PermissionContext
from synapse.missions.dag import TaskGraph
from synapse.missions.models import MissionTask
from synapse.missions.planner import PlannerRuntime
from synapse.missions.runtime import MissionRuntime
from synapse.models.router import ModelRouter
from synapse.mom.contracts import Operation, Route
from synapse.mom.runtime import MoMRuntime
from synapse.mom.selection import requires_plan


class ProposedTask(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    title: str = Field(min_length=1, max_length=200)
    objective: str = Field(min_length=1, max_length=4000)
    capability: Operation
    dependencies: list[str] = Field(default_factory=list, max_length=32)
    acceptance_criteria: list[str] = Field(min_length=1, max_length=16)


class ProposedPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tasks: list[ProposedTask] = Field(min_length=1, max_length=32)


class CognitivePlanning:
    def __init__(self, mom: MoMRuntime, inference: PrimaryInference, models: ModelRouter,
                 missions: MissionRuntime, planner: PlannerRuntime):
        self.mom, self.inference, self.models = mom, inference, models
        self.missions, self.planner = missions, planner

    def prepare(self, context: PermissionContext, agent_id: str | None, message: str,
                conversation_id: str, project_id: str | None) -> PlannedMission | None:
        if not requires_plan(message):
            return None
        workspace = project_id or "default"
        primary = self.mom.primary.current_agent(workspace)
        if agent_id and agent_id != primary:
            return None
        configuration = self.mom.get_configuration(context, workspace)
        self.mom.permissions.require(context, "filesystem.write")
        current = None
        prior_plan = None
        if re.search(r"^(replaneje|revise o plano|ajuste o plano|replan)\b", message.strip().lower()):
            candidates = [item for item in self.missions.list_missions()
                          if item.metadata.get("chat_session_id") == conversation_id
                          and item.created_by == context.actor_id
                          and item.status not in {"completed", "cancelled", "archived"}]
            if len(candidates) != 1 or not candidates[0].plan_id:
                raise ValidationError("Identify one active mission before requesting replanning.")
            current = candidates[0]
            assert current.plan_id is not None
            prior_plan = self.planner.get_plan(current.mission_id, current.plan_id)
        default = self.models.default_route()
        route = next((item for item in configuration.routes if item.operation == Operation.REASONING), None)
        if route is None:
            if not default.model:
                raise ValidationError("Configure a reasoning or generalist model for mission planning.")
            route = Route(operation=Operation.REASONING, provider=default.provider, model=default.model)
        prompt = (
            "Propose a bounded task DAG for the user's request. Return ONLY JSON matching this schema. "
            "Do not execute tools or claim implementation. Acceptance criteria must be verifiable.\n"
            + json.dumps(ProposedPlan.model_json_schema()) + "\nUser request:\n" + message
        )
        if current is not None and prior_plan is not None:
            prompt += ("\nPreserve the original objective: " + current.objective
                       + "\nKeep existing task ids for unchanged tasks. Existing plan:\n"
                       + json.dumps([{"id": item.task_id, "title": item.title,
                                      "objective": item.objective, "dependencies": item.dependencies,
                                      "capability": item.metadata.get("capability"),
                                      "acceptance_criteria": item.metadata.get("acceptance_criteria", [])}
                                     for item in prior_plan.tasks]))
        output = self.inference.generate(context, primary, route, prompt, str(uuid4()), max_tokens=4096)
        proposal = ProposedPlan.model_validate_json(output.content)
        tasks: list[MissionTask] = []
        for proposed in proposal.tasks:
            selected = next((item for item in configuration.routes if item.operation == proposed.capability), None)
            if selected is None:
                raise ValidationError(f"Configure the {proposed.capability.value} route before creating this mission.")
            self.inference.validate_route(selected)
            tasks.append(MissionTask(
                mission_id="proposal", task_id=proposed.id, title=proposed.title,
                objective=proposed.objective, dependencies=proposed.dependencies,
                metadata={"capability": proposed.capability.value, "provider": selected.provider,
                          "model": selected.model, "acceptance_criteria": proposed.acceptance_criteria,
                          "idempotent": False, "source": "cognitive_planning"},
                verification_policy=({"checks": ["non_empty", "tests_passed"], "require_tool_evidence": True}
                                     if proposed.capability == Operation.CODING else {"checks": ["non_empty"]}),
            ))
        TaskGraph(tasks).validate()
        if current is not None and prior_plan is not None:
            existing_ids = {item.task_id for item in prior_plan.tasks}
            ids = {item.task_id: item.task_id if item.task_id in existing_ids else str(uuid4()) for item in tasks}
            revision_tasks = [replace(item, mission_id=current.mission_id, task_id=ids[item.task_id],
                                      dependencies=[ids[dependency] for dependency in item.dependencies]) for item in tasks]
            proposal_plan = self.planner.replace_plan(current.mission_id, prior_plan.plan_id,
                                                       prior_plan.version, [item for item in revision_tasks])
            return PlannedMission(current.mission_id,
                f"Revisão proposta para a missão {current.mission_id}: plano {proposal_plan.plan_id}. "
                "O plano ativo permanece intacto até a revisão pela governança de missões.")
        persisted_conversation: str | None = conversation_id
        if self.missions.conversations is not None:
            try:
                self.missions.conversations.get_conversation(conversation_id)
            except ConversationError as exc:
                if exc.code != "conversation_not_found":
                    raise
                persisted_conversation = None
        mission = self.missions.create_mission(
            title=message[:96], objective=message, owner_agent_id=primary,
            created_by=context.actor_id, conversation_id=persisted_conversation, project_id=project_id,
            metadata={"source": "cognitive_planning", "execution_regime": "NORMAL",
                      "chat_session_id": conversation_id,
                      "requires_plan_review": True, "resource_pressure_guard": True},
        )
        # Scope task identities to this mission; model-provided ids are local labels.
        ids = {task.task_id: str(uuid4()) for task in tasks}
        tasks = [replace(task, mission_id=mission.mission_id, task_id=ids[task.task_id],
                         dependencies=[ids[item] for item in task.dependencies]) for task in tasks]
        plan = self.planner.create_plan(mission.mission_id, message, tasks=[task for task in tasks])
        self.missions.attach_plan(mission.mission_id, plan.plan_id)
        return PlannedMission(mission.mission_id,
            "Missão planejada: " + mission.mission_id + "\nPlano: " + plan.plan_id + "\n"
            + "\n".join(f"• {task.title}" for task in tasks)
            + "\nO plano está salvo para revisão e execução pela governança de missões. Regime NORMAL.")
