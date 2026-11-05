from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, datetime
from threading import RLock
from typing import Any
from uuid import uuid4

from synapse.core.exceptions import ValidationError
from synapse.core.serialization import dump_structured_file, load_structured_file
from synapse.missions.models import MissionTask
from synapse.swarm.request_policy import SwarmRequest, classify_swarm_request


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class SwarmInteraction:
    request_id: str
    conversation_id: str
    workspace_id: str
    project_id: str | None
    session_id: str | None
    actor_id: str
    primary_agent_id: str
    task: str
    requested_agents: int | None
    recommended_agents: int
    explicit_models: tuple[str, ...] = ()
    status: str = "pending"
    mission_id: str | None = None
    swarm_id: str | None = None
    execution_status: str | None = None
    error: str | None = None
    idempotency_key: str | None = None
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)
    outputs: list[str] = field(default_factory=list)
    approval_ids: list[str] = field(default_factory=list)


class SwarmInteractionRuntime:
    """Owns explicit, persisted confirmation before any Swarm side effect."""

    def __init__(self, data_dir: Any, events: Any, missions: Any, planner: Any,
                 swarm: Any, ephemeral_agents: Any, primary_agent: Any) -> None:
        self.data_dir = data_dir
        self.events = events
        self.missions = missions
        self.planner = planner
        self.swarm = swarm
        self.ephemeral_agents = ephemeral_agents
        self.primary_agent = primary_agent
        self.select_model_routes: Callable[[int, tuple[str, ...]], list[tuple[str, str]]] | None = None
        self.execution_lock = RLock()

    def prepare(self, *, text: str, conversation_id: str, workspace_id: str,
                project_id: str | None, session_id: str | None, actor_id: str,
                idempotency_key: str | None = None) -> SwarmInteraction | None:
        request = classify_swarm_request(text)
        if not request.requested:
            return None
        existing = self._find_by_idempotency(
            idempotency_key, actor_id=actor_id, workspace_id=workspace_id
        )
        if existing is not None:
            return existing
        pending = self._find_pending(
            conversation_id, actor_id=actor_id, workspace_id=workspace_id
        )
        if pending is not None:
            return pending
        primary_id = self.primary_agent.get_primary(workspace_id).agent_id
        recommendation = self._recommended_agents(text, request)
        interaction = SwarmInteraction(
            request_id=str(uuid4()), conversation_id=conversation_id,
            workspace_id=workspace_id, project_id=project_id, session_id=session_id,
            actor_id=actor_id,
            primary_agent_id=primary_id, task=text.strip(),
            requested_agents=request.requested_agents,
            recommended_agents=recommendation,
            explicit_models=request.explicit_models,
            status="pending" if self._needs_confirmation(request, recommendation) else "accepted",
            idempotency_key=idempotency_key,
        )
        self._write(interaction)
        self.events.emit("swarm.interaction.prepared", primary_id, asdict(interaction))
        return interaction

    def execute_accepted(self, request_id: str) -> SwarmInteraction:
        with self.execution_lock:
            return self._execute_accepted(request_id)

    def _execute_accepted(self, request_id: str) -> SwarmInteraction:
        current = self.get(request_id)
        if current.status == "completed":
            return current
        if current.status != "accepted":
            raise ValidationError("Swarm request must be accepted before execution.")
        mission_id: str | None = None
        swarm_id: str | None = None
        try:
            mission = self.missions.create_mission(
                title=self._title(current.task), objective=self._objective(current.task), description=current.task,
                status="active", owner_agent_id=current.primary_agent_id,
                created_by=current.actor_id, conversation_id=current.conversation_id,
                project_id=current.project_id,
                metadata={"source": "primary_swarm_interaction", "request_id": current.request_id},
            )
            mission_id = mission.mission_id
            tasks = self._tasks(current, mission_id)
            plan = self.planner.create_plan(
                mission_id, self._objective(current.task), tasks=tasks,
                preferred_agents=[current.primary_agent_id],
                constraints={"requested_agents": current.requested_agents,
                             "recommended_agents": current.recommended_agents},
            )
            self.missions.attach_plan(mission_id, plan.plan_id)
            swarm = self.swarm.create(
                mission_id=mission_id, strategy="parallel",
                leader_agent_id=current.primary_agent_id, member_agent_ids=[],
                metadata={"max_parallelism": current.recommended_agents,
                          "allow_worker_reuse": False, "drain_ready_tasks": True,
                          "request_id": current.request_id},
            )
            swarm_id = swarm.swarm_id
            instances = self.swarm.provision_workforce(swarm_id)
            if not instances or not all(getattr(item, "worker_id", None) for item in instances):
                raise ValidationError("Swarm did not provision temporary agents; execution has not started.")
            updated_swarm = self.swarm.get(swarm_id)
            execution_status = "awaiting_workers"
            outputs: list[str] = []
            if instances and all(getattr(item, "worker_id", None) for item in instances):
                result = self.swarm.run(swarm_id)
                execution_status = str(result.get("status", "running"))
                outputs = self._verified_outputs(result.get("result", {}))
            completed = replace(
                current, status=execution_status, mission_id=mission_id,
                swarm_id=updated_swarm.swarm_id, execution_status=execution_status,
                updated_at=now_iso(),
                outputs=outputs,
                approval_ids=[approval_id for attempt in self.missions.attempts.list(mission_id=mission_id)
                              if attempt.status == "waiting_approval"
                              for approval_id in (attempt.result or {}).get("approval_ids", [])]
                if execution_status == "waiting_approval" else [],
            )
            self._write(completed)
            self.events.emit(
                f"swarm.interaction.{execution_status}", current.primary_agent_id, asdict(completed)
            )
            return completed
        except Exception as exc:
            failed = replace(
                current, status="failed", mission_id=mission_id, swarm_id=swarm_id,
                execution_status="failed", error=str(exc), updated_at=now_iso(),
            )
            self._write(failed)
            self.events.emit(
                "swarm.interaction.failed", current.primary_agent_id, asdict(failed)
            )
            raise

    def resolve(self, request_id: str, action: str) -> SwarmInteraction:
        current = self.get(request_id)
        if current.status != "pending":
            raise ValidationError("Swarm confirmation is no longer pending.")
        if action == "cancel":
            cancelled = replace(current, status="cancelled", updated_at=now_iso())
            self._write(cancelled)
            self.events.emit("swarm.interaction.cancelled", current.primary_agent_id, asdict(cancelled))
            return cancelled
        if action not in {"accept_recommended", "keep_requested"}:
            raise ValidationError("Unsupported Swarm confirmation action.")
        count = current.recommended_agents
        if action == "keep_requested" and current.requested_agents:
            count = self._bounded(max(current.requested_agents, len(current.explicit_models)))
        accepted = replace(current, status="accepted", recommended_agents=count, updated_at=now_iso())
        self._write(accepted)
        return self.execute_accepted(request_id)

    def refresh_execution(self, swarm_id: str) -> None:
        swarm = self.swarm.get(swarm_id)
        root = self.data_dir.resolve("swarm/interactions")
        if not root.exists():
            return
        result_path = self.data_dir.resolve(f"swarms/{swarm_id}.result.yaml")
        result = load_structured_file(result_path) if result_path.exists() else {}
        outputs = self._verified_outputs(result)
        approval_ids = [approval_id for attempt in self.missions.attempts.list(mission_id=swarm.mission_id)
                        if attempt.status == "waiting_approval"
                        for approval_id in (attempt.result or {}).get("approval_ids", [])]
        for path in root.glob("*.yaml"):
            current = self.get(path.stem)
            if current.swarm_id == swarm_id:
                self._write(replace(current, status=swarm.status, execution_status=swarm.status,
                                    outputs=outputs, approval_ids=approval_ids if swarm.status == "waiting_approval" else [],
                                    updated_at=now_iso()))

    @staticmethod
    def _verified_outputs(result: dict[str, Any]) -> list[str]:
        outputs = []
        for item in result.get("outputs", []):
            task_result = item.get("result", {})
            paths: dict[str, list[str]] = {"read_file": [], "edit_file": [], "write_file": [], "delete_file": []}
            for evidence in task_result.get("evidence", []):
                receipt = evidence.get("value", {}) if evidence.get("kind") == "tool_result" else {}
                name = receipt.get("request", {}).get("name")
                path = (receipt.get("result") or {}).get("path")
                if name in paths and path and receipt.get("success") is True and receipt.get("status") == "executed":
                    if str(path) not in paths[name]:
                        paths[name].append(str(path))
            facts = []
            for name, label in (("read_file", "Leitura confirmada"), ("edit_file", "Edição aplicada"),
                                ("write_file", "Gravação aplicada"), ("delete_file", "Exclusão aplicada")):
                if paths[name]:
                    facts.append(f"{label}: {', '.join(paths[name])}.")
            if any(paths[name] for name in ("edit_file", "write_file", "delete_file")):
                facts.append("As operações em arquivos foram verificadas. Esta missão não executou a suíte de testes do projeto.")
            if facts:
                outputs.append("\n".join(facts))
            elif task_result.get("output"):
                outputs.append(str(task_result["output"]))
        return outputs

    def get(self, request_id: str) -> SwarmInteraction:
        path = self._path(request_id)
        if not path.exists():
            raise ValidationError("Swarm confirmation was not found.")
        raw = load_structured_file(path)
        raw["explicit_models"] = tuple(raw.get("explicit_models", ()))
        raw.setdefault("session_id", None)
        raw.setdefault("error", None)
        raw.setdefault("idempotency_key", None)
        return SwarmInteraction(**raw)

    def _recommended_agents(self, text: str, request: SwarmRequest) -> int:
        complexity_terms = ("pesquis", "analis", "código", "codigo", "test", "document", "revis")
        score = sum(term in text.lower() for term in complexity_terms)
        if request.requested_agents:
            requested = max(request.requested_agents, len(request.explicit_models))
            if score >= 2:
                requested = max(requested, score)
            return self._bounded(requested)
        if request.explicit_models:
            return self._bounded(max(len(request.explicit_models), score or 1))
        return self._bounded(max(2, min(4, score or 2)))

    def _needs_confirmation(self, request: SwarmRequest, recommendation: int) -> bool:
        return request.requires_confirmation or (
            request.requested_agents is not None and request.requested_agents != recommendation
        )

    def _bounded(self, count: int) -> int:
        limits = self.ephemeral_agents.limits()
        maximum = min(int(limits["max_ephemeral_agents_per_mission"]),
                      int(limits["max_child_agents_per_agent"]),
                      int(limits["max_concurrent_ephemeral_agents"]))
        return max(1, min(count, maximum))

    def _tasks(self, request: SwarmInteraction, mission_id: str) -> list[MissionTask]:
        models = request.explicit_models
        routes = self.select_model_routes(request.recommended_agents, models) if self.select_model_routes else []
        tasks = [
            MissionTask(
                mission_id=mission_id,
                title=f"Especialista {index + 1}",
                objective=self._objective(request.task),
                required_capabilities=["swarm"],
                metadata={
                    "requires_ephemeral": True,
                    "specialist_role": f"specialist_{index + 1}",
                    "model_capability": "swarm",
                    "provider": routes[index % len(routes)][0] if routes else None,
                    "model": (routes[index % len(routes)][1] if routes
                              else models[index % len(models)] if models else None),
                    "request_id": request.request_id,
                },
            )
            for index in range(request.recommended_agents)
        ]
        # Filesystem work needs observed operations, not merely non-empty prose.
        path_match = re.search(r'"([A-Za-z]:[\\/][^"]+)"|([A-Za-z]:[\\/][^\s`]+)|(/[^\s`]+)', request.task)
        if path_match:
            root = next(value for value in path_match.groups() if value).rstrip(".,;")
            repairing = bool(re.search(r"\b(?:consert\w*|concert\w*|corrij\w*|corrig\w*|fix|repair|edit\w*|alter\w*)\b", request.task, re.I))
            for index, task in enumerate(tasks):
                repair = repairing and index == len(tasks) - 1
                tools = ["list_directory", "read_file", "search_files"]
                groups = [["read_file"]]
                objective = f"Inspect the actual project at {root} using file tools. Read relevant source files and report concrete findings. Your assigned task is analysis only; after inspecting the source, report your findings and stop. Another specialist handles repairs."
                if repair:
                    tools += ["edit_file", "write_file", "delete_file"]
                    groups.append(["edit_file", "write_file", "delete_file"])
                    objective = (f"Read the actual project at {root}, inspect the findings, and apply the requested repair using file tools. "
                                 "Request approval for changes. After a change, read the changed file to verify it; after deletion, list its parent directory to verify absence. "
                                 "Do not claim completion or successful tests without tool evidence.")
                tasks[index] = replace(
                    task, title="Correção do projeto" if repair else f"Análise do projeto {index + 1}",
                    objective=(f"The project root {root} is a DIRECTORY, not a file. "
                               "First call list_directory on the project root to discover filenames. "
                               "Then call read_file with the full path of an individual source file. "
                               "Never call read_file on the project root itself. "
                               + objective + f" User request: {self._objective(request.task)}"),
                    dependencies=[previous.task_id for previous in tasks[:index]] if repair else [],
                    required_tools=["read_file"],
                    verification_policy={"checks": ["non_empty", "file_operations"], "root": root,
                                         "tool_groups": groups, "require_readback": repair},
                    metadata={**task.metadata, "authorized_tools": tools, "file_root": root},
                )
        return tasks

    def _path(self, request_id: str):
        return self.data_dir.resolve(f"swarm/interactions/{request_id}.yaml")

    def _find_by_idempotency(
        self, idempotency_key: str | None, *, actor_id: str, workspace_id: str
    ) -> SwarmInteraction | None:
        if not idempotency_key:
            return None
        root = self.data_dir.resolve("swarm/interactions")
        if not root.exists():
            return None
        for path in root.glob("*.yaml"):
            raw = load_structured_file(path)
            if (
                raw.get("idempotency_key") == idempotency_key
                and raw.get("actor_id") == actor_id
                and raw.get("workspace_id") == workspace_id
            ):
                raw["explicit_models"] = tuple(raw.get("explicit_models", ()))
                raw.setdefault("session_id", None)
                raw.setdefault("error", None)
                raw.setdefault("idempotency_key", None)
                return SwarmInteraction(**raw)
        return None

    def _find_pending(
        self, conversation_id: str, *, actor_id: str, workspace_id: str
    ) -> SwarmInteraction | None:
        root = self.data_dir.resolve("swarm/interactions")
        if not root.exists():
            return None
        for path in root.glob("*.yaml"):
            raw = load_structured_file(path)
            if (
                raw.get("conversation_id") == conversation_id
                and raw.get("actor_id") == actor_id
                and raw.get("workspace_id") == workspace_id
                and raw.get("status") == "pending"
            ):
                raw["explicit_models"] = tuple(raw.get("explicit_models", ()))
                raw.setdefault("session_id", None)
                raw.setdefault("error", None)
                raw.setdefault("idempotency_key", None)
                return SwarmInteraction(**raw)
        return None

    def _write(self, interaction: SwarmInteraction) -> None:
        dump_structured_file(self._path(interaction.request_id), asdict(interaction))

    @staticmethod
    def _objective(text: str) -> str:
        match = re.match(
            r"^\s*(?:faça|faca|crie|inicie|use|utilize|execute|start|create|run)\s+"
            r"(?:(?:um|a)\s+)?swarm(?:\s*,\s*|\s+(?:para|e|to)\s+)(.+)$",
            text, flags=re.IGNORECASE | re.DOTALL,
        )
        return match.group(1).strip() if match else text

    @staticmethod
    def _title(task: str) -> str:
        text = " ".join(task.strip().split())
        return text[:96] or "Swarm task"
