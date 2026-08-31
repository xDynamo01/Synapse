"""Opaque Search identities and references with canonical representations."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import ClassVar

_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,254}$")
_IDENTITY = re.compile(
    r"^search-(request|invocation|result|result-set|retrieval-request|retrieval-attempt|"
    r"artifact|extraction-request|extraction-attempt|extracted-content):"
    r"[A-Za-z0-9][A-Za-z0-9._:@-]{0,190}$"
)
_FINGERPRINT = re.compile(r"^sha256:[0-9a-f]{64}$")


class InvalidSearchIdentity(ValueError):
    pass


def _validate_token(value: str, kind: str) -> None:
    if not isinstance(value, str) or not _TOKEN.fullmatch(value):
        raise InvalidSearchIdentity(f"{kind} must be bounded printable ASCII")
    if value.startswith(("/", "\\")) or "\\" in value or ".." in value.split("/"):
        raise InvalidSearchIdentity(f"{kind} cannot contain an absolute or traversing path")
    if "://" in value:
        raise InvalidSearchIdentity(f"{kind} cannot use a raw URL as identity")


@dataclass(frozen=True, slots=True, order=True)
class _OpaqueReference:
    value: str
    kind: ClassVar[str] = "reference"

    def __post_init__(self) -> None:
        _validate_token(self.value, self.kind)

    def canonical_value(self) -> str:
        return self.value

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True, order=True)
class RequesterReference(_OpaqueReference):
    kind = "requester reference"


@dataclass(frozen=True, slots=True, order=True)
class PolicyReference(_OpaqueReference):
    kind = "policy reference"


@dataclass(frozen=True, slots=True, order=True)
class CorrelationReference(_OpaqueReference):
    kind = "correlation reference"


@dataclass(frozen=True, slots=True, order=True)
class CausationReference(_OpaqueReference):
    kind = "causation reference"


@dataclass(frozen=True, slots=True, order=True)
class SearchCapabilityReference(_OpaqueReference):
    kind = "capability reference"


@dataclass(frozen=True, slots=True, order=True)
class SearchDetailReference(_OpaqueReference):
    kind = "detail reference"


@dataclass(frozen=True, slots=True, order=True)
class SearchProviderReference(_OpaqueReference):
    kind = "provider reference"


@dataclass(frozen=True, slots=True, order=True)
class SearchSourceReference(_OpaqueReference):
    kind = "source reference"


@dataclass(frozen=True, slots=True, order=True)
class ProviderResultReference(_OpaqueReference):
    kind = "provider result reference"


@dataclass(frozen=True, slots=True, order=True)
class RetrievedContentReference(_OpaqueReference):
    kind = "retrieved content reference"


@dataclass(frozen=True, slots=True, order=True)
class ExtractedTextReference(_OpaqueReference):
    kind = "extracted text reference"


@dataclass(frozen=True, slots=True, order=True)
class AgentSummaryReference(_OpaqueReference):
    kind = "agent summary reference"


@dataclass(frozen=True, slots=True, order=True)
class ArtifactContentReference(_OpaqueReference):
    kind = "artifact content reference"


@dataclass(frozen=True, slots=True, order=True)
class ExtractedContentReference(_OpaqueReference):
    kind = "extracted content reference"


@dataclass(frozen=True, slots=True, order=True)
class RetrievalTransportReference(_OpaqueReference):
    kind = "retrieval transport reference"


@dataclass(frozen=True, slots=True, order=True)
class ExtractorReference(_OpaqueReference):
    kind = "extractor reference"


@dataclass(frozen=True, slots=True, order=True)
class CacheNamespaceReference(_OpaqueReference):
    kind = "cache namespace reference"


@dataclass(frozen=True, slots=True, order=True)
class CachePolicyReference(_OpaqueReference):
    kind = "cache policy reference"


@dataclass(frozen=True, slots=True, order=True)
class CachedObservationVersion(_OpaqueReference):
    kind = "cached observation version"


@dataclass(frozen=True, slots=True, order=True)
class CacheValidatorReference(_OpaqueReference):
    kind = "cache validator reference"


@dataclass(frozen=True, slots=True, order=True)
class CacheEntryId(_OpaqueReference):
    """Opaque cache-entry identity, never a timestamp, URL or filesystem path."""

    kind = "cache entry identity"


@dataclass(frozen=True, slots=True, order=True)
class _SearchIdentity:
    value: str
    prefix: ClassVar[str] = ""

    def __post_init__(self) -> None:
        if (
            not isinstance(self.value, str)
            or not _IDENTITY.fullmatch(self.value)
            or not self.value.startswith(f"{self.prefix}:")
        ):
            raise InvalidSearchIdentity("search identity has an invalid canonical form")

    def canonical_value(self) -> str:
        return self.value

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True, order=True)
class SearchRequestId(_SearchIdentity):
    prefix = "search-request"


@dataclass(frozen=True, slots=True, order=True)
class SearchInvocationId(_SearchIdentity):
    """Reserved for a future provider invocation; not part of SearchRequestV1."""

    prefix = "search-invocation"


@dataclass(frozen=True, slots=True, order=True)
class SearchResultId(_SearchIdentity):
    prefix = "search-result"


@dataclass(frozen=True, slots=True, order=True)
class SearchResultSetId(_SearchIdentity):
    prefix = "search-result-set"


@dataclass(frozen=True, slots=True, order=True)
class RetrievalRequestId(_SearchIdentity):
    prefix = "search-retrieval-request"


@dataclass(frozen=True, slots=True, order=True)
class RetrievalAttemptId(_SearchIdentity):
    prefix = "search-retrieval-attempt"


@dataclass(frozen=True, slots=True, order=True)
class RetrievedArtifactId(_SearchIdentity):
    prefix = "search-artifact"


@dataclass(frozen=True, slots=True, order=True)
class ExtractionRequestId(_SearchIdentity):
    prefix = "search-extraction-request"


@dataclass(frozen=True, slots=True, order=True)
class ExtractionAttemptId(_SearchIdentity):
    prefix = "search-extraction-attempt"


@dataclass(frozen=True, slots=True, order=True)
class ExtractedContentId(_SearchIdentity):
    prefix = "search-extracted-content"


@dataclass(frozen=True, slots=True, order=True)
class SearchFingerprint:
    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not _FINGERPRINT.fullmatch(self.value):
            raise InvalidSearchIdentity("fingerprint must use sha256 lowercase hex")

    def canonical_value(self) -> str:
        return self.value

    def __str__(self) -> str:
        return self.value
