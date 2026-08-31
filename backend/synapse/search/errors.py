"""Closed, safe error and outcome taxonomy for Search Runtime contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from .identities import (
    SearchCapabilityReference,
    SearchDetailReference,
    SearchRequestId,
)


class SearchErrorCode(StrEnum):
    QUERY_INVALID = "query_invalid"
    UNSUPPORTED_CAPABILITY = "unsupported_capability"
    POLICY_BLOCKED = "policy_blocked"
    PROVIDER_UNCONFIGURED = "provider_unconfigured"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    PROVIDER_TIMEOUT = "provider_timeout"
    PROVIDER_RESPONSE_MALFORMED = "provider_response_malformed"
    RETRIEVAL_UNAVAILABLE = "retrieval_unavailable"
    RETRIEVAL_FAILED = "retrieval_failed"
    UNSUPPORTED_CONTENT = "unsupported_content"
    EXTRACTION_FAILED = "extraction_failed"
    CACHE_STALE = "cache_stale"
    CACHE_INVALID = "cache_invalid"
    CACHE_INCOMPATIBLE = "cache_incompatible"
    CACHE_ENTRY_UNAVAILABLE = "cache_entry_unavailable"
    CACHE_VERSION_MISMATCH = "cache_version_mismatch"
    PERSISTENCE_UNAVAILABLE = "persistence_unavailable"
    PERSISTENCE_CONFLICT = "persistence_conflict"
    PERSISTENCE_CORRUPT = "persistence_corrupt"
    PERSISTENCE_VERSION_MISMATCH = "persistence_version_mismatch"
    PERSISTENCE_RECORD_NOT_FOUND = "persistence_record_not_found"
    PROVENANCE_INCOMPLETE = "provenance_incomplete"
    URL_MALFORMED = "url_malformed"
    URL_SCHEME_UNSUPPORTED = "url_scheme_unsupported"
    URL_NORMALIZATION_UNSAFE = "url_normalization_unsafe"
    DUPLICATE_GROUPING_INCONSISTENT = "duplicate_grouping_inconsistent"
    RANKING_INCONSISTENT = "ranking_inconsistent"
    INVOCATION_INVALID = "invocation_invalid"
    CAPABILITY_DECLARATION_INVALID = "capability_declaration_invalid"
    CORRESPONDENCE_MISMATCH = "correspondence_mismatch"
    PROVIDER_RESULT_CONTRADICTORY = "provider_result_contradictory"
    PAYLOAD_TOO_LARGE = "payload_too_large"
    ARTIFACT_MALFORMED = "artifact_malformed"
    EXTRACTION_REQUEST_INVALID = "extraction_request_invalid"
    LINEAGE_INCOMPLETE = "lineage_incomplete"


class SearchOutcomeCode(StrEnum):
    """Valid non-error outcomes; intentionally separate from SearchErrorCode."""

    RESULTS = "results"
    NO_RESULTS = "no_results"


class SearchError(ValueError):
    """Base safe domain error without provider payload or sensitive request content."""

    code: SearchErrorCode

    def __init__(self, code: SearchErrorCode, message: str) -> None:
        self.code = code
        super().__init__(message)


class SearchValidationError(SearchError):
    def __init__(self, message: str) -> None:
        super().__init__(SearchErrorCode.QUERY_INVALID, message)


class SearchOperationalError(SearchError):
    """Reserved typed error for operational slices; it performs no operation itself."""


@dataclass(frozen=True, slots=True)
class SearchDiagnostic:
    code: SearchErrorCode | SearchOutcomeCode
    safe_message: str
    occurred_at: datetime
    request_id: SearchRequestId | None = None
    capability_reference: SearchCapabilityReference | None = None
    detail_reference: SearchDetailReference | None = None

    def __post_init__(self) -> None:
        message = self.safe_message.strip()
        if not message or len(message) > 240 or "\n" in message or "\r" in message:
            raise SearchValidationError("diagnostic message must be a bounded single line")
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            raise SearchValidationError("diagnostic occurrence must be timezone-aware")
        object.__setattr__(self, "safe_message", message)
        object.__setattr__(self, "occurred_at", self.occurred_at.astimezone(UTC))
