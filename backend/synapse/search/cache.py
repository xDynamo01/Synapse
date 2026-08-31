"""Pure cache contracts and deterministic compatibility assessments; no storage I/O."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Protocol, runtime_checkable

from .canonical import SEARCH_CANONICAL_FORMAT_V1, canonical_json, semantic_fingerprint
from .errors import SearchOutcomeCode, SearchValidationError
from .identities import (
    CachedObservationVersion,
    CacheEntryId,
    CacheNamespaceReference,
    CachePolicyReference,
    CacheValidatorReference,
    ExtractorReference,
    SearchFingerprint,
    SearchProviderReference,
)
from .models import SearchRequestV1
from .results import SearchResultSetV1
from .retrieval import (
    ArtifactChecksum,
    ExtractedContentV1,
    ExtractionRequestV1,
    RetrievalRequestV1,
    RetrievedArtifactV1,
)

CACHE_POLICY_FORMAT_V1 = "search-cache-policy-v1"
CACHE_KEY_FORMAT_V1 = "search-cache-key-v1"
CACHE_ENTRY_FORMAT_V1 = "search-cache-entry-v1"
CACHE_ASSESSMENT_FORMAT_V1 = "search-cache-assessment-v1"
MAX_CACHE_TTL_SECONDS = 2_592_000


def _utc(value: datetime, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise SearchValidationError(f"{label} must be timezone-aware")
    return value.astimezone(UTC)


class CacheNamespace(StrEnum):
    SEARCH = "search"
    RETRIEVAL = "retrieval"
    EXTRACTION = "extraction"


SEARCH_CACHE_NAMESPACE = CacheNamespaceReference("cache-namespace:search")
RETRIEVAL_CACHE_NAMESPACE = CacheNamespaceReference("cache-namespace:retrieval")
EXTRACTION_CACHE_NAMESPACE = CacheNamespaceReference("cache-namespace:extraction")


class CacheReadStatus(StrEnum):
    HIT_FRESH = "hit_fresh"
    HIT_STALE = "hit_stale"
    MISS = "miss"
    INVALID = "invalid"
    UNAVAILABLE = "unavailable"


class StaleUsagePolicy(StrEnum):
    FRESH_ONLY = "fresh_only"
    STALE_ALLOWED = "stale_allowed"
    STALE_IF_ERROR_FUTURE = "stale_if_error_future"
    REVALIDATE_REQUIRED = "revalidate_required"


class PayloadCustody(StrEnum):
    METADATA_ONLY = "metadata_only"
    TRANSIENT_REFERENCE = "transient_reference"
    CACHEABLE_CONTENT_REFERENCE = "cacheable_content_reference"
    EXPLICIT_PERSISTENCE_FUTURE = "explicit_persistence_future"


class CacheRecordRepetition(StrEnum):
    FIRST = "first"
    IDENTICAL = "identical"
    CONTRADICTORY = "contradictory"


@dataclass(frozen=True, slots=True)
class CacheTTLPolicy:
    seconds: int

    def __post_init__(self) -> None:
        if (
            isinstance(self.seconds, bool)
            or not isinstance(self.seconds, int)
            or not 1 <= self.seconds <= MAX_CACHE_TTL_SECONDS
        ):
            raise SearchValidationError("cache TTL must be finite and within bounds")


@dataclass(frozen=True, slots=True)
class SearchCachePolicyV1:
    policy_reference: CachePolicyReference
    search_ttl: CacheTTLPolicy
    retrieval_ttl: CacheTTLPolicy
    extraction_ttl: CacheTTLPolicy
    search_stale_usage: StaleUsagePolicy = StaleUsagePolicy.FRESH_ONLY
    retrieval_stale_usage: StaleUsagePolicy = StaleUsagePolicy.FRESH_ONLY
    extraction_stale_usage: StaleUsagePolicy = StaleUsagePolicy.FRESH_ONLY
    cache_no_results: bool = False
    format_version: str = CACHE_POLICY_FORMAT_V1

    def __post_init__(self) -> None:
        if self.format_version != CACHE_POLICY_FORMAT_V1:
            raise SearchValidationError("unsupported cache policy version")

    def ttl_for(self, namespace: CacheNamespace) -> CacheTTLPolicy:
        return {
            CacheNamespace.SEARCH: self.search_ttl,
            CacheNamespace.RETRIEVAL: self.retrieval_ttl,
            CacheNamespace.EXTRACTION: self.extraction_ttl,
        }[namespace]

    def stale_usage_for(self, namespace: CacheNamespace) -> StaleUsagePolicy:
        return {
            CacheNamespace.SEARCH: self.search_stale_usage,
            CacheNamespace.RETRIEVAL: self.retrieval_stale_usage,
            CacheNamespace.EXTRACTION: self.extraction_stale_usage,
        }[namespace]

    def semantic_content(self) -> dict[str, object]:
        return {
            "format": self.format_version,
            "policy_reference": self.policy_reference,
            "search_ttl": self.search_ttl,
            "retrieval_ttl": self.retrieval_ttl,
            "extraction_ttl": self.extraction_ttl,
            "search_stale_usage": self.search_stale_usage,
            "retrieval_stale_usage": self.retrieval_stale_usage,
            "extraction_stale_usage": self.extraction_stale_usage,
            "cache_no_results": self.cache_no_results,
        }

    @property
    def semantic_fingerprint(self) -> SearchFingerprint:
        return semantic_fingerprint(self.semantic_content())

    def canonical_serialization(self) -> str:
        return canonical_json({"canonical_format": SEARCH_CANONICAL_FORMAT_V1, "cache_policy": self, "semantic_fingerprint": self.semantic_fingerprint})


@dataclass(frozen=True, slots=True)
class CacheSemanticKeyV1:
    namespace: CacheNamespace
    namespace_reference: CacheNamespaceReference
    fingerprint: SearchFingerprint
    provider: SearchProviderReference | None = None
    format_version: str = CACHE_KEY_FORMAT_V1

    def __post_init__(self) -> None:
        expected = {
            CacheNamespace.SEARCH: SEARCH_CACHE_NAMESPACE,
            CacheNamespace.RETRIEVAL: RETRIEVAL_CACHE_NAMESPACE,
            CacheNamespace.EXTRACTION: EXTRACTION_CACHE_NAMESPACE,
        }[self.namespace]
        if self.namespace_reference != expected:
            raise SearchValidationError("cache key namespace correspondence mismatch")
        if self.namespace is CacheNamespace.SEARCH and self.provider is None:
            raise SearchValidationError("Search cache key requires provider scope")
        if self.namespace is not CacheNamespace.SEARCH and self.provider is not None:
            raise SearchValidationError("only Search cache keys carry provider scope")
        if self.format_version != CACHE_KEY_FORMAT_V1:
            raise SearchValidationError("unsupported cache key version")

    def semantic_content(self) -> dict[str, object]:
        return {"format": self.format_version, "namespace": self.namespace, "namespace_reference": self.namespace_reference, "fingerprint": self.fingerprint, "provider": self.provider}

    def canonical_serialization(self) -> str:
        return canonical_json({"canonical_format": SEARCH_CANONICAL_FORMAT_V1, "cache_key": self})


def search_cache_key(
    request: SearchRequestV1, provider: SearchProviderReference
) -> CacheSemanticKeyV1:
    fingerprint = semantic_fingerprint(
        {"namespace": CacheNamespace.SEARCH, "request": request.semantic_content(), "provider": provider}
    )
    return CacheSemanticKeyV1(CacheNamespace.SEARCH, SEARCH_CACHE_NAMESPACE, fingerprint, provider)


def retrieval_cache_key(request: RetrievalRequestV1) -> CacheSemanticKeyV1:
    fingerprint = semantic_fingerprint(
        {"namespace": CacheNamespace.RETRIEVAL, "request": request.semantic_content()}
    )
    return CacheSemanticKeyV1(CacheNamespace.RETRIEVAL, RETRIEVAL_CACHE_NAMESPACE, fingerprint)


def extraction_cache_key(
    artifact: RetrievedArtifactV1,
    request: ExtractionRequestV1,
    extractor: ExtractorReference,
    extractor_version: str,
    output_policy_fingerprint: SearchFingerprint,
) -> CacheSemanticKeyV1:
    if request.artifact_id != artifact.artifact_id or artifact.checksum is None:
        raise SearchValidationError("extraction cache key requires corresponding artifact checksum")
    fingerprint = semantic_fingerprint(
        {
            "namespace": CacheNamespace.EXTRACTION,
            "artifact_id": artifact.artifact_id,
            "artifact_checksum": artifact.checksum,
            "capability": request.capability,
            "extractor": extractor,
            "extractor_version": extractor_version,
            "output_policy_fingerprint": output_policy_fingerprint,
        }
    )
    return CacheSemanticKeyV1(CacheNamespace.EXTRACTION, EXTRACTION_CACHE_NAMESPACE, fingerprint)


def cached_observation_version(
    fingerprint: SearchFingerprint,
) -> CachedObservationVersion:
    return CachedObservationVersion(
        "observation-version:sha256-" + fingerprint.value.removeprefix("sha256:")
    )


@dataclass(frozen=True, slots=True)
class SearchCacheEntryV1:
    entry_id: CacheEntryId
    key: CacheSemanticKeyV1
    result_set: SearchResultSetV1
    policy_reference: CachePolicyReference
    policy_fingerprint: SearchFingerprint
    cached_observation_version: CachedObservationVersion
    written_at: datetime
    expires_at: datetime
    payload_custody: PayloadCustody = PayloadCustody.METADATA_ONLY
    format_version: str = CACHE_ENTRY_FORMAT_V1

    def __post_init__(self) -> None:
        written = _utc(self.written_at, "cache write occurrence")
        expires = _utc(self.expires_at, "cache expiry")
        if self.key.namespace is not CacheNamespace.SEARCH or self.key.provider != self.result_set.provider:
            raise SearchValidationError("Search cache entry correspondence mismatch")
        if self.result_set.semantic_fingerprint != self.cached_observation_version_fingerprint:
            raise SearchValidationError("Search cached observation version mismatch")
        if expires <= written or self.payload_custody is not PayloadCustody.METADATA_ONLY:
            raise SearchValidationError("Search cache entry expiry or payload custody is invalid")
        if self.format_version != CACHE_ENTRY_FORMAT_V1:
            raise SearchValidationError("unsupported Search cache entry version")
        object.__setattr__(self, "written_at", written)
        object.__setattr__(self, "expires_at", expires)

    @property
    def cached_observation_version_fingerprint(self) -> SearchFingerprint:
        value = self.cached_observation_version.value
        if not value.startswith("observation-version:sha256-"):
            raise SearchValidationError("cached observation version must bind a fingerprint")
        return SearchFingerprint("sha256:" + value.removeprefix("observation-version:sha256-"))

    def semantic_content(self) -> dict[str, object]:
        return {"format": self.format_version, "key": self.key, "result_set": self.result_set.semantic_fingerprint, "policy_reference": self.policy_reference, "policy_fingerprint": self.policy_fingerprint, "cached_observation_version": self.cached_observation_version, "written_at": self.written_at, "expires_at": self.expires_at, "payload_custody": self.payload_custody}

    @property
    def semantic_fingerprint(self) -> SearchFingerprint:
        return semantic_fingerprint(self.semantic_content())

    def canonical_serialization(self) -> str:
        return canonical_json({"canonical_format": SEARCH_CANONICAL_FORMAT_V1, "search_cache_entry": self, "semantic_fingerprint": self.semantic_fingerprint})


@dataclass(frozen=True, slots=True)
class RetrievalCacheEntryV1:
    entry_id: CacheEntryId
    key: CacheSemanticKeyV1
    artifact: RetrievedArtifactV1
    policy_reference: CachePolicyReference
    policy_fingerprint: SearchFingerprint
    cached_observation_version: CachedObservationVersion
    written_at: datetime
    expires_at: datetime
    payload_custody: PayloadCustody
    validator_references: tuple[CacheValidatorReference, ...] = ()
    format_version: str = CACHE_ENTRY_FORMAT_V1

    def __post_init__(self) -> None:
        written = _utc(self.written_at, "cache write occurrence")
        expires = _utc(self.expires_at, "cache expiry")
        if self.key.namespace is not CacheNamespace.RETRIEVAL or expires <= written:
            raise SearchValidationError("Retrieval cache entry namespace or expiry is invalid")
        if self.artifact.checksum is None or self.artifact.content_reference is None:
            raise SearchValidationError("Retrieval cache entry requires retrieved payload facts")
        if self.cached_observation_version != cached_observation_version(
            self.artifact.semantic_fingerprint
        ):
            raise SearchValidationError("Retrieval cached observation version mismatch")
        if self.payload_custody is PayloadCustody.EXPLICIT_PERSISTENCE_FUTURE:
            raise SearchValidationError("explicit content persistence is not implemented")
        if len(set(self.validator_references)) != len(self.validator_references):
            raise SearchValidationError("cache validator references must be unique")
        if self.format_version != CACHE_ENTRY_FORMAT_V1:
            raise SearchValidationError("unsupported Retrieval cache entry version")
        object.__setattr__(self, "written_at", written)
        object.__setattr__(self, "expires_at", expires)

    def semantic_content(self) -> dict[str, object]:
        return {"format": self.format_version, "key": self.key, "artifact": self.artifact.semantic_fingerprint, "policy_reference": self.policy_reference, "policy_fingerprint": self.policy_fingerprint, "cached_observation_version": self.cached_observation_version, "written_at": self.written_at, "expires_at": self.expires_at, "payload_custody": self.payload_custody, "validator_references": self.validator_references}

    @property
    def semantic_fingerprint(self) -> SearchFingerprint:
        return semantic_fingerprint(self.semantic_content())


@dataclass(frozen=True, slots=True)
class ExtractionCacheEntryV1:
    entry_id: CacheEntryId
    key: CacheSemanticKeyV1
    extracted_content: ExtractedContentV1
    artifact_checksum: ArtifactChecksum
    policy_reference: CachePolicyReference
    policy_fingerprint: SearchFingerprint
    cached_observation_version: CachedObservationVersion
    written_at: datetime
    expires_at: datetime
    payload_custody: PayloadCustody
    format_version: str = CACHE_ENTRY_FORMAT_V1

    def __post_init__(self) -> None:
        written = _utc(self.written_at, "cache write occurrence")
        expires = _utc(self.expires_at, "cache expiry")
        if self.key.namespace is not CacheNamespace.EXTRACTION or expires <= written:
            raise SearchValidationError("Extraction cache entry namespace or expiry is invalid")
        if self.extracted_content.content_checksum is None or self.extracted_content.content_reference is None:
            raise SearchValidationError("Extraction cache entry requires extracted content facts")
        if self.cached_observation_version != cached_observation_version(
            self.extracted_content.semantic_fingerprint
        ):
            raise SearchValidationError("Extraction cached observation version mismatch")
        if self.payload_custody is PayloadCustody.EXPLICIT_PERSISTENCE_FUTURE:
            raise SearchValidationError("explicit content persistence is not implemented")
        if self.format_version != CACHE_ENTRY_FORMAT_V1:
            raise SearchValidationError("unsupported Extraction cache entry version")
        object.__setattr__(self, "written_at", written)
        object.__setattr__(self, "expires_at", expires)

    def semantic_content(self) -> dict[str, object]:
        return {"format": self.format_version, "key": self.key, "extracted_content": self.extracted_content.semantic_fingerprint, "artifact_checksum": self.artifact_checksum, "policy_reference": self.policy_reference, "policy_fingerprint": self.policy_fingerprint, "cached_observation_version": self.cached_observation_version, "written_at": self.written_at, "expires_at": self.expires_at, "payload_custody": self.payload_custody}

    @property
    def semantic_fingerprint(self) -> SearchFingerprint:
        return semantic_fingerprint(self.semantic_content())


CacheEntry = SearchCacheEntryV1 | RetrievalCacheEntryV1 | ExtractionCacheEntryV1


@dataclass(frozen=True, slots=True)
class CacheReadAssessmentV1:
    namespace: CacheNamespace
    status: CacheReadStatus
    read_at: datetime
    original_observation_at: datetime | None
    cache_written_at: datetime | None
    age_seconds: int | None
    usable: bool
    revalidation_required: bool
    revalidation_possible: bool
    reasons: tuple[str, ...] = ()
    entry_id: CacheEntryId | None = None
    format_version: str = CACHE_ASSESSMENT_FORMAT_V1

    def __post_init__(self) -> None:
        read_at = _utc(self.read_at, "cache read occurrence")
        original = _utc(self.original_observation_at, "original observation") if self.original_observation_at else None
        written = _utc(self.cache_written_at, "cache write occurrence") if self.cache_written_at else None
        if written is None:
            if self.age_seconds is not None or original is not None:
                raise SearchValidationError("cache miss/unavailable cannot claim entry age")
        elif self.age_seconds != max(0, int((read_at - written).total_seconds())):
            raise SearchValidationError("cache age does not correspond to supplied occurrences")
        if self.status is CacheReadStatus.HIT_FRESH and (not self.usable or self.revalidation_required):
            raise SearchValidationError("fresh cache hit must be usable without revalidation")
        if self.status in {CacheReadStatus.MISS, CacheReadStatus.INVALID, CacheReadStatus.UNAVAILABLE} and self.usable:
            raise SearchValidationError("non-hit cache assessment cannot be usable")
        if self.format_version != CACHE_ASSESSMENT_FORMAT_V1:
            raise SearchValidationError("unsupported cache assessment version")
        object.__setattr__(self, "read_at", read_at)
        object.__setattr__(self, "original_observation_at", original)
        object.__setattr__(self, "cache_written_at", written)
        object.__setattr__(self, "reasons", tuple(sorted(set(self.reasons))))

    def semantic_content(self) -> dict[str, object]:
        return {"format": self.format_version, "namespace": self.namespace, "status": self.status, "usable": self.usable, "revalidation_required": self.revalidation_required, "revalidation_possible": self.revalidation_possible, "reasons": self.reasons, "entry_id": self.entry_id}

    @property
    def semantic_fingerprint(self) -> SearchFingerprint:
        return semantic_fingerprint(self.semantic_content())

    def canonical_serialization(self) -> str:
        return canonical_json({"canonical_format": SEARCH_CANONICAL_FORMAT_V1, "cache_assessment": self, "semantic_fingerprint": self.semantic_fingerprint})


def _assessment(
    namespace: CacheNamespace,
    entry: CacheEntry | None,
    read_at: datetime,
    policy: SearchCachePolicyV1,
    *,
    backend_available: bool,
    compatible: bool,
    reference_available: bool,
    original_observation_at: datetime | None,
    reasons: tuple[str, ...] = (),
    revalidation_possible: bool = False,
) -> CacheReadAssessmentV1:
    read = _utc(read_at, "cache read occurrence")
    if not backend_available:
        return CacheReadAssessmentV1(namespace, CacheReadStatus.UNAVAILABLE, read, None, None, None, False, False, False, ("cache-backend-unavailable",))
    if entry is None:
        return CacheReadAssessmentV1(namespace, CacheReadStatus.MISS, read, None, None, None, False, False, False)
    age = max(0, int((read - entry.written_at).total_seconds()))
    expected_expiry = entry.written_at + timedelta(seconds=policy.ttl_for(namespace).seconds)
    validity_reasons = list(reasons)
    if entry.policy_reference != policy.policy_reference or entry.policy_fingerprint != policy.semantic_fingerprint:
        validity_reasons.append("cache-policy-mismatch")
    if entry.expires_at != expected_expiry:
        validity_reasons.append("cache-ttl-version-mismatch")
    if entry.format_version != CACHE_ENTRY_FORMAT_V1:
        validity_reasons.append("cache-schema-version-mismatch")
    if not compatible:
        validity_reasons.append("cache-semantic-key-incompatible")
    if not reference_available:
        validity_reasons.append("cache-content-reference-unavailable")
    if validity_reasons:
        return CacheReadAssessmentV1(namespace, CacheReadStatus.INVALID, read, original_observation_at, entry.written_at, age, False, True, revalidation_possible, tuple(validity_reasons), entry_id=entry.entry_id)
    if read < entry.expires_at:
        return CacheReadAssessmentV1(namespace, CacheReadStatus.HIT_FRESH, read, original_observation_at, entry.written_at, age, True, False, revalidation_possible, entry_id=entry.entry_id)
    stale_policy = policy.stale_usage_for(namespace)
    usable = stale_policy is StaleUsagePolicy.STALE_ALLOWED
    return CacheReadAssessmentV1(namespace, CacheReadStatus.HIT_STALE, read, original_observation_at, entry.written_at, age, usable, not usable, revalidation_possible, ("cache-ttl-expired",), entry_id=entry.entry_id)


def assess_search_cache(
    entry: SearchCacheEntryV1 | None,
    request: SearchRequestV1,
    provider: SearchProviderReference,
    policy: SearchCachePolicyV1,
    read_at: datetime,
    *,
    backend_available: bool = True,
) -> CacheReadAssessmentV1:
    expected = search_cache_key(request, provider)
    original = entry.result_set.search_occurrence.occurred_at if entry else None
    negative_allowed = entry is None or entry.result_set.outcome is not SearchOutcomeCode.NO_RESULTS or policy.cache_no_results
    return _assessment(CacheNamespace.SEARCH, entry, read_at, policy, backend_available=backend_available, compatible=entry is None or (entry.key == expected and negative_allowed), reference_available=True, original_observation_at=original, reasons=() if negative_allowed else ("negative-search-cache-not-admitted",))


def assess_retrieval_cache(
    entry: RetrievalCacheEntryV1 | None,
    request: RetrievalRequestV1,
    policy: SearchCachePolicyV1,
    read_at: datetime,
    *,
    reference_available: bool,
    backend_available: bool = True,
) -> CacheReadAssessmentV1:
    expected = retrieval_cache_key(request)
    original = entry.artifact.retrieval_occurrence.occurred_at if entry else None
    return _assessment(CacheNamespace.RETRIEVAL, entry, read_at, policy, backend_available=backend_available, compatible=entry is None or entry.key == expected, reference_available=reference_available, original_observation_at=original, revalidation_possible=bool(entry and entry.validator_references))


def assess_extraction_cache(
    entry: ExtractionCacheEntryV1 | None,
    expected_key: CacheSemanticKeyV1,
    artifact_checksum: ArtifactChecksum,
    policy: SearchCachePolicyV1,
    read_at: datetime,
    *,
    reference_available: bool,
    backend_available: bool = True,
) -> CacheReadAssessmentV1:
    original = entry.extracted_content.occurrence.occurred_at if entry else None
    checksum_matches = entry is None or entry.artifact_checksum == artifact_checksum
    return _assessment(CacheNamespace.EXTRACTION, entry, read_at, policy, backend_available=backend_available, compatible=entry is None or (entry.key == expected_key and checksum_matches), reference_available=reference_available, original_observation_at=original, reasons=() if checksum_matches else ("artifact-checksum-mismatch",))


def classify_cache_record_repetition(
    existing: CacheEntry | None, observed: CacheEntry
) -> CacheRecordRepetition:
    if existing is None:
        return CacheRecordRepetition.FIRST
    if type(existing) is not type(observed) or existing.entry_id != observed.entry_id:
        raise SearchValidationError("cache records have different identity or namespace")
    return CacheRecordRepetition.IDENTICAL if existing.semantic_fingerprint == observed.semantic_fingerprint else CacheRecordRepetition.CONTRADICTORY


@runtime_checkable
class SearchCachePort(Protocol):
    def lookup(self, key: CacheSemanticKeyV1) -> SearchCacheEntryV1 | None: ...
    def append(self, entry: SearchCacheEntryV1) -> CacheRecordRepetition: ...
    def record_assessment(self, assessment: CacheReadAssessmentV1) -> None: ...


@runtime_checkable
class RetrievalCachePort(Protocol):
    def lookup(self, key: CacheSemanticKeyV1) -> RetrievalCacheEntryV1 | None: ...
    def append(self, entry: RetrievalCacheEntryV1) -> CacheRecordRepetition: ...
    def record_assessment(self, assessment: CacheReadAssessmentV1) -> None: ...


@runtime_checkable
class ExtractionCachePort(Protocol):
    def lookup(self, key: CacheSemanticKeyV1) -> ExtractionCacheEntryV1 | None: ...
    def append(self, entry: ExtractionCacheEntryV1) -> CacheRecordRepetition: ...
    def record_assessment(self, assessment: CacheReadAssessmentV1) -> None: ...
