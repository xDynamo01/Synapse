"""Distinct Deployment identities, fingerprints and opaque references."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import ClassVar

from .errors import InvalidDeploymentIdentity, InvalidDeploymentReference

_IDENTITY_SUFFIX = r"[A-Za-z0-9][A-Za-z0-9._:@-]{0,190}"
_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,254}$")
_FINGERPRINT = re.compile(r"^sha256:[0-9a-f]{64}$")


def _validate_safe_token(value: str, label: str) -> None:
    if not isinstance(value, str) or not _TOKEN.fullmatch(value):
        raise InvalidDeploymentReference(f"{label} must be bounded printable ASCII")
    if value.startswith(("/", "\\")) or "\\" in value or ".." in value.split("/"):
        raise InvalidDeploymentReference(f"{label} cannot contain a host path")
    if "://" in value:
        raise InvalidDeploymentReference(f"{label} cannot contain a provider endpoint")


@dataclass(frozen=True, slots=True, order=True)
class _DeploymentIdentity:
    value: str
    prefix: ClassVar[str] = ""

    def __post_init__(self) -> None:
        pattern = re.compile(rf"^{re.escape(self.prefix)}:{_IDENTITY_SUFFIX}$")
        if not isinstance(self.value, str) or not pattern.fullmatch(self.value):
            raise InvalidDeploymentIdentity(f"{type(self).__name__} has an invalid canonical form")

    def canonical_value(self) -> str:
        return self.value

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True, order=True)
class DeploymentIntentId(_DeploymentIdentity):
    prefix = "deployment-intent"


@dataclass(frozen=True, slots=True, order=True)
class ReleaseId(_DeploymentIdentity):
    prefix = "deployment-release"


@dataclass(frozen=True, slots=True, order=True)
class DeploymentAttemptId(_DeploymentIdentity):
    prefix = "deployment-attempt"


@dataclass(frozen=True, slots=True, order=True)
class EnvironmentId(_DeploymentIdentity):
    prefix = "deployment-environment"


@dataclass(frozen=True, slots=True, order=True)
class DeploymentTargetId(_DeploymentIdentity):
    prefix = "deployment-target"


@dataclass(frozen=True, slots=True, order=True)
class SlotId(_DeploymentIdentity):
    prefix = "deployment-slot"


@dataclass(frozen=True, slots=True, order=True)
class RevisionId(_DeploymentIdentity):
    prefix = "deployment-revision"


@dataclass(frozen=True, slots=True, order=True)
class RolloutId(_DeploymentIdentity):
    prefix = "deployment-rollout"


@dataclass(frozen=True, slots=True, order=True)
class PromotionId(_DeploymentIdentity):
    prefix = "deployment-promotion"


@dataclass(frozen=True, slots=True, order=True)
class RollbackAttemptId(_DeploymentIdentity):
    prefix = "deployment-rollback-attempt"


@dataclass(frozen=True, slots=True, order=True)
class DeploymentIdempotencyKey(_DeploymentIdentity):
    prefix = "deployment-idempotency"


@dataclass(frozen=True, slots=True, order=True)
class DeploymentEventId(_DeploymentIdentity):
    prefix = "deployment-event"


@dataclass(frozen=True, slots=True, order=True)
class DeploymentFingerprint:
    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not _FINGERPRINT.fullmatch(self.value):
            raise InvalidDeploymentIdentity("fingerprint must use sha256 lowercase hex")

    def canonical_value(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True, order=True)
class _OpaqueReference:
    value: str
    kind: ClassVar[str] = "reference"

    def __post_init__(self) -> None:
        _validate_safe_token(self.value, self.kind)

    def canonical_value(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True, order=True)
class ArtifactReference(_OpaqueReference):
    kind = "artifact reference"


@dataclass(frozen=True, slots=True, order=True)
class ArtifactFingerprintReference(_OpaqueReference):
    kind = "artifact fingerprint reference"


@dataclass(frozen=True, slots=True, order=True)
class ProvenanceReference(_OpaqueReference):
    kind = "provenance reference"


@dataclass(frozen=True, slots=True, order=True)
class EvidenceReference(_OpaqueReference):
    kind = "evidence reference"


@dataclass(frozen=True, slots=True, order=True)
class CustodyReference(_OpaqueReference):
    kind = "custody reference"


@dataclass(frozen=True, slots=True, order=True)
class AuthorizationReference(_OpaqueReference):
    kind = "authorization reference"


@dataclass(frozen=True, slots=True, order=True)
class ApplyReceiptReference(_OpaqueReference):
    kind = "apply receipt reference"


@dataclass(frozen=True, slots=True, order=True)
class ObservationReference(_OpaqueReference):
    kind = "observation reference"


@dataclass(frozen=True, slots=True, order=True)
class VerificationReference(_OpaqueReference):
    kind = "verification reference"


@dataclass(frozen=True, slots=True, order=True)
class PreparationReference(_OpaqueReference):
    kind = "preparation reference"


@dataclass(frozen=True, slots=True, order=True)
class PolicyReference(_OpaqueReference):
    kind = "policy reference"


@dataclass(frozen=True, slots=True, order=True)
class RequesterReference(_OpaqueReference):
    kind = "requester reference"


@dataclass(frozen=True, slots=True, order=True)
class AdapterBindingReference(_OpaqueReference):
    kind = "adapter binding reference"


@dataclass(frozen=True, slots=True, order=True)
class CapabilityReference(_OpaqueReference):
    kind = "capability reference"


@dataclass(frozen=True, slots=True, order=True)
class CorrelationReference(_OpaqueReference):
    kind = "correlation reference"


@dataclass(frozen=True, slots=True, order=True)
class CausationReference(_OpaqueReference):
    kind = "causation reference"


@dataclass(frozen=True, slots=True, order=True)
class OccurrenceReference(_OpaqueReference):
    kind = "occurrence reference"


@dataclass(frozen=True, slots=True, order=True)
class SecretReference(_OpaqueReference):
    kind = "secret reference"


@dataclass(frozen=True, slots=True, order=True)
class FencingReference(_OpaqueReference):
    kind = "fencing reference"


@dataclass(frozen=True, slots=True, order=True)
class RollbackReceiptReference(_OpaqueReference):
    kind = "rollback receipt reference"
