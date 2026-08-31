from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Header, Request
from pydantic import BaseModel, Field

from synapse.api.common import api_error, require_admin, runtime_from
from synapse.project_governance.models import (
    AcceptanceCriterion,
    ChangeClass,
    CriterionStatus,
    EvidenceRecord,
    ImplementationPlan,
    ProjectManifest,
    ReviewDecision,
    ReviewRole,
    RFCGateRequest,
    RFCManifest,
    RFCReview,
    RFCStatus,
)

router = APIRouter(tags=["project-governance"])


class ProjectPayload(BaseModel):
    project_id: str
    name: str
    description: str
    root_reference: str
    owner: str
    default_policy_id: str
    primary_agent_id: str | None = None
    allowed_provider_profiles: list[str] = Field(default_factory=list)
    classification_policy: dict[str, Any] = Field(default_factory=dict)
    rfc_policy: dict[str, Any] = Field(default_factory=dict)
    quality_gate_policy: dict[str, Any] = Field(default_factory=dict)
    skill_scope: dict[str, Any] = Field(default_factory=dict)
    memory_scope: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProjectUpdatePayload(BaseModel):
    description: str | None = None
    status: str | None = None
    owner: str | None = None
    primary_agent_id: str | None = None
    allowed_provider_profiles: list[str] | None = None
    classification_policy: dict[str, Any] | None = None
    rfc_policy: dict[str, Any] | None = None
    quality_gate_policy: dict[str, Any] | None = None
    skill_scope: dict[str, Any] | None = None
    memory_scope: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None


class CriterionPayload(BaseModel):
    criterion_id: str
    description: str
    type: str
    verification_method: str
    required: bool = True
    evidence_types: list[str] = Field(default_factory=list)
    linked_requirements: list[str] = Field(default_factory=list)
    linked_invariants: list[str] = Field(default_factory=list)


class RFCCreatePayload(BaseModel):
    rfc_id: str
    title: str
    markdown: str
    authors: list[str]
    reviewers: list[str]
    affected_domains: list[str]
    affected_contracts: list[str]
    change_classification: str
    risk_level: str = "medium"
    affected_references: list[str] = Field(default_factory=list)
    required_approvals: list[str] = Field(default_factory=list)
    acceptance_criteria: list[CriterionPayload] = Field(default_factory=list)
    invariants: list[str] = Field(default_factory=list)
    out_of_scope: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RFCRevisePayload(BaseModel):
    markdown: str
    change_summary: str
    title: str | None = None
    affected_domains: list[str] | None = None
    affected_contracts: list[str] | None = None
    acceptance_criteria: list[CriterionPayload] | None = None


class RFCReviewPayload(BaseModel):
    reviewer_id: str
    reviewer_type: str
    role: str
    decision: str
    comment: str
    reference_type: str
    reference_id: str


class RFCSupersedePayload(BaseModel):
    replacement_rfc_id: str


class RFCGatePayload(BaseModel):
    requested_change: str
    domains: list[str] = Field(default_factory=list)
    contracts: list[str] = Field(default_factory=list)
    mission_id: str | None = None
    skill_ids: list[str] = Field(default_factory=list)
    plan_reference: dict[str, Any] | None = None
    rfc_id: str | None = None
    rfc_revision: int | None = None
    rfc_checksum: str | None = None
    impact: dict[str, Any] = Field(default_factory=dict)
    correlation_id: str | None = None


class PlanCreatePayload(BaseModel):
    rfc_id: str
    rfc_revision: int
    rfc_checksum: str
    objective: str
    scope: list[str]
    allowed_domains: list[str]
    allowed_references: list[str] = Field(default_factory=list)
    forbidden_changes: list[str] = Field(default_factory=list)
    tasks: list[dict[str, Any]]
    dependencies: dict[str, list[str]] = Field(default_factory=dict)
    required_skills: list[str] = Field(default_factory=list)
    required_tools: list[str] = Field(default_factory=list)
    acceptance_criteria: list[CriterionPayload]
    rollback_plan: str
    correlation_id: str | None = None


class EvidencePayload(BaseModel):
    rfc_id: str
    rfc_revision: int
    plan_id: str
    evidence_type: str
    summary: str
    artifact_reference: str
    checksum: str
    produced_by: str
    validation_status: str
    mission_id: str | None = None
    task_id: str | None = None
    attempt_id: str | None = None
    correlation_id: str | None = None
    classification: str = "internal"


class CriterionUpdatePayload(BaseModel):
    status: str
    result_reference: str | None = None
    waiver: dict[str, Any] | None = None


def _criteria(items: list[CriterionPayload]) -> tuple[AcceptanceCriterion, ...]:
    return tuple(
        AcceptanceCriterion(
            item.criterion_id,
            item.description,
            item.type,
            item.verification_method,
            item.required,
            tuple(item.evidence_types),
            linked_requirements=tuple(item.linked_requirements),
            linked_invariants=tuple(item.linked_invariants),
        )
        for item in items
    )


@router.get("/projects")
def list_projects(request: Request) -> dict[str, Any]:
    items = runtime_from(request).project_governance.projects.list()
    return {"projects": [asdict(item) for item in items], "total": len(items)}


@router.post("/projects")
def register_project(
    payload: ProjectPayload,
    request: Request,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
) -> dict[str, Any]:
    require_admin(x_actor_type)
    try:
        manifest = ProjectManifest(
            payload.project_id,
            payload.name,
            payload.description,
            payload.root_reference,
            payload.owner,
            payload.default_policy_id,
            primary_agent_id=payload.primary_agent_id,
            allowed_provider_profiles=tuple(payload.allowed_provider_profiles),
            classification_policy=payload.classification_policy,
            rfc_policy=payload.rfc_policy,
            quality_gate_policy=payload.quality_gate_policy,
            skill_scope=payload.skill_scope,
            memory_scope=payload.memory_scope or {"ownership": "project-owned"},
            metadata=payload.metadata,
        )
        return asdict(
            runtime_from(request).project_governance.projects.register(
                manifest, actor_id=x_actor_id or "system"
            )
        )
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/projects/{project_id}")
def get_project(project_id: str, request: Request) -> dict[str, Any]:
    try:
        return asdict(runtime_from(request).project_governance.projects.get(project_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.patch("/projects/{project_id}")
def update_project(
    project_id: str,
    payload: ProjectUpdatePayload,
    request: Request,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
) -> dict[str, Any]:
    require_admin(x_actor_type)
    updates = payload.model_dump(exclude_none=True)
    if "allowed_provider_profiles" in updates:
        updates["allowed_provider_profiles"] = tuple(updates["allowed_provider_profiles"])
    try:
        return asdict(
            runtime_from(request).project_governance.projects.update(
                project_id, updates, actor_id=x_actor_id or "system"
            )
        )
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/projects/{project_id}/archive")
def archive_project(
    project_id: str,
    request: Request,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
) -> dict[str, Any]:
    require_admin(x_actor_type)
    return asdict(
        runtime_from(request).project_governance.projects.archive(
            project_id, actor_id=x_actor_id or "system"
        )
    )


@router.get("/projects/{project_id}/context")
def project_context(project_id: str, request: Request, budget: int = 8000) -> dict[str, Any]:
    return asdict(
        runtime_from(request).project_governance.read_project_context(project_id, budget=budget)
    )


@router.get("/projects/{project_id}/rfcs")
def list_rfcs(
    project_id: str,
    request: Request,
    status: str | None = None,
    domain: str | None = None,
) -> dict[str, Any]:
    items = runtime_from(request).project_governance.rfcs.list(
        project_id, status=status, domain=domain
    )
    return {"rfcs": [asdict(item) for item in items], "total": len(items)}


@router.post("/projects/{project_id}/rfcs")
def create_rfc(
    project_id: str,
    payload: RFCCreatePayload,
    request: Request,
    x_actor_id: str | None = Header(default=None),
) -> dict[str, Any]:
    try:
        manifest = RFCManifest(
            payload.rfc_id,
            project_id,
            payload.title,
            tuple(payload.authors),
            tuple(payload.reviewers),
            tuple(payload.affected_domains),
            tuple(payload.affected_contracts),
            ChangeClass(payload.change_classification),
            risk_level=payload.risk_level,
            affected_references=tuple(payload.affected_references),
            required_approvals=tuple(payload.required_approvals),
            acceptance_criteria=_criteria(payload.acceptance_criteria),
            invariants=tuple(payload.invariants),
            out_of_scope=tuple(payload.out_of_scope),
            metadata=payload.metadata,
        )
        governance = runtime_from(request).project_governance
        created = governance.rfcs.create(
            manifest, payload.markdown, actor_id=x_actor_id or payload.authors[0]
        )
        return {
            "manifest": asdict(created),
            "validation": asdict(governance.validation.validate(project_id, payload.rfc_id)),
        }
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/projects/{project_id}/rfcs/{rfc_id}")
def get_rfc(project_id: str, rfc_id: str, request: Request) -> dict[str, Any]:
    try:
        governance = runtime_from(request).project_governance
        return {
            "manifest": asdict(governance.rfcs.get(project_id, rfc_id)),
            "markdown": governance.rfcs.content(project_id, rfc_id),
            "revisions": [asdict(item) for item in governance.versions.list(project_id, rfc_id)],
        }
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/projects/{project_id}/rfcs/{rfc_id}/revise")
def revise_rfc(
    project_id: str,
    rfc_id: str,
    payload: RFCRevisePayload,
    request: Request,
    x_actor_id: str | None = Header(default=None),
) -> dict[str, Any]:
    updates = payload.model_dump(exclude={"markdown", "change_summary"}, exclude_none=True)
    for field in ("affected_domains", "affected_contracts"):
        if field in updates:
            updates[field] = tuple(updates[field])
    if "acceptance_criteria" in updates:
        updates["acceptance_criteria"] = _criteria(payload.acceptance_criteria or [])
    try:
        return asdict(
            runtime_from(request).project_governance.rfcs.revise(
                project_id,
                rfc_id,
                payload.markdown,
                actor_id=x_actor_id or "author",
                change_summary=payload.change_summary,
                updates=updates,
            )
        )
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/projects/{project_id}/rfcs/{rfc_id}/validate")
def validate_rfc(project_id: str, rfc_id: str, request: Request) -> dict[str, Any]:
    return asdict(runtime_from(request).project_governance.validation.validate(project_id, rfc_id))


def _review(project_id: str, rfc_id: str, payload: RFCReviewPayload, request: Request) -> RFCReview:
    current = runtime_from(request).project_governance.rfcs.get(project_id, rfc_id)
    return RFCReview(
        project_id,
        rfc_id,
        current.revision,
        payload.reviewer_id,
        payload.reviewer_type,
        ReviewRole(payload.role),
        ReviewDecision(payload.decision),
        payload.comment,
        payload.reference_type,
        payload.reference_id,
    )


@router.post("/projects/{project_id}/rfcs/{rfc_id}/review")
def review_rfc(
    project_id: str, rfc_id: str, payload: RFCReviewPayload, request: Request
) -> dict[str, Any]:
    try:
        return asdict(
            runtime_from(request).project_governance.reviews.record(
                _review(project_id, rfc_id, payload, request)
            )
        )
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/projects/{project_id}/rfcs/{rfc_id}/approve")
def approve_rfc(
    project_id: str, rfc_id: str, payload: RFCReviewPayload, request: Request
) -> dict[str, Any]:
    try:
        return asdict(
            runtime_from(request).project_governance.reviews.approve(
                _review(project_id, rfc_id, payload, request)
            )
        )
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/projects/{project_id}/rfcs/{rfc_id}/reject")
def reject_rfc(
    project_id: str, rfc_id: str, payload: RFCReviewPayload, request: Request
) -> dict[str, Any]:
    try:
        return asdict(
            runtime_from(request).project_governance.reviews.reject(
                _review(project_id, rfc_id, payload, request)
            )
        )
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/projects/{project_id}/rfcs/{rfc_id}/supersede")
def supersede_rfc(
    project_id: str,
    rfc_id: str,
    payload: RFCSupersedePayload,
    request: Request,
    x_actor_id: str | None = Header(default=None),
) -> dict[str, Any]:
    governance = runtime_from(request).project_governance
    governance.rfcs.get(project_id, payload.replacement_rfc_id)
    return asdict(
        governance.rfcs.transition(
            project_id,
            rfc_id,
            RFCStatus.SUPERSEDED,
            actor_id=x_actor_id or "owner",
            extra={"superseded_by": payload.replacement_rfc_id},
        )
    )


@router.post("/projects/{project_id}/rfc-gate")
def evaluate_rfc_gate(
    project_id: str,
    payload: RFCGatePayload,
    request: Request,
    x_actor_id: str | None = Header(default=None),
) -> dict[str, Any]:
    return asdict(
        runtime_from(request).project_governance.evaluate_gate(
            RFCGateRequest(
                project_id,
                payload.requested_change,
                tuple(payload.domains),
                tuple(payload.contracts),
                payload.mission_id,
                tuple(payload.skill_ids),
                payload.plan_reference,
                x_actor_id or "system",
                payload.correlation_id,
                payload.rfc_id,
                payload.rfc_revision,
                payload.rfc_checksum,
                payload.impact,
            )
        )
    )


@router.get("/projects/{project_id}/implementation-plans")
def list_plans(project_id: str, request: Request) -> dict[str, Any]:
    items = runtime_from(request).project_governance.plans.list(project_id)
    return {"plans": [asdict(item) for item in items], "total": len(items)}


@router.post("/projects/{project_id}/implementation-plans")
def create_plan(
    project_id: str,
    payload: PlanCreatePayload,
    request: Request,
    x_actor_id: str | None = Header(default=None),
) -> dict[str, Any]:
    try:
        plan = ImplementationPlan(
            project_id,
            payload.rfc_id,
            payload.rfc_revision,
            payload.rfc_checksum,
            payload.objective,
            tuple(payload.scope),
            tuple(payload.allowed_domains),
            tuple(payload.allowed_references),
            tuple(payload.forbidden_changes),
            tuple(payload.tasks),
            {key: tuple(value) for key, value in payload.dependencies.items()},
            tuple(payload.required_skills),
            tuple(payload.required_tools),
            (),
            (),
            _criteria(payload.acceptance_criteria),
            payload.rollback_plan,
            x_actor_id or "system",
            payload.correlation_id,
        )
        return asdict(runtime_from(request).project_governance.plans.create(plan))
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/projects/{project_id}/implementation-plans/{plan_id}")
def get_plan(project_id: str, plan_id: str, request: Request) -> dict[str, Any]:
    plan = runtime_from(request).project_governance.plans.get(plan_id)
    if plan.project_id != project_id:
        raise api_error(ValueError("Plan belongs to another project"))
    return asdict(plan)


@router.post("/projects/{project_id}/implementation-plans/{plan_id}/validate")
def validate_plan(project_id: str, plan_id: str, request: Request) -> dict[str, Any]:
    plan = runtime_from(request).project_governance.plans.validate(plan_id)
    if plan.project_id != project_id:
        raise api_error(ValueError("Plan belongs to another project"))
    return asdict(plan)


@router.get("/projects/{project_id}/evidence")
def list_evidence(project_id: str, request: Request, rfc_id: str | None = None) -> dict[str, Any]:
    items = runtime_from(request).project_governance.evidence.list(project_id, rfc_id=rfc_id)
    return {"evidence": [asdict(item) for item in items], "total": len(items)}


@router.post("/projects/{project_id}/evidence")
def record_evidence(project_id: str, payload: EvidencePayload, request: Request) -> dict[str, Any]:
    try:
        return asdict(
            runtime_from(request).project_governance.record_evidence(
                EvidenceRecord(
                    project_id,
                    payload.rfc_id,
                    payload.rfc_revision,
                    payload.plan_id,
                    payload.evidence_type,
                    payload.summary,
                    payload.artifact_reference,
                    payload.checksum,
                    payload.produced_by,
                    payload.validation_status,
                    payload.correlation_id,
                    payload.mission_id,
                    payload.task_id,
                    payload.attempt_id,
                    classification=payload.classification,
                )
            )
        )
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/projects/{project_id}/implementation-plans/{plan_id}/acceptance")
def acceptance_status(project_id: str, plan_id: str, request: Request) -> dict[str, Any]:
    plan = runtime_from(request).project_governance.plans.get(plan_id)
    if plan.project_id != project_id:
        raise api_error(ValueError("Plan belongs to another project"))
    return {"criteria": [asdict(item) for item in plan.acceptance_criteria]}


@router.patch("/projects/{project_id}/implementation-plans/{plan_id}/acceptance/{criterion_id}")
def update_acceptance(
    project_id: str,
    plan_id: str,
    criterion_id: str,
    payload: CriterionUpdatePayload,
    request: Request,
    x_actor_id: str | None = Header(default=None),
) -> dict[str, Any]:
    plan = runtime_from(request).project_governance.plans.get(plan_id)
    if plan.project_id != project_id:
        raise api_error(ValueError("Plan belongs to another project"))
    return asdict(
        runtime_from(request).project_governance.update_criterion(
            plan_id,
            criterion_id,
            CriterionStatus(payload.status),
            actor_id=x_actor_id or "system",
            result_reference=payload.result_reference,
            waiver=payload.waiver,
        )
    )
