"""Minimal immutable causal metadata for future Coding Sessions artifacts."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .errors import InvalidCodingSessionCausalRevision, InvalidCodingSessionLineage
from .identities import (
    CodingSessionCheckpointIdentity,
    CodingSessionExternalReceiptIdentity,
    CodingSessionFactIdentity,
    CodingSessionFingerprint,
    CodingSessionIdentity,
    CodingSessionIntentIdentity,
    CodingSessionLeaseFactIdentity,
    CodingSessionRecoveryArtifactIdentity,
)

_OCCURRENCE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,127}$")

CodingSessionSemanticIdentity = (
    CodingSessionIdentity
    | CodingSessionFactIdentity
    | CodingSessionCheckpointIdentity
    | CodingSessionIntentIdentity
    | CodingSessionExternalReceiptIdentity
    | CodingSessionLeaseFactIdentity
    | CodingSessionRecoveryArtifactIdentity
)


@dataclass(frozen=True, slots=True, order=True)
class CodingSessionCausalRevision:
    value: int

    def __post_init__(self) -> None:
        if isinstance(self.value, bool) or not isinstance(self.value, int) or self.value < 1:
            raise InvalidCodingSessionCausalRevision()

    def canonical_value(self) -> int:
        return self.value


@dataclass(frozen=True, slots=True)
class CodingSessionLineage:
    parents: tuple[CodingSessionFingerprint, ...] = ()
    references: tuple[CodingSessionFingerprint, ...] = ()

    def __post_init__(self) -> None:
        if (
            len(set(self.parents)) != len(self.parents)
            or len(set(self.references)) != len(self.references)
            or set(self.parents) & set(self.references)
        ):
            raise InvalidCodingSessionLineage()
        object.__setattr__(self, "parents", tuple(sorted(self.parents, key=lambda item: item.value)))
        object.__setattr__(
            self, "references", tuple(sorted(self.references, key=lambda item: item.value))
        )


@dataclass(frozen=True, slots=True)
class CodingSessionCausalMetadata:
    semantic_identity: CodingSessionSemanticIdentity
    revision: CodingSessionCausalRevision
    lineage: CodingSessionLineage
    occurrence_metadata: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if any(
            not _OCCURRENCE.fullmatch(key) or not _OCCURRENCE.fullmatch(value)
            for key, value in self.occurrence_metadata
        ):
            raise InvalidCodingSessionLineage()
        object.__setattr__(
            self, "occurrence_metadata", tuple(sorted(set(self.occurrence_metadata)))
        )

    def semantic_content(self) -> object:
        return self.semantic_identity, self.revision, self.lineage

    @property
    def semantic_fingerprint(self) -> CodingSessionFingerprint:
        return CodingSessionFingerprint.from_content(self.semantic_content())
