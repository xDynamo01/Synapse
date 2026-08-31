from __future__ import annotations

from dataclasses import FrozenInstanceError, fields, replace
from datetime import UTC, datetime, timedelta

import pytest

from synapse.search import (
    AgentSummaryReference,
    ArtifactChecksum,
    ArtifactContentReference,
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
    ObservationRepetition,
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
    SearchFingerprint,
    SearchOccurrence,
    SearchProviderReference,
    SearchRequestId,
    SearchResultId,
    SearchResultProvenance,
    SearchSourceReference,
    SearchValidationError,
    classify_observation_repetition,
    observation_is_late,
)

NOW = datetime(2026, 8, 12, 20, 0, tzinfo=UTC)
SEARCH_REQUEST = SearchRequestId("search-request:retrieval-1")
RESULT_ID = SearchResultId("search-result:retrieval-1")
RETRIEVAL_ID = RetrievalRequestId("search-retrieval-request:request-1")
ATTEMPT_ID = RetrievalAttemptId("search-retrieval-attempt:attempt-1")
ARTIFACT_ID = RetrievedArtifactId("search-artifact:artifact-1")
CORRELATION = CorrelationReference("correlation:retrieval-1")
SOURCE_URL = "https://example.com/document"
CHECKSUM = ArtifactChecksum("sha256:" + "a" * 64)


def search_result() -> NormalizedSearchResultV1:
    occurrence = SearchOccurrence(NOW - timedelta(minutes=2))
    provenance = SearchResultProvenance(
        search_request_id := SEARCH_REQUEST,
        SearchFingerprint("sha256:" + "1" * 64),
        SearchProviderReference("provider:neutral"),
        RESULT_ID,
        ProviderResultReference("provider-result:retrieval-1"),
        SOURCE_URL,
        occurrence,
        1,
    )
    facts = FreshnessFacts.from_observation(
        FreshnessConstraint(),
        publication_date=None,
        provider_reported_date=None,
        search_occurrence=occurrence,
    )
    assert search_request_id is SEARCH_REQUEST
    return NormalizedSearchResultV1(
        RESULT_ID,
        SOURCE_URL,
        "Document",
        "Provider snippet only.",
        SearchSourceReference("source:example.com"),
        SearchProviderReference("provider:neutral"),
        ProviderResultReference("provider-result:retrieval-1"),
        1,
        1,
        occurrence,
        facts,
        provenance,
        publication_date_provenance=PublicationDateProvenance.UNKNOWN,
    )


def retrieval_request(**updates: object) -> RetrievalRequestV1:
    values: dict[str, object] = {
        "retrieval_request_id": RETRIEVAL_ID,
        "source_result_id": RESULT_ID,
        "search_request_id": SEARCH_REQUEST,
        "source_url": SOURCE_URL,
        "requester": RequesterReference("principal:owner"),
        "accepted_content_types": ("text/html", "text/plain"),
        "maximum_bytes": 1_000_000,
        "policy_reference": PolicyReference("policy:retrieval-v1"),
        "correlation": CORRELATION,
        "causation": (),
        "occurrence": SearchOccurrence(NOW),
    }
    values.update(updates)
    return RetrievalRequestV1(**values)  # type: ignore[arg-type]


def artifact(**updates: object) -> RetrievedArtifactV1:
    provenance = RetrievalProvenance(
        SEARCH_REQUEST,
        RESULT_ID,
        RETRIEVAL_ID,
        ATTEMPT_ID,
        SOURCE_URL,
        RetrievalTransportReference("transport:future-http-1"),
        CORRELATION,
        (),
    )
    values: dict[str, object] = {
        "artifact_id": ARTIFACT_ID,
        "retrieval_request_id": RETRIEVAL_ID,
        "retrieval_attempt_id": ATTEMPT_ID,
        "source_result_id": RESULT_ID,
        "source_url": SOURCE_URL,
        "outcome": RetrievalOutcome.RETRIEVED,
        "retrieval_occurrence": SearchOccurrence(NOW + timedelta(seconds=2)),
        "provenance": provenance,
        "observed_final_url": "https://cdn.example.com/document",
        "reported_content_type": "Text/HTML; charset=utf-8",
        "normalized_content_type": "text/html",
        "content_length": 500,
        "checksum": CHECKSUM,
        "content_reference": ArtifactContentReference("artifact-body:transient-1"),
    }
    values.update(updates)
    return RetrievedArtifactV1(**values)  # type: ignore[arg-type]


def extraction_request(**updates: object) -> ExtractionRequestV1:
    values: dict[str, object] = {
        "extraction_request_id": ExtractionRequestId("search-extraction-request:request-1"),
        "artifact_id": ARTIFACT_ID,
        "retrieval_request_id": RETRIEVAL_ID,
        "capability": ExtractionCapability.HTML_TO_TEXT,
        "requester": RequesterReference("principal:owner"),
        "policy_reference": PolicyReference("policy:extraction-v1"),
        "correlation": CORRELATION,
        "causation": (),
        "occurrence": SearchOccurrence(NOW + timedelta(seconds=3)),
    }
    values.update(updates)
    return ExtractionRequestV1(**values)  # type: ignore[arg-type]


def extracted(**updates: object) -> ExtractedContentV1:
    request = extraction_request()
    attempt = ExtractionAttemptId("search-extraction-attempt:attempt-1")
    extractor = ExtractorReference("extractor:future-html-v1")
    provenance = ExtractionProvenance(
        SEARCH_REQUEST,
        RESULT_ID,
        RETRIEVAL_ID,
        ARTIFACT_ID,
        request.extraction_request_id,
        attempt,
        extractor,
        CORRELATION,
    )
    values: dict[str, object] = {
        "extracted_content_id": ExtractedContentId("search-extracted-content:content-1"),
        "extraction_request_id": request.extraction_request_id,
        "extraction_attempt_id": attempt,
        "artifact_id": ARTIFACT_ID,
        "capability": request.capability,
        "outcome": ExtractionOutcome.EXTRACTED,
        "extractor_reference": extractor,
        "extractor_version": "future-v1",
        "occurrence": SearchOccurrence(NOW + timedelta(seconds=4)),
        "provenance": provenance,
        "content_reference": ExtractedContentReference("extracted-text:transient-1"),
        "content_checksum": ExtractedContentChecksum("sha256:" + "b" * 64),
        "observed_text_length": 42,
        "delivered_text_length": 42,
        "limitations": ("reference-only",),
    }
    values.update(updates)
    return ExtractedContentV1(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("identity", "value"),
    [
        (RetrievalRequestId, "search-retrieval-request:one"),
        (RetrievalAttemptId, "search-retrieval-attempt:one"),
        (RetrievedArtifactId, "search-artifact:one"),
        (ExtractionRequestId, "search-extraction-request:one"),
        (ExtractionAttemptId, "search-extraction-attempt:one"),
        (ExtractedContentId, "search-extracted-content:one"),
    ],
)
def test_retrieval_and_extraction_identities_are_opaque(identity, value) -> None:
    assert str(identity(value)) == value
    with pytest.raises(ValueError):
        identity(SOURCE_URL)


def test_retrieval_is_explicit_immutable_and_corresponds_to_search_result() -> None:
    value = RetrievalRequestV1.for_result(
        retrieval_request_id=RETRIEVAL_ID,
        result=search_result(),
        search_request_id=SEARCH_REQUEST,
        requester=RequesterReference("principal:owner"),
        accepted_content_types=("TEXT/HTML",),
        maximum_bytes=1000,
        policy_reference=PolicyReference("policy:retrieval-v1"),
        correlation=CORRELATION,
        causation=(),
        occurrence=SearchOccurrence(NOW),
    )
    assert value.accepted_content_types == ("text/html",)
    assert not hasattr(search_result(), "retrieval_executed")
    with pytest.raises(FrozenInstanceError):
        value.source_url = "https://other.example"  # type: ignore[misc]


def test_retrieval_request_rejects_wrong_result_lineage_and_transport_fields() -> None:
    with pytest.raises(SearchValidationError, match="correspond"):
        RetrievalRequestV1.for_result(
            retrieval_request_id=RETRIEVAL_ID,
            result=search_result(),
            search_request_id=SearchRequestId("search-request:wrong"),
            requester=RequesterReference("principal:owner"),
            accepted_content_types=("text/html",),
            maximum_bytes=1000,
            policy_reference=PolicyReference("policy:retrieval-v1"),
            correlation=CORRELATION,
            causation=(),
            occurrence=SearchOccurrence(NOW),
        )
    assert {"headers", "cookies", "credentials", "browser_instructions", "prompt"}.isdisjoint(
        {item.name for item in fields(RetrievalRequestV1)}
    )


def test_artifact_metadata_checksum_redirect_and_reference_are_separate_facts() -> None:
    value = artifact()
    value.validate_correspondence(retrieval_request())
    assert value.artifact_id.value != value.source_url
    assert value.checksum != value.artifact_id
    assert value.observed_final_url == "https://cdn.example.com/document"
    assert value.content_reference is not None
    assert not hasattr(value, "raw_payload")
    assert not hasattr(value, "publisher_canonical_url")


@pytest.mark.parametrize(
    "outcome",
    [
        RetrievalOutcome.NOT_FOUND,
        RetrievalOutcome.POLICY_BLOCKED,
        RetrievalOutcome.UNAVAILABLE,
        RetrievalOutcome.TIMEOUT,
        RetrievalOutcome.TOO_LARGE,
        RetrievalOutcome.UNSUPPORTED_CONTENT,
        RetrievalOutcome.MALFORMED_SOURCE,
        RetrievalOutcome.FAILED,
    ],
)
def test_non_success_retrieval_outcomes_never_claim_payload(outcome: RetrievalOutcome) -> None:
    value = artifact(
        outcome=outcome,
        content_length=None,
        checksum=None,
        content_reference=None,
        normalized_content_type=None,
    )
    assert value.outcome is outcome


def test_size_content_type_wrong_source_and_stale_artifact_fail_correspondence() -> None:
    with pytest.raises(SearchValidationError, match="maximum"):
        artifact(content_length=2_000_000).validate_correspondence(retrieval_request())
    with pytest.raises(SearchValidationError, match="unsupported"):
        artifact(normalized_content_type="application/pdf").validate_correspondence(retrieval_request())
    with pytest.raises(SearchValidationError, match="correspond"):
        artifact().validate_correspondence(retrieval_request(source_url="https://other.example/a"))
    with pytest.raises(SearchValidationError, match="stale"):
        artifact(retrieval_occurrence=SearchOccurrence(NOW - timedelta(seconds=1))).validate_correspondence(retrieval_request())


def test_extraction_is_explicit_separate_and_pdf_capability_is_future_unsupported() -> None:
    value = ExtractionRequestV1.for_artifact(
        extraction_request_id=ExtractionRequestId("search-extraction-request:request-1"),
        artifact=artifact(),
        capability=ExtractionCapability.HTML_TO_TEXT,
        requester=RequesterReference("principal:owner"),
        policy_reference=PolicyReference("policy:extraction-v1"),
        correlation=CORRELATION,
        causation=(),
        occurrence=SearchOccurrence(NOW + timedelta(seconds=3)),
    )
    assert value.artifact_id == ARTIFACT_ID
    with pytest.raises(SearchValidationError, match="PDF"):
        replace(value, capability=ExtractionCapability.PDF_TO_TEXT_FUTURE)


def test_retrieval_success_does_not_imply_extraction_success() -> None:
    failed = extracted(
        outcome=ExtractionOutcome.EXTRACTOR_UNAVAILABLE,
        content_reference=None,
        content_checksum=None,
        observed_text_length=None,
        delivered_text_length=None,
    )
    assert artifact().outcome is RetrievalOutcome.RETRIEVED
    assert failed.outcome is ExtractionOutcome.EXTRACTOR_UNAVAILABLE


def test_extracted_content_lineage_and_wrong_artifact_are_validated() -> None:
    value = extracted()
    value.validate_correspondence(extraction_request(), artifact())
    with pytest.raises(SearchValidationError, match="lineage"):
        value.validate_correspondence(
            extraction_request(artifact_id=RetrievedArtifactId("search-artifact:wrong")),
            artifact(),
        )


def test_provider_snippet_extracted_content_and_agent_summary_are_distinct() -> None:
    value = extracted(agent_summary_reference=AgentSummaryReference("agent-summary:future-1"))
    assert search_result().provider_snippet == "Provider snippet only."
    assert value.content_reference == ExtractedContentReference("extracted-text:transient-1")
    assert value.agent_summary_reference == AgentSummaryReference("agent-summary:future-1")
    assert not hasattr(value, "agent_summary")
    assert not hasattr(value, "provider_snippet")


def test_multimodal_artifact_is_reference_only_and_not_interpreted() -> None:
    image = artifact(
        reported_content_type="image/png",
        normalized_content_type="image/png",
        content_reference=ArtifactContentReference("artifact-body:image-1"),
    )
    image.validate_correspondence(
        retrieval_request(accepted_content_types=("image/png",))
    )
    assert not hasattr(image, "image_interpretation")
    assert not hasattr(image, "perception_result")


def test_identical_and_contradictory_observations_are_explicit() -> None:
    first = artifact()
    repeated = replace(first, retrieval_occurrence=SearchOccurrence(NOW + timedelta(seconds=9)))
    assert classify_observation_repetition(None, first) is ObservationRepetition.FIRST
    assert classify_observation_repetition(first, repeated) is ObservationRepetition.IDENTICAL
    assert classify_observation_repetition(first, replace(first, checksum=ArtifactChecksum("sha256:" + "c" * 64))) is ObservationRepetition.CONTRADICTORY


def test_search_retrieval_extraction_occurrences_are_independent_and_lateness_is_factual() -> None:
    assert search_result().search_occurrence.occurred_at < retrieval_request().occurrence.occurred_at
    assert retrieval_request().occurrence.occurred_at < extraction_request().occurrence.occurred_at
    assert observation_is_late(retrieval_request().occurrence, artifact().retrieval_occurrence, 1)
    assert artifact().retrieval_occurrence.occurred_at != search_result().publication_date


def test_occurrence_does_not_change_semantic_fingerprints_or_lineage() -> None:
    first = retrieval_request()
    second = replace(first, occurrence=SearchOccurrence(NOW + timedelta(hours=1)))
    assert first.semantic_fingerprint == second.semantic_fingerprint
    content = extracted()
    later = replace(content, occurrence=SearchOccurrence(NOW + timedelta(hours=1)))
    assert content.semantic_fingerprint == later.semantic_fingerprint
    assert content.canonical_serialization() != later.canonical_serialization()
