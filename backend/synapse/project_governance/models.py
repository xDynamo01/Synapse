from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


class ProjectStatus(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    ARCHIVED = "archived"
    UNAVAILABLE = "unavailable"
    MISCONFIGURED = "misconfigured"


class RFCStatus(StrEnum):
    DRAFT = "draft"
    UNDER_REVIEW = "under_review"
    CHANGES_REQUESTED = "changes_requested"
    APPROVED = "approved"
    IMPLEMENTING = "implementing"
    IMPLEMENTED = "implemented"
    SUPERSEDED = "superseded"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


class ChangeClass(StrEnum):
    TRIVIAL = "trivial"
    LOCAL_NON_BEHAVIORAL = "local_non_behavioral"
    BEHAVIORAL = "behavioral"
    CONTRACT_CHANGE = "contract_change"
    ARCHITECTURAL = "architectural"
    PERSISTENCE_CHANGE = "persistence_change"
    LIFECYCLE_CHANGE = "lifecycle_change"
    POLICY_CHANGE = "policy_change"
    DESTRUCTIVE = "destructive"
    REMOVAL = "removal"


class ReviewRole(StrEnum):
    AUTHOR = "author"
    TECHNICAL_REVIEWER = "technical_reviewer"
    DOMAIN_REVIEWER = "domain_reviewer"
    QUALITY_REVIEWER = "quality_reviewer"
    OPERATOR = "operator"
    OWNER = "owner"


class ReviewDecision(StrEnum):
    COMMENT = "comment"
    REQUEST_CHANGES = "request_changes"
    APPROVE = "approve"
    REJECT = "reject"
    ABSTAIN = "abstain"


class ImplementationPlanStatus(StrEnum):
    DRAFT = "draft"
    VALIDATED = "validated"
    APPROVED = "approved"
    EXECUTING = "executing"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    STALE = "stale"


class CriterionStatus(StrEnum):
    PENDING = "pending"
    SATISFIED = "satisfied"
    FAILED = "failed"
    WAIVED = "waived"


@dataclass(frozen=True)
class ProjectManifest:
    project_id: str
    name: str
    description: str
    root_reference: str
    owner: str
    default_policy_id: str
    status: ProjectStatus = ProjectStatus.ACTIVE
    primary_agent_id: str | None = None
    default_model_requirements: dict[str, Any] = field(default_factory=dict)
    allowed_provider_profiles: tuple[str, ...] = ()
    classification_policy: dict[str, Any] = field(default_factory=dict)
    rfc_policy: dict[str, Any] = field(default_factory=dict)
    quality_gate_policy: dict[str, Any] = field(default_factory=dict)
    skill_scope: dict[str, Any] = field(default_factory=dict)
    memory_scope: dict[str, Any] = field(default_factory=lambda: {"ownership": "project-owned"})
    classification: str = "internal"
    external_processing_allowed: bool = False
    redaction_required: bool = True
    private_eval_only: bool = True
    training_use: str = "prohibited"
    ownership: str = "project-owned"
    metadata: dict[str, Any] = field(default_factory=dict)
    revision: int = 1
    checksum: str = ""
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)


@dataclass(frozen=True)
class EvalReference:
    eval_id: str
    version: str
    required: bool
    dataset_reference: str
    metric: str
    threshold: float | int | str
    private_only: bool = True


@dataclass(frozen=True)
class QualityGateDescriptor:
    gate_id: str
    name: str
    type: str
    required: bool
    tool_reference: str
    thresholds: dict[str, Any] = field(default_factory=dict)
    blocking: bool = True
    evidence_type: str = "test_result"
    platform_constraints: tuple[str, ...] = ()


@dataclass(frozen=True)
class AcceptanceCriterion:
    criterion_id: str
    description: str
    type: str
    verification_method: str
    required: bool = True
    evidence_types: tuple[str, ...] = ()
    status: CriterionStatus = CriterionStatus.PENDING
    linked_requirements: tuple[str, ...] = ()
    linked_invariants: tuple[str, ...] = ()
    result_reference: str | None = None
    waiver: dict[str, Any] | None = None


@dataclass(frozen=True)
class RFCManifest:
    rfc_id: str
    project_id: str
    title: str
    authors: tuple[str, ...]
    reviewers: tuple[str, ...]
    affected_domains: tuple[str, ...]
    affected_contracts: tuple[str, ...]
    change_classification: ChangeClass
    risk_level: str = "medium"
    revision: int = 1
    status: RFCStatus = RFCStatus.DRAFT
    approved_at: str | None = None
    implemented_at: str | None = None
    supersedes: tuple[str, ...] = ()
    superseded_by: str | None = None
    affected_references: tuple[str, ...] = ()
    required_approvals: tuple[str, ...] = ()
    required_evals: tuple[EvalReference, ...] = ()
    required_quality_gates: tuple[QualityGateDescriptor, ...] = ()
    implementation_plan_ids: tuple[str, ...] = ()
    acceptance_criteria: tuple[AcceptanceCriterion, ...] = ()
    invariants: tuple[str, ...] = ()
    out_of_scope: tuple[str, ...] = ()
    classification: str = "internal"
    external_processing_allowed: bool = False
    allowed_provider_profiles: tuple[str, ...] = ()
    redaction_required: bool = True
    private_eval_only: bool = True
    training_use: str = "prohibited"
    ownership: str = "project-owned"
    metadata: dict[str, Any] = field(default_factory=dict)
    checksum: str = ""
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)


@dataclass(frozen=True)
class RFCRevision:
    rfc_id: str
    project_id: str
    revision: int
    checksum: str
    author: str
    change_summary: str
    base_revision: int | None
    created_at: str = field(default_factory=now_iso)


@dataclass(frozen=True)
class RFCValidationResult:
    valid: bool
    warnings: tuple[str, ...] = ()
    missing_sections: tuple[str, ...] = ()
    unresolved_questions: tuple[str, ...] = ()
    conflicting_rfcs: tuple[str, ...] = ()
    stale_references: tuple[str, ...] = ()
    missing_evals: tuple[str, ...] = ()
    missing_acceptance_criteria: tuple[str, ...] = ()


@dataclass(frozen=True)
class RFCReview:
    project_id: str
    rfc_id: str
    rfc_revision: int
    reviewer_id: str
    reviewer_type: str
    role: ReviewRole
    decision: ReviewDecision
    comment: str
    reference_type: str
    reference_id: str
    review_id: str = field(default_factory=lambda: str(uuid4()))
    created_at: str = field(default_factory=now_iso)


@dataclass(frozen=True)
class ClarificationResult:
    resolved_decisions: tuple[dict[str, str], ...] = ()
    open_questions: tuple[dict[str, str], ...] = ()
    proposed_patches: tuple[dict[str, Any], ...] = ()
    assumptions: tuple[str, ...] = ()
    risks: tuple[str, ...] = ()
    complete: bool = False


@dataclass(frozen=True)
class ChangeClassificationResult:
    classification: ChangeClass
    rfc_disposition: str
    reasons: tuple[str, ...]
    required_reviewers: tuple[str, ...] = ()
    required_evidence: tuple[str, ...] = ()
    approval_required: bool = False


@dataclass(frozen=True)
class RFCGateRequest:
    project_id: str
    requested_change: str
    domains: tuple[str, ...]
    contracts: tuple[str, ...]
    mission_id: str | None = None
    skill_ids: tuple[str, ...] = ()
    plan_reference: dict[str, Any] | None = None
    requester: str = "system"
    correlation_id: str | None = None
    rfc_id: str | None = None
    rfc_revision: int | None = None
    rfc_checksum: str | None = None
    impact: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RFCGateResult:
    disposition: str
    allowed: bool
    reasons: tuple[str, ...]
    approval_required: bool = False
    rfc_id: str | None = None
    rfc_revision: int | None = None
    rfc_checksum: str | None = None


@dataclass(frozen=True)
class ImplementationPlan:
    project_id: str
    rfc_id: str
    rfc_revision: int
    rfc_checksum: str
    objective: str
    scope: tuple[str, ...]
    allowed_domains: tuple[str, ...]
    allowed_references: tuple[str, ...]
    forbidden_changes: tuple[str, ...]
    tasks: tuple[dict[str, Any], ...]
    dependencies: dict[str, tuple[str, ...]]
    required_skills: tuple[str, ...]
    required_tools: tuple[str, ...]
    quality_gates: tuple[QualityGateDescriptor, ...]
    evals: tuple[EvalReference, ...]
    acceptance_criteria: tuple[AcceptanceCriterion, ...]
    rollback_plan: str
    created_by: str
    correlation_id: str | None = None
    status: ImplementationPlanStatus = ImplementationPlanStatus.DRAFT
    revision: int = 1
    checksum: str = ""
    plan_id: str = field(default_factory=lambda: str(uuid4()))
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)


@dataclass(frozen=True)
class RFCImplementationBinding:
    project_id: str
    rfc_id: str
    rfc_revision: int
    rfc_checksum: str
    plan_id: str
    plan_revision: int
    plan_checksum: str


@dataclass(frozen=True)
class EvidenceRecord:
    project_id: str
    rfc_id: str
    rfc_revision: int
    plan_id: str
    evidence_type: str
    summary: str
    artifact_reference: str
    checksum: str
    produced_by: str
    validation_status: str
    correlation_id: str | None = None
    mission_id: str | None = None
    task_id: str | None = None
    attempt_id: str | None = None
    provenance: tuple[dict[str, Any], ...] = ()
    classification: str = "internal"
    evidence_id: str = field(default_factory=lambda: str(uuid4()))
    created_at: str = field(default_factory=now_iso)


@dataclass(frozen=True)
class ADRRecord:
    project_id: str
    title: str
    context: str
    decision: str
    consequences: tuple[str, ...]
    alternatives: tuple[str, ...]
    linked_rfc_ids: tuple[str, ...]
    status: str = "proposed"
    supersedes: tuple[str, ...] = ()
    revision: int = 1
    checksum: str = ""
    adr_id: str = field(default_factory=lambda: str(uuid4()))


@dataclass(frozen=True)
class ProjectContext:
    project_id: str
    project_revision: int
    active_rfcs: tuple[dict[str, Any], ...]
    relevant_adrs: tuple[dict[str, Any], ...]
    active_plans: tuple[dict[str, Any], ...]
    constraints: tuple[str, ...]
    invariants: tuple[str, ...]
    allowed_skills: tuple[str, ...]
    quality_gates: tuple[dict[str, Any], ...]
    provenance: tuple[dict[str, Any], ...]
    classification: str
    truncated: bool = False
