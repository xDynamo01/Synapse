"""Pure durable-metadata record, replay and persistence port contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol, TypeAlias, runtime_checkable

from .cache import (
    CacheReadAssessmentV1,
    ExtractionCacheEntryV1,
    RetrievalCacheEntryV1,
    SearchCacheEntryV1,
)
from .canonical import SEARCH_CANONICAL_FORMAT_V1, canonical_json, semantic_fingerprint
from .errors import SearchError, SearchErrorCode, SearchValidationError
from .identities import PolicyReference, SearchFingerprint
from .models import SearchRequestV1
from .provider import SearchProviderInvocationV1, SearchProviderResultV1
from .results import NormalizedSearchResultV1, SearchResultSetV1
from .retrieval import (
    ExtractedContentV1,
    ExtractionRequestV1,
    RetrievalRequestV1,
    RetrievedArtifactV1,
)

SEARCH_PERSISTENCE_RECORD_FORMAT_V1 = "search-persistence-record-v1"
SEARCH_PERSISTENCE_SCHEMA_VERSION_V1 = 1


class SearchPersistenceError(SearchError):
    pass


class SearchPersistenceUnavailable(SearchPersistenceError):
    def __init__(self, message: str = "Search persistence is unavailable") -> None:
        super().__init__(SearchErrorCode.PERSISTENCE_UNAVAILABLE, message)


class SearchPersistenceConflict(SearchPersistenceError):
    def __init__(self, message: str = "Search persistence conflict") -> None:
        super().__init__(SearchErrorCode.PERSISTENCE_CONFLICT, message)


class SearchPersistenceCorrupt(SearchPersistenceError):
    def __init__(self, message: str = "Search persistence is corrupt") -> None:
        super().__init__(SearchErrorCode.PERSISTENCE_CORRUPT, message)


class SearchPersistenceVersionMismatch(SearchPersistenceError):
    def __init__(self, message: str = "Search persistence version mismatch") -> None:
        super().__init__(SearchErrorCode.PERSISTENCE_VERSION_MISMATCH, message)


class SearchPersistenceRecordNotFound(SearchPersistenceError):
    def __init__(self, message: str = "Search persistence record not found") -> None:
        super().__init__(SearchErrorCode.PERSISTENCE_RECORD_NOT_FOUND, message)


def _utc(value: datetime, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise SearchValidationError(f"{label} must be timezone-aware")
    return value.astimezone(UTC)


class SearchPersistedKind(StrEnum):
    SEARCH_REQUEST = "search_request"
    PROVIDER_INVOCATION = "provider_invocation"
    PROVIDER_RESULT = "provider_result"
    NORMALIZED_RESULT = "normalized_result"
    RESULT_SET = "result_set"
    RETRIEVAL_REQUEST = "retrieval_request"
    RETRIEVED_ARTIFACT = "retrieved_artifact"
    EXTRACTION_REQUEST = "extraction_request"
    EXTRACTED_CONTENT = "extracted_content"
    SEARCH_CACHE_ENTRY = "search_cache_entry"
    RETRIEVAL_CACHE_ENTRY = "retrieval_cache_entry"
    EXTRACTION_CACHE_ENTRY = "extraction_cache_entry"
    CACHE_ASSESSMENT = "cache_assessment"


PersistableSearchFact: TypeAlias = (
    SearchRequestV1
    | SearchProviderInvocationV1
    | SearchProviderResultV1
    | NormalizedSearchResultV1
    | SearchResultSetV1
    | RetrievalRequestV1
    | RetrievedArtifactV1
    | ExtractionRequestV1
    | ExtractedContentV1
    | SearchCacheEntryV1
    | RetrievalCacheEntryV1
    | ExtractionCacheEntryV1
    | CacheReadAssessmentV1
)


_KIND_TYPE: dict[SearchPersistedKind, type[object]] = {
    SearchPersistedKind.SEARCH_REQUEST: SearchRequestV1,
    SearchPersistedKind.PROVIDER_INVOCATION: SearchProviderInvocationV1,
    SearchPersistedKind.PROVIDER_RESULT: SearchProviderResultV1,
    SearchPersistedKind.NORMALIZED_RESULT: NormalizedSearchResultV1,
    SearchPersistedKind.RESULT_SET: SearchResultSetV1,
    SearchPersistedKind.RETRIEVAL_REQUEST: RetrievalRequestV1,
    SearchPersistedKind.RETRIEVED_ARTIFACT: RetrievedArtifactV1,
    SearchPersistedKind.EXTRACTION_REQUEST: ExtractionRequestV1,
    SearchPersistedKind.EXTRACTED_CONTENT: ExtractedContentV1,
    SearchPersistedKind.SEARCH_CACHE_ENTRY: SearchCacheEntryV1,
    SearchPersistedKind.RETRIEVAL_CACHE_ENTRY: RetrievalCacheEntryV1,
    SearchPersistedKind.EXTRACTION_CACHE_ENTRY: ExtractionCacheEntryV1,
    SearchPersistedKind.CACHE_ASSESSMENT: CacheReadAssessmentV1,
}


class SearchRecordCompleteness(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    UNKNOWN = "unknown"


class PersistedPayloadAvailability(StrEnum):
    NOT_APPLICABLE = "not_applicable"
    AVAILABLE_AT_WRITE = "available_at_write"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


class SearchWriteDisposition(StrEnum):
    APPENDED = "appended"
    IDEMPOTENT = "idempotent"


class SearchPersistenceHealthState(StrEnum):
    HEALTHY = "healthy"
    UNAVAILABLE = "unavailable"
    SCHEMA_MISMATCH = "schema_mismatch"
    MIGRATION_MISMATCH = "migration_mismatch"
    APPEND_ONLY_PROTECTION_MISSING = "append_only_protection_missing"
    INTEGRITY_FAILED = "integrity_failed"
    MALFORMED_RECORD = "malformed_record"


class RestartReferenceAvailability(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class SearchPersistenceDraft:
    record_id: str
    stream_id: str
    sequence: int
    expected_stream_version: int
    idempotency_key: str
    kind: SearchPersistedKind
    fact: PersistableSearchFact
    occurred_at: datetime
    observed_at: datetime
    policy_reference: PolicyReference
    lineage_fingerprints: tuple[SearchFingerprint, ...] = ()
    completeness: SearchRecordCompleteness = SearchRecordCompleteness.COMPLETE
    payload_availability: PersistedPayloadAvailability = PersistedPayloadAvailability.NOT_APPLICABLE

    def __post_init__(self) -> None:
        if not self.record_id or not self.stream_id or not self.idempotency_key:
            raise SearchValidationError("persistence draft identities are required")
        if self.sequence < 1 or self.expected_stream_version < 0:
            raise SearchValidationError("persistence sequence is invalid")
        if self.sequence != self.expected_stream_version + 1:
            raise SearchValidationError("persistence sequence must follow expected stream version")
        if not isinstance(self.fact, _KIND_TYPE[self.kind]):
            raise SearchValidationError("persisted kind does not correspond to factual contract")
        if len(set(self.lineage_fingerprints)) != len(self.lineage_fingerprints):
            raise SearchValidationError("persistence lineage must be unique")
        object.__setattr__(self, "occurred_at", _utc(self.occurred_at, "fact occurrence"))
        object.__setattr__(self, "observed_at", _utc(self.observed_at, "persistence observation"))

    def semantic_content(self) -> dict[str, object]:
        return {
            "record_format": SEARCH_PERSISTENCE_RECORD_FORMAT_V1,
            "kind": self.kind,
            "stream_id": self.stream_id,
            "sequence": self.sequence,
            "fact": self.fact,
            "occurred_at": self.occurred_at,
            "policy_reference": self.policy_reference,
            "lineage_fingerprints": self.lineage_fingerprints,
            "completeness": self.completeness,
            "payload_availability": self.payload_availability,
        }

    @property
    def factual_fingerprint(self) -> SearchFingerprint:
        return semantic_fingerprint(self.semantic_content())

    def canonical_serialization(self) -> str:
        return canonical_json(
            {
                "canonical_format": SEARCH_CANONICAL_FORMAT_V1,
                "persistence_draft": self,
                "factual_fingerprint": self.factual_fingerprint,
            }
        )


@dataclass(frozen=True, slots=True)
class SearchPersistedRecord:
    record_id: str
    stream_id: str
    sequence: int
    idempotency_key: str
    kind: SearchPersistedKind
    fact: PersistableSearchFact
    factual_fingerprint: SearchFingerprint
    canonical_payload: str
    payload_checksum: SearchFingerprint
    occurred_at: datetime
    observed_at: datetime
    policy_reference: PolicyReference
    lineage_fingerprints: tuple[SearchFingerprint, ...]
    missing_lineage_fingerprints: tuple[SearchFingerprint, ...]
    completeness: SearchRecordCompleteness
    payload_availability: PersistedPayloadAvailability
    format_version: str = SEARCH_PERSISTENCE_RECORD_FORMAT_V1
    schema_version: int = SEARCH_PERSISTENCE_SCHEMA_VERSION_V1

    def __post_init__(self) -> None:
        if not isinstance(self.fact, _KIND_TYPE[self.kind]):
            raise SearchValidationError("persisted record kind mismatch")
        if self.format_version != SEARCH_PERSISTENCE_RECORD_FORMAT_V1:
            raise SearchValidationError("unsupported Search persistence record format")
        if self.schema_version != SEARCH_PERSISTENCE_SCHEMA_VERSION_V1:
            raise SearchValidationError("unsupported Search persistence schema")


@dataclass(frozen=True, slots=True)
class SearchWriteResult:
    disposition: SearchWriteDisposition
    record: SearchPersistedRecord


@dataclass(frozen=True, slots=True)
class SearchReplay:
    stream_id: str
    records: tuple[SearchPersistedRecord, ...]
    missing_sequences: tuple[int, ...]
    missing_lineage_fingerprints: tuple[SearchFingerprint, ...]
    complete: bool
    reconciliation_required: bool

    def __post_init__(self) -> None:
        if self.complete == self.reconciliation_required:
            raise SearchValidationError("replay completeness and reconciliation facts conflict")


@dataclass(frozen=True, slots=True)
class SearchRestartReferenceFact:
    record_id: str
    reference: str
    availability: RestartReferenceAvailability


@dataclass(frozen=True, slots=True)
class SearchRestartState:
    replay: SearchReplay
    reference_facts: tuple[SearchRestartReferenceFact, ...]

    @property
    def reconciliation_required(self) -> bool:
        return self.replay.reconciliation_required


@dataclass(frozen=True, slots=True)
class SearchPersistenceHealth:
    state: SearchPersistenceHealthState
    schema_exists: bool
    schema_version_compatible: bool
    migration_checksum_valid: bool
    append_only_protected: bool
    database_readable: bool
    integrity_check_passed: bool
    replay_capable: bool

    @property
    def healthy(self) -> bool:
        return self.state is SearchPersistenceHealthState.HEALTHY


@runtime_checkable
class SearchMetadataStorePort(Protocol):
    def append(self, draft: SearchPersistenceDraft) -> SearchWriteResult: ...
    def get_exact(self, record_id: str, fingerprint: SearchFingerprint) -> SearchPersistedRecord: ...
    def history(self, stream_id: str, start_sequence: int = 1, end_sequence: int | None = None) -> tuple[SearchPersistedRecord, ...]: ...
    def replay(self, stream_id: str) -> SearchReplay: ...
    def restart_state(self, stream_id: str, available_references: frozenset[str]) -> SearchRestartState: ...


@runtime_checkable
class SearchPersistenceHealthPort(Protocol):
    def health(self) -> SearchPersistenceHealth: ...
