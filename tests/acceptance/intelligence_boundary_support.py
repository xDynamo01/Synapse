from __future__ import annotations

from pathlib import Path

from synapse.bootstrap.adapters.intelligence_boundary import BoundaryRecordStoreAdapter
from synapse.core.events import EventBus
from synapse.intelligence_boundary.models import (
    DataClassification,
    EgressRequest,
    InformationAsset,
    InformationOwnership,
    ProcessingBoundary,
    ProcessingPurpose,
    ProviderTrustProfile,
    TrainingUsePolicy,
    TrustProfileStatus,
)
from synapse.intelligence_boundary.runtime import IntelligenceBoundaryRuntime
from synapse.storage.collection import FileCollection


def boundary_runtime(root: Path) -> IntelligenceBoundaryRuntime:
    root = root.resolve()
    events = EventBus(root)
    stores = {
        name: BoundaryRecordStoreAdapter(
            FileCollection(
                collection_id=f"test_intelligence_{name}",
                root=root / "boundary" / name,
                current_schema_version=1,
                events=events,
            )
        )
        for name in (
            "assets", "trust_profiles", "decisions", "manifests", "approvals",
            "ledger", "settings",
        )
    }
    return IntelligenceBoundaryRuntime(
        stores=stores,
        events=events,
        protected_integrations=("models", "tools", "mcp"),
        unguarded_paths=("desktop_automation_ui_uploads",),
    )


def trust_external(runtime: IntelligenceBoundaryRuntime, provider_id: str = "external") -> None:
    runtime.register_trust_profile(
        ProviderTrustProfile(
            trust_profile_id=f"trust-{provider_id}",
            provider_id=provider_id,
            processing_boundary=ProcessingBoundary.EXTERNAL_PROVIDER,
            supported_classifications=(
                DataClassification.PUBLIC,
                DataClassification.INTERNAL,
                DataClassification.CONFIDENTIAL,
            ),
            status=TrustProfileStatus.ACTIVE,
        )
    )


def asset(
    runtime: IntelligenceBoundaryRuntime,
    asset_id: str,
    classification: DataClassification = DataClassification.INTERNAL,
    *,
    category: str = "memory.project",
    relevant: bool = True,
    external_policy: str = "policy-controlled",
) -> InformationAsset:
    return runtime.register_asset(
        InformationAsset(
            asset_id=asset_id,
            owner=InformationOwnership.PROJECT,
            project_id="project-a",
            source_domain="acceptance",
            source_reference=f"test:{asset_id}",
            content_type="text/plain",
            classification=classification,
            categories=(category,),
            training_use_policy=TrainingUsePolicy.PROHIBITED,
            external_processing_policy=external_policy,
            metadata={"estimated_tokens": 10, "relevant": relevant},
        )
    )


def egress_request(
    asset_ids: tuple[str, ...],
    *,
    boundary: ProcessingBoundary = ProcessingBoundary.EXTERNAL_PROVIDER,
    provider_id: str = "external",
    payload_checksum: str = "payload-v1",
    approval_reference: str | None = None,
    constraints: tuple[str, ...] = (),
) -> EgressRequest:
    return EgressRequest(
        asset_ids=asset_ids,
        requester="user-a",
        destination="https://provider.example",
        boundary=boundary,
        purpose=ProcessingPurpose.MODEL_INFERENCE,
        provider_id=provider_id,
        project_id="project-a",
        rfc_id="rfc-a",
        rfc_revision=1,
        mission_id="mission-a",
        payload_checksum=payload_checksum,
        estimated_size=100,
        estimated_tokens=20,
        correlation_id="acceptance-a",
        approval_reference=approval_reference,
        constraints=constraints,
    )
