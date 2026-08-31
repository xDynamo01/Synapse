"""Pure Retrieval/Artifact/Extraction contracts; no I/O or content parsing."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from .canonical import SEARCH_CANONICAL_FORMAT_V1, canonical_json, semantic_fingerprint
from .errors import SearchValidationError
from .identities import (
    AgentSummaryReference,
    ArtifactContentReference,
    CausationReference,
    CorrelationReference,
    ExtractedContentId,
    ExtractedContentReference,
    ExtractionAttemptId,
    ExtractionRequestId,
    ExtractorReference,
    PolicyReference,
    RequesterReference,
    RetrievalAttemptId,
    RetrievalRequestId,
    RetrievalTransportReference,
    RetrievedArtifactId,
    SearchFingerprint,
    SearchRequestId,
    SearchResultId,
)
from .normalization import normalize_search_url
from .results import NormalizedSearchResultV1, SearchOccurrence

RETRIEVAL_REQUEST_FORMAT_V1 = "retrieval-request-v1"
RETRIEVED_ARTIFACT_FORMAT_V1 = "retrieved-artifact-v1"
EXTRACTION_REQUEST_FORMAT_V1 = "extraction-request-v1"
EXTRACTED_CONTENT_FORMAT_V1 = "extracted-content-v1"
ARTIFACT_CHECKSUM_ALGORITHM_V1 = "sha256"

_MIME = re.compile(r"^[a-z0-9][a-z0-9.+-]{0,63}/[a-z0-9][a-z0-9.+-]{0,127}$")
_CHECKSUM = re.compile(r"^sha256:[0-9a-f]{64}$")
_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$")


def _utc(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise SearchValidationError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def _mime(value: str) -> str:
    normalized = value.lower()
    if _MIME.fullmatch(normalized) is None:
        raise SearchValidationError("content type must be a canonical MIME value")
    return normalized


@dataclass(frozen=True, slots=True, order=True)
class ArtifactChecksum:
    value: str
    algorithm: str = ARTIFACT_CHECKSUM_ALGORITHM_V1

    def __post_init__(self) -> None:
        if self.algorithm != ARTIFACT_CHECKSUM_ALGORITHM_V1 or _CHECKSUM.fullmatch(self.value) is None:
            raise SearchValidationError("artifact checksum must use sha256 lowercase hex")

    def canonical_value(self) -> dict[str, str]:
        return {"algorithm": self.algorithm, "value": self.value}


@dataclass(frozen=True, slots=True, order=True)
class ExtractedContentChecksum:
    """Checksum of delivered extracted text, distinct from artifact bytes."""

    value: str
    algorithm: str = ARTIFACT_CHECKSUM_ALGORITHM_V1

    def __post_init__(self) -> None:
        if self.algorithm != ARTIFACT_CHECKSUM_ALGORITHM_V1 or _CHECKSUM.fullmatch(self.value) is None:
            raise SearchValidationError("extracted content checksum must use sha256 lowercase hex")

    def canonical_value(self) -> dict[str, str]:
        return {"algorithm": self.algorithm, "value": self.value}


@dataclass(frozen=True, slots=True)
class RetrievalRequestV1:
    retrieval_request_id: RetrievalRequestId
    source_result_id: SearchResultId
    search_request_id: SearchRequestId
    source_url: str
    requester: RequesterReference
    accepted_content_types: tuple[str, ...]
    maximum_bytes: int
    policy_reference: PolicyReference
    correlation: CorrelationReference
    causation: tuple[CausationReference, ...]
    occurrence: SearchOccurrence
    format_version: str = RETRIEVAL_REQUEST_FORMAT_V1

    def __post_init__(self) -> None:
        normalize_search_url(self.source_url)
        types = tuple(sorted({_mime(item) for item in self.accepted_content_types}))
        if not types:
            raise SearchValidationError("retrieval requires accepted content types")
        if (
            isinstance(self.maximum_bytes, bool)
            or not isinstance(self.maximum_bytes, int)
            or not 1 <= self.maximum_bytes <= 100_000_000
        ):
            raise SearchValidationError("retrieval maximum bytes is invalid")
        if len(set(self.causation)) != len(self.causation):
            raise SearchValidationError("retrieval causation references must be unique")
        if self.format_version != RETRIEVAL_REQUEST_FORMAT_V1:
            raise SearchValidationError("unsupported retrieval request format")
        object.__setattr__(self, "accepted_content_types", types)

    @classmethod
    def for_result(
        cls,
        *,
        retrieval_request_id: RetrievalRequestId,
        result: NormalizedSearchResultV1,
        search_request_id: SearchRequestId,
        requester: RequesterReference,
        accepted_content_types: tuple[str, ...],
        maximum_bytes: int,
        policy_reference: PolicyReference,
        correlation: CorrelationReference,
        causation: tuple[CausationReference, ...],
        occurrence: SearchOccurrence,
    ) -> RetrievalRequestV1:
        if result.provenance.request_id != search_request_id:
            raise SearchValidationError("Search result does not correspond to retrieval request")
        return cls(
            retrieval_request_id,
            result.result_id,
            search_request_id,
            result.source_url,
            requester,
            accepted_content_types,
            maximum_bytes,
            policy_reference,
            correlation,
            causation,
            occurrence,
        )

    def semantic_content(self) -> dict[str, object]:
        return {
            "format": self.format_version,
            "source_result_id": self.source_result_id,
            "search_request_id": self.search_request_id,
            "source_url": self.source_url,
            "requester": self.requester,
            "accepted_content_types": self.accepted_content_types,
            "maximum_bytes": self.maximum_bytes,
            "policy_reference": self.policy_reference,
        }

    @property
    def semantic_fingerprint(self) -> SearchFingerprint:
        return semantic_fingerprint(self.semantic_content())

    def canonical_serialization(self) -> str:
        return canonical_json({"canonical_format": SEARCH_CANONICAL_FORMAT_V1, "retrieval_request": self, "semantic_fingerprint": self.semantic_fingerprint})


class RetrievalOutcome(StrEnum):
    RETRIEVED = "retrieved"
    NOT_FOUND = "not_found"
    POLICY_BLOCKED = "policy_blocked"
    UNAVAILABLE = "unavailable"
    TIMEOUT = "timeout"
    TOO_LARGE = "too_large"
    UNSUPPORTED_CONTENT = "unsupported_content"
    MALFORMED_SOURCE = "malformed_source"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class RetrievalProvenance:
    search_request_id: SearchRequestId
    search_result_id: SearchResultId
    retrieval_request_id: RetrievalRequestId
    retrieval_attempt_id: RetrievalAttemptId
    source_url: str
    transport_reference: RetrievalTransportReference | None
    correlation: CorrelationReference
    causation: tuple[CausationReference, ...]

    def __post_init__(self) -> None:
        normalize_search_url(self.source_url)


@dataclass(frozen=True, slots=True)
class RetrievedArtifactV1:
    artifact_id: RetrievedArtifactId
    retrieval_request_id: RetrievalRequestId
    retrieval_attempt_id: RetrievalAttemptId
    source_result_id: SearchResultId
    source_url: str
    outcome: RetrievalOutcome
    retrieval_occurrence: SearchOccurrence
    provenance: RetrievalProvenance
    observed_final_url: str | None = None
    redirect_chain: tuple[str, ...] = ()
    reported_content_type: str | None = None
    normalized_content_type: str | None = None
    content_length: int | None = None
    checksum: ArtifactChecksum | None = None
    content_reference: ArtifactContentReference | None = None
    format_version: str = RETRIEVED_ARTIFACT_FORMAT_V1

    def __post_init__(self) -> None:
        normalize_search_url(self.source_url)
        if self.observed_final_url is not None:
            normalize_search_url(self.observed_final_url)
        for redirect_url in self.redirect_chain:
            normalize_search_url(redirect_url)
        normalized_type = _mime(self.normalized_content_type) if self.normalized_content_type else None
        if self.reported_content_type is not None and not self.reported_content_type.strip():
            raise SearchValidationError("reported content type cannot be empty")
        if self.content_length is not None and self.content_length < 0:
            raise SearchValidationError("artifact content length cannot be negative")
        if self.outcome is RetrievalOutcome.RETRIEVED:
            if self.content_length is None or self.checksum is None or self.content_reference is None:
                raise SearchValidationError("retrieved artifact requires length, checksum and content reference")
        elif any(item is not None for item in (self.checksum, self.content_reference)):
            raise SearchValidationError("non-retrieved artifact cannot claim payload facts")
        correspondence = (
            self.provenance.retrieval_request_id == self.retrieval_request_id
            and self.provenance.retrieval_attempt_id == self.retrieval_attempt_id
            and self.provenance.search_result_id == self.source_result_id
            and self.provenance.source_url == self.source_url
        )
        if not correspondence:
            raise SearchValidationError("artifact provenance correspondence mismatch")
        if self.format_version != RETRIEVED_ARTIFACT_FORMAT_V1:
            raise SearchValidationError("unsupported retrieved artifact format")
        object.__setattr__(self, "normalized_content_type", normalized_type)

    def validate_correspondence(self, request: RetrievalRequestV1) -> None:
        if (
            self.retrieval_request_id != request.retrieval_request_id
            or self.source_result_id != request.source_result_id
            or self.source_url != request.source_url
            or self.provenance.search_request_id != request.search_request_id
            or self.provenance.correlation != request.correlation
        ):
            raise SearchValidationError("artifact does not correspond to retrieval request")
        if self.retrieval_occurrence.occurred_at < request.occurrence.occurred_at:
            raise SearchValidationError("artifact is stale relative to retrieval request")
        if self.outcome is RetrievalOutcome.RETRIEVED:
            assert self.content_length is not None
            if self.content_length > request.maximum_bytes:
                raise SearchValidationError("retrieved artifact exceeds admitted maximum size")
            if (
                self.normalized_content_type is not None
                and self.normalized_content_type not in request.accepted_content_types
            ):
                raise SearchValidationError("retrieved artifact content type is unsupported")

    def semantic_content(self) -> dict[str, object]:
        return {"format": self.format_version, "source_result_id": self.source_result_id, "source_url": self.source_url, "outcome": self.outcome, "observed_final_url": self.observed_final_url, "redirect_chain": self.redirect_chain, "normalized_content_type": self.normalized_content_type, "content_length": self.content_length, "checksum": self.checksum, "content_reference": self.content_reference}

    @property
    def semantic_fingerprint(self) -> SearchFingerprint:
        return semantic_fingerprint(self.semantic_content())


class ExtractionCapability(StrEnum):
    PLAIN_TEXT = "plain_text"
    HTML_TO_TEXT = "html_to_text"
    METADATA = "metadata"
    BINARY_PASSTHROUGH = "binary_passthrough"
    PDF_TO_TEXT_FUTURE = "pdf_to_text_future"


@dataclass(frozen=True, slots=True)
class ExtractionRequestV1:
    extraction_request_id: ExtractionRequestId
    artifact_id: RetrievedArtifactId
    retrieval_request_id: RetrievalRequestId
    capability: ExtractionCapability
    requester: RequesterReference
    policy_reference: PolicyReference
    correlation: CorrelationReference
    causation: tuple[CausationReference, ...]
    occurrence: SearchOccurrence
    format_version: str = EXTRACTION_REQUEST_FORMAT_V1

    def __post_init__(self) -> None:
        if self.capability is ExtractionCapability.PDF_TO_TEXT_FUTURE:
            raise SearchValidationError("PDF extraction is unsupported in this slice")
        if len(set(self.causation)) != len(self.causation):
            raise SearchValidationError("extraction causation references must be unique")
        if self.format_version != EXTRACTION_REQUEST_FORMAT_V1:
            raise SearchValidationError("unsupported extraction request format")

    @classmethod
    def for_artifact(cls, *, extraction_request_id: ExtractionRequestId, artifact: RetrievedArtifactV1, capability: ExtractionCapability, requester: RequesterReference, policy_reference: PolicyReference, correlation: CorrelationReference, causation: tuple[CausationReference, ...], occurrence: SearchOccurrence) -> ExtractionRequestV1:
        if artifact.outcome is not RetrievalOutcome.RETRIEVED:
            raise SearchValidationError("extraction requires a successfully retrieved artifact")
        return cls(extraction_request_id, artifact.artifact_id, artifact.retrieval_request_id, capability, requester, policy_reference, correlation, causation, occurrence)

    def semantic_content(self) -> dict[str, object]:
        return {"format": self.format_version, "artifact_id": self.artifact_id, "retrieval_request_id": self.retrieval_request_id, "capability": self.capability, "requester": self.requester, "policy_reference": self.policy_reference}

    @property
    def semantic_fingerprint(self) -> SearchFingerprint:
        return semantic_fingerprint(self.semantic_content())


class ExtractionOutcome(StrEnum):
    EXTRACTED = "extracted"
    EMPTY = "empty"
    UNSUPPORTED_CONTENT = "unsupported_content"
    MALFORMED_CONTENT = "malformed_content"
    ARTIFACT_UNAVAILABLE = "artifact_unavailable"
    DECODING_FAILED = "decoding_failed"
    OUTPUT_TOO_LARGE = "output_too_large"
    EXTRACTOR_UNAVAILABLE = "extractor_unavailable"
    FAILED = "failed"


class CharsetSource(StrEnum):
    TRANSPORT = "transport"
    HTML = "html"
    UTF8_FALLBACK = "utf8_fallback"


@dataclass(frozen=True, slots=True)
class ExtractionProvenance:
    search_request_id: SearchRequestId
    search_result_id: SearchResultId
    retrieval_request_id: RetrievalRequestId
    artifact_id: RetrievedArtifactId
    extraction_request_id: ExtractionRequestId
    extraction_attempt_id: ExtractionAttemptId
    extractor_reference: ExtractorReference
    correlation: CorrelationReference


@dataclass(frozen=True, slots=True)
class ExtractedContentV1:
    extracted_content_id: ExtractedContentId
    extraction_request_id: ExtractionRequestId
    extraction_attempt_id: ExtractionAttemptId
    artifact_id: RetrievedArtifactId
    capability: ExtractionCapability
    outcome: ExtractionOutcome
    extractor_reference: ExtractorReference
    extractor_version: str
    occurrence: SearchOccurrence
    provenance: ExtractionProvenance
    content_reference: ExtractedContentReference | None = None
    content_checksum: ExtractedContentChecksum | None = None
    declared_transport_charset: str | None = None
    declared_html_charset: str | None = None
    used_charset: str | None = None
    charset_source: CharsetSource | None = None
    observed_text_length: int | None = None
    delivered_text_length: int | None = None
    truncated: bool = False
    limitations: tuple[str, ...] = ()
    agent_summary_reference: AgentSummaryReference | None = None
    format_version: str = EXTRACTED_CONTENT_FORMAT_V1

    def __post_init__(self) -> None:
        if _VERSION.fullmatch(self.extractor_version) is None:
            raise SearchValidationError("extractor version is invalid")
        if self.outcome is ExtractionOutcome.EXTRACTED:
            if self.content_reference is None or self.content_checksum is None:
                raise SearchValidationError("extracted outcome requires content reference and checksum")
        elif self.outcome is ExtractionOutcome.EMPTY:
            if self.content_reference is not None or self.content_checksum is not None:
                raise SearchValidationError("empty extraction cannot claim content")
        elif self.content_reference is not None or self.content_checksum is not None:
            raise SearchValidationError("failed extraction cannot claim content")
        if self.truncated:
            raise SearchValidationError("extraction V1 does not permit truncated output")
        if (self.used_charset is None) != (self.charset_source is None):
            raise SearchValidationError("used charset requires its provenance source")
        for value in (self.observed_text_length, self.delivered_text_length):
            if value is not None and value < 0:
                raise SearchValidationError("extracted text length cannot be negative")
        if self.outcome is ExtractionOutcome.EXTRACTED:
            if self.observed_text_length is None or self.delivered_text_length is None:
                raise SearchValidationError("extracted outcome requires text lengths")
            if self.observed_text_length != self.delivered_text_length:
                raise SearchValidationError("untruncated extraction lengths must match")
        elif self.outcome is ExtractionOutcome.EMPTY:
            if self.observed_text_length != 0 or self.delivered_text_length != 0:
                raise SearchValidationError("empty extraction requires zero text lengths")
        elif self.delivered_text_length not in (None, 0):
            raise SearchValidationError("failed extraction cannot claim delivered text")
        correspondence = (
            self.provenance.extraction_request_id == self.extraction_request_id
            and self.provenance.extraction_attempt_id == self.extraction_attempt_id
            and self.provenance.artifact_id == self.artifact_id
            and self.provenance.extractor_reference == self.extractor_reference
        )
        if not correspondence:
            raise SearchValidationError("extracted content provenance correspondence mismatch")
        if self.format_version != EXTRACTED_CONTENT_FORMAT_V1:
            raise SearchValidationError("unsupported extracted content format")

    def validate_correspondence(self, request: ExtractionRequestV1, artifact: RetrievedArtifactV1) -> None:
        if (
            self.extraction_request_id != request.extraction_request_id
            or self.artifact_id != request.artifact_id
            or self.capability != request.capability
            or request.artifact_id != artifact.artifact_id
            or request.retrieval_request_id != artifact.retrieval_request_id
            or self.provenance.retrieval_request_id != artifact.retrieval_request_id
            or self.provenance.search_result_id != artifact.source_result_id
        ):
            raise SearchValidationError("extracted content lineage or correspondence mismatch")
        if self.occurrence.occurred_at < request.occurrence.occurred_at:
            raise SearchValidationError("extracted content is stale relative to extraction request")

    def semantic_content(self) -> dict[str, object]:
        return {"format": self.format_version, "artifact_id": self.artifact_id, "capability": self.capability, "outcome": self.outcome, "extractor_reference": self.extractor_reference, "extractor_version": self.extractor_version, "content_reference": self.content_reference, "content_checksum": self.content_checksum, "declared_transport_charset": self.declared_transport_charset, "declared_html_charset": self.declared_html_charset, "used_charset": self.used_charset, "charset_source": self.charset_source, "observed_text_length": self.observed_text_length, "delivered_text_length": self.delivered_text_length, "truncated": self.truncated, "limitations": self.limitations}

    @property
    def semantic_fingerprint(self) -> SearchFingerprint:
        return semantic_fingerprint(self.semantic_content())

    def canonical_serialization(self) -> str:
        return canonical_json({"canonical_format": SEARCH_CANONICAL_FORMAT_V1, "extracted_content": self, "semantic_fingerprint": self.semantic_fingerprint})


class ObservationRepetition(StrEnum):
    FIRST = "first"
    IDENTICAL = "identical"
    CONTRADICTORY = "contradictory"


def classify_observation_repetition(existing: RetrievedArtifactV1 | ExtractedContentV1 | None, observed: RetrievedArtifactV1 | ExtractedContentV1) -> ObservationRepetition:
    if existing is None:
        return ObservationRepetition.FIRST
    if type(existing) is not type(observed):
        raise SearchValidationError("observations have incomparable artifact types")
    existing_id = existing.artifact_id if isinstance(existing, RetrievedArtifactV1) else existing.extracted_content_id
    observed_id = observed.artifact_id if isinstance(observed, RetrievedArtifactV1) else observed.extracted_content_id
    if existing_id != observed_id:
        raise SearchValidationError("observations have different identities")
    return ObservationRepetition.IDENTICAL if existing.semantic_fingerprint == observed.semantic_fingerprint else ObservationRepetition.CONTRADICTORY


def observation_is_late(request_occurrence: SearchOccurrence, observation_occurrence: SearchOccurrence, admitted_seconds: int) -> bool:
    if admitted_seconds < 1:
        raise SearchValidationError("admitted observation window must be positive")
    return observation_occurrence.occurred_at > request_occurrence.occurred_at + timedelta(seconds=admitted_seconds)
