from __future__ import annotations

from dataclasses import fields, replace
from datetime import UTC, datetime, timedelta

import pytest

from synapse.search import (
    ArtifactChecksum,
    ArtifactContentReference,
    CacheEntryId,
    CacheNamespace,
    CacheReadAssessmentV1,
    CacheReadStatus,
    CausationReference,
    CorrelationReference,
    ExtractedContentChecksum,
    ExtractedContentId,
    ExtractedContentReference,
    ExtractedContentV1,
    ExtractionAttemptId,
    ExtractionCapability,
    ExtractionOutcome,
    ExtractionProvenance,
    ExtractionRequestId,
    ExtractionRequestV1,
    ExtractorReference,
    FreshnessConstraint,
    FreshnessFacts,
    NormalizedSearchResultV1,
    PolicyReference,
    ProviderResultReference,
    PublicationDateProvenance,
    RequesterReference,
    RetrievalAttemptId,
    RetrievalOutcome,
    RetrievalProvenance,
    RetrievalRequestId,
    RetrievalRequestV1,
    RetrievalTransportReference,
    RetrievedArtifactId,
    RetrievedArtifactV1,
    SearchOccurrence,
    SearchOutcomeCode,
    SearchProviderReference,
    SearchPurpose,
    SearchRequestId,
    SearchRequestOccurrence,
    SearchRequestV1,
    SearchResultId,
    SearchResultProvenance,
    SearchResultSetId,
    SearchResultSetProvenance,
    SearchResultSetV1,
    SearchSourceReference,
)
from synapse.search_integrations import (
    ExternalContentTrust,
    SearchResultRetrievalHandoffV1,
    SearchSourceEvidenceProjector,
    SearchSourceProjectionStatus,
)

NOW = datetime(2026, 8, 13, 12, tzinfo=UTC)
REQUESTER = RequesterReference("agent:researcher")
PROVIDER = SearchProviderReference("provider:neutral")
SOURCE = SearchSourceReference("source:example.com")
CORRELATION = CorrelationReference("correlation:source-review")
RETRIEVAL_POLICY = PolicyReference("policy:external-retrieval-v1")


def search_request() -> SearchRequestV1:
    return SearchRequestV1(
        SearchRequestId("search-request:evidence-1"),
        REQUESTER,
        "explicit source selection",
        SearchPurpose("technical.research"),
        CORRELATION,
        SearchRequestOccurrence(NOW),
        policy_reference=PolicyReference("policy:external-search-v1"),
    )


def search_result(index: int = 1, *, url: str | None = None) -> NormalizedSearchResultV1:
    request = search_request()
    source_url = url or "https://example.com/article"
    result_id = SearchResultId(f"search-result:evidence-{index}")
    provider_result = ProviderResultReference(f"provider-result:evidence-{index}")
    occurrence = SearchOccurrence(NOW + timedelta(seconds=1))
    provenance = SearchResultProvenance(
        request.request_id,
        request.semantic_fingerprint,
        PROVIDER,
        result_id,
        provider_result,
        source_url,
        occurrence,
        index,
        correlation=CORRELATION,
    )
    publication = NOW - timedelta(days=2)
    return NormalizedSearchResultV1(
        result_id,
        source_url,
        f"Source {index}",
        "Provider snippet only.",
        SOURCE,
        PROVIDER,
        provider_result,
        index,
        index,
        occurrence,
        FreshnessFacts.from_observation(
            FreshnessConstraint(),
            publication_date=publication,
            provider_reported_date=publication,
            search_occurrence=occurrence,
        ),
        provenance,
        canonical_url="https://publisher.example/article",
        publication_date=publication,
        publication_date_provenance=PublicationDateProvenance.PROVIDER_EXPLICIT,
        provider_reported_date=publication,
    )


def result_set(results: tuple[NormalizedSearchResultV1, ...] | None = None) -> SearchResultSetV1:
    request = search_request()
    values = results or (search_result(),)
    occurrence = values[0].search_occurrence
    provenance = SearchResultSetProvenance(
        request.request_id,
        request.semantic_fingerprint,
        PROVIDER,
        occurrence,
        correlation=CORRELATION,
    )
    return SearchResultSetV1(
        SearchResultSetId("search-result-set:evidence-1"),
        request.request_id,
        request.semantic_fingerprint,
        PROVIDER,
        SearchOutcomeCode.RESULTS,
        values,
        occurrence,
        provenance,
    )


def handoff(
    *, result: NormalizedSearchResultV1 | None = None,
    results: tuple[NormalizedSearchResultV1, ...] | None = None,
) -> SearchResultRetrievalHandoffV1:
    selected = result or search_result()
    return SearchResultRetrievalHandoffV1.select(
        request=search_request(),
        result_set=result_set(results),
        result=selected,
        requester=REQUESTER,
        purpose=SearchPurpose("source.review"),
        retrieval_policy_reference=RETRIEVAL_POLICY,
        correlation=CORRELATION,
        causation=(CausationReference("cause:search-result-selection"),),
        accepted_content_types=("text/html",),
        maximum_bytes=100_000,
        requested_at=SearchOccurrence(NOW + timedelta(seconds=2)),
    )


def retrieval() -> RetrievalRequestV1:
    return handoff().to_retrieval_request(RetrievalRequestId("search-retrieval-request:evidence-1"))


def artifact(*, outcome: RetrievalOutcome = RetrievalOutcome.RETRIEVED) -> RetrievedArtifactV1:
    request = retrieval()
    attempt = RetrievalAttemptId("search-retrieval-attempt:evidence-1")
    provenance = RetrievalProvenance(
        request.search_request_id,
        request.source_result_id,
        request.retrieval_request_id,
        attempt,
        request.source_url,
        RetrievalTransportReference("retrieval-transport:http-v1"),
        request.correlation,
        request.causation,
    )
    success = outcome is RetrievalOutcome.RETRIEVED
    return RetrievedArtifactV1(
        RetrievedArtifactId("search-artifact:evidence-1"),
        request.retrieval_request_id,
        attempt,
        request.source_result_id,
        request.source_url,
        outcome,
        SearchOccurrence(NOW + timedelta(seconds=3)),
        provenance,
        normalized_content_type="text/html" if success else None,
        content_length=100 if success else None,
        checksum=ArtifactChecksum("sha256:" + "a" * 64) if success else None,
        content_reference=ArtifactContentReference("artifact-body:evidence-1") if success else None,
    )


def extraction_request() -> ExtractionRequestV1:
    return ExtractionRequestV1.for_artifact(
        extraction_request_id=ExtractionRequestId("search-extraction-request:evidence-1"),
        artifact=artifact(),
        capability=ExtractionCapability.HTML_TO_TEXT,
        requester=REQUESTER,
        policy_reference=PolicyReference("policy:extraction-v1"),
        correlation=CORRELATION,
        causation=(),
        occurrence=SearchOccurrence(NOW + timedelta(seconds=4)),
    )


def extracted() -> ExtractedContentV1:
    request = extraction_request()
    source = artifact()
    attempt = ExtractionAttemptId("search-extraction-attempt:evidence-1")
    extractor = ExtractorReference("extractor:text-v1")
    provenance = ExtractionProvenance(
        search_request().request_id,
        source.source_result_id,
        source.retrieval_request_id,
        source.artifact_id,
        request.extraction_request_id,
        attempt,
        extractor,
        CORRELATION,
    )
    return ExtractedContentV1(
        ExtractedContentId("search-extracted-content:evidence-1"),
        request.extraction_request_id,
        attempt,
        source.artifact_id,
        request.capability,
        ExtractionOutcome.EXTRACTED,
        extractor,
        "text-v1",
        SearchOccurrence(NOW + timedelta(seconds=5)),
        provenance,
        ExtractedContentReference("extracted-text:evidence-1"),
        ExtractedContentChecksum("sha256:" + "b" * 64),
        observed_text_length=20,
        delivered_text_length=20,
        limitations=("reference-only",),
    )


PROJECTOR = SearchSourceEvidenceProjector()


def test_result_selection_is_explicit_and_does_not_retrieve() -> None:
    selected = handoff()
    assert selected.result_id == search_result().result_id
    assert selected.policy_reference == RETRIEVAL_POLICY
    assert not hasattr(selected, "execute")
    projection = PROJECTOR.project(handoff=selected, result=search_result())
    assert projection.status is SearchSourceProjectionStatus.SEARCH_ONLY
    assert "source-content-not-retrieved" in projection.limitations
    assert projection.provider_snippet_available
    assert projection.artifact_id is None and projection.extracted_content_id is None


def test_wrong_request_result_set_result_source_and_lineage_are_blocked() -> None:
    selected = search_result()
    with pytest.raises(ValueError, match="result set"):
        SearchResultRetrievalHandoffV1.select(
            request=replace(search_request(), query="different semantics"),
            result_set=result_set(),
            result=selected,
            requester=REQUESTER,
            purpose=SearchPurpose("source.review"),
            retrieval_policy_reference=RETRIEVAL_POLICY,
            correlation=CORRELATION,
            causation=(),
            accepted_content_types=("text/html",),
            maximum_bytes=1000,
            requested_at=SearchOccurrence(NOW + timedelta(seconds=2)),
        )
    with pytest.raises(ValueError, match="belong"):
        handoff(result=search_result(2))
    forged = search_result(url="https://other.example/article")
    with pytest.raises(ValueError, match="belong|correspondence"):
        handoff(result=forged, results=(selected,))


def test_retrieval_request_preserves_selection_and_uses_distinct_authorization_policy() -> None:
    selected = handoff()
    request = selected.to_retrieval_request(RetrievalRequestId("search-retrieval-request:evidence-1"))
    assert request.source_url == selected.normalized_url
    assert request.source_result_id == selected.result_id
    assert request.policy_reference == RETRIEVAL_POLICY
    assert request.policy_reference != search_request().policy_reference
    assert request.semantic_fingerprint != search_request().semantic_fingerprint


def test_retrieved_not_extracted_and_failed_retrieval_are_factual() -> None:
    request = retrieval()
    retrieved = PROJECTOR.project(
        handoff=handoff(), result=search_result(), retrieval_request=request, artifact=artifact()
    )
    assert retrieved.status is SearchSourceProjectionStatus.RETRIEVED
    assert retrieved.artifact_checksum is not None
    assert retrieved.extracted_content_reference is None
    failed = artifact(outcome=RetrievalOutcome.TIMEOUT)
    failure = PROJECTOR.project(
        handoff=handoff(), result=search_result(), retrieval_request=request, artifact=failed
    )
    assert failure.status is SearchSourceProjectionStatus.RETRIEVAL_FAILED
    assert failure.artifact_checksum is None


def test_extracted_projection_preserves_checksum_lineage_without_verification() -> None:
    projection = PROJECTOR.project(
        handoff=handoff(),
        result=search_result(),
        retrieval_request=retrieval(),
        artifact=artifact(),
        extraction_request=extraction_request(),
        extracted_content=extracted(),
    )
    assert projection.status is SearchSourceProjectionStatus.EXTRACTED
    assert projection.artifact_checksum == artifact().checksum
    assert projection.extracted_content_checksum == extracted().content_checksum
    assert projection.external_content_trust is ExternalContentTrust.UNTRUSTED
    forbidden = {"verified", "truth_score", "trust_score", "claim", "citation_text", "agent_summary"}
    assert forbidden.isdisjoint({item.name for item in fields(projection)})


def test_publication_search_retrieval_extraction_occurrences_remain_independent() -> None:
    projection = PROJECTOR.project(
        handoff=handoff(),
        result=search_result(),
        retrieval_request=retrieval(),
        artifact=artifact(),
        extraction_request=extraction_request(),
        extracted_content=extracted(),
    )
    assert projection.publication_date is not None
    assert projection.retrieval_occurrence is not None
    assert projection.extraction_occurrence is not None
    assert projection.publication_date < projection.search_occurrence.occurred_at
    assert projection.search_occurrence.occurred_at < projection.retrieval_occurrence.occurred_at
    assert projection.retrieval_occurrence.occurred_at < projection.extraction_occurrence.occurred_at


def test_cache_origin_and_duplicate_provider_provenance_are_not_erased() -> None:
    duplicate = search_result(2)
    duplicate = replace(
        duplicate,
        source_url=search_result().source_url,
        normalized_rank=2,
        provenance=replace(duplicate.provenance, source_url=search_result().source_url),
    )
    cache = CacheReadAssessmentV1(
        CacheNamespace.RETRIEVAL,
        CacheReadStatus.HIT_FRESH,
        NOW + timedelta(seconds=20),
        NOW + timedelta(seconds=3),
        NOW + timedelta(seconds=10),
        10,
        True,
        False,
        False,
        entry_id=CacheEntryId("cache-entry:retrieval-evidence"),
    )
    projection = PROJECTOR.project(
        handoff=handoff(),
        result=search_result(),
        duplicate_results=(duplicate,),
        cache_assessments=(cache,),
    )
    assert len(projection.result_provenance) == 2
    assert projection.cache_provenance[0].cache_age_seconds == 10
    assert projection.cache_provenance[0].original_occurrence != projection.cache_provenance[0].cache_read_occurrence


def test_missing_lineage_is_rejected_and_projection_replay_has_no_external_execution() -> None:
    with pytest.raises(ValueError, match="requires"):
        PROJECTOR.project(handoff=handoff(), result=search_result(), artifact=artifact())
    first = PROJECTOR.project(handoff=handoff(), result=search_result())
    replay = PROJECTOR.project(handoff=handoff(), result=search_result())
    assert replay == first
    assert not hasattr(PROJECTOR, "retrieve")
    assert not hasattr(PROJECTOR, "extract")


def test_historical_references_can_be_currently_unavailable_without_reexecution() -> None:
    projection = PROJECTOR.project(
        handoff=handoff(),
        result=search_result(),
        retrieval_request=retrieval(),
        artifact=artifact(),
        source_reference_available=False,
        artifact_content_available=False,
    )
    assert projection.status is SearchSourceProjectionStatus.SOURCE_REFERENCE_UNAVAILABLE
    assert projection.artifact_content_reference is not None
    assert projection.artifact_content_available is False
    assert projection.external_content_trust is ExternalContentTrust.UNTRUSTED


def test_incomplete_provenance_is_never_promoted_to_success() -> None:
    projection = PROJECTOR.project(
        handoff=handoff(),
        result=search_result(),
        provenance_complete=False,
    )
    assert projection.status is SearchSourceProjectionStatus.PROVENANCE_INCOMPLETE
    assert "provenance-incomplete" in projection.limitations
