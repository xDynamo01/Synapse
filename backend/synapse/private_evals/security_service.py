from __future__ import annotations

from dataclasses import dataclass

from synapse.intelligence_boundary.contracts import IntelligenceEgressPort
from synapse.intelligence_boundary.models import (
    EgressAuthorization,
    EgressDecisionStatus,
    EgressManifest,
    EgressRequest,
    InformationAsset,
)

from .catalog import DatasetBinding
from .runs import SecuritySnapshotRef
from .security import (
    AssetSecurityProjection,
    AssetVersionReference,
    DerivedAssetRegistration,
    EvalAssetSourceKind,
    EvalEgressPreparation,
    EvalSecurityDecision,
    EvalSecurityDisposition,
    EvalSecuritySnapshot,
    ProviderTrustProjection,
    SecurityReasonCode,
)
from .security_contracts import SecuritySnapshotReadPort
from .security_errors import (
    AssetChecksumMismatch,
    AssetClassificationMismatch,
    AssetNotFound,
    AssetOwnerMismatch,
    AssetRevisionMismatch,
    CanonicalEgressResponseInvalid,
    CustodyNotGoverned,
    DerivedAssetInvalid,
    DesktopSourceProhibited,
    ProvenanceIncomplete,
    ProviderProjectionMismatch,
    SecurityProjectionMismatch,
)
from .states import DatasetCustodyKind
from .values import ContentChecksum, Revision

_DESKTOP_SOURCES = {
    EvalAssetSourceKind.DESKTOP_UPLOAD,
    EvalAssetSourceKind.DESKTOP_FORM_SUBMISSION,
}
_ALLOWED_STATUSES = {
    EgressDecisionStatus.ALLOWED,
    EgressDecisionStatus.ALLOWED_MINIMIZED,
    EgressDecisionStatus.ALLOWED_REDACTED,
    EgressDecisionStatus.ALLOWED_SUMMARY_ONLY,
}


@dataclass(frozen=True)
class EvalSecurityService:
    """Coordinates canonical Intelligence decisions into eval run readiness."""

    intelligence: IntelligenceEgressPort
    security_snapshots: SecuritySnapshotReadPort

    def obtain_security_snapshot(
        self,
        *,
        project_id: str,
        asset_ids: tuple[str, ...],
        provider_ids: tuple[str, ...],
    ) -> EvalSecuritySnapshot:
        snapshot = self.security_snapshots.snapshot(project_id, asset_ids, provider_ids)
        if tuple(sorted(item.reference.asset_id for item in snapshot.assets)) != tuple(
            sorted(asset_ids)
        ):
            raise SecurityProjectionMismatch("security snapshot assets are inconsistent")
        if tuple(sorted(item.provider_id for item in snapshot.providers)) != tuple(
            sorted(provider_ids)
        ):
            raise SecurityProjectionMismatch("security snapshot providers are inconsistent")
        return snapshot

    def validate_dataset(
        self,
        binding: DatasetBinding,
        *,
        snapshot: EvalSecuritySnapshot,
    ) -> AssetVersionReference:
        if binding.custody_kind is not DatasetCustodyKind.GOVERNED_LOCAL:
            raise CustodyNotGoverned("dataset custody is not governed")
        canonical = self._get_asset(binding.asset_id)
        projection = self._asset_projection(snapshot, binding.asset_id)
        self._validate_asset_projection(canonical, projection)
        if canonical.revision != binding.dataset_revision.value:
            raise AssetRevisionMismatch("asset revision does not match dataset binding")
        if canonical.checksum != binding.content_checksum.value:
            raise AssetChecksumMismatch("asset checksum does not match dataset binding")
        if canonical.owner is not binding.owner:
            raise AssetOwnerMismatch("asset owner does not match dataset binding")
        if canonical.classification is not binding.classification:
            raise AssetClassificationMismatch(
                "asset classification does not match dataset binding"
            )
        return projection.reference

    def register_input_asset(
        self,
        asset: InformationAsset,
        *,
        source_kind: EvalAssetSourceKind,
        governed_custody: bool,
    ) -> AssetVersionReference:
        self._reject_source(source_kind, governed_custody)
        registered = self.intelligence.register_asset(asset)
        if registered.asset_id != asset.asset_id:
            raise AssetNotFound("registered asset identity is inconsistent")
        if registered.checksum != asset.checksum:
            raise AssetChecksumMismatch("registered asset checksum is inconsistent")
        if not registered.provenance:
            raise ProvenanceIncomplete("registered asset provenance is incomplete")
        return self._canonical_reference(registered)

    def authorize_egress(
        self,
        preparation: EvalEgressPreparation,
        *,
        snapshot: EvalSecuritySnapshot,
    ) -> EvalSecurityDecision:
        provider = self._provider_projection(snapshot, preparation.provider_id)
        if provider.boundary is not preparation.boundary:
            raise ProviderProjectionMismatch("provider boundary projection is inconsistent")
        boundary = self.intelligence.provider_boundary(preparation.provider_id)
        if boundary != preparation.boundary.value:
            raise ProviderProjectionMismatch("canonical provider boundary is inconsistent")
        for reference in preparation.assets:
            canonical = self._get_asset(reference.asset_id)
            projection = self._asset_projection(snapshot, reference.asset_id)
            self._validate_asset_projection(canonical, projection)
            if projection.reference != reference:
                raise SecurityProjectionMismatch("egress asset projection is inconsistent")
        if not provider.approved:
            return self._decision(
                snapshot=snapshot,
                status=EgressDecisionStatus.DENIED,
                disposition=EvalSecurityDisposition.POLICY_DENIED,
                reasons=(SecurityReasonCode.PROVIDER_NOT_APPROVED,),
                decision_reference=provider.trust_profile_reference,
                decision_checksum=provider.checksum,
            )

        authorization = self.intelligence.authorize_egress(
            EgressRequest(
                asset_ids=tuple(item.asset_id for item in preparation.assets),
                requester=preparation.requester,
                destination=preparation.destination,
                boundary=preparation.boundary,
                purpose=preparation.purpose,
                provider_id=preparation.provider_id,
                project_id=preparation.project_id,
                requested_transformations=preparation.requested_transformations,
                payload_checksum=preparation.payload_checksum.value,
                correlation_id=str(preparation.run_id),
                approval_reference=preparation.approval_reference,
                constraints=(
                    f"operating-profile:{preparation.operating_profile.value}",
                    f"run-manifest:{preparation.run_manifest_reference}",
                ),
            )
        )
        self._validate_authorization(preparation, authorization)
        decision = authorization.decision
        decision_checksum = self._checksum(decision.checksum, "egress decision")
        if decision.status in {EgressDecisionStatus.DENIED, EgressDecisionStatus.LOCAL_ONLY}:
            return self._decision(
                snapshot=snapshot,
                status=decision.status,
                disposition=EvalSecurityDisposition.POLICY_DENIED,
                reasons=(SecurityReasonCode.POLICY_DENIED,),
                decision_reference=decision.decision_id,
                decision_checksum=decision_checksum,
            )
        if decision.status is EgressDecisionStatus.APPROVAL_REQUIRED:
            return self._decision(
                snapshot=snapshot,
                status=decision.status,
                disposition=EvalSecurityDisposition.BLOCKED,
                reasons=(SecurityReasonCode.APPROVAL_REQUIRED,),
                decision_reference=decision.decision_id,
                decision_checksum=decision_checksum,
                approval_reference=preparation.approval_reference,
            )
        if decision.status not in _ALLOWED_STATUSES or not authorization.allowed:
            raise CanonicalEgressResponseInvalid("canonical egress response is inconsistent")
        if authorization.manifest is None:
            raise CanonicalEgressResponseInvalid("canonical egress manifest is missing")
        manifest = self._validate_canonical_manifest(preparation, authorization.manifest)
        return self._decision(
            snapshot=snapshot,
            status=decision.status,
            disposition=EvalSecurityDisposition.READY,
            reasons=(SecurityReasonCode.AUTHORIZED,),
            decision_reference=decision.decision_id,
            decision_checksum=decision_checksum,
            manifest=manifest,
            approval_reference=manifest.approval_reference,
        )

    def create_security_snapshot_ref(
        self,
        *,
        snapshot: EvalSecuritySnapshot,
        decision: EvalSecurityDecision,
    ) -> SecuritySnapshotRef:
        references = (*snapshot.policy_references, decision.decision_reference)
        checksums = (*snapshot.policy_checksums, decision.decision_checksum)
        manifest_references = tuple(
            item
            for item in (decision.manifest_reference, decision.approval_reference)
            if item is not None
        )
        return SecuritySnapshotRef(
            operating_profile=snapshot.operating_profile,
            policy_references=references,
            policy_checksums=checksums,
            approval_manifest_references=manifest_references,
        )

    def register_derived_asset(
        self,
        request: DerivedAssetRegistration,
    ) -> AssetVersionReference:
        registered = self.intelligence.register_derived_asset(
            asset_id=request.asset_id,
            input_asset_ids=tuple(item.asset_id for item in request.input_assets),
            source_reference=request.source_reference,
            content_type=request.content_type,
            output_checksum=request.output_checksum.value,
            purpose=request.purpose,
            provider_id=request.provider_id,
            model_id=request.model_id,
            manifest_id=request.manifest_reference,
        )
        if (
            registered.asset_id != request.asset_id
            or registered.checksum != request.output_checksum.value
            or tuple(sorted(registered.parent_asset_ids))
            != tuple(sorted(item.asset_id for item in request.input_assets))
        ):
            raise DerivedAssetInvalid("canonical derived asset response is inconsistent")
        if not registered.provenance:
            raise ProvenanceIncomplete("canonical derived asset provenance is incomplete")
        return self._canonical_reference(registered)

    def _validate_canonical_manifest(
        self,
        preparation: EvalEgressPreparation,
        manifest: EgressManifest,
    ) -> EgressManifest:
        validated = self.intelligence.validate_manifest(
            manifest.manifest_id,
            payload_checksum=preparation.payload_checksum.value,
            provider_id=preparation.provider_id,
            destination=preparation.destination,
            purpose=preparation.purpose.value,
        )
        if (
            validated.manifest_id != manifest.manifest_id
            or validated.decision_id != manifest.decision_id
            or validated.checksum != manifest.checksum
            or validated.provider_id != preparation.provider_id
            or validated.boundary is not preparation.boundary
            or validated.purpose is not preparation.purpose
            or tuple(sorted(validated.asset_references))
            != tuple(sorted(item.asset_id for item in preparation.assets))
        ):
            raise CanonicalEgressResponseInvalid("validated egress manifest is inconsistent")
        self._checksum(validated.checksum, "egress manifest")
        return validated

    @staticmethod
    def _validate_authorization(
        preparation: EvalEgressPreparation,
        authorization: EgressAuthorization,
    ) -> None:
        decision = authorization.decision
        requested = tuple(sorted(item.asset_id for item in preparation.assets))
        decided = tuple(sorted((*decision.allowed_assets, *decision.blocked_assets)))
        if decided != requested or len(decided) != len(set(decided)):
            raise CanonicalEgressResponseInvalid("canonical egress assets are inconsistent")
        if decision.approval_required != (
            decision.status is EgressDecisionStatus.APPROVAL_REQUIRED
        ):
            raise CanonicalEgressResponseInvalid("canonical approval state is inconsistent")

    @staticmethod
    def _decision(
        *,
        snapshot: EvalSecuritySnapshot,
        status: EgressDecisionStatus,
        disposition: EvalSecurityDisposition,
        reasons: tuple[SecurityReasonCode, ...],
        decision_reference: str,
        decision_checksum: ContentChecksum,
        manifest: EgressManifest | None = None,
        approval_reference: str | None = None,
    ) -> EvalSecurityDecision:
        return EvalSecurityDecision(
            canonical_status=status,
            disposition=disposition,
            reason_codes=reasons,
            decision_reference=decision_reference,
            decision_checksum=decision_checksum,
            security_snapshot_reference=snapshot.snapshot_reference,
            security_snapshot_checksum=snapshot.checksum,
            security_snapshot_fingerprint=snapshot.fingerprint,
            manifest_reference=manifest.manifest_id if manifest is not None else None,
            manifest_checksum=(
                ContentChecksum(manifest.checksum) if manifest is not None else None
            ),
            transformation_references=(manifest.transformations if manifest is not None else ()),
            approval_reference=approval_reference,
        )

    def _get_asset(self, asset_id: str) -> InformationAsset:
        try:
            asset = self.intelligence.get_asset(asset_id)
        except LookupError as exc:
            raise AssetNotFound("canonical information asset was not found") from exc
        if asset is None:  # defensive against an invalid port implementation
            raise AssetNotFound("canonical information asset was not found")
        return asset

    @staticmethod
    def _asset_projection(
        snapshot: EvalSecuritySnapshot,
        asset_id: str,
    ) -> AssetSecurityProjection:
        match = next(
            (item for item in snapshot.assets if item.reference.asset_id == asset_id),
            None,
        )
        if match is None:
            raise SecurityProjectionMismatch("asset is absent from security snapshot")
        return match

    @staticmethod
    def _provider_projection(
        snapshot: EvalSecuritySnapshot,
        provider_id: str,
    ) -> ProviderTrustProjection:
        match = next((item for item in snapshot.providers if item.provider_id == provider_id), None)
        if match is None:
            raise ProviderProjectionMismatch("provider is absent from security snapshot")
        return match

    @classmethod
    def _validate_asset_projection(
        cls,
        canonical: InformationAsset,
        projection: AssetSecurityProjection,
    ) -> None:
        cls._reject_source(projection.source_kind, projection.governed_custody)
        if (
            projection.reference != cls._canonical_reference(canonical)
            or projection.owner is not canonical.owner
            or projection.classification is not canonical.classification
        ):
            raise SecurityProjectionMismatch("canonical asset projection is inconsistent")
        if not canonical.provenance:
            raise ProvenanceIncomplete("canonical asset provenance is incomplete")

    @staticmethod
    def _reject_source(source_kind: EvalAssetSourceKind, governed_custody: bool) -> None:
        if source_kind in _DESKTOP_SOURCES:
            raise DesktopSourceProhibited("desktop-mediated asset sources are prohibited")
        if not governed_custody or source_kind is EvalAssetSourceKind.UNGOVERNED:
            raise CustodyNotGoverned("asset custody is not governed")

    @staticmethod
    def _canonical_reference(asset: InformationAsset) -> AssetVersionReference:
        try:
            return AssetVersionReference(
                asset_id=asset.asset_id,
                revision=Revision(asset.revision),
                content_checksum=ContentChecksum(asset.checksum),
            )
        except ValueError as exc:
            raise SecurityProjectionMismatch("canonical asset identity is invalid") from exc

    @staticmethod
    def _checksum(value: str, label: str) -> ContentChecksum:
        try:
            return ContentChecksum(value)
        except ValueError as exc:
            raise CanonicalEgressResponseInvalid(f"canonical {label} checksum is invalid") from exc
