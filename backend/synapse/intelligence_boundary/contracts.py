from __future__ import annotations

from typing import Any, Protocol

from synapse.intelligence_boundary.models import (
    EgressAuthorization,
    EgressManifest,
    EgressRequest,
    InformationAsset,
    ProcessingPurpose,
)


class BoundaryRecordStore(Protocol):
    def put(
        self,
        record_id: str,
        payload: dict[str, Any],
        *,
        expected_revision: int | None = None,
        create_only: bool = False,
    ) -> None: ...
    def get(self, record_id: str) -> dict[str, Any]: ...
    def list(self, filters: dict[str, Any] | None = None) -> tuple[dict[str, Any], ...]: ...


class InformationAssetRegistrationPort(Protocol):
    def register_asset(self, asset: InformationAsset) -> InformationAsset: ...
    def ensure_asset(self, asset: InformationAsset) -> InformationAsset: ...
    def get_asset(self, asset_id: str) -> InformationAsset: ...


class EgressDecisionPort(Protocol):
    def preview_egress(self, request: EgressRequest) -> EgressAuthorization: ...


class EgressGatePort(Protocol):
    def authorize_egress(self, request: EgressRequest) -> EgressAuthorization: ...
    def validate_manifest(
        self,
        manifest_id: str,
        *,
        payload_checksum: str,
        provider_id: str | None,
        destination: str,
        purpose: str,
    ) -> EgressManifest: ...


class ProviderTrustReadPort(Protocol):
    def provider_boundary(self, provider_id: str) -> str | None: ...


class IntelligenceEgressPort(
    EgressGatePort,
    InformationAssetRegistrationPort,
    ProviderTrustReadPort,
    Protocol,
):
    def register_derived_asset(
        self,
        *,
        asset_id: str,
        input_asset_ids: tuple[str, ...],
        source_reference: str,
        content_type: str,
        output_checksum: str,
        purpose: ProcessingPurpose,
        provider_id: str | None = None,
        model_id: str | None = None,
        manifest_id: str | None = None,
    ) -> InformationAsset: ...
    def complete_egress(
        self,
        manifest_id: str,
        *,
        result_reference: str,
        status: str = "completed",
        error_code: str | None = None,
    ) -> Any: ...
