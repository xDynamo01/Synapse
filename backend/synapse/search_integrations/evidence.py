"""Consumer-owned retrieval handoff and factual source projection."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from synapse.search import (
    ArtifactChecksum,
    ArtifactContentReference,
    CacheEntryId,
    CacheReadAssessmentV1,
    CausationReference,
    CorrelationReference,
    ExtractedContentChecksum,
    ExtractedContentId,
    ExtractedContentReference,
    ExtractedContentV1,
    ExtractionOutcome,
    ExtractionRequestId,
    ExtractionRequestV1,
    ExtractorReference,
    NormalizedSearchResultV1,
    PolicyReference,
    ProviderResultReference,
    RequesterReference,
    RetrievalOutcome,
    RetrievalRequestId,
    RetrievalRequestV1,
    RetrievedArtifactId,
    RetrievedArtifactV1,
    SearchFingerprint,
    SearchOccurrence,
    SearchProviderReference,
    SearchPurpose,
    SearchRequestId,
    SearchRequestV1,
    SearchResultId,
    SearchResultSetId,
    SearchResultSetV1,
    SearchSourceReference,
    semantic_fingerprint,
)


class SearchSourceProjectionStatus(StrEnum):
    SEARCH_ONLY = "search_only"
    RETRIEVAL_REQUESTED = "retrieval_requested"
    RETRIEVED = "retrieved"
    RETRIEVAL_FAILED = "retrieval_failed"
    EXTRACTION_UNAVAILABLE = "extraction_unavailable"
    EXTRACTED = "extracted"
    SOURCE_REFERENCE_UNAVAILABLE = "source_reference_unavailable"
    PROVENANCE_INCOMPLETE = "provenance_incomplete"


class ExternalContentTrust(StrEnum):
    UNTRUSTED = "untrusted"


@dataclass(frozen=True, slots=True)
class SearchResultRetrievalHandoffV1:
    search_request_id: SearchRequestId
    search_request_fingerprint: SearchFingerprint
    result_set_id: SearchResultSetId
    result_set_fingerprint: SearchFingerprint
    result_id: SearchResultId
    result_fingerprint: SearchFingerprint
    source_reference: SearchSourceReference
    original_url: str
    normalized_url: str
    provider_canonical_url: str | None
    provider: SearchProviderReference
    provider_result_reference: ProviderResultReference
    requester: RequesterReference
    purpose: SearchPurpose
    policy_reference: PolicyReference
    correlation: CorrelationReference
    causation: tuple[CausationReference, ...]
    accepted_content_types: tuple[str, ...]
    maximum_bytes: int
    search_occurrence: SearchOccurrence
    requested_at: SearchOccurrence

    @classmethod
    def select(
        cls,
        *,
        request: SearchRequestV1,
        result_set: SearchResultSetV1,
        result: NormalizedSearchResultV1,
        requester: RequesterReference,
        purpose: SearchPurpose,
        retrieval_policy_reference: PolicyReference,
        correlation: CorrelationReference,
        causation: tuple[CausationReference, ...],
        accepted_content_types: tuple[str, ...],
        maximum_bytes: int,
        requested_at: SearchOccurrence,
    ) -> SearchResultRetrievalHandoffV1:
        if result_set.request_id != request.request_id or result_set.request_fingerprint != request.semantic_fingerprint:
            raise ValueError("result set does not correspond to Search request")
        selected = next((item for item in result_set.results if item.result_id == result.result_id), None)
        if selected is None or selected.semantic_fingerprint != result.semantic_fingerprint:
            raise ValueError("selected result does not belong to result set")
        if (
            result.provenance.request_id != request.request_id
            or result.provenance.request_fingerprint != request.semantic_fingerprint
            or result.provider != result_set.provider
            or result.provenance.provider != result_set.provider
            or result.provenance.source_url != result.source_url
            or result.source_url != selected.source_url
            or result.source != selected.source
        ):
            raise ValueError("selected result provenance or source correspondence mismatch")
        return cls(
            request.request_id,
            request.semantic_fingerprint,
            result_set.result_set_id,
            result_set.semantic_fingerprint,
            result.result_id,
            result.semantic_fingerprint,
            result.source,
            result.provenance.source_url,
            result.source_url,
            result.canonical_url,
            result.provider,
            result.provider_result_reference,
            requester,
            purpose,
            retrieval_policy_reference,
            correlation,
            causation,
            accepted_content_types,
            maximum_bytes,
            result.search_occurrence,
            requested_at,
        )

    @property
    def semantic_fingerprint(self) -> SearchFingerprint:
        return semantic_fingerprint(
            {
                "search_request": self.search_request_fingerprint,
                "result_set": self.result_set_fingerprint,
                "result": self.result_fingerprint,
                "source": self.source_reference,
                "original_url": self.original_url,
                "normalized_url": self.normalized_url,
                "provider_canonical_url": self.provider_canonical_url,
                "provider": self.provider,
                "provider_result": self.provider_result_reference,
                "requester": self.requester,
                "purpose": self.purpose,
                "retrieval_policy": self.policy_reference,
                "accepted_content_types": self.accepted_content_types,
                "maximum_bytes": self.maximum_bytes,
            }
        )

    def to_retrieval_request(self, retrieval_request_id: RetrievalRequestId) -> RetrievalRequestV1:
        return RetrievalRequestV1(
            retrieval_request_id=retrieval_request_id,
            source_result_id=self.result_id,
            search_request_id=self.search_request_id,
            source_url=self.normalized_url,
            requester=self.requester,
            accepted_content_types=self.accepted_content_types,
            maximum_bytes=self.maximum_bytes,
            policy_reference=self.policy_reference,
            correlation=self.correlation,
            causation=self.causation,
            occurrence=self.requested_at,
        )


@dataclass(frozen=True, slots=True)
class SearchResultProvenanceProjectionV1:
    result_id: SearchResultId
    result_fingerprint: SearchFingerprint
    provider: SearchProviderReference
    provider_result_reference: ProviderResultReference
    source_reference: SearchSourceReference
    source_url: str
    search_occurrence: SearchOccurrence


@dataclass(frozen=True, slots=True)
class SearchCacheProvenanceProjectionV1:
    namespace: str
    original_occurrence: datetime | None
    cache_read_occurrence: datetime
    cache_written_occurrence: datetime | None
    cache_age_seconds: int | None
    cache_entry_reference: CacheEntryId | None

    @classmethod
    def from_assessment(cls, assessment: CacheReadAssessmentV1) -> SearchCacheProvenanceProjectionV1:
        return cls(
            assessment.namespace.value,
            assessment.original_observation_at,
            assessment.read_at,
            assessment.cache_written_at,
            assessment.age_seconds,
            assessment.entry_id,
        )


@dataclass(frozen=True, slots=True)
class SearchSourceEvidenceV1:
    status: SearchSourceProjectionStatus
    search_request_id: SearchRequestId
    result_set_id: SearchResultSetId
    result_id: SearchResultId
    source_reference: SearchSourceReference
    source_url: str
    title: str
    provider: SearchProviderReference
    provider_result_reference: ProviderResultReference
    provider_snippet_available: bool
    publication_date: datetime | None
    provider_reported_date: datetime | None
    search_occurrence: SearchOccurrence
    retrieval_request_id: RetrievalRequestId | None
    retrieval_occurrence: SearchOccurrence | None
    artifact_id: RetrievedArtifactId | None
    artifact_checksum: ArtifactChecksum | None
    artifact_content_reference: ArtifactContentReference | None
    extraction_request_id: ExtractionRequestId | None
    extraction_occurrence: SearchOccurrence | None
    extracted_content_id: ExtractedContentId | None
    extracted_content_reference: ExtractedContentReference | None
    extracted_content_checksum: ExtractedContentChecksum | None
    extractor_reference: ExtractorReference | None
    extractor_version: str | None
    limitations: tuple[str, ...]
    cache_provenance: tuple[SearchCacheProvenanceProjectionV1, ...]
    result_provenance: tuple[SearchResultProvenanceProjectionV1, ...]
    external_content_trust: ExternalContentTrust = ExternalContentTrust.UNTRUSTED
    source_reference_available: bool = True
    artifact_content_available: bool | None = None
    extracted_content_available: bool | None = None


class SearchSourceEvidenceProjector:
    """Builds metadata only; it performs no retrieval, extraction or evidence write."""

    def project(
        self,
        *,
        handoff: SearchResultRetrievalHandoffV1,
        result: NormalizedSearchResultV1,
        retrieval_request: RetrievalRequestV1 | None = None,
        artifact: RetrievedArtifactV1 | None = None,
        extraction_request: ExtractionRequestV1 | None = None,
        extracted_content: ExtractedContentV1 | None = None,
        duplicate_results: tuple[NormalizedSearchResultV1, ...] = (),
        cache_assessments: tuple[CacheReadAssessmentV1, ...] = (),
        source_reference_available: bool = True,
        artifact_content_available: bool | None = None,
        extracted_content_available: bool | None = None,
        provenance_complete: bool = True,
    ) -> SearchSourceEvidenceV1:
        self._validate_result(handoff, result)
        if artifact is not None and retrieval_request is None:
            raise ValueError("artifact requires its explicit retrieval request")
        if retrieval_request is not None:
            self._validate_retrieval(handoff, retrieval_request)
        if artifact is not None:
            assert retrieval_request is not None
            artifact.validate_correspondence(retrieval_request)
        if extraction_request is not None and artifact is None:
            raise ValueError("extraction request requires a retrieved artifact")
        if extracted_content is not None and (extraction_request is None or artifact is None):
            raise ValueError("extracted content requires complete artifact and extraction lineage")
        if extracted_content is not None:
            assert extraction_request is not None and artifact is not None
            extracted_content.validate_correspondence(extraction_request, artifact)

        status, limitations = self._status(
            result,
            retrieval_request,
            artifact,
            extraction_request,
            extracted_content,
        )
        if not provenance_complete:
            status = SearchSourceProjectionStatus.PROVENANCE_INCOMPLETE
            limitations = tuple(sorted(set(limitations + ("provenance-incomplete",))))
        elif not source_reference_available:
            status = SearchSourceProjectionStatus.SOURCE_REFERENCE_UNAVAILABLE
            limitations = tuple(sorted(set(limitations + ("source-reference-unavailable",))))
        provenance_results = (result,) + tuple(item for item in duplicate_results if item.result_id != result.result_id)
        for item in provenance_results:
            if item.source != result.source or item.source_url != result.source_url:
                raise ValueError("duplicate provenance must preserve the same normalized source")
        return SearchSourceEvidenceV1(
            status,
            handoff.search_request_id,
            handoff.result_set_id,
            handoff.result_id,
            handoff.source_reference,
            handoff.normalized_url,
            result.title,
            handoff.provider,
            handoff.provider_result_reference,
            result.provider_snippet is not None,
            result.publication_date,
            result.provider_reported_date,
            result.search_occurrence,
            retrieval_request.retrieval_request_id if retrieval_request else None,
            artifact.retrieval_occurrence if artifact else None,
            artifact.artifact_id if artifact else None,
            artifact.checksum if artifact else None,
            artifact.content_reference if artifact else None,
            extraction_request.extraction_request_id if extraction_request else None,
            extracted_content.occurrence if extracted_content else None,
            extracted_content.extracted_content_id if extracted_content else None,
            extracted_content.content_reference if extracted_content else None,
            extracted_content.content_checksum if extracted_content else None,
            extracted_content.extractor_reference if extracted_content else None,
            extracted_content.extractor_version if extracted_content else None,
            limitations,
            tuple(SearchCacheProvenanceProjectionV1.from_assessment(item) for item in cache_assessments),
            tuple(
                SearchResultProvenanceProjectionV1(
                    item.result_id,
                    item.semantic_fingerprint,
                    item.provider,
                    item.provider_result_reference,
                    item.source,
                    item.source_url,
                    item.search_occurrence,
                )
                for item in provenance_results
            ),
            ExternalContentTrust.UNTRUSTED,
            source_reference_available,
            artifact_content_available,
            extracted_content_available,
        )

    @staticmethod
    def _validate_result(handoff: SearchResultRetrievalHandoffV1, result: NormalizedSearchResultV1) -> None:
        if (
            result.result_id != handoff.result_id
            or result.semantic_fingerprint != handoff.result_fingerprint
            or result.source != handoff.source_reference
            or result.source_url != handoff.normalized_url
            or result.provider != handoff.provider
        ):
            raise ValueError("result does not correspond to retrieval handoff")

    @staticmethod
    def _validate_retrieval(handoff: SearchResultRetrievalHandoffV1, request: RetrievalRequestV1) -> None:
        if (
            request.search_request_id != handoff.search_request_id
            or request.source_result_id != handoff.result_id
            or request.source_url != handoff.normalized_url
            or request.requester != handoff.requester
            or request.policy_reference != handoff.policy_reference
            or request.correlation != handoff.correlation
        ):
            raise ValueError("retrieval request does not correspond to selected Search result")

    @staticmethod
    def _status(
        result: NormalizedSearchResultV1,
        request: RetrievalRequestV1 | None,
        artifact: RetrievedArtifactV1 | None,
        extraction_request: ExtractionRequestV1 | None,
        extracted: ExtractedContentV1 | None,
    ) -> tuple[SearchSourceProjectionStatus, tuple[str, ...]]:
        if request is None:
            return SearchSourceProjectionStatus.SEARCH_ONLY, ("source-content-not-retrieved", "extraction-unavailable")
        if artifact is None:
            return SearchSourceProjectionStatus.RETRIEVAL_REQUESTED, ("retrieval-not-observed", "extraction-unavailable")
        if artifact.outcome is not RetrievalOutcome.RETRIEVED:
            return SearchSourceProjectionStatus.RETRIEVAL_FAILED, (f"retrieval-{artifact.outcome.value}", "extraction-unavailable")
        if extraction_request is None:
            return SearchSourceProjectionStatus.RETRIEVED, ("artifact-content-untrusted", "extraction-not-requested")
        if extracted is None or extracted.outcome is not ExtractionOutcome.EXTRACTED:
            reason = "extraction-not-observed" if extracted is None else f"extraction-{extracted.outcome.value}"
            return SearchSourceProjectionStatus.EXTRACTION_UNAVAILABLE, ("artifact-content-untrusted", reason)
        return SearchSourceProjectionStatus.EXTRACTED, tuple(sorted(set(("extracted-content-untrusted",) + extracted.limitations)))
