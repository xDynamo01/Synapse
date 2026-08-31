from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class DataClassification(StrEnum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"
    SECRET = "secret"


CLASSIFICATION_ORDER = {
    DataClassification.PUBLIC: 0,
    DataClassification.INTERNAL: 1,
    DataClassification.CONFIDENTIAL: 2,
    DataClassification.RESTRICTED: 3,
    DataClassification.SECRET: 4,
}


class InformationOwnership(StrEnum):
    USER = "user-owned"
    PROJECT = "project-owned"
    WORKSPACE = "workspace-owned"
    ORGANIZATION = "organization-owned"
    AGENT_TEMPORARY = "agent-temporary"
    MISSION_TEMPORARY = "mission-temporary"
    PROVIDER_DERIVED = "provider-derived"
    SHARED_WITH_CONSENT = "shared-with-consent"


class ProcessingBoundary(StrEnum):
    LOCAL_PROCESS = "local_process"
    LOCAL_MODEL = "local_model"
    LOCAL_NETWORK = "local_network"
    PRIVATE_TENANT = "private_tenant"
    MANAGED_ENTERPRISE = "managed_enterprise"
    EXTERNAL_PROVIDER = "external_provider"
    EXTERNAL_TOOL = "external_tool"
    EXTERNAL_MCP = "external_mcp"
    EXPORT = "export"
    USER_DEVICE = "user_device"
    AIR_GAPPED = "air_gapped"


LOCAL_BOUNDARIES = {
    ProcessingBoundary.LOCAL_PROCESS,
    ProcessingBoundary.LOCAL_MODEL,
    ProcessingBoundary.LOCAL_NETWORK,
    ProcessingBoundary.USER_DEVICE,
    ProcessingBoundary.AIR_GAPPED,
}


class ProcessingPurpose(StrEnum):
    MODEL_INFERENCE = "model_inference"
    TRANSCRIPTION = "transcription"
    SYNTHESIS = "synthesis"
    VISUAL_ANALYSIS = "visual_analysis"
    TOOL_EXECUTION = "tool_execution"
    CODE_ANALYSIS = "code_analysis"
    SUMMARIZATION = "summarization"
    EMBEDDING = "embedding"
    EVALUATION = "evaluation"
    SKILL_EXECUTION = "skill_execution"
    EXTERNAL_SEARCH = "external_search"
    EXTERNAL_RETRIEVAL = "external_retrieval"
    EXPORT = "export"
    BACKUP = "backup"
    TRAINING_FUTURE = "training_future"
    FINE_TUNING_FUTURE = "fine_tuning_future"
    DISTILLATION_FUTURE = "distillation_future"


class TrainingUsePolicy(StrEnum):
    PROHIBITED = "prohibited"
    LOCAL_EVALUATION_ONLY = "local_evaluation_only"
    LOCAL_TRAINING_ALLOWED = "local_training_allowed"
    LOCAL_FINE_TUNING_ALLOWED = "local_fine_tuning_allowed"
    LOCAL_DISTILLATION_ALLOWED = "local_distillation_allowed"
    TENANT_TRAINING_ALLOWED = "tenant_training_allowed"
    EXTERNAL_TRAINING_PROHIBITED = "external_training_prohibited"
    EXPLICIT_CONSENT_REQUIRED = "explicit_consent_required"


class EgressDecisionStatus(StrEnum):
    ALLOWED = "allowed"
    ALLOWED_MINIMIZED = "allowed_minimized"
    ALLOWED_REDACTED = "allowed_redacted"
    ALLOWED_SUMMARY_ONLY = "allowed_summary_only"
    APPROVAL_REQUIRED = "approval_required"
    LOCAL_ONLY = "local_only"
    DENIED = "denied"


class OperatingProfile(StrEnum):
    LOCAL_SOVEREIGN = "LOCAL_SOVEREIGN"
    HYBRID_GUARDED = "HYBRID_GUARDED"
    EXTERNAL_ASSISTED = "EXTERNAL_ASSISTED"
    AIR_GAPPED = "AIR_GAPPED"


class TrustProfileStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    EXPIRED = "expired"
    SUSPENDED = "suspended"
    INVALID = "invalid"


@dataclass(frozen=True)
class InformationAsset:
    asset_id: str
    owner: InformationOwnership
    source_domain: str
    source_reference: str
    content_type: str
    classification: DataClassification
    categories: tuple[str, ...]
    processing_constraints: tuple[str, ...] = ()
    retention_policy: str = "inherit"
    training_use_policy: TrainingUsePolicy = TrainingUsePolicy.PROHIBITED
    external_processing_policy: str = "policy-controlled"
    provenance: dict[str, Any] = field(default_factory=dict)
    parent_asset_ids: tuple[str, ...] = ()
    project_id: str | None = None
    workspace_id: str | None = None
    content_handle: str | None = None
    created_at: str = ""
    revision: int = 1
    checksum: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProviderTrustProfile:
    trust_profile_id: str
    provider_id: str
    processing_boundary: ProcessingBoundary
    organization_controlled: bool = False
    tenant_isolated: bool = False
    declared_retention: str = "unknown"
    declared_training_use: str = "unknown"
    data_residency: str | None = None
    contractual_controls: tuple[str, ...] = ()
    supported_classifications: tuple[DataClassification, ...] = ()
    blocked_classifications: tuple[DataClassification, ...] = ()
    requires_redaction: bool = False
    allowed_categories: tuple[str, ...] = ()
    blocked_categories: tuple[str, ...] = ()
    supports_zero_retention_mode: bool = False
    verification_level: str = "user-configured-assumption"
    reviewed_at: str = ""
    expires_at: str | None = None
    status: TrustProfileStatus = TrustProfileStatus.DRAFT
    provenance: dict[str, Any] = field(default_factory=dict)
    revision: int = 1
    checksum: str = ""


@dataclass(frozen=True)
class MinimizationPlan:
    included_assets: tuple[str, ...]
    omitted_assets: tuple[str, ...]
    summarized_assets: tuple[str, ...]
    redaction_candidates: tuple[str, ...]
    reasons: dict[str, str]
    estimated_tokens: int
    original_estimated_tokens: int
    residual_risk: str


@dataclass(frozen=True)
class RedactionPlan:
    source_checksum: str
    transformed_checksum: str
    rules_applied: tuple[str, ...]
    fields_removed: tuple[str, ...]
    classification_before: DataClassification
    classification_after: DataClassification
    residual_risk: str
    validation_status: str


@dataclass(frozen=True)
class EgressRequest:
    asset_ids: tuple[str, ...]
    requester: str
    destination: str
    boundary: ProcessingBoundary
    purpose: ProcessingPurpose
    provider_id: str | None = None
    project_id: str | None = None
    rfc_id: str | None = None
    rfc_revision: int | None = None
    mission_id: str | None = None
    task_id: str | None = None
    requested_transformations: tuple[str, ...] = ()
    payload_checksum: str = ""
    estimated_size: int = 0
    estimated_tokens: int = 0
    correlation_id: str = ""
    actor_type: str = "user"
    approval_reference: str | None = None
    constraints: tuple[str, ...] = ()


@dataclass(frozen=True)
class EgressDecision:
    decision_id: str
    status: EgressDecisionStatus
    allowed_assets: tuple[str, ...]
    blocked_assets: tuple[str, ...]
    required_transformations: tuple[str, ...]
    redaction_plan: RedactionPlan | None
    minimization_plan: MinimizationPlan
    approval_required: bool
    approval_scope: dict[str, Any]
    reasons: tuple[str, ...]
    warnings: tuple[str, ...]
    expires_at: str
    revision: int
    checksum: str
    trace_id: str


@dataclass(frozen=True)
class EgressManifest:
    manifest_id: str
    decision_id: str
    requester: str
    provider_id: str | None
    destination: str
    boundary: ProcessingBoundary
    purpose: ProcessingPurpose
    asset_references: tuple[str, ...]
    source_classifications: tuple[DataClassification, ...]
    resulting_classifications: tuple[DataClassification, ...]
    categories: tuple[str, ...]
    transformations: tuple[str, ...]
    payload_checksum: str
    estimated_size: int
    estimated_tokens: int
    created_at: str
    expires_at: str
    revision: int
    checksum: str
    project_id: str | None = None
    rfc_id: str | None = None
    rfc_revision: int | None = None
    mission_id: str | None = None
    task_id: str | None = None
    approval_reference: str | None = None


@dataclass(frozen=True)
class EgressApprovalBinding:
    approval_id: str
    decision_id: str
    manifest_checksum: str
    provider_id: str | None
    destination: str
    purpose: ProcessingPurpose
    classifications: tuple[DataClassification, ...]
    categories: tuple[str, ...]
    transformations: tuple[str, ...]
    requester: str
    approver: str
    expires_at: str
    status: str = "approved"


@dataclass(frozen=True)
class EgressLedgerRecord:
    record_id: str
    record_type: str
    decision_id: str
    manifest_id: str | None
    provider_id: str | None
    destination: str
    purpose: ProcessingPurpose
    categories: tuple[str, ...]
    classifications: tuple[DataClassification, ...]
    transformation_summary: tuple[str, ...]
    approval_reference: str | None
    status: str
    estimated_bytes: int
    estimated_tokens: int
    result_reference: str | None
    created_at: str
    correlation_id: str
    error_code: str | None = None
    related_record_id: str | None = None


@dataclass(frozen=True)
class DerivedArtifactProvenance:
    asset_id: str
    input_asset_ids: tuple[str, ...]
    provider_id: str | None
    model_id: str | None
    purpose: ProcessingPurpose
    manifest_id: str | None
    output_checksum: str
    classification_rule: str
    owner: InformationOwnership
    created_at: str
    training_use_policy: TrainingUsePolicy


@dataclass(frozen=True)
class EgressAuthorization:
    allowed: bool
    decision: EgressDecision
    manifest: EgressManifest | None
    reason: str
