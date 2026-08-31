from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Header, Request
from pydantic import BaseModel, Field

from synapse.api.common import api_error, require_admin, runtime_from
from synapse.intelligence_boundary.models import (
    DataClassification,
    EgressRequest,
    InformationAsset,
    InformationOwnership,
    OperatingProfile,
    ProcessingBoundary,
    ProcessingPurpose,
    ProviderTrustProfile,
    TrainingUsePolicy,
    TrustProfileStatus,
)

router = APIRouter(tags=["intelligence-boundary"])


class InformationAssetPayload(BaseModel):
    asset_id: str
    owner: str
    source_domain: str
    source_reference: str
    content_type: str
    classification: str
    categories: list[str]
    project_id: str | None = None
    workspace_id: str | None = None
    content_handle: str | None = None
    processing_constraints: list[str] = Field(default_factory=list)
    retention_policy: str = "inherit"
    training_use_policy: str = "prohibited"
    external_processing_policy: str = "policy-controlled"
    provenance: dict[str, Any] = Field(default_factory=dict)
    parent_asset_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReclassificationPayload(BaseModel):
    classification: str
    justification: str
    approval_id: str | None = None
    redaction_validated: bool = False


class TrustProfilePayload(BaseModel):
    trust_profile_id: str
    provider_id: str
    processing_boundary: str
    organization_controlled: bool = False
    tenant_isolated: bool = False
    declared_retention: str = "unknown"
    declared_training_use: str = "unknown"
    data_residency: str | None = None
    contractual_controls: list[str] = Field(default_factory=list)
    supported_classifications: list[str] = Field(default_factory=list)
    blocked_classifications: list[str] = Field(default_factory=list)
    requires_redaction: bool = False
    allowed_categories: list[str] = Field(default_factory=list)
    blocked_categories: list[str] = Field(default_factory=list)
    supports_zero_retention_mode: bool = False
    verification_level: str = "user-configured-assumption"
    reviewed_at: str = ""
    expires_at: str | None = None
    status: str = "draft"
    provenance: dict[str, Any] = Field(default_factory=dict)


class TrustProfileUpdatePayload(BaseModel):
    processing_boundary: str | None = None
    organization_controlled: bool | None = None
    tenant_isolated: bool | None = None
    declared_retention: str | None = None
    declared_training_use: str | None = None
    data_residency: str | None = None
    contractual_controls: list[str] | None = None
    supported_classifications: list[str] | None = None
    blocked_classifications: list[str] | None = None
    requires_redaction: bool | None = None
    allowed_categories: list[str] | None = None
    blocked_categories: list[str] | None = None
    supports_zero_retention_mode: bool | None = None
    verification_level: str | None = None
    reviewed_at: str | None = None
    expires_at: str | None = None
    status: str | None = None
    provenance: dict[str, Any] | None = None


class EgressPreviewPayload(BaseModel):
    asset_ids: list[str]
    requester: str
    destination: str
    boundary: str
    purpose: str
    provider_id: str | None = None
    project_id: str | None = None
    rfc_id: str | None = None
    rfc_revision: int | None = None
    mission_id: str | None = None
    task_id: str | None = None
    requested_transformations: list[str] = Field(default_factory=list)
    payload_checksum: str
    estimated_size: int = 0
    estimated_tokens: int = 0
    correlation_id: str = ""
    constraints: list[str] = Field(default_factory=list)


class ApprovalPayload(BaseModel):
    manifest_id: str
    expires_in_minutes: int = 15


class ProfilePayload(BaseModel):
    profile: str


@router.get("/intelligence-boundary/status")
def boundary_status(request: Request) -> dict[str, Any]:
    return runtime_from(request).intelligence_boundary.status()


@router.get("/intelligence-boundary/profile")
def boundary_profile(request: Request) -> dict[str, str]:
    profile = runtime_from(request).intelligence_boundary.operating_profile()
    return {"profile": profile.value}


@router.put("/intelligence-boundary/profile")
def set_boundary_profile(
    payload: ProfilePayload,
    request: Request,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
) -> dict[str, str]:
    require_admin(x_actor_type)
    try:
        profile = runtime_from(request).intelligence_boundary.set_operating_profile(
            OperatingProfile(payload.profile), actor_id=x_actor_id or "system"
        )
        return {"profile": profile}
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/information-assets/{asset_id}")
def get_information_asset(asset_id: str, request: Request) -> dict[str, Any]:
    try:
        return asdict(runtime_from(request).intelligence_boundary.get_asset(asset_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/information-assets")
def classify_information_asset(
    payload: InformationAssetPayload,
    request: Request,
    x_actor_type: str | None = Header(default=None),
) -> dict[str, Any]:
    require_admin(x_actor_type)
    try:
        asset = InformationAsset(
            asset_id=payload.asset_id,
            owner=InformationOwnership(payload.owner),
            project_id=payload.project_id,
            workspace_id=payload.workspace_id,
            source_domain=payload.source_domain,
            source_reference=payload.source_reference,
            content_type=payload.content_type,
            classification=DataClassification(payload.classification),
            categories=tuple(payload.categories),
            processing_constraints=tuple(payload.processing_constraints),
            retention_policy=payload.retention_policy,
            training_use_policy=TrainingUsePolicy(payload.training_use_policy),
            external_processing_policy=payload.external_processing_policy,
            provenance=payload.provenance,
            parent_asset_ids=tuple(payload.parent_asset_ids),
            content_handle=payload.content_handle,
            metadata=payload.metadata,
        )
        return asdict(runtime_from(request).intelligence_boundary.register_asset(asset))
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/information-assets/{asset_id}/reclassify")
def reclassify_information_asset(
    asset_id: str,
    payload: ReclassificationPayload,
    request: Request,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
) -> dict[str, Any]:
    require_admin(x_actor_type)
    try:
        item = runtime_from(request).intelligence_boundary.reclassify_asset(
            asset_id,
            DataClassification(payload.classification),
            actor_id=x_actor_id or "system",
            justification=payload.justification,
            approval_id=payload.approval_id,
            redaction_validated=payload.redaction_validated,
        )
        return asdict(item)
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/egress/preview")
def preview_egress(payload: EgressPreviewPayload, request: Request) -> dict[str, Any]:
    try:
        authorization = runtime_from(request).intelligence_boundary.preview_egress(
            _egress_request(payload)
        )
        return asdict(authorization)
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/egress/decisions/{decision_id}")
def get_egress_decision(decision_id: str, request: Request) -> dict[str, Any]:
    try:
        return asdict(runtime_from(request).intelligence_boundary.get_decision(decision_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/egress/decisions/{decision_id}/approve")
def approve_egress(
    decision_id: str,
    payload: ApprovalPayload,
    request: Request,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
) -> dict[str, Any]:
    require_admin(x_actor_type)
    try:
        binding = runtime_from(request).intelligence_boundary.grant_approval(
            decision_id,
            payload.manifest_id,
            approver=x_actor_id or "system",
            actor_type=x_actor_type or "system",
            expires_in_minutes=payload.expires_in_minutes,
        )
        return asdict(binding)
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/egress/manifests/{manifest_id}")
def get_egress_manifest(manifest_id: str, request: Request) -> dict[str, Any]:
    try:
        return asdict(runtime_from(request).intelligence_boundary.get_manifest(manifest_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/egress/history")
def egress_history(request: Request) -> dict[str, Any]:
    records = runtime_from(request).intelligence_boundary.ledger_history()
    return {"records": [asdict(item) for item in records], "total": len(records)}


@router.get("/provider-trust-profiles")
def list_provider_trust_profiles(request: Request) -> dict[str, Any]:
    items = runtime_from(request).intelligence_boundary.list_trust_profiles()
    return {"profiles": [asdict(item) for item in items], "total": len(items)}


@router.get("/provider-trust-profiles/{trust_profile_id}")
def get_provider_trust_profile(
    trust_profile_id: str, request: Request
) -> dict[str, Any]:
    try:
        return asdict(
            runtime_from(request).intelligence_boundary.get_trust_profile(trust_profile_id)
        )
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/provider-trust-profiles")
def register_provider_trust_profile(
    payload: TrustProfilePayload,
    request: Request,
    x_actor_type: str | None = Header(default=None),
) -> dict[str, Any]:
    require_admin(x_actor_type)
    try:
        return asdict(
            runtime_from(request).intelligence_boundary.register_trust_profile(
                _trust_profile(payload)
            )
        )
    except Exception as exc:
        raise api_error(exc) from exc


@router.patch("/provider-trust-profiles/{trust_profile_id}")
def update_provider_trust_profile(
    trust_profile_id: str,
    payload: TrustProfileUpdatePayload,
    request: Request,
    x_actor_type: str | None = Header(default=None),
) -> dict[str, Any]:
    require_admin(x_actor_type)
    try:
        changes = payload.model_dump(exclude_none=True)
        return asdict(
            runtime_from(request).intelligence_boundary.update_trust_profile(
                trust_profile_id, changes
            )
        )
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/intelligence-boundary/unclassified")
def unclassified_assets(
    request: Request, x_actor_type: str | None = Header(default=None)
) -> dict[str, Any]:
    require_admin(x_actor_type)
    items = runtime_from(request).intelligence_boundary.list_assets(unclassified=True)
    return {"assets": [asdict(item) for item in items], "total": len(items)}


@router.get("/intelligence-boundary/unguarded-integrations")
def unguarded_integrations(
    request: Request, x_actor_type: str | None = Header(default=None)
) -> dict[str, Any]:
    require_admin(x_actor_type)
    status = runtime_from(request).intelligence_boundary.status()
    return {"paths": status["unguarded_paths"], "total": len(status["unguarded_paths"])}


@router.get("/intelligence-boundary/ledger-report")
def ledger_report(
    request: Request, x_actor_type: str | None = Header(default=None)
) -> dict[str, Any]:
    require_admin(x_actor_type)
    records = runtime_from(request).intelligence_boundary.ledger_history()
    return {
        "records": [asdict(item) for item in records],
        "payloads_included": False,
        "immutable": True,
    }


def _egress_request(payload: EgressPreviewPayload) -> EgressRequest:
    return EgressRequest(
        asset_ids=tuple(payload.asset_ids),
        requester=payload.requester,
        destination=payload.destination,
        boundary=ProcessingBoundary(payload.boundary),
        purpose=ProcessingPurpose(payload.purpose),
        provider_id=payload.provider_id,
        project_id=payload.project_id,
        rfc_id=payload.rfc_id,
        rfc_revision=payload.rfc_revision,
        mission_id=payload.mission_id,
        task_id=payload.task_id,
        requested_transformations=tuple(payload.requested_transformations),
        payload_checksum=payload.payload_checksum,
        estimated_size=payload.estimated_size,
        estimated_tokens=payload.estimated_tokens,
        correlation_id=payload.correlation_id,
        constraints=tuple(payload.constraints),
    )


def _trust_profile(payload: TrustProfilePayload) -> ProviderTrustProfile:
    return ProviderTrustProfile(
        trust_profile_id=payload.trust_profile_id,
        provider_id=payload.provider_id,
        processing_boundary=ProcessingBoundary(payload.processing_boundary),
        organization_controlled=payload.organization_controlled,
        tenant_isolated=payload.tenant_isolated,
        declared_retention=payload.declared_retention,
        declared_training_use=payload.declared_training_use,
        data_residency=payload.data_residency,
        contractual_controls=tuple(payload.contractual_controls),
        supported_classifications=tuple(
            DataClassification(item) for item in payload.supported_classifications
        ),
        blocked_classifications=tuple(
            DataClassification(item) for item in payload.blocked_classifications
        ),
        requires_redaction=payload.requires_redaction,
        allowed_categories=tuple(payload.allowed_categories),
        blocked_categories=tuple(payload.blocked_categories),
        supports_zero_retention_mode=payload.supports_zero_retention_mode,
        verification_level=payload.verification_level,
        reviewed_at=payload.reviewed_at,
        expires_at=payload.expires_at,
        status=TrustProfileStatus(payload.status),
        provenance=payload.provenance,
    )
