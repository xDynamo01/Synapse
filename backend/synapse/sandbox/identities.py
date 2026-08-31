"""Deterministic semantic identities and opaque external references."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .canonical import content_fingerprint
from .errors import InvalidSandboxIdentity

_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,254}$")
_FINGERPRINT = re.compile(r"^sha256:[0-9a-f]{64}$")


def _validate_token(value: str) -> None:
    if not isinstance(value, str) or not _TOKEN.fullmatch(value):
        raise InvalidSandboxIdentity("identity must be bounded printable ASCII")
    if value.startswith(("/", "\\")) or "\\" in value or ".." in value.split("/"):
        raise InvalidSandboxIdentity("identity cannot contain an absolute or traversing path")


@dataclass(frozen=True, slots=True)
class OpaqueReference:
    value: str

    def __post_init__(self) -> None:
        _validate_token(self.value)

    def canonical_value(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class _SemanticIdentity:
    value: str

    def __post_init__(self) -> None:
        _validate_token(self.value)

    def canonical_value(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class SandboxWorkloadId(_SemanticIdentity):
    pass


@dataclass(frozen=True, slots=True)
class SandboxAdmissionId(_SemanticIdentity):
    pass


@dataclass(frozen=True, slots=True)
class SandboxAdmissionPolicyId(_SemanticIdentity):
    pass


@dataclass(frozen=True, slots=True)
class SandboxCapabilityGrantSetId(_SemanticIdentity):
    pass


@dataclass(frozen=True, slots=True)
class SandboxFilesystemPolicyId(_SemanticIdentity):
    pass


@dataclass(frozen=True, slots=True)
class SandboxFilesystemGrantSetId(_SemanticIdentity):
    pass


@dataclass(frozen=True, slots=True)
class SandboxNetworkPolicyId(_SemanticIdentity):
    pass


@dataclass(frozen=True, slots=True)
class SandboxNetworkGrantSetId(_SemanticIdentity):
    pass


@dataclass(frozen=True, slots=True)
class SandboxProcessPolicyId(_SemanticIdentity):
    pass


@dataclass(frozen=True, slots=True)
class SandboxProcessGrantSetId(_SemanticIdentity):
    pass


@dataclass(frozen=True, slots=True)
class SandboxResourceLimitPolicyId(_SemanticIdentity):
    pass


@dataclass(frozen=True, slots=True)
class SandboxResourceGrantSetId(_SemanticIdentity):
    pass


@dataclass(frozen=True, slots=True)
class SandboxSecretPolicyId(_SemanticIdentity):
    pass


@dataclass(frozen=True, slots=True)
class SandboxSecretGrantSetId(_SemanticIdentity):
    pass


@dataclass(frozen=True, slots=True)
class SandboxMaterializationPlanId(_SemanticIdentity):
    pass


@dataclass(frozen=True, slots=True)
class SandboxMaterializationId(_SemanticIdentity):
    pass


@dataclass(frozen=True, slots=True)
class SandboxWorkspaceId(_SemanticIdentity):
    pass


@dataclass(frozen=True, slots=True)
class SandboxTerminationProofId(_SemanticIdentity):
    pass


@dataclass(frozen=True, slots=True)
class SandboxSupervisionResultId(_SemanticIdentity):
    pass


@dataclass(frozen=True, slots=True)
class SandboxTimeoutPolicyId(_SemanticIdentity):
    pass


@dataclass(frozen=True, slots=True)
class SandboxDeadlineSetId(_SemanticIdentity):
    pass


@dataclass(frozen=True, slots=True)
class SandboxCancellationDecisionId(_SemanticIdentity):
    pass


@dataclass(frozen=True, slots=True)
class SandboxCancellationResultId(_SemanticIdentity):
    pass


@dataclass(frozen=True, slots=True)
class SandboxExecutionResultId(_SemanticIdentity):
    pass


@dataclass(frozen=True, slots=True)
class SandboxEvidencePolicyId(_SemanticIdentity):
    pass


@dataclass(frozen=True, slots=True)
class SandboxEvidenceProjectionId(_SemanticIdentity):
    pass


@dataclass(frozen=True, slots=True)
class SandboxPlanId(_SemanticIdentity):
    pass


@dataclass(frozen=True, slots=True)
class SandboxAttemptId(_SemanticIdentity):
    pass


@dataclass(frozen=True, slots=True)
class SandboxEvidenceId(_SemanticIdentity):
    pass


@dataclass(frozen=True, slots=True)
class SandboxPolicyVersion(_SemanticIdentity):
    pass


@dataclass(frozen=True, slots=True)
class SandboxIsolationProfileId(_SemanticIdentity):
    pass


@dataclass(frozen=True, slots=True)
class _Fingerprint:
    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not _FINGERPRINT.fullmatch(self.value):
            raise InvalidSandboxIdentity("fingerprint must use sha256 lowercase hex")

    def canonical_value(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class SandboxArtifactFingerprint(_Fingerprint):
    @classmethod
    def from_content(cls, content: object) -> SandboxArtifactFingerprint:
        return cls(content_fingerprint(content))


@dataclass(frozen=True, slots=True)
class SandboxPlanFingerprint(_Fingerprint):
    @classmethod
    def from_content(cls, content: object) -> SandboxPlanFingerprint:
        return cls(content_fingerprint(content))


def derive_identity(
    identity_type: type[_SemanticIdentity], *semantic_inputs: object
) -> _SemanticIdentity:
    """Derive an identity from ordered semantic inputs, never occurrence metadata."""

    digest = content_fingerprint(semantic_inputs).removeprefix("sha256:")
    return identity_type(f"{identity_type.__name__.lower()}:{digest}")
