from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Header, Request
from pydantic import BaseModel, Field

from synapse.api.common import api_error, require_admin, runtime_from
from synapse.skills.models import (
    SkillAssignment,
    SkillResolutionRequest,
    SkillScope,
)

router = APIRouter(tags=["skills"])


class SkillPackageRefPayload(BaseModel):
    package_ref: str


class SkillResolvePayload(BaseModel):
    objective: str
    explicit_skill_ids: list[str] = Field(default_factory=list)
    agent_id: str | None = None
    agent_kind: str = "persistent"
    workspace_id: str | None = None
    project_id: str | None = None
    mission_id: str | None = None
    task_id: str | None = None
    available_tools: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    providers: list[str] = Field(default_factory=list)
    context_budget: int = 8000
    correlation_id: str | None = None
    rfc_id: str | None = None
    rfc_revision: int | None = None
    rfc_checksum: str | None = None
    change_class: str | None = None
    required_evidence: list[str] = Field(default_factory=list)


class SkillAssignmentPayload(BaseModel):
    skill_id: str
    version_constraint: str
    scope: str = "agent"
    enabled: bool = True
    auto_discovery: bool = True
    explicit_only: bool = False
    priority: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


@router.get("/skills/status")
def skill_status(request: Request) -> dict[str, Any]:
    return runtime_from(request).skills.status()


@router.get("/skills/conflicts")
def skill_conflicts(request: Request) -> dict[str, Any]:
    skills = runtime_from(request).skills
    conflicts = [
        {
            "skill_id": package.manifest.skill_id,
            "conflicts": [asdict(x) for x in package.manifest.conflicts],
        }
        for package in skills.registry.packages()
        if package.manifest.conflicts
    ]
    return {"conflicts": conflicts}


@router.get("/skills/invalid")
def invalid_skills(request: Request) -> dict[str, Any]:
    return {"invalid": list(runtime_from(request).skills.invalid_packages)}


@router.get("/skills/leases")
def skill_leases(request: Request) -> dict[str, Any]:
    items = runtime_from(request).skills.list_leases()
    return {"leases": list(items), "total": len(items)}


@router.get("/skills")
def list_skills(
    request: Request,
    query: str = "",
    status: str | None = None,
    agent_kind: str | None = None,
) -> dict[str, Any]:
    items = runtime_from(request).skills.list(query, status=status, agent_kind=agent_kind)
    return {"skills": [asdict(item) for item in items], "total": len(items)}


@router.post("/skills/resolve")
def resolve_skills(payload: SkillResolvePayload, request: Request) -> dict[str, Any]:
    try:
        result = runtime_from(request).skills.resolve(
            SkillResolutionRequest(
                objective=payload.objective,
                explicit_skill_ids=tuple(payload.explicit_skill_ids),
                agent_id=payload.agent_id,
                agent_kind=payload.agent_kind,
                workspace_id=payload.workspace_id,
                project_id=payload.project_id,
                mission_id=payload.mission_id,
                task_id=payload.task_id,
                available_tools=tuple(payload.available_tools),
                capabilities=tuple(payload.capabilities),
                providers=tuple(payload.providers),
                context_budget=payload.context_budget,
                correlation_id=payload.correlation_id,
                rfc_id=payload.rfc_id,
                rfc_revision=payload.rfc_revision,
                rfc_checksum=payload.rfc_checksum,
                change_class=payload.change_class,
                required_evidence=tuple(payload.required_evidence),
            )
        )
        return asdict(result)
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/skills/inspect")
def inspect_skill(
    payload: SkillPackageRefPayload,
    request: Request,
    x_actor_type: str | None = Header(default=None),
) -> dict[str, Any]:
    require_admin(x_actor_type)
    try:
        package = runtime_from(request).skills.inspect(payload.package_ref)
        return {"manifest": asdict(package.manifest), "checksum": package.checksum}
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/skills/validate")
def validate_skill(
    payload: SkillPackageRefPayload,
    request: Request,
    x_actor_type: str | None = Header(default=None),
) -> dict[str, Any]:
    require_admin(x_actor_type)
    try:
        return runtime_from(request).skills.validate(payload.package_ref)
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/skills/install")
def install_skill(
    payload: SkillPackageRefPayload,
    request: Request,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
) -> dict[str, Any]:
    require_admin(x_actor_type)
    try:
        package = runtime_from(request).skills.install(
            payload.package_ref, actor_id=x_actor_id or "system"
        )
        return {"manifest": asdict(package.manifest), "checksum": package.checksum}
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/skills/{skill_id}/enable")
def enable_skill(
    skill_id: str,
    version: str,
    request: Request,
    x_actor_type: str | None = Header(default=None),
) -> dict[str, Any]:
    require_admin(x_actor_type)
    return {
        "manifest": asdict(
            runtime_from(request).skills.set_status(skill_id, version, "active").manifest
        )
    }


@router.post("/skills/{skill_id}/disable")
def disable_skill(
    skill_id: str,
    version: str,
    request: Request,
    x_actor_type: str | None = Header(default=None),
) -> dict[str, Any]:
    require_admin(x_actor_type)
    return {
        "manifest": asdict(
            runtime_from(request).skills.set_status(skill_id, version, "disabled").manifest
        )
    }


@router.delete("/skills/{skill_id}")
def uninstall_skill(
    skill_id: str,
    version: str,
    request: Request,
    x_actor_type: str | None = Header(default=None),
) -> dict[str, Any]:
    require_admin(x_actor_type)
    try:
        runtime_from(request).skills.uninstall(skill_id, version)
        return {"uninstalled": True, "skill_id": skill_id, "version": version}
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/skills/{skill_id}/versions")
def skill_versions(skill_id: str, request: Request) -> dict[str, Any]:
    versions = runtime_from(request).skills.versions(skill_id)
    return {"skill_id": skill_id, "versions": list(versions)}


@router.get("/skills/{skill_id}")
def get_skill(skill_id: str, request: Request, version: str | None = None) -> dict[str, Any]:
    try:
        package = runtime_from(request).skills.get(skill_id, version)
        return {"manifest": asdict(package.manifest), "checksum": package.checksum}
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/agents/{agent_id}/skills")
def agent_skills(agent_id: str, request: Request) -> dict[str, Any]:
    items = runtime_from(request).skills.assignment_summaries(agent_id)
    return {"agent_id": agent_id, "assignments": list(items)}


@router.post("/agents/{agent_id}/skills/assign")
def assign_skill(
    agent_id: str,
    payload: SkillAssignmentPayload,
    request: Request,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
) -> dict[str, Any]:
    require_admin(x_actor_type)
    try:
        assignment = SkillAssignment(
            agent_id=agent_id,
            skill_id=payload.skill_id,
            version_constraint=payload.version_constraint,
            scope=SkillScope(payload.scope),
            enabled=payload.enabled,
            auto_discovery=payload.auto_discovery,
            explicit_only=payload.explicit_only,
            priority=payload.priority,
            assigned_by=x_actor_id or "system",
            metadata=payload.metadata,
        )
        return asdict(runtime_from(request).skills.assign(assignment))
    except Exception as exc:
        raise api_error(exc) from exc


@router.delete("/agents/{agent_id}/skills/{assignment_id}")
def unassign_skill(
    agent_id: str,
    assignment_id: str,
    request: Request,
    x_actor_type: str | None = Header(default=None),
) -> dict[str, Any]:
    require_admin(x_actor_type)
    runtime_from(request).skills.unassign(assignment_id)
    return {"unassigned": True, "agent_id": agent_id, "assignment_id": assignment_id}


@router.get("/missions/{mission_id}/skill-leases")
def mission_skill_leases(mission_id: str, request: Request) -> dict[str, Any]:
    items = [
        item
        for item in runtime_from(request).skills.list_leases()
        if item.get("mission_id") == mission_id
    ]
    return {"mission_id": mission_id, "leases": items}
