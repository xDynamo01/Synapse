from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from synapse.intelligence_boundary.contracts import BoundaryRecordStore
from synapse.intelligence_boundary.errors import (
    BoundaryConflict,
    BoundaryNotFound,
    BoundaryValidationError,
    EgressApprovalRequired,
    EgressDenied,
    StaleEgressManifest,
)
from synapse.intelligence_boundary.models import (
    CLASSIFICATION_ORDER,
    LOCAL_BOUNDARIES,
    DataClassification,
    DerivedArtifactProvenance,
    EgressApprovalBinding,
    EgressAuthorization,
    EgressDecision,
    EgressDecisionStatus,
    EgressLedgerRecord,
    EgressManifest,
    EgressRequest,
    InformationAsset,
    InformationOwnership,
    MinimizationPlan,
    OperatingProfile,
    ProcessingBoundary,
    ProcessingPurpose,
    ProviderTrustProfile,
    RedactionPlan,
    TrainingUsePolicy,
    TrustProfileStatus,
)

CATEGORY_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")
SENSITIVE_KEYS = re.compile(r"secret|password|token|api[_-]?key|credential", re.IGNORECASE)


def _now() -> datetime:
    return datetime.now(UTC)


def _iso(value: datetime | None = None) -> str:
    return (value or _now()).isoformat()


def _checksum(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def _safe_metadata(value: dict[str, Any]) -> dict[str, Any]:
    return {
        str(key): item
        for key, item in value.items()
        if not SENSITIVE_KEYS.search(str(key)) and not isinstance(item, (bytes, bytearray))
    }


class IntelligenceBoundaryRuntime:
    """Canonical decision and audit runtime. It never performs transport I/O."""

    def __init__(
        self,
        *,
        stores: Mapping[str, BoundaryRecordStore],
        events: Any,
        default_profile: OperatingProfile = OperatingProfile.HYBRID_GUARDED,
        protected_integrations: tuple[str, ...] = (),
        unguarded_paths: tuple[str, ...] = (),
    ) -> None:
        self.stores = stores
        self.events = events
        self._profile = default_profile
        self.protected_integrations = protected_integrations
        self.unguarded_paths = unguarded_paths
        self.last_error: str | None = None
        self._load_profile()

    # Information assets -------------------------------------------------
    def register_asset(self, asset: InformationAsset) -> InformationAsset:
        self._validate_categories(asset.categories)
        if not asset.asset_id.strip() or not asset.source_domain.strip():
            raise BoundaryValidationError("asset_id and source_domain are required")
        payload = asdict(
            replace(
                asset,
                created_at=asset.created_at or _iso(),
                metadata=_safe_metadata(asset.metadata),
                checksum="",
            )
        )
        saved = replace(
            asset,
            created_at=str(payload["created_at"]),
            metadata=dict(payload["metadata"]),
            checksum=_checksum(payload),
        )
        try:
            self.stores["assets"].put(saved.asset_id, asdict(saved), create_only=True)
        except Exception as exc:
            raise BoundaryConflict(f"Information asset already exists: {saved.asset_id}") from exc
        self._emit("information_asset.registered", saved.asset_id, self._asset_event(saved))
        return saved

    def get_asset(self, asset_id: str) -> InformationAsset:
        try:
            return self._asset(self.stores["assets"].get(asset_id))
        except Exception as exc:
            raise BoundaryNotFound(f"Information asset not found: {asset_id}") from exc

    def list_assets(self, *, unclassified: bool = False) -> tuple[InformationAsset, ...]:
        assets = tuple(self._asset(raw) for raw in self.stores["assets"].list())
        if unclassified:
            return tuple(item for item in assets if item.metadata.get("classification_unknown"))
        return assets

    def reclassify_asset(
        self,
        asset_id: str,
        classification: DataClassification,
        *,
        actor_id: str,
        justification: str,
        approval_id: str | None = None,
        redaction_validated: bool = False,
    ) -> InformationAsset:
        current = self.get_asset(asset_id)
        downgrade = CLASSIFICATION_ORDER[classification] < CLASSIFICATION_ORDER[
            current.classification
        ]
        if downgrade and (not justification.strip() or not approval_id or not redaction_validated):
            raise BoundaryValidationError(
                "classification downgrade requires justification, approval and validated redaction"
            )
        payload = asdict(replace(current, classification=classification, revision=current.revision + 1))
        payload["checksum"] = ""
        updated = replace(
            current,
            classification=classification,
            revision=current.revision + 1,
            checksum=_checksum(payload),
        )
        self.stores["assets"].put(
            asset_id, asdict(updated), expected_revision=current.revision
        )
        self._append_ledger(
            record_type="classification_change",
            decision_id=f"classification:{asset_id}:{updated.revision}",
            manifest=None,
            request=EgressRequest(
                (asset_id,), actor_id, "local-registry", ProcessingBoundary.LOCAL_PROCESS,
                ProcessingPurpose.SUMMARIZATION,
            ),
            assets=(updated,),
            status="reclassified",
            approval_reference=approval_id,
        )
        self._emit("information_asset.reclassified", asset_id, self._asset_event(updated))
        return updated

    # Trust profiles and operating mode ----------------------------------
    def register_trust_profile(self, profile: ProviderTrustProfile) -> ProviderTrustProfile:
        self._validate_categories(profile.allowed_categories + profile.blocked_categories)
        payload = asdict(replace(profile, checksum=""))
        saved = replace(profile, checksum=_checksum(payload))
        try:
            self.stores["trust_profiles"].put(
                saved.trust_profile_id, asdict(saved), create_only=True
            )
        except Exception as exc:
            raise BoundaryConflict(f"Trust profile already exists: {profile.trust_profile_id}") from exc
        self._emit("provider_trust.updated", profile.provider_id, self._trust_event(saved))
        return saved

    def update_trust_profile(
        self, trust_profile_id: str, changes: dict[str, Any]
    ) -> ProviderTrustProfile:
        current = self.get_trust_profile(trust_profile_id)
        forbidden = {"trust_profile_id", "provider_id", "revision", "checksum"}
        if forbidden.intersection(changes):
            raise BoundaryValidationError("immutable trust profile fields cannot be changed")
        normalized = dict(changes)
        for key in ("processing_boundary", "status"):
            if key in normalized:
                enum_type = ProcessingBoundary if key == "processing_boundary" else TrustProfileStatus
                normalized[key] = enum_type(normalized[key])
        for key in ("supported_classifications", "blocked_classifications"):
            if key in normalized:
                normalized[key] = tuple(DataClassification(item) for item in normalized[key])
        for key in (
            "contractual_controls", "allowed_categories", "blocked_categories"
        ):
            if key in normalized:
                normalized[key] = tuple(str(item) for item in normalized[key])
        updated = replace(current, **normalized, revision=current.revision + 1, checksum="")
        self._validate_categories(updated.allowed_categories + updated.blocked_categories)
        updated = replace(updated, checksum=_checksum(asdict(updated)))
        self.stores["trust_profiles"].put(
            trust_profile_id, asdict(updated), expected_revision=current.revision
        )
        self._emit("provider_trust.updated", updated.provider_id, self._trust_event(updated))
        return updated

    def get_trust_profile(self, trust_profile_id: str) -> ProviderTrustProfile:
        try:
            return self._trust(self.stores["trust_profiles"].get(trust_profile_id))
        except Exception as exc:
            raise BoundaryNotFound(f"Trust profile not found: {trust_profile_id}") from exc

    def list_trust_profiles(self) -> tuple[ProviderTrustProfile, ...]:
        return tuple(self._trust(raw) for raw in self.stores["trust_profiles"].list())

    def trust_for_provider(self, provider_id: str) -> ProviderTrustProfile | None:
        candidates = [
            item
            for item in self.list_trust_profiles()
            if item.provider_id == provider_id and item.status == TrustProfileStatus.ACTIVE
        ]
        if not candidates:
            return None
        profile = max(candidates, key=lambda item: item.revision)
        if profile.expires_at and datetime.fromisoformat(profile.expires_at) <= _now():
            return None
        return profile

    def provider_boundary(self, provider_id: str) -> str | None:
        profile = self.trust_for_provider(provider_id)
        return profile.processing_boundary.value if profile else None

    def set_operating_profile(self, profile: OperatingProfile, *, actor_id: str) -> str:
        self._profile = profile
        payload = {"profile": profile.value, "revision": self._profile_revision() + 1}
        self.stores["settings"].put("operating_profile", payload)
        self._emit("intelligence_profile.updated", actor_id, payload)
        return profile.value

    def operating_profile(self) -> OperatingProfile:
        return self._profile

    # Decision, minimization, redaction and gate --------------------------
    def preview_egress(self, request: EgressRequest) -> EgressAuthorization:
        return self._evaluate(request, gate=False)

    def authorize_egress(self, request: EgressRequest) -> EgressAuthorization:
        if request.approval_reference:
            return self._authorize_with_binding(request)
        authorization = self._evaluate(request, gate=True)
        if not authorization.allowed:
            if authorization.decision.approval_required:
                raise EgressApprovalRequired(
                    authorization.reason, code="egress_approval_required"
                )
            raise EgressDenied(authorization.reason)
        return authorization

    def _authorize_with_binding(self, request: EgressRequest) -> EgressAuthorization:
        try:
            approval = self._approval(
                self.stores["approvals"].get(str(request.approval_reference))
            )
        except Exception as exc:
            raise EgressApprovalRequired("egress approval not found") from exc
        manifests = [
            self._manifest(raw)
            for raw in self.stores["manifests"].list()
            if raw.get("checksum") == approval.manifest_checksum
        ]
        if not manifests:
            raise EgressApprovalRequired("approved egress manifest not found")
        manifest = manifests[-1]
        decision = self.get_decision(approval.decision_id)
        self._validate_approval(approval.approval_id, decision, manifest)
        self.validate_manifest(
            manifest.manifest_id,
            payload_checksum=request.payload_checksum,
            provider_id=request.provider_id,
            destination=request.destination,
            purpose=request.purpose.value,
        )
        assets = tuple(self.get_asset(item) for item in manifest.asset_references)
        if tuple(request.asset_ids) != manifest.asset_references:
            raise EgressApprovalRequired("approved asset set changed")
        self._append_ledger(
            record_type="egress_attempt",
            decision_id=decision.decision_id,
            manifest=manifest,
            request=request,
            assets=assets,
            status="allowed",
            approval_reference=approval.approval_id,
        )
        self._emit("egress.allowed", request.requester, self._decision_event(decision, request))
        return EgressAuthorization(True, decision, manifest, "scoped approval validated")

    def _evaluate(self, request: EgressRequest, *, gate: bool) -> EgressAuthorization:
        try:
            assets = tuple(self.get_asset(asset_id) for asset_id in request.asset_ids)
            if not assets:
                raise BoundaryValidationError("at least one classified asset is required")
            minimization = self._minimize(assets, request)
            included = tuple(
                asset for asset in assets if asset.asset_id in minimization.included_assets
            )
            status, reasons, warnings, transformations = self._policy(
                included, request, minimization
            )
            redaction = self._redaction(included, request, transformations)
            if redaction and redaction.validation_status != "validated":
                status = EgressDecisionStatus.DENIED
                reasons.append("required redaction could not be verified")
            expires = _now() + timedelta(minutes=15)
            decision_id = f"edg-{uuid4().hex}"
            approval_required = status == EgressDecisionStatus.APPROVAL_REQUIRED
            decision = EgressDecision(
                decision_id=decision_id,
                status=status,
                allowed_assets=(
                    tuple(item.asset_id for item in included)
                    if status not in {EgressDecisionStatus.DENIED, EgressDecisionStatus.LOCAL_ONLY}
                    else ()
                ),
                blocked_assets=(
                    tuple(item.asset_id for item in included)
                    if status in {EgressDecisionStatus.DENIED, EgressDecisionStatus.LOCAL_ONLY}
                    else minimization.omitted_assets
                ),
                required_transformations=tuple(transformations),
                redaction_plan=redaction,
                minimization_plan=minimization,
                approval_required=approval_required,
                approval_scope=self._approval_scope(request, included, transformations),
                reasons=tuple(reasons),
                warnings=tuple(warnings),
                expires_at=_iso(expires),
                revision=1,
                checksum="",
                trace_id=request.correlation_id or f"trace-{uuid4().hex}",
            )
            decision = replace(decision, checksum=_checksum(asdict(decision)))
            self.stores["decisions"].put(decision_id, asdict(decision), create_only=True)
            manifest = None
            if status not in {EgressDecisionStatus.DENIED, EgressDecisionStatus.LOCAL_ONLY}:
                manifest = self._create_manifest(decision, request, included)
            allowed = status not in {
                EgressDecisionStatus.DENIED,
                EgressDecisionStatus.LOCAL_ONLY,
                EgressDecisionStatus.APPROVAL_REQUIRED,
            }
            if approval_required and request.approval_reference and manifest:
                self._validate_approval(request.approval_reference, decision, manifest)
                allowed = True
            ledger_status = "allowed" if allowed else status.value
            self._append_ledger(
                record_type="egress_attempt" if gate else "egress_preview",
                decision_id=decision_id,
                manifest=manifest,
                request=request,
                assets=included,
                status=ledger_status,
                approval_reference=request.approval_reference,
            )
            self._emit("egress.evaluated", request.requester, self._decision_event(decision, request))
            event = "egress.allowed" if allowed else (
                "egress.approval_required" if approval_required else "egress.blocked"
            )
            self._emit(event, request.requester, self._decision_event(decision, request))
            return EgressAuthorization(allowed, decision, manifest, "; ".join(reasons))
        except Exception as exc:
            self.last_error = getattr(exc, "code", type(exc).__name__)
            raise

    def validate_manifest(
        self,
        manifest_id: str,
        *,
        payload_checksum: str,
        provider_id: str | None,
        destination: str,
        purpose: str,
    ) -> EgressManifest:
        manifest = self.get_manifest(manifest_id)
        if datetime.fromisoformat(manifest.expires_at) <= _now():
            raise StaleEgressManifest("egress manifest expired")
        checks = (
            manifest.payload_checksum == payload_checksum,
            manifest.provider_id == provider_id,
            manifest.destination == destination,
            manifest.purpose == ProcessingPurpose(purpose),
        )
        if not all(checks):
            raise StaleEgressManifest("payload, provider, destination or purpose changed")
        expected = replace(manifest, checksum="")
        if manifest.checksum != _checksum(asdict(expected)):
            raise StaleEgressManifest("egress manifest checksum mismatch")
        if manifest.provider_id and manifest.boundary not in LOCAL_BOUNDARIES:
            profile = self.trust_for_provider(manifest.provider_id)
            if not profile or profile.processing_boundary != manifest.boundary:
                raise StaleEgressManifest("provider trust profile changed or expired")
        if manifest.approval_reference:
            decision = self.get_decision(manifest.decision_id)
            self._validate_approval(manifest.approval_reference, decision, manifest)
        return manifest

    def grant_approval(
        self,
        decision_id: str,
        manifest_id: str,
        *,
        approver: str,
        actor_type: str = "user",
        expires_in_minutes: int = 15,
    ) -> EgressApprovalBinding:
        if actor_type == "ephemeral_agent":
            raise EgressDenied("ephemeral agents cannot approve egress")
        decision = self.get_decision(decision_id)
        manifest = self.get_manifest(manifest_id)
        if manifest.decision_id != decision_id or not decision.approval_required:
            raise BoundaryValidationError("approval does not match an approval-required decision")
        approval = EgressApprovalBinding(
            approval_id=f"eap-{uuid4().hex}",
            decision_id=decision_id,
            manifest_checksum=manifest.checksum,
            provider_id=manifest.provider_id,
            destination=manifest.destination,
            purpose=manifest.purpose,
            classifications=manifest.source_classifications,
            categories=manifest.categories,
            transformations=manifest.transformations,
            requester=manifest.requester,
            approver=approver,
            expires_at=_iso(_now() + timedelta(minutes=expires_in_minutes)),
        )
        self.stores["approvals"].put(approval.approval_id, asdict(approval), create_only=True)
        self._emit("consent.granted", approver, {"approval_id": approval.approval_id})
        return approval

    def revoke_approval(self, approval_id: str, *, actor_id: str) -> EgressApprovalBinding:
        current = self._approval(self.stores["approvals"].get(approval_id))
        revoked = replace(current, status="revoked")
        self.stores["approvals"].put(approval_id, asdict(revoked))
        self._emit("consent.revoked", actor_id, {"approval_id": approval_id})
        return revoked

    # Records and derived outputs ----------------------------------------
    def get_decision(self, decision_id: str) -> EgressDecision:
        try:
            return self._decision(self.stores["decisions"].get(decision_id))
        except Exception as exc:
            raise BoundaryNotFound(f"Egress decision not found: {decision_id}") from exc

    def get_manifest(self, manifest_id: str) -> EgressManifest:
        try:
            return self._manifest(self.stores["manifests"].get(manifest_id))
        except Exception as exc:
            raise BoundaryNotFound(f"Egress manifest not found: {manifest_id}") from exc

    def ledger_history(self) -> tuple[EgressLedgerRecord, ...]:
        return tuple(self._ledger(raw) for raw in self.stores["ledger"].list())

    def complete_egress(
        self,
        manifest_id: str,
        *,
        result_reference: str,
        status: str = "completed",
        error_code: str | None = None,
    ) -> EgressLedgerRecord:
        manifest = self.get_manifest(manifest_id)
        existing = [
            item
            for item in self.ledger_history()
            if item.manifest_id == manifest_id and item.record_type == "egress_result"
        ]
        if existing:
            return existing[-1]
        assets = tuple(self.get_asset(item) for item in manifest.asset_references)
        request = EgressRequest(
            manifest.asset_references,
            manifest.requester,
            manifest.destination,
            manifest.boundary,
            manifest.purpose,
            provider_id=manifest.provider_id,
            payload_checksum=manifest.payload_checksum,
            estimated_size=manifest.estimated_size,
            estimated_tokens=manifest.estimated_tokens,
            approval_reference=manifest.approval_reference,
        )
        return self._append_ledger(
            record_type="egress_result",
            decision_id=manifest.decision_id,
            manifest=manifest,
            request=request,
            assets=assets,
            status=status,
            approval_reference=manifest.approval_reference,
            result_reference=result_reference,
            error_code=error_code,
        )

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
    ) -> InformationAsset:
        parents = tuple(self.get_asset(item) for item in input_asset_ids)
        if not parents:
            raise BoundaryValidationError("derived assets require source assets")
        classification = max(parents, key=lambda item: CLASSIFICATION_ORDER[item.classification])
        training = (
            TrainingUsePolicy.PROHIBITED
            if any(item.training_use_policy == TrainingUsePolicy.PROHIBITED for item in parents)
            else parents[0].training_use_policy
        )
        provenance = DerivedArtifactProvenance(
            asset_id,
            input_asset_ids,
            provider_id,
            model_id,
            purpose,
            manifest_id,
            output_checksum,
            "most-restrictive-input",
            parents[0].owner,
            _iso(),
            training,
        )
        asset = self.register_asset(
            InformationAsset(
                asset_id=asset_id,
                owner=parents[0].owner,
                project_id=parents[0].project_id,
                source_domain="derived",
                source_reference=source_reference,
                content_type=content_type,
                classification=classification.classification,
                categories=("provider.output",),
                training_use_policy=training,
                provenance=asdict(provenance),
                parent_asset_ids=input_asset_ids,
            )
        )
        self._emit("derived_asset.created", asset_id, self._asset_event(asset))
        return asset

    def status(self) -> dict[str, Any]:
        profiles = self.list_trust_profiles()
        return {
            "available": True,
            "profile": self._profile.value,
            "classification_registry": [item.value for item in DataClassification],
            "assets": len(self.list_assets()),
            "unclassified_assets": len(self.list_assets(unclassified=True)),
            "trust_profiles": len(profiles),
            "invalid_or_expired_profiles": sum(
                item.status != TrustProfileStatus.ACTIVE
                or bool(item.expires_at and datetime.fromisoformat(item.expires_at) <= _now())
                for item in profiles
            ),
            "decisions": len(self.stores["decisions"].list()),
            "manifests": len(self.stores["manifests"].list()),
            "ledger_records": len(self.stores["ledger"].list()),
            "protected_integrations": list(self.protected_integrations),
            "unguarded_paths": list(self.unguarded_paths),
            "last_error": self.last_error,
            "external_provider_behavior_guaranteed": False,
        }

    # Internal policy helpers --------------------------------------------
    def _policy(
        self,
        assets: tuple[InformationAsset, ...],
        request: EgressRequest,
        minimization: MinimizationPlan,
    ) -> tuple[EgressDecisionStatus, list[str], list[str], list[str]]:
        external = request.boundary not in LOCAL_BOUNDARIES
        reasons: list[str] = []
        warnings: list[str] = []
        transformations: list[str] = list(request.requested_transformations)
        if not external:
            reasons.append("destination boundary is explicitly local")
            status = (
                EgressDecisionStatus.ALLOWED_MINIMIZED
                if minimization.omitted_assets
                else EgressDecisionStatus.ALLOWED
            )
            return status, reasons, warnings, transformations
        if self._profile in {OperatingProfile.LOCAL_SOVEREIGN, OperatingProfile.AIR_GAPPED}:
            return EgressDecisionStatus.LOCAL_ONLY, ["operating profile forbids external egress"], [], []
        if any(asset.classification == DataClassification.SECRET for asset in assets):
            return EgressDecisionStatus.DENIED, ["secret assets are local-only"], [], []
        if any(asset.classification == DataClassification.RESTRICTED for asset in assets):
            return EgressDecisionStatus.LOCAL_ONLY, ["restricted assets are local-only by default"], [], []
        if any(asset.external_processing_policy in {"denied", "local-only"} for asset in assets):
            return EgressDecisionStatus.DENIED, ["asset external-processing policy denies egress"], [], []
        if any(asset.training_use_policy == TrainingUsePolicy.PROHIBITED for asset in assets) and (
            request.purpose
            in {
                ProcessingPurpose.TRAINING_FUTURE,
                ProcessingPurpose.FINE_TUNING_FUTURE,
                ProcessingPurpose.DISTILLATION_FUTURE,
            }
        ):
            return EgressDecisionStatus.DENIED, ["training-use policy denies requested purpose"], [], []
        if not request.provider_id:
            return EgressDecisionStatus.DENIED, ["external destination requires provider identity"], [], []
        trust = self.trust_for_provider(request.provider_id)
        if not trust:
            return EgressDecisionStatus.DENIED, ["provider has no active trust profile"], [], []
        if trust.processing_boundary != request.boundary:
            return EgressDecisionStatus.DENIED, ["destination boundary differs from trust profile"], [], []
        classifications = {asset.classification for asset in assets}
        categories = {category for asset in assets for category in asset.categories}
        if classifications.intersection(trust.blocked_classifications):
            return EgressDecisionStatus.DENIED, ["provider blocks an asset classification"], [], []
        if trust.supported_classifications and not classifications.issubset(
            set(trust.supported_classifications)
        ):
            return EgressDecisionStatus.DENIED, ["provider does not support an asset classification"], [], []
        if categories.intersection(trust.blocked_categories):
            return EgressDecisionStatus.DENIED, ["provider blocks an asset category"], [], []
        if trust.allowed_categories and not categories.issubset(set(trust.allowed_categories)):
            return EgressDecisionStatus.DENIED, ["provider does not allow an asset category"], [], []
        confidential = DataClassification.CONFIDENTIAL in classifications
        if trust.requires_redaction or confidential:
            if "mask_secret" not in transformations:
                transformations.append("mask_secret")
        if confidential and self._profile == OperatingProfile.HYBRID_GUARDED:
            reasons.append("confidential external egress requires scoped approval")
            return EgressDecisionStatus.APPROVAL_REQUIRED, reasons, warnings, transformations
        if "approval_required" in request.constraints:
            return EgressDecisionStatus.APPROVAL_REQUIRED, ["request policy requires approval"], [], transformations
        reasons.append("active trust profile and policy allow external processing")
        if transformations:
            return EgressDecisionStatus.ALLOWED_REDACTED, reasons, warnings, transformations
        if minimization.omitted_assets:
            return EgressDecisionStatus.ALLOWED_MINIMIZED, reasons, warnings, transformations
        return EgressDecisionStatus.ALLOWED, reasons, warnings, transformations

    def _minimize(
        self, assets: tuple[InformationAsset, ...], request: EgressRequest
    ) -> MinimizationPlan:
        included: list[str] = []
        omitted: list[str] = []
        summarized: list[str] = []
        redaction: list[str] = []
        reasons: dict[str, str] = {}
        original = sum(max(1, int(item.metadata.get("estimated_tokens", 1))) for item in assets)
        budget = request.estimated_tokens or original
        used = 0
        for asset in assets:
            tokens = max(1, int(asset.metadata.get("estimated_tokens", 1)))
            relevant = bool(asset.metadata.get("relevant", True))
            required = bool(asset.metadata.get("required", False))
            if not relevant and not required:
                omitted.append(asset.asset_id)
                reasons[asset.asset_id] = "omitted as not relevant to declared purpose"
                continue
            if used + tokens > budget and not required:
                omitted.append(asset.asset_id)
                reasons[asset.asset_id] = "omitted by deterministic token budget"
                continue
            included.append(asset.asset_id)
            used += tokens
            reasons[asset.asset_id] = "included as relevant and within budget"
            if asset.metadata.get("summary_only"):
                summarized.append(asset.asset_id)
            if asset.classification in {
                DataClassification.CONFIDENTIAL,
                DataClassification.RESTRICTED,
                DataClassification.SECRET,
            }:
                redaction.append(asset.asset_id)
        self._emit(
            "egress.minimized",
            request.requester,
            {"included": len(included), "omitted": len(omitted), "correlation_id": request.correlation_id},
        )
        return MinimizationPlan(
            tuple(included), tuple(omitted), tuple(summarized), tuple(redaction), reasons,
            used, original, "medium" if redaction else "low",
        )

    def _redaction(
        self,
        assets: tuple[InformationAsset, ...],
        request: EgressRequest,
        transformations: list[str],
    ) -> RedactionPlan | None:
        if not transformations:
            return None
        supported = {
            "remove_field", "replace_identifier", "hash_identifier", "mask_secret",
            "extract_schema", "structural_summary", "code_symbol_anonymization",
            "metadata_removal", "transcript_segment_removal",
        }
        unsupported = set(transformations).difference(supported)
        before = max(assets, key=lambda item: CLASSIFICATION_ORDER[item.classification]).classification
        validated = not unsupported and "redaction_failure" not in request.constraints
        source = request.payload_checksum or _checksum(tuple(item.checksum for item in assets))
        transformed = _checksum({"source": source, "rules": transformations}) if validated else ""
        result = RedactionPlan(
            source, transformed, tuple(transformations), (), before, before,
            "medium", "validated" if validated else "failed",
        )
        self._emit(
            "egress.redaction_applied",
            request.requester,
            {"rules": list(transformations), "validation_status": result.validation_status},
        )
        return result

    def _create_manifest(
        self,
        decision: EgressDecision,
        request: EgressRequest,
        assets: tuple[InformationAsset, ...],
    ) -> EgressManifest:
        manifest = EgressManifest(
            manifest_id=f"egm-{uuid4().hex}",
            decision_id=decision.decision_id,
            requester=request.requester,
            provider_id=request.provider_id,
            destination=request.destination,
            boundary=request.boundary,
            purpose=request.purpose,
            asset_references=tuple(item.asset_id for item in assets),
            source_classifications=tuple(item.classification for item in assets),
            resulting_classifications=tuple(item.classification for item in assets),
            categories=tuple(sorted({category for item in assets for category in item.categories})),
            transformations=decision.required_transformations,
            payload_checksum=request.payload_checksum,
            estimated_size=request.estimated_size,
            estimated_tokens=decision.minimization_plan.estimated_tokens,
            created_at=_iso(),
            expires_at=decision.expires_at,
            revision=1,
            checksum="",
            project_id=request.project_id,
            rfc_id=request.rfc_id,
            rfc_revision=request.rfc_revision,
            mission_id=request.mission_id,
            task_id=request.task_id,
            approval_reference=request.approval_reference,
        )
        manifest = replace(manifest, checksum=_checksum(asdict(manifest)))
        self.stores["manifests"].put(manifest.manifest_id, asdict(manifest), create_only=True)
        return manifest

    def _validate_approval(
        self, approval_id: str, decision: EgressDecision, manifest: EgressManifest
    ) -> None:
        try:
            approval = self._approval(self.stores["approvals"].get(approval_id))
        except Exception as exc:
            raise EgressApprovalRequired("egress approval not found") from exc
        if approval.status != "approved" or datetime.fromisoformat(approval.expires_at) <= _now():
            raise EgressApprovalRequired("egress approval is revoked or expired")
        expected = self._approval_scope_from_manifest(manifest)
        actual = {
            "decision_id": approval.decision_id,
            "manifest_checksum": approval.manifest_checksum,
            "provider_id": approval.provider_id,
            "destination": approval.destination,
            "purpose": approval.purpose,
            "classifications": approval.classifications,
            "categories": approval.categories,
            "transformations": approval.transformations,
            "requester": approval.requester,
        }
        if actual != expected or approval.decision_id != decision.decision_id:
            raise EgressApprovalRequired("egress approval scope no longer matches payload")

    def _append_ledger(
        self,
        *,
        record_type: str,
        decision_id: str,
        manifest: EgressManifest | None,
        request: EgressRequest,
        assets: tuple[InformationAsset, ...],
        status: str,
        approval_reference: str | None,
        result_reference: str | None = None,
        error_code: str | None = None,
    ) -> EgressLedgerRecord:
        record = EgressLedgerRecord(
            record_id=f"egl-{uuid4().hex}",
            record_type=record_type,
            decision_id=decision_id,
            manifest_id=manifest.manifest_id if manifest else None,
            provider_id=request.provider_id,
            destination=request.destination,
            purpose=request.purpose,
            categories=tuple(sorted({category for item in assets for category in item.categories})),
            classifications=tuple(item.classification for item in assets),
            transformation_summary=manifest.transformations if manifest else (),
            approval_reference=approval_reference,
            status=status,
            estimated_bytes=request.estimated_size,
            estimated_tokens=request.estimated_tokens,
            result_reference=result_reference,
            created_at=_iso(),
            correlation_id=request.correlation_id,
            error_code=error_code,
        )
        self.stores["ledger"].put(record.record_id, asdict(record), create_only=True)
        return record

    def _load_profile(self) -> None:
        try:
            raw = self.stores["settings"].get("operating_profile")
            self._profile = OperatingProfile(str(raw["profile"]))
        except Exception:
            return

    def _profile_revision(self) -> int:
        try:
            return int(self.stores["settings"].get("operating_profile").get("revision", 0))
        except Exception:
            return 0

    @staticmethod
    def _validate_categories(categories: tuple[str, ...]) -> None:
        invalid = [item for item in categories if not CATEGORY_PATTERN.fullmatch(item)]
        if invalid:
            raise BoundaryValidationError(f"invalid namespaced categories: {invalid}")

    @staticmethod
    def _approval_scope(
        request: EgressRequest,
        assets: tuple[InformationAsset, ...],
        transformations: list[str],
    ) -> dict[str, Any]:
        return {
            "provider_id": request.provider_id,
            "destination": request.destination,
            "purpose": request.purpose.value,
            "classifications": [item.classification.value for item in assets],
            "categories": sorted({category for item in assets for category in item.categories}),
            "transformations": transformations,
            "requester": request.requester,
        }

    @staticmethod
    def _approval_scope_from_manifest(manifest: EgressManifest) -> dict[str, Any]:
        return {
            "decision_id": manifest.decision_id,
            "manifest_checksum": manifest.checksum,
            "provider_id": manifest.provider_id,
            "destination": manifest.destination,
            "purpose": manifest.purpose,
            "classifications": manifest.source_classifications,
            "categories": manifest.categories,
            "transformations": manifest.transformations,
            "requester": manifest.requester,
        }

    def _emit(self, event_type: str, source: str, payload: dict[str, Any]) -> None:
        self.events.emit(event_type, source, _safe_metadata(payload))

    @staticmethod
    def _asset_event(asset: InformationAsset) -> dict[str, Any]:
        return {
            "asset_id": asset.asset_id,
            "classification": asset.classification.value,
            "categories": list(asset.categories),
            "owner": asset.owner.value,
            "revision": asset.revision,
        }

    @staticmethod
    def _trust_event(profile: ProviderTrustProfile) -> dict[str, Any]:
        return {
            "trust_profile_id": profile.trust_profile_id,
            "provider_id": profile.provider_id,
            "boundary": profile.processing_boundary.value,
            "status": profile.status.value,
            "verification_level": profile.verification_level,
        }

    @staticmethod
    def _decision_event(decision: EgressDecision, request: EgressRequest) -> dict[str, Any]:
        return {
            "decision_id": decision.decision_id,
            "decision": decision.status.value,
            "provider": request.provider_id,
            "boundary": request.boundary.value,
            "purpose": request.purpose.value,
            "correlation_id": request.correlation_id,
        }

    @staticmethod
    def _asset(raw: dict[str, Any]) -> InformationAsset:
        return InformationAsset(
            **{
                **raw,
                "owner": InformationOwnership(raw["owner"]),
                "classification": DataClassification(raw["classification"]),
                "categories": tuple(raw.get("categories", ())),
                "processing_constraints": tuple(raw.get("processing_constraints", ())),
                "training_use_policy": TrainingUsePolicy(raw["training_use_policy"]),
                "parent_asset_ids": tuple(raw.get("parent_asset_ids", ())),
            }
        )

    @staticmethod
    def _trust(raw: dict[str, Any]) -> ProviderTrustProfile:
        return ProviderTrustProfile(
            **{
                **raw,
                "processing_boundary": ProcessingBoundary(raw["processing_boundary"]),
                "contractual_controls": tuple(raw.get("contractual_controls", ())),
                "supported_classifications": tuple(
                    DataClassification(item) for item in raw.get("supported_classifications", ())
                ),
                "blocked_classifications": tuple(
                    DataClassification(item) for item in raw.get("blocked_classifications", ())
                ),
                "allowed_categories": tuple(raw.get("allowed_categories", ())),
                "blocked_categories": tuple(raw.get("blocked_categories", ())),
                "status": TrustProfileStatus(raw["status"]),
            }
        )

    @staticmethod
    def _minimization(raw: dict[str, Any]) -> MinimizationPlan:
        return MinimizationPlan(
            tuple(raw["included_assets"]), tuple(raw["omitted_assets"]),
            tuple(raw["summarized_assets"]), tuple(raw["redaction_candidates"]),
            dict(raw["reasons"]), int(raw["estimated_tokens"]),
            int(raw["original_estimated_tokens"]), str(raw["residual_risk"]),
        )

    @staticmethod
    def _redaction_plan(raw: dict[str, Any] | None) -> RedactionPlan | None:
        if not raw:
            return None
        return RedactionPlan(
            **{
                **raw,
                "rules_applied": tuple(raw["rules_applied"]),
                "fields_removed": tuple(raw["fields_removed"]),
                "classification_before": DataClassification(raw["classification_before"]),
                "classification_after": DataClassification(raw["classification_after"]),
            }
        )

    @classmethod
    def _decision(cls, raw: dict[str, Any]) -> EgressDecision:
        return EgressDecision(
            **{
                **raw,
                "status": EgressDecisionStatus(raw["status"]),
                "allowed_assets": tuple(raw["allowed_assets"]),
                "blocked_assets": tuple(raw["blocked_assets"]),
                "required_transformations": tuple(raw["required_transformations"]),
                "redaction_plan": cls._redaction_plan(raw.get("redaction_plan")),
                "minimization_plan": cls._minimization(raw["minimization_plan"]),
                "reasons": tuple(raw["reasons"]),
                "warnings": tuple(raw["warnings"]),
            }
        )

    @staticmethod
    def _manifest(raw: dict[str, Any]) -> EgressManifest:
        return EgressManifest(
            **{
                **raw,
                "boundary": ProcessingBoundary(raw["boundary"]),
                "purpose": ProcessingPurpose(raw["purpose"]),
                "asset_references": tuple(raw["asset_references"]),
                "source_classifications": tuple(
                    DataClassification(item) for item in raw["source_classifications"]
                ),
                "resulting_classifications": tuple(
                    DataClassification(item) for item in raw["resulting_classifications"]
                ),
                "categories": tuple(raw["categories"]),
                "transformations": tuple(raw["transformations"]),
            }
        )

    @staticmethod
    def _approval(raw: dict[str, Any]) -> EgressApprovalBinding:
        return EgressApprovalBinding(
            **{
                **raw,
                "purpose": ProcessingPurpose(raw["purpose"]),
                "classifications": tuple(
                    DataClassification(item) for item in raw["classifications"]
                ),
                "categories": tuple(raw["categories"]),
                "transformations": tuple(raw["transformations"]),
            }
        )

    @staticmethod
    def _ledger(raw: dict[str, Any]) -> EgressLedgerRecord:
        return EgressLedgerRecord(
            **{
                **raw,
                "purpose": ProcessingPurpose(raw["purpose"]),
                "categories": tuple(raw["categories"]),
                "classifications": tuple(
                    DataClassification(item) for item in raw["classifications"]
                ),
                "transformation_summary": tuple(raw["transformation_summary"]),
            }
        )
