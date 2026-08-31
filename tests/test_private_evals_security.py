from __future__ import annotations

from dataclasses import replace
from typing import Any, cast

import pytest

from synapse.intelligence_boundary.models import (
    DataClassification,
    EgressAuthorization,
    EgressDecision,
    EgressDecisionStatus,
    EgressManifest,
    EgressRequest,
    InformationAsset,
    InformationOwnership,
    MinimizationPlan,
    OperatingProfile,
    ProcessingBoundary,
    ProcessingPurpose,
    TrainingUsePolicy,
)
from synapse.private_evals.canonical import fingerprint
from synapse.private_evals.catalog import DatasetBinding
from synapse.private_evals.security import (
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
from synapse.private_evals.security_errors import (
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
from synapse.private_evals.security_service import EvalSecurityService
from synapse.private_evals.states import DatasetCustodyKind
from synapse.private_evals.values import (
    ContentChecksum,
    DatasetBindingId,
    EvalRunId,
    Fingerprint,
    Revision,
    UtcTimestamp,
)

SHA_A = ContentChecksum("a" * 64)
SHA_B = ContentChecksum("b" * 64)
SHA_C = ContentChecksum("c" * 64)
FP_A = Fingerprint("1" * 64)
RUN = EvalRunId("run-security-1")


def canonical_asset(
    asset_id: str = "asset-a",
    *,
    checksum: str = "a" * 64,
    revision: int = 1,
    owner: InformationOwnership = InformationOwnership.PROJECT,
    classification: DataClassification = DataClassification.CONFIDENTIAL,
    provenance: dict[str, Any] | None = None,
    parents: tuple[str, ...] = (),
) -> InformationAsset:
    return InformationAsset(
        asset_id=asset_id,
        owner=owner,
        source_domain="approved-local-custody",
        source_reference="opaque-asset-reference",
        content_type="application/json",
        classification=classification,
        categories=("eval",),
        retention_policy="retention-90d",
        training_use_policy=TrainingUsePolicy.EXTERNAL_TRAINING_PROHIBITED,
        provenance=provenance if provenance is not None else {"source": "registry"},
        parent_asset_ids=parents,
        revision=revision,
        checksum=checksum,
    )


def asset_projection(
    item: InformationAsset | None = None,
    *,
    source: EvalAssetSourceKind = EvalAssetSourceKind.GOVERNED_LOCAL_CUSTODY,
    governed: bool = True,
) -> AssetSecurityProjection:
    item = item or canonical_asset()
    return AssetSecurityProjection(
        reference=AssetVersionReference(
            item.asset_id, Revision(item.revision), ContentChecksum(item.checksum)
        ),
        owner=item.owner,
        classification=item.classification,
        source_kind=source,
        governed_custody=governed,
        provenance_fingerprint=FP_A,
    )


def provider_projection(**changes: object) -> ProviderTrustProjection:
    base = ProviderTrustProjection(
        provider_id="provider-1",
        trust_profile_reference="trust-profile-1",
        revision=Revision(3),
        checksum=SHA_B,
        boundary=ProcessingBoundary.PRIVATE_TENANT,
        approved=True,
    )
    return replace(base, **changes)


def snapshot_fingerprint_values(
    *,
    snapshot_reference: str,
    revision: Revision,
    checksum: ContentChecksum,
    operating_profile: OperatingProfile,
    policy_references: tuple[str, ...],
    policy_checksums: tuple[ContentChecksum, ...],
    assets: tuple[AssetSecurityProjection, ...],
    providers: tuple[ProviderTrustProjection, ...],
) -> Fingerprint:
    """Independent contract-fixture implementation, not a service helper."""
    return fingerprint(
        {
            "snapshot_reference": snapshot_reference,
            "revision": revision,
            "checksum": checksum,
            "operating_profile": operating_profile,
            "policies": tuple(sorted(zip(policy_references, policy_checksums, strict=True))),
            "assets": tuple(
                sorted(
                    (
                        item.reference,
                        item.owner,
                        item.classification,
                        item.source_kind,
                        item.governed_custody,
                        item.provenance_fingerprint,
                    )
                    for item in assets
                )
            ),
            "providers": tuple(
                sorted(
                    (
                        item.provider_id,
                        item.trust_profile_reference,
                        item.revision,
                        item.checksum,
                        item.boundary,
                        item.approved,
                    )
                    for item in providers
                )
            ),
        }
    )


def security_snapshot(
    *assets: AssetSecurityProjection,
    providers: tuple[ProviderTrustProjection, ...] | None = None,
    **changes: object,
) -> EvalSecuritySnapshot:
    values: dict[str, object] = {
        "snapshot_reference": "security-snapshot-1",
        "revision": Revision(2),
        "checksum": SHA_C,
        "operating_profile": OperatingProfile.HYBRID_GUARDED,
        "policy_references": ("policy-1",),
        "policy_checksums": (SHA_A,),
        "assets": assets or (asset_projection(),),
        "providers": providers if providers is not None else (provider_projection(),),
    }
    values.update(changes)
    semantic = cast(dict[str, Any], values)
    values["fingerprint"] = snapshot_fingerprint_values(**semantic)
    return EvalSecuritySnapshot(**cast(dict[str, Any], values))


def dataset(item: InformationAsset | None = None) -> DatasetBinding:
    item = item or canonical_asset()
    return DatasetBinding(
        binding_id=DatasetBindingId("binding-1"),
        asset_id=item.asset_id,
        content_reference="asset://opaque/reference",
        dataset_revision=Revision(item.revision),
        content_checksum=ContentChecksum(item.checksum),
        item_manifest_checksum=SHA_B,
        item_count=4,
        classification=item.classification,
        owner=item.owner,
        classification_snapshot_reference="classification-snapshot-1",
        ownership_snapshot_reference="ownership-snapshot-1",
        retention_policy_reference="retention-90d",
        selection_fingerprint=FP_A,
        custody_kind=DatasetCustodyKind.GOVERNED_LOCAL,
        created_at=UtcTimestamp("2026-07-18T12:00:00Z"),
        checksum=SHA_C,
    )


def preparation(*references: AssetVersionReference, **changes: object) -> EvalEgressPreparation:
    base = EvalEgressPreparation(
        run_id=RUN,
        run_manifest_reference="run-manifest-1",
        requester="eval-runtime",
        project_id="project-1",
        assets=references or (asset_projection().reference,),
        provider_id="provider-1",
        destination="provider-endpoint-1",
        boundary=ProcessingBoundary.PRIVATE_TENANT,
        purpose=ProcessingPurpose.EVALUATION,
        operating_profile=OperatingProfile.HYBRID_GUARDED,
        payload_checksum=SHA_A,
    )
    return replace(base, **changes)


def canonical_manifest(**changes: object) -> EgressManifest:
    base = EgressManifest(
        manifest_id="manifest-1",
        decision_id="decision-1",
        requester="eval-runtime",
        provider_id="provider-1",
        destination="provider-endpoint-1",
        boundary=ProcessingBoundary.PRIVATE_TENANT,
        purpose=ProcessingPurpose.EVALUATION,
        asset_references=("asset-a",),
        source_classifications=(DataClassification.CONFIDENTIAL,),
        resulting_classifications=(DataClassification.CONFIDENTIAL,),
        categories=("eval",),
        transformations=(),
        payload_checksum="a" * 64,
        estimated_size=0,
        estimated_tokens=0,
        created_at="2026-07-18T12:00:00Z",
        expires_at="2026-07-18T13:00:00Z",
        revision=1,
        checksum="c" * 64,
        project_id="project-1",
    )
    return replace(base, **changes)


def authorization(
    status: EgressDecisionStatus = EgressDecisionStatus.ALLOWED,
    *,
    allowed: bool | None = None,
    manifest: EgressManifest | None | object = ...,
    **changes: object,
) -> EgressAuthorization:
    is_allowed = status in {
        EgressDecisionStatus.ALLOWED,
        EgressDecisionStatus.ALLOWED_MINIMIZED,
        EgressDecisionStatus.ALLOWED_REDACTED,
        EgressDecisionStatus.ALLOWED_SUMMARY_ONLY,
    }
    decision = EgressDecision(
        decision_id="decision-1",
        status=status,
        allowed_assets=("asset-a",) if is_allowed else (),
        blocked_assets=() if is_allowed else ("asset-a",),
        required_transformations=(),
        redaction_plan=None,
        minimization_plan=MinimizationPlan((), (), (), (), {}, 0, 0, "low"),
        approval_required=status is EgressDecisionStatus.APPROVAL_REQUIRED,
        approval_scope={},
        reasons=("canonical-policy",),
        warnings=(),
        expires_at="2026-07-18T13:00:00Z",
        revision=1,
        checksum="b" * 64,
        trace_id="trace-1",
    )
    decision = replace(decision, **changes)
    resolved_manifest = (
        canonical_manifest() if manifest is ... and is_allowed else None if manifest is ... else manifest
    )
    return EgressAuthorization(
        allowed=is_allowed if allowed is None else allowed,
        decision=decision,
        manifest=cast(EgressManifest | None, resolved_manifest),
        reason="canonical-result",
    )


class IntelligenceFake:
    def __init__(
        self,
        item: InformationAsset | None = None,
        auth: EgressAuthorization | None = None,
    ) -> None:
        self.items = {item.asset_id: item} if item is not None else {"asset-a": canonical_asset()}
        self.auth = auth or authorization()
        self.validated_manifest = self.auth.manifest
        self.authorize_calls: list[EgressRequest] = []
        self.manifest_calls: list[tuple[str, str]] = []
        self.derived_response: InformationAsset | None = None

    def register_asset(self, item: InformationAsset) -> InformationAsset:
        self.items[item.asset_id] = item
        return item

    def get_asset(self, asset_id: str) -> InformationAsset:
        return self.items[asset_id]

    def provider_boundary(self, provider_id: str) -> str | None:
        return ProcessingBoundary.PRIVATE_TENANT.value

    def authorize_egress(self, request: EgressRequest) -> EgressAuthorization:
        self.authorize_calls.append(request)
        return self.auth

    def validate_manifest(
        self,
        manifest_id: str,
        *,
        payload_checksum: str,
        provider_id: str | None,
        destination: str,
        purpose: str,
    ) -> EgressManifest:
        self.manifest_calls.append((manifest_id, payload_checksum))
        assert self.validated_manifest is not None
        return self.validated_manifest

    def register_derived_asset(self, **values: Any) -> InformationAsset:
        if self.derived_response is not None:
            return self.derived_response
        return canonical_asset(
            values["asset_id"],
            checksum=values["output_checksum"],
            owner=InformationOwnership.PROVIDER_DERIVED,
            parents=values["input_asset_ids"],
            provenance={"manifest": values["manifest_id"]},
        )

    def complete_egress(
        self,
        manifest_id: str,
        *,
        result_reference: str,
        status: str = "completed",
        error_code: str | None = None,
    ) -> Any:
        raise AssertionError("completion is outside Slice 7")


class SnapshotFake:
    def __init__(self, value: EvalSecuritySnapshot) -> None:
        self.value = value

    def snapshot(
        self,
        project_id: str,
        asset_ids: tuple[str, ...],
        provider_ids: tuple[str, ...],
    ) -> EvalSecuritySnapshot:
        return self.value


def service(
    item: InformationAsset | None = None,
    *,
    snap: EvalSecuritySnapshot | None = None,
    auth: EgressAuthorization | None = None,
) -> tuple[EvalSecurityService, IntelligenceFake, EvalSecuritySnapshot]:
    item = item or canonical_asset()
    snap = snap or security_snapshot(asset_projection(item))
    intelligence = IntelligenceFake(item, auth)
    return EvalSecurityService(intelligence, SnapshotFake(snap)), intelligence, snap


def test_obtains_exact_security_projection_from_consumer_port() -> None:
    subject, _, snap = service()
    assert subject.obtain_security_snapshot(
        project_id="project-1", asset_ids=("asset-a",), provider_ids=("provider-1",)
    ) is snap
    with pytest.raises(SecurityProjectionMismatch):
        subject.obtain_security_snapshot(
            project_id="project-1", asset_ids=("other",), provider_ids=("provider-1",)
        )


def test_validates_dataset_against_canonical_information_asset() -> None:
    item = canonical_asset()
    subject, _, snap = service(item)
    assert subject.validate_dataset(dataset(item), snapshot=snap) == asset_projection(item).reference


@pytest.mark.parametrize(
    ("change", "error"),
    [
        ({"dataset_revision": Revision(2)}, AssetRevisionMismatch),
        ({"content_checksum": SHA_B}, AssetChecksumMismatch),
        ({"owner": InformationOwnership.USER}, AssetOwnerMismatch),
        ({"classification": DataClassification.PUBLIC}, AssetClassificationMismatch),
    ],
)
def test_dataset_mismatches_are_typed(change: dict[str, object], error: type[Exception]) -> None:
    subject, _, snap = service()
    with pytest.raises(error):
        subject.validate_dataset(replace(dataset(), **change), snapshot=snap)


def test_missing_asset_and_incomplete_provenance_are_typed() -> None:
    subject, _, snap = service()
    with pytest.raises(AssetNotFound):
        subject.validate_dataset(replace(dataset(), asset_id="missing"), snapshot=snap)
    item = canonical_asset(provenance={})
    subject, _, snap = service(item, snap=security_snapshot(asset_projection(item)))
    with pytest.raises(ProvenanceIncomplete):
        subject.validate_dataset(dataset(item), snapshot=snap)


@pytest.mark.parametrize(
    "source", [EvalAssetSourceKind.DESKTOP_UPLOAD, EvalAssetSourceKind.DESKTOP_FORM_SUBMISSION]
)
def test_desktop_projection_is_rejected_without_path_interpretation(
    source: EvalAssetSourceKind,
) -> None:
    item = canonical_asset()
    snap = security_snapshot(asset_projection(item, source=source))
    subject, _, _ = service(item, snap=snap)
    with pytest.raises(DesktopSourceProhibited) as caught:
        subject.validate_dataset(dataset(item), snapshot=snap)
    assert "C:\\private\\dataset.json" not in str(caught.value)


def test_ungoverned_projection_is_rejected() -> None:
    item = canonical_asset()
    snap = security_snapshot(asset_projection(item, governed=False))
    subject, _, _ = service(item, snap=snap)
    with pytest.raises(CustodyNotGoverned):
        subject.validate_dataset(dataset(item), snapshot=snap)


def test_register_input_delegates_to_frozen_contract_and_blocks_desktop() -> None:
    item = canonical_asset()
    subject, _, _ = service(item)
    assert subject.register_input_asset(
        item,
        source_kind=EvalAssetSourceKind.GOVERNED_LOCAL_CUSTODY,
        governed_custody=True,
    ) == asset_projection(item).reference
    with pytest.raises(DesktopSourceProhibited):
        subject.register_input_asset(
            item, source_kind=EvalAssetSourceKind.DESKTOP_UPLOAD, governed_custody=True
        )


def test_provider_trust_is_consumed_as_decision_not_recalculated() -> None:
    snap = security_snapshot(providers=(provider_projection(approved=False),))
    subject, intelligence, _ = service(snap=snap)
    decision = subject.authorize_egress(preparation(), snapshot=snap)
    assert decision.disposition is EvalSecurityDisposition.POLICY_DENIED
    assert decision.reason_codes == (SecurityReasonCode.PROVIDER_NOT_APPROVED,)
    assert intelligence.authorize_calls == []


def test_provider_projection_and_canonical_boundary_must_correspond() -> None:
    snap = security_snapshot(
        providers=(provider_projection(boundary=ProcessingBoundary.EXTERNAL_PROVIDER),)
    )
    subject, _, _ = service(snap=snap)
    with pytest.raises(ProviderProjectionMismatch):
        subject.authorize_egress(preparation(), snapshot=snap)
    subject, intelligence, snap = service()
    intelligence.provider_boundary = lambda provider_id: ProcessingBoundary.EXTERNAL_PROVIDER.value  # type: ignore[method-assign]
    with pytest.raises(ProviderProjectionMismatch):
        subject.authorize_egress(preparation(), snapshot=snap)


@pytest.mark.parametrize(
    "status",
    [
        EgressDecisionStatus.ALLOWED,
        EgressDecisionStatus.ALLOWED_MINIMIZED,
        EgressDecisionStatus.ALLOWED_REDACTED,
        EgressDecisionStatus.ALLOWED_SUMMARY_ONLY,
    ],
)
def test_canonical_allowed_states_map_to_ready(status: EgressDecisionStatus) -> None:
    auth = authorization(status)
    subject, intelligence, snap = service(auth=auth)
    result = subject.authorize_egress(preparation(), snapshot=snap)
    assert result.canonical_status is status
    assert result.disposition is EvalSecurityDisposition.READY
    assert result.manifest_reference == "manifest-1"
    assert intelligence.manifest_calls == [("manifest-1", "a" * 64)]


@pytest.mark.parametrize(
    "status", [EgressDecisionStatus.DENIED, EgressDecisionStatus.LOCAL_ONLY]
)
def test_canonical_denial_is_distinct_from_approval_block(status: EgressDecisionStatus) -> None:
    subject, _, snap = service(auth=authorization(status))
    denied = subject.authorize_egress(preparation(), snapshot=snap)
    assert denied.disposition is EvalSecurityDisposition.POLICY_DENIED
    subject, _, snap = service(auth=authorization(EgressDecisionStatus.APPROVAL_REQUIRED))
    blocked = subject.authorize_egress(preparation(), snapshot=snap)
    assert blocked.disposition is EvalSecurityDisposition.BLOCKED
    assert blocked.reason_codes == (SecurityReasonCode.APPROVAL_REQUIRED,)


def test_malformed_canonical_authorizations_fail_closed() -> None:
    malformed = (
        authorization(EgressDecisionStatus.ALLOWED, allowed=False),
        authorization(EgressDecisionStatus.ALLOWED, manifest=None),
        authorization(EgressDecisionStatus.ALLOWED, allowed_assets=("other",)),
        authorization(EgressDecisionStatus.ALLOWED, approval_required=True),
    )
    for auth in malformed:
        subject, _, snap = service(auth=auth)
        with pytest.raises(CanonicalEgressResponseInvalid):
            subject.authorize_egress(preparation(), snapshot=snap)


@pytest.mark.parametrize(
    "change",
    [
        {"provider_id": "provider-2"},
        {"boundary": ProcessingBoundary.EXTERNAL_PROVIDER},
        {"purpose": ProcessingPurpose.EXPORT},
        {"asset_references": ("other",)},
        {"checksum": "not-a-checksum"},
    ],
)
def test_malformed_validated_manifest_fails_closed(change: dict[str, object]) -> None:
    subject, intelligence, snap = service()
    intelligence.validated_manifest = replace(canonical_manifest(), **change)
    with pytest.raises(CanonicalEgressResponseInvalid):
        subject.authorize_egress(preparation(), snapshot=snap)


def test_run_security_snapshot_remains_a_minimal_reference() -> None:
    subject, _, snap = service()
    decision = subject.authorize_egress(preparation(), snapshot=snap)
    reference = subject.create_security_snapshot_ref(snapshot=snap, decision=decision)
    assert reference.policy_references == ("policy-1", "decision-1")
    assert reference.approval_manifest_references == ("manifest-1",)
    assert not hasattr(reference, "asset_references")
    assert not hasattr(reference, "provider_trust_reference")
    assert not hasattr(reference, "snapshot_fingerprint")


def derived_request() -> DerivedAssetRegistration:
    return DerivedAssetRegistration(
        run_id=RUN,
        asset_id="derived-1",
        input_assets=(asset_projection().reference,),
        source_reference="derived-output-1",
        content_type="application/json",
        output_checksum=SHA_C,
        purpose=ProcessingPurpose.EVALUATION,
        provider_id="provider-1",
        model_id="model-1",
        manifest_reference="manifest-1",
    )


def test_derived_asset_policy_is_owned_by_intelligence() -> None:
    subject, intelligence, _ = service()
    result = subject.register_derived_asset(derived_request())
    assert result.asset_id == "derived-1"
    canonical = intelligence.items["asset-a"]
    assert canonical.training_use_policy is TrainingUsePolicy.EXTERNAL_TRAINING_PROHIBITED
    assert not hasattr(derived_request(), "classification")
    assert not hasattr(derived_request(), "training_use_policy")
    assert not hasattr(derived_request(), "owner")


@pytest.mark.parametrize(
    "response",
    [
        canonical_asset("other", checksum="c" * 64, parents=("asset-a",)),
        canonical_asset("derived-1", checksum="b" * 64, parents=("asset-a",)),
        canonical_asset("derived-1", checksum="c" * 64, parents=("other",)),
        canonical_asset("derived-1", checksum="c" * 64, parents=("asset-a",), provenance={}),
    ],
)
def test_malformed_derived_asset_responses_fail_closed(response: InformationAsset) -> None:
    subject, intelligence, _ = service()
    intelligence.derived_response = response
    error = ProvenanceIncomplete if not response.provenance else DerivedAssetInvalid
    with pytest.raises(error):
        subject.register_derived_asset(derived_request())


def test_security_snapshot_fingerprint_binds_each_semantic_projection_field() -> None:
    original = security_snapshot()
    variants = (
        security_snapshot(snapshot_reference="security-snapshot-2"),
        security_snapshot(revision=Revision(3)),
        security_snapshot(checksum=SHA_B),
        security_snapshot(operating_profile=OperatingProfile.LOCAL_SOVEREIGN),
        security_snapshot(policy_references=("policy-2",)),
        security_snapshot(policy_checksums=(SHA_B,)),
        security_snapshot(
            asset_projection(canonical_asset(classification=DataClassification.RESTRICTED))
        ),
        security_snapshot(providers=(provider_projection(checksum=SHA_C),)),
    )
    assert all(item.fingerprint != original.fingerprint for item in variants)


def test_decision_fingerprint_binds_manifest_snapshot_transformations_and_approval() -> None:
    subject, _, snap = service()
    original = subject.authorize_egress(preparation(), snapshot=snap)
    variants = (
        replace(original, manifest_reference="manifest-2", fingerprint=None),
        replace(original, security_snapshot_checksum=SHA_B, fingerprint=None),
        replace(original, security_snapshot_fingerprint=FP_A, fingerprint=None),
        replace(original, transformation_references=("redaction-1",), fingerprint=None),
        replace(original, approval_reference="approval-1", fingerprint=None),
    )
    assert all(item.fingerprint != original.fingerprint for item in variants)


def test_projection_and_decision_reprs_exclude_payload_uri_and_provider_messages() -> None:
    subject, _, snap = service()
    decision = subject.authorize_egress(preparation(), snapshot=snap)
    rendered = repr((snap, decision))
    for forbidden in ("asset://", "C:\\private", "provider response", "sk-private-token"):
        assert forbidden not in rendered
    assert not hasattr(decision, "payload")
    assert not hasattr(decision, "manifest")


def test_secret_shaped_metadata_is_rejected() -> None:
    with pytest.raises(ValueError):
        replace(preparation(), approval_reference="sk-private-token")


def test_reason_codes_are_closed_and_do_not_duplicate_egress_state_machine() -> None:
    assert set(SecurityReasonCode) == {
        SecurityReasonCode.AUTHORIZED,
        SecurityReasonCode.APPROVAL_REQUIRED,
        SecurityReasonCode.POLICY_DENIED,
        SecurityReasonCode.PROVIDER_NOT_APPROVED,
    }
    assert set(EvalSecurityDisposition) == {
        EvalSecurityDisposition.READY,
        EvalSecurityDisposition.BLOCKED,
        EvalSecurityDisposition.INVALID,
        EvalSecurityDisposition.POLICY_DENIED,
    }


def test_wrong_snapshot_fingerprint_is_rejected_independently() -> None:
    with pytest.raises(ValueError):
        replace(security_snapshot(), fingerprint=Fingerprint("9" * 64))


def test_wrong_decision_fingerprint_is_rejected() -> None:
    decision = EvalSecurityDecision(
        canonical_status=EgressDecisionStatus.DENIED,
        disposition=EvalSecurityDisposition.POLICY_DENIED,
        reason_codes=(SecurityReasonCode.POLICY_DENIED,),
        decision_reference="decision-1",
        decision_checksum=SHA_A,
        security_snapshot_reference="security-snapshot-1",
        security_snapshot_checksum=SHA_B,
        security_snapshot_fingerprint=FP_A,
        manifest_reference=None,
        manifest_checksum=None,
        transformation_references=(),
        approval_reference=None,
    )
    with pytest.raises(ValueError):
        replace(decision, fingerprint=Fingerprint("9" * 64))
