from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from synapse.intelligence_boundary.models import (
    DataClassification,
    EgressDecisionStatus,
    InformationOwnership,
    OperatingProfile,
    ProcessingBoundary,
    ProcessingPurpose,
)

from .canonical import fingerprint
from .errors import SensitivePayloadViolation
from .values import ContentChecksum, EvalRunId, Fingerprint, Revision

_SAFE_CODE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
_SENSITIVE_VALUE = re.compile(
    r"(?i)(?:token|secret|password|credential|authorization|bearer|api[_-]?key|sk-)"
)


def _code(value: str, label: str) -> None:
    if isinstance(value, str) and _SENSITIVE_VALUE.search(value):
        raise SensitivePayloadViolation("security metadata contains a forbidden value")
    if not isinstance(value, str) or not _SAFE_CODE.fullmatch(value):
        raise ValueError(f"{label} must be a safe canonical code")


def _unique(values: tuple[object, ...], label: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"duplicate {label} reference")


class EvalAssetSourceKind(StrEnum):
    GOVERNED_REGISTRY = "governed_registry"
    GOVERNED_LOCAL_CUSTODY = "governed_local_custody"
    DESKTOP_UPLOAD = "desktop_upload"
    DESKTOP_FORM_SUBMISSION = "desktop_form_submission"
    UNGOVERNED = "ungoverned"


class EvalSecurityDisposition(StrEnum):
    READY = "ready"
    BLOCKED = "blocked"
    INVALID = "invalid"
    POLICY_DENIED = "policy_denied"


class SecurityReasonCode(StrEnum):
    AUTHORIZED = "authorized"
    APPROVAL_REQUIRED = "approval_required"
    POLICY_DENIED = "policy_denied"
    PROVIDER_NOT_APPROVED = "provider_not_approved"


@dataclass(frozen=True, order=True)
class AssetVersionReference:
    asset_id: str
    revision: Revision
    content_checksum: ContentChecksum

    def __post_init__(self) -> None:
        _code(self.asset_id, "asset ID")


@dataclass(frozen=True)
class AssetSecurityProjection:
    """Minimal Intelligence-owned asset policy projection for eval correlation."""

    reference: AssetVersionReference
    owner: InformationOwnership
    classification: DataClassification
    source_kind: EvalAssetSourceKind
    governed_custody: bool
    provenance_fingerprint: Fingerprint


@dataclass(frozen=True)
class ProviderTrustProjection:
    """Versioned trust result; it contains no rules used to calculate trust."""

    provider_id: str
    trust_profile_reference: str
    revision: Revision
    checksum: ContentChecksum
    boundary: ProcessingBoundary
    approved: bool

    def __post_init__(self) -> None:
        _code(self.provider_id, "provider ID")
        _code(self.trust_profile_reference, "trust profile reference")


@dataclass(frozen=True)
class EvalSecuritySnapshot:
    """Safe, versioned projection returned by the Intelligence adapter boundary."""

    snapshot_reference: str
    revision: Revision
    checksum: ContentChecksum
    operating_profile: OperatingProfile
    policy_references: tuple[str, ...]
    policy_checksums: tuple[ContentChecksum, ...]
    assets: tuple[AssetSecurityProjection, ...]
    providers: tuple[ProviderTrustProjection, ...]
    fingerprint: Fingerprint

    def __post_init__(self) -> None:
        _code(self.snapshot_reference, "security snapshot reference")
        if not self.policy_references:
            raise ValueError("security snapshot requires policy references")
        if len(self.policy_references) != len(self.policy_checksums):
            raise ValueError("security policy references and checksums must align")
        _unique(self.policy_references, "security policy")
        _unique(tuple(item.reference.asset_id for item in self.assets), "security asset")
        _unique(tuple(item.provider_id for item in self.providers), "security provider")
        if self.fingerprint != security_snapshot_fingerprint(self):
            raise ValueError("security snapshot fingerprint is inconsistent")

    def __repr__(self) -> str:
        return (
            "EvalSecuritySnapshot("
            f"snapshot_reference={self.snapshot_reference!r}, revision={self.revision!r}, "
            f"fingerprint={self.fingerprint!r})"
        )


def security_snapshot_fingerprint(snapshot: EvalSecuritySnapshot) -> Fingerprint:
    return fingerprint(
        {
            "snapshot_reference": snapshot.snapshot_reference,
            "revision": snapshot.revision,
            "checksum": snapshot.checksum,
            "operating_profile": snapshot.operating_profile,
            "policies": tuple(
                sorted(zip(snapshot.policy_references, snapshot.policy_checksums, strict=True))
            ),
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
                    for item in snapshot.assets
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
                    for item in snapshot.providers
                )
            ),
        }
    )


@dataclass(frozen=True)
class EvalEgressPreparation:
    """Eval-specific request mapped to the canonical Intelligence EgressRequest."""

    run_id: EvalRunId
    run_manifest_reference: str
    requester: str
    project_id: str
    assets: tuple[AssetVersionReference, ...]
    provider_id: str
    destination: str
    boundary: ProcessingBoundary
    purpose: ProcessingPurpose
    operating_profile: OperatingProfile
    payload_checksum: ContentChecksum
    requested_transformations: tuple[str, ...] = ()
    approval_reference: str | None = None

    def __post_init__(self) -> None:
        for value, label in (
            (self.run_manifest_reference, "run manifest reference"),
            (self.requester, "requester"),
            (self.project_id, "project ID"),
            (self.provider_id, "provider ID"),
            (self.destination, "destination"),
        ):
            _code(value, label)
        if not self.assets:
            raise ValueError("egress preparation requires assets")
        _unique(tuple(item.asset_id for item in self.assets), "egress asset")
        for transformation in self.requested_transformations:
            _code(transformation, "transformation reference")
        if self.approval_reference is not None:
            _code(self.approval_reference, "approval reference")


@dataclass(frozen=True)
class EvalSecurityDecision:
    """Run readiness derived from a canonical Intelligence authorization."""

    canonical_status: EgressDecisionStatus
    disposition: EvalSecurityDisposition
    reason_codes: tuple[SecurityReasonCode, ...]
    decision_reference: str
    decision_checksum: ContentChecksum
    security_snapshot_reference: str
    security_snapshot_checksum: ContentChecksum
    security_snapshot_fingerprint: Fingerprint
    manifest_reference: str | None
    manifest_checksum: ContentChecksum | None
    transformation_references: tuple[str, ...]
    approval_reference: str | None
    fingerprint: Fingerprint | None = None

    def __post_init__(self) -> None:
        for value, label in (
            (self.decision_reference, "egress decision reference"),
            (self.security_snapshot_reference, "security snapshot reference"),
        ):
            _code(value, label)
        if (self.manifest_reference is None) != (self.manifest_checksum is None):
            raise ValueError("manifest reference and checksum must align")
        if self.manifest_reference is not None:
            _code(self.manifest_reference, "egress manifest reference")
        if self.approval_reference is not None:
            _code(self.approval_reference, "approval reference")
        _unique(self.reason_codes, "security reason")
        if self.disposition is EvalSecurityDisposition.READY and (
            self.canonical_status
            not in {
                EgressDecisionStatus.ALLOWED,
                EgressDecisionStatus.ALLOWED_MINIMIZED,
                EgressDecisionStatus.ALLOWED_REDACTED,
                EgressDecisionStatus.ALLOWED_SUMMARY_ONLY,
            }
            or self.manifest_reference is None
        ):
            raise ValueError("ready security decision requires canonical authorization")
        if self.disposition is EvalSecurityDisposition.BLOCKED and (
            self.canonical_status is not EgressDecisionStatus.APPROVAL_REQUIRED
            or self.manifest_reference is not None
        ):
            raise ValueError("blocked security decision requires pending approval")
        if self.disposition is EvalSecurityDisposition.POLICY_DENIED and (
            self.canonical_status
            not in {EgressDecisionStatus.DENIED, EgressDecisionStatus.LOCAL_ONLY}
            or self.manifest_reference is not None
        ):
            raise ValueError("policy denial must reflect a canonical denial")
        expected = eval_security_decision_fingerprint(self)
        if self.fingerprint is None:
            object.__setattr__(self, "fingerprint", expected)
        elif self.fingerprint != expected:
            raise ValueError("eval security decision fingerprint is inconsistent")

    def __repr__(self) -> str:
        return (
            "EvalSecurityDecision("
            f"canonical_status={self.canonical_status!r}, disposition={self.disposition!r}, "
            f"decision_reference={self.decision_reference!r}, fingerprint={self.fingerprint!r})"
        )


def eval_security_decision_fingerprint(decision: EvalSecurityDecision) -> Fingerprint:
    return fingerprint(
        {
            "canonical_status": decision.canonical_status,
            "disposition": decision.disposition,
            "reason_codes": tuple(sorted(decision.reason_codes, key=lambda item: item.value)),
            "decision_reference": decision.decision_reference,
            "decision_checksum": decision.decision_checksum,
            "security_snapshot_reference": decision.security_snapshot_reference,
            "security_snapshot_checksum": decision.security_snapshot_checksum,
            "security_snapshot_fingerprint": decision.security_snapshot_fingerprint,
            "manifest_reference": decision.manifest_reference,
            "manifest_checksum": decision.manifest_checksum,
            "transformations": tuple(sorted(decision.transformation_references)),
            "approval_reference": decision.approval_reference,
        }
    )


@dataclass(frozen=True)
class DerivedAssetRegistration:
    """Eval request for canonical derived-asset registration by Intelligence."""

    run_id: EvalRunId
    asset_id: str
    input_assets: tuple[AssetVersionReference, ...]
    source_reference: str
    content_type: str
    output_checksum: ContentChecksum
    purpose: ProcessingPurpose
    provider_id: str | None = None
    model_id: str | None = None
    manifest_reference: str | None = None

    def __post_init__(self) -> None:
        for value, label in (
            (self.asset_id, "derived asset ID"),
            (self.source_reference, "derived source reference"),
            (self.content_type, "derived content type"),
        ):
            _code(value, label)
        if not self.input_assets:
            raise ValueError("derived asset requires input references")
        _unique(tuple(item.asset_id for item in self.input_assets), "derived input")
        for optional_value, label in (
            (self.provider_id, "provider ID"),
            (self.model_id, "model ID"),
            (self.manifest_reference, "manifest reference"),
        ):
            if optional_value is not None:
                _code(optional_value, label)
