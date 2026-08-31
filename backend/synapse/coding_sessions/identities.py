"""Distinct deterministic identities for Coding Sessions artifacts."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import ClassVar, Self

from .canonical import content_fingerprint
from .errors import InvalidCodingSessionIdentity

_STABLE_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,191}$")
_FINGERPRINT = re.compile(r"^sha256:[0-9a-f]{64}$")


def _valid_stable_key(value: str) -> bool:
    return (
        isinstance(value, str)
        and bool(_STABLE_KEY.fullmatch(value))
        and not value.startswith(("/", "\\"))
        and "\\" not in value
        and ".." not in value.split("/")
    )


@dataclass(frozen=True, slots=True)
class CodingSessionFingerprint:
    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not _FINGERPRINT.fullmatch(self.value):
            raise InvalidCodingSessionIdentity()

    @classmethod
    def from_content(cls, content: object) -> CodingSessionFingerprint:
        return cls(content_fingerprint(content))

    def canonical_value(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class _SemanticIdentity:
    value: str
    prefix: ClassVar[str]
    identity_version: ClassVar[str]

    def __post_init__(self) -> None:
        pattern = rf"^{re.escape(self.prefix)}:[0-9a-f]{{64}}$"
        if not isinstance(self.value, str) or not re.fullmatch(pattern, self.value):
            raise InvalidCodingSessionIdentity()

    @classmethod
    def from_stable_key(cls, stable_key: str) -> Self:
        if not _valid_stable_key(stable_key):
            raise InvalidCodingSessionIdentity()
        digest = content_fingerprint((cls.identity_version, stable_key)).removeprefix("sha256:")
        return cls(f"{cls.prefix}:{digest}")

    def canonical_value(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class CodingSessionIdentity(_SemanticIdentity):
    prefix = "coding-session"
    identity_version = "coding-session-identity-v1"


@dataclass(frozen=True, slots=True)
class CodingSessionFactIdentity(_SemanticIdentity):
    prefix = "coding-session-fact"
    identity_version = "coding-session-fact-identity-v1"


@dataclass(frozen=True, slots=True)
class CodingSessionCheckpointIdentity(_SemanticIdentity):
    prefix = "coding-session-checkpoint"
    identity_version = "coding-session-checkpoint-identity-v1"


@dataclass(frozen=True, slots=True)
class CodingSessionIntentIdentity(_SemanticIdentity):
    prefix = "coding-session-intent"
    identity_version = "coding-session-intent-identity-v1"


@dataclass(frozen=True, slots=True)
class CodingSessionExternalReceiptIdentity(_SemanticIdentity):
    prefix = "coding-session-receipt"
    identity_version = "coding-session-receipt-identity-v1"


@dataclass(frozen=True, slots=True)
class CodingSessionLeaseFactIdentity(_SemanticIdentity):
    prefix = "coding-session-lease-fact"
    identity_version = "coding-session-lease-fact-identity-v1"


@dataclass(frozen=True, slots=True)
class CodingSessionRecoveryArtifactIdentity(_SemanticIdentity):
    prefix = "coding-session-recovery"
    identity_version = "coding-session-recovery-identity-v1"


@dataclass(frozen=True, slots=True)
class CodingSessionPersistenceRecordIdentity(_SemanticIdentity):
    prefix = "coding-session-record"
    identity_version = "coding-session-record-identity-v1"
