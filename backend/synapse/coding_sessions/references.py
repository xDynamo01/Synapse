"""Opaque references that carry no external authority or producer state."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import ClassVar, Self

from .errors import InvalidCodingSessionReference
from .identities import CodingSessionFingerprint

_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,191}$")


def _valid_token(value: str) -> bool:
    return (
        isinstance(value, str)
        and bool(_TOKEN.fullmatch(value))
        and not value.startswith(("/", "\\"))
        and "\\" not in value
        and ".." not in value.split("/")
    )


@dataclass(frozen=True, slots=True)
class _OpaqueReference:
    value: str

    def __post_init__(self) -> None:
        if not _valid_token(self.value):
            raise InvalidCodingSessionReference()

    def canonical_value(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class CodingSessionActorReference(_OpaqueReference):
    pass


@dataclass(frozen=True, slots=True)
class CodingSessionProjectReference(_OpaqueReference):
    pass


@dataclass(frozen=True, slots=True)
class CodingSessionTaskReference(_OpaqueReference):
    pass


@dataclass(frozen=True, slots=True)
class CodingSessionPurposeReference(_OpaqueReference):
    pass


@dataclass(frozen=True, slots=True)
class CodingSessionCorrelationReference(_OpaqueReference):
    pass


@dataclass(frozen=True, slots=True)
class _ExternalReference:
    producer: str
    artifact_type: str
    version: str
    identity: str
    fingerprint: CodingSessionFingerprint | None = None
    expected_type: ClassVar[str]

    def __post_init__(self) -> None:
        if (
            not all(
                _valid_token(value)
                for value in (self.producer, self.artifact_type, self.version, self.identity)
            )
            or self.artifact_type != self.expected_type
        ):
            raise InvalidCodingSessionReference()

    @classmethod
    def create(
        cls,
        producer: str,
        version: str,
        identity: str,
        fingerprint: CodingSessionFingerprint | None = None,
    ) -> Self:
        return cls(producer, cls.expected_type, version, identity, fingerprint)

    def canonical_value(self) -> object:
        return (
            self.producer,
            self.artifact_type,
            self.version,
            self.identity,
            self.fingerprint,
        )


@dataclass(frozen=True, slots=True)
class CodingSessionRepositoryReference(_ExternalReference):
    expected_type = "repository"


@dataclass(frozen=True, slots=True)
class CodingSessionCheckoutReference(_ExternalReference):
    expected_type = "checkout"


@dataclass(frozen=True, slots=True)
class CodingSessionWorktreeReference(_ExternalReference):
    expected_type = "worktree"


@dataclass(frozen=True, slots=True)
class CodingSessionPlatformContextReference(_ExternalReference):
    expected_type = "platform-context"


@dataclass(frozen=True, slots=True)
class CodingSessionWorkerAssignmentReference(_ExternalReference):
    expected_type = "worker-assignment"


@dataclass(frozen=True, slots=True)
class CodingSessionWorkerAttemptReference(_ExternalReference):
    expected_type = "worker-attempt"


@dataclass(frozen=True, slots=True)
class CodingSessionSandboxPlanReference(_ExternalReference):
    expected_type = "sandbox-plan"


@dataclass(frozen=True, slots=True)
class CodingSessionSandboxAttemptReference(_ExternalReference):
    expected_type = "sandbox-attempt"


@dataclass(frozen=True, slots=True)
class CodingSessionSandboxResultReference(_ExternalReference):
    expected_type = "sandbox-result"


@dataclass(frozen=True, slots=True)
class CodingSessionAuthorizationReference(_ExternalReference):
    expected_type = "authorization"


@dataclass(frozen=True, slots=True)
class CodingSessionApprovalReference(_ExternalReference):
    expected_type = "approval"


@dataclass(frozen=True, slots=True)
class CodingSessionPrivateEvalRunReference(_ExternalReference):
    expected_type = "private-eval-run"


@dataclass(frozen=True, slots=True)
class CodingSessionPrivateEvalResultReference(_ExternalReference):
    expected_type = "private-eval-result"


@dataclass(frozen=True, slots=True)
class CodingSessionPrivateEvalEvidenceReference(_ExternalReference):
    expected_type = "private-eval-evidence"


@dataclass(frozen=True, slots=True)
class CodingSessionArtifactReference(_ExternalReference):
    expected_type = "artifact"


@dataclass(frozen=True, slots=True)
class CodingSessionDeploymentCandidateReference(_ExternalReference):
    expected_type = "deployment-candidate"
