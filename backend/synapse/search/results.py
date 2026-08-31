"""Provider-neutral normalized Search result facts."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from .canonical import SEARCH_CANONICAL_FORMAT_V1, canonical_json, semantic_fingerprint
from .errors import SearchDiagnostic, SearchOutcomeCode, SearchValidationError
from .identities import (
    AgentSummaryReference,
    CausationReference,
    CorrelationReference,
    ExtractedTextReference,
    ProviderResultReference,
    RetrievedContentReference,
    SearchFingerprint,
    SearchInvocationId,
    SearchProviderReference,
    SearchRequestId,
    SearchResultId,
    SearchResultSetId,
    SearchSourceReference,
)
from .models import FreshnessConstraint, FreshnessKind

NORMALIZED_SEARCH_RESULT_FORMAT_V1 = "normalized-search-result-v1"
SEARCH_RESULT_SET_FORMAT_V1 = "search-result-set-v1"

_URL = re.compile(r"^https?://([^/?#\s]+)(?:[/?#][^\s]*)?$", re.IGNORECASE)
_HOST = re.compile(
    r"^(?=.{1,253}$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?::[0-9]{1,5})?$"
)
_LANGUAGE_TAG = re.compile(r"^[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*$")
_CONTENT_TYPE = re.compile(r"^[a-z0-9][a-z0-9.+-]{0,63}/[a-z0-9][a-z0-9.+-]{0,127}$")
_METADATA_PART = re.compile(r"^[a-z][a-z0-9._-]{0,63}$")
_SENSITIVE_KEY = re.compile(r"(?:credential|password|passwd|secret|token|api[_-]?key)", re.I)


def _aware_utc(value: datetime | None, field_name: str) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        raise SearchValidationError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def _validated_url(value: str, field_name: str) -> str:
    if not isinstance(value, str) or len(value) > 2048:
        raise SearchValidationError(f"{field_name} must be a bounded HTTP(S) URL")
    match = _URL.fullmatch(value)
    if match is None or _HOST.fullmatch(match.group(1)) is None:
        raise SearchValidationError(f"{field_name} must be a structurally valid HTTP(S) URL")
    return value


def _hostname(value: str) -> str:
    authority = value.split("://", 1)[1].split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
    return authority.rsplit(":", 1)[0].lower().removesuffix(".")


class PublicationDateProvenance(StrEnum):
    PROVIDER_EXPLICIT = "provider_explicit"
    SOURCE_EXTRACTED = "source_extracted"
    UNKNOWN = "unknown"


class FreshnessStatus(StrEnum):
    SATISFIED = "satisfied"
    VIOLATED = "violated"
    UNKNOWN = "unknown"
    NOT_REQUESTED = "not_requested"


@dataclass(frozen=True, slots=True, order=True)
class ProviderMetadataEntry:
    namespace: str
    key: str
    value: str | int | bool | None

    def __post_init__(self) -> None:
        if not _METADATA_PART.fullmatch(self.namespace) or not _METADATA_PART.fullmatch(self.key):
            raise SearchValidationError("provider metadata requires canonical namespace and key")
        if _SENSITIVE_KEY.search(self.key):
            raise SearchValidationError("provider metadata cannot preserve sensitive fields")
        if isinstance(self.value, str) and len(self.value) > 1024:
            raise SearchValidationError("provider metadata value is too large")


@dataclass(frozen=True, slots=True)
class SearchOccurrence:
    occurred_at: datetime

    def __post_init__(self) -> None:
        normalized = _aware_utc(self.occurred_at, "search occurrence")
        assert normalized is not None
        object.__setattr__(self, "occurred_at", normalized)


@dataclass(frozen=True, slots=True)
class FreshnessFacts:
    requested: FreshnessConstraint
    status: FreshnessStatus
    publication_date: datetime | None
    provider_reported_date: datetime | None
    search_occurrence: SearchOccurrence

    def __post_init__(self) -> None:
        publication = _aware_utc(self.publication_date, "publication date")
        provider_date = _aware_utc(self.provider_reported_date, "provider-reported date")
        object.__setattr__(self, "publication_date", publication)
        object.__setattr__(self, "provider_reported_date", provider_date)
        expected = self._evaluate(self.requested, publication, self.search_occurrence.occurred_at)
        if self.status is not expected:
            raise SearchValidationError("freshness status does not match the available date facts")

    @staticmethod
    def _evaluate(
        constraint: FreshnessConstraint, publication: datetime | None, occurrence: datetime
    ) -> FreshnessStatus:
        if constraint.kind is FreshnessKind.NONE:
            return FreshnessStatus.NOT_REQUESTED
        if publication is None:
            return FreshnessStatus.UNKNOWN
        satisfied = False
        if constraint.kind is FreshnessKind.WINDOW:
            assert constraint.window_seconds is not None
            satisfied = occurrence - timedelta(seconds=constraint.window_seconds) <= publication <= occurrence
        elif constraint.kind is FreshnessKind.AFTER:
            assert constraint.after is not None
            satisfied = publication >= constraint.after
        elif constraint.kind is FreshnessKind.BEFORE:
            assert constraint.before is not None
            satisfied = publication <= constraint.before
        elif constraint.kind is FreshnessKind.RANGE:
            assert constraint.after is not None and constraint.before is not None
            satisfied = constraint.after <= publication <= constraint.before
        return FreshnessStatus.SATISFIED if satisfied else FreshnessStatus.VIOLATED

    @classmethod
    def from_observation(
        cls,
        requested: FreshnessConstraint,
        *,
        publication_date: datetime | None,
        provider_reported_date: datetime | None,
        search_occurrence: SearchOccurrence,
    ) -> FreshnessFacts:
        publication = _aware_utc(publication_date, "publication date")
        provider_date = _aware_utc(provider_reported_date, "provider-reported date")
        status = cls._evaluate(requested, publication, search_occurrence.occurred_at)
        return cls(requested, status, publication, provider_date, search_occurrence)


@dataclass(frozen=True, slots=True)
class SearchResultProvenance:
    request_id: SearchRequestId
    request_fingerprint: SearchFingerprint
    provider: SearchProviderReference
    result_id: SearchResultId
    provider_result_reference: ProviderResultReference
    source_url: str
    search_occurrence: SearchOccurrence
    provider_position: int
    provider_invocation: SearchInvocationId | None = None
    correlation: CorrelationReference | None = None
    causation: tuple[CausationReference, ...] = ()

    def __post_init__(self) -> None:
        _validated_url(self.source_url, "provenance source URL")
        if (
            isinstance(self.provider_position, bool)
            or not isinstance(self.provider_position, int)
            or self.provider_position < 1
        ):
            raise SearchValidationError("provenance provider position must be positive")
        if len(set(self.causation)) != len(self.causation):
            raise SearchValidationError("provenance causation references must be unique")

    def semantic_content(self) -> dict[str, object]:
        return {
            "request_fingerprint": self.request_fingerprint,
            "provider": self.provider,
            "provider_result_reference": self.provider_result_reference,
            "source_url": self.source_url,
            "provider_position": self.provider_position,
        }

    @property
    def semantic_fingerprint(self) -> SearchFingerprint:
        return semantic_fingerprint(self.semantic_content())


@dataclass(frozen=True, slots=True)
class NormalizedSearchResultV1:
    result_id: SearchResultId
    source_url: str
    title: str
    provider_snippet: str | None
    source: SearchSourceReference
    provider: SearchProviderReference
    provider_result_reference: ProviderResultReference
    provider_position: int
    normalized_rank: int
    search_occurrence: SearchOccurrence
    freshness: FreshnessFacts
    provenance: SearchResultProvenance
    canonical_url: str | None = None
    source_label: str | None = None
    publication_date: datetime | None = None
    publication_date_provenance: PublicationDateProvenance = PublicationDateProvenance.UNKNOWN
    provider_reported_date: datetime | None = None
    language: str | None = None
    content_type: str | None = None
    retrieved_content_reference: RetrievedContentReference | None = None
    extracted_text_reference: ExtractedTextReference | None = None
    agent_summary_reference: AgentSummaryReference | None = None
    provider_metadata: tuple[ProviderMetadataEntry, ...] = ()
    format_version: str = NORMALIZED_SEARCH_RESULT_FORMAT_V1

    def __post_init__(self) -> None:
        source_url = _validated_url(self.source_url, "source URL")
        if self.canonical_url is not None:
            _validated_url(self.canonical_url, "provider canonical URL")
        title = self.title.strip() if isinstance(self.title, str) else ""
        if not title or len(title) > 1000:
            raise SearchValidationError("result title must be explicit and bounded")
        snippet = self.provider_snippet
        if snippet is not None and (not isinstance(snippet, str) or len(snippet) > 8000):
            raise SearchValidationError("provider snippet must be bounded text")
        if (
            isinstance(self.provider_position, bool)
            or not isinstance(self.provider_position, int)
            or self.provider_position < 1
        ):
            raise SearchValidationError("provider position must be positive")
        if (
            isinstance(self.normalized_rank, bool)
            or not isinstance(self.normalized_rank, int)
            or self.normalized_rank < 1
        ):
            raise SearchValidationError("normalized rank must be positive")
        publication = _aware_utc(self.publication_date, "publication date")
        provider_date = _aware_utc(self.provider_reported_date, "provider-reported date")
        if self.publication_date_provenance is PublicationDateProvenance.UNKNOWN:
            if publication is not None:
                raise SearchValidationError("unknown publication provenance cannot carry a date")
        elif publication is None:
            raise SearchValidationError("known publication provenance requires a date")
        if self.publication_date_provenance is PublicationDateProvenance.PROVIDER_EXPLICIT:
            if provider_date is None or provider_date != publication:
                raise SearchValidationError("provider publication date must match provider-reported date")
        language = self.language
        if language is not None:
            if not isinstance(language, str) or not _LANGUAGE_TAG.fullmatch(language):
                raise SearchValidationError("result language must be a valid language tag")
            language = language.lower()
        content_type = self.content_type
        if content_type is not None:
            content_type = content_type.lower()
            if not _CONTENT_TYPE.fullmatch(content_type):
                raise SearchValidationError("content type must be a provider-reported MIME type")
        metadata = tuple(sorted(self.provider_metadata))
        if len({(item.namespace, item.key) for item in metadata}) != len(metadata):
            raise SearchValidationError("provider metadata keys must be unique per namespace")
        correspondence = (
            self.provenance.result_id == self.result_id
            and self.provenance.provider == self.provider
            and self.provenance.provider_result_reference == self.provider_result_reference
            and self.provenance.source_url == source_url
            and self.provenance.search_occurrence == self.search_occurrence
            and self.provenance.provider_position == self.provider_position
            and self.freshness.publication_date == publication
            and self.freshness.provider_reported_date == provider_date
            and self.freshness.search_occurrence == self.search_occurrence
        )
        if not correspondence:
            raise SearchValidationError("result facts do not correspond to provenance/freshness")
        object.__setattr__(self, "title", title)
        object.__setattr__(self, "publication_date", publication)
        object.__setattr__(self, "provider_reported_date", provider_date)
        object.__setattr__(self, "language", language)
        object.__setattr__(self, "content_type", content_type)
        object.__setattr__(self, "provider_metadata", metadata)
        if self.format_version != NORMALIZED_SEARCH_RESULT_FORMAT_V1:
            raise SearchValidationError("unsupported normalized Search result format")

    @property
    def source_domain(self) -> str:
        return _hostname(self.source_url)

    def semantic_content(self) -> dict[str, object]:
        return {
            "format": self.format_version,
            "source_url": self.source_url,
            "canonical_url": self.canonical_url,
            "title": self.title,
            "provider_snippet": self.provider_snippet,
            "source": self.source,
            "provider": self.provider,
            "provider_result_reference": self.provider_result_reference,
            "provider_position": self.provider_position,
            "normalized_rank": self.normalized_rank,
            "publication_date": self.publication_date,
            "publication_date_provenance": self.publication_date_provenance,
            "provider_reported_date": self.provider_reported_date,
            "language": self.language,
            "content_type": self.content_type,
            "freshness_status": self.freshness.status,
        }

    @property
    def semantic_fingerprint(self) -> SearchFingerprint:
        return semantic_fingerprint(self.semantic_content())

    def canonical_serialization(self) -> str:
        return canonical_json(
            {
                "canonical_format": SEARCH_CANONICAL_FORMAT_V1,
                "result": self,
                "semantic_fingerprint": self.semantic_fingerprint,
            }
        )


@dataclass(frozen=True, slots=True)
class SearchResultSetProvenance:
    request_id: SearchRequestId
    request_fingerprint: SearchFingerprint
    provider: SearchProviderReference
    search_occurrence: SearchOccurrence
    provider_invocation: SearchInvocationId | None = None
    correlation: CorrelationReference | None = None
    causation: tuple[CausationReference, ...] = ()

    def __post_init__(self) -> None:
        if len(set(self.causation)) != len(self.causation):
            raise SearchValidationError("result-set causation references must be unique")


@dataclass(frozen=True, slots=True)
class SearchResultSetV1:
    result_set_id: SearchResultSetId
    request_id: SearchRequestId
    request_fingerprint: SearchFingerprint
    provider: SearchProviderReference
    outcome: SearchOutcomeCode
    results: tuple[NormalizedSearchResultV1, ...]
    search_occurrence: SearchOccurrence
    provenance: SearchResultSetProvenance
    provider_invocation: SearchInvocationId | None = None
    diagnostics: tuple[SearchDiagnostic, ...] = ()
    format_version: str = SEARCH_RESULT_SET_FORMAT_V1

    def __post_init__(self) -> None:
        if self.outcome not in (SearchOutcomeCode.RESULTS, SearchOutcomeCode.NO_RESULTS):
            raise SearchValidationError("result-set outcome must be a successful Search outcome")
        if self.outcome is SearchOutcomeCode.NO_RESULTS and self.results:
            raise SearchValidationError("NO_RESULTS requires an empty result sequence")
        if self.outcome is SearchOutcomeCode.RESULTS and not self.results:
            raise SearchValidationError("RESULTS requires normalized results")
        ids = [item.result_id for item in self.results]
        positions = [item.provider_position for item in self.results]
        ranks = [item.normalized_rank for item in self.results]
        if len(set(ids)) != len(ids):
            raise SearchValidationError("result identities must be unique")
        if len(set(positions)) != len(positions):
            raise SearchValidationError("provider positions must be unique")
        if ranks != list(range(1, len(self.results) + 1)):
            raise SearchValidationError("normalized ranks must be contiguous and ordered")
        if any(
            item.provenance.request_id != self.request_id
            or item.provenance.request_fingerprint != self.request_fingerprint
            or item.provider != self.provider
            or item.search_occurrence != self.search_occurrence
            or item.provenance.provider_invocation != self.provider_invocation
            for item in self.results
        ):
            raise SearchValidationError("result does not correspond to its result set")
        if (
            self.provenance.request_id != self.request_id
            or self.provenance.request_fingerprint != self.request_fingerprint
            or self.provenance.provider != self.provider
            or self.provenance.search_occurrence != self.search_occurrence
            or self.provenance.provider_invocation != self.provider_invocation
        ):
            raise SearchValidationError("result-set provenance mismatch")
        if any(
            diagnostic.request_id is not None and diagnostic.request_id != self.request_id
            for diagnostic in self.diagnostics
        ):
            raise SearchValidationError("diagnostic request mismatch")
        if self.format_version != SEARCH_RESULT_SET_FORMAT_V1:
            raise SearchValidationError("unsupported Search result-set format")

    def semantic_content(self) -> dict[str, object]:
        return {
            "format": self.format_version,
            "request_fingerprint": self.request_fingerprint,
            "provider": self.provider,
            "outcome": self.outcome,
            "results": tuple(item.semantic_fingerprint for item in self.results),
        }

    @property
    def semantic_fingerprint(self) -> SearchFingerprint:
        return semantic_fingerprint(self.semantic_content())

    def canonical_serialization(self) -> str:
        return canonical_json(
            {
                "canonical_format": SEARCH_CANONICAL_FORMAT_V1,
                "result_set": self,
                "semantic_fingerprint": self.semantic_fingerprint,
            }
        )
