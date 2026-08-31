from __future__ import annotations

import json
from dataclasses import FrozenInstanceError, fields, replace
from datetime import UTC, datetime, timedelta

import pytest

from synapse.search import (
    AgentSummaryReference,
    CorrelationReference,
    ExtractedTextReference,
    FreshnessConstraint,
    FreshnessFacts,
    FreshnessKind,
    FreshnessStatus,
    NormalizedSearchResultV1,
    ProviderMetadataEntry,
    ProviderResultReference,
    PublicationDateProvenance,
    RetrievedContentReference,
    SearchFingerprint,
    SearchInvocationId,
    SearchOccurrence,
    SearchOutcomeCode,
    SearchProviderReference,
    SearchRequestId,
    SearchResultId,
    SearchResultProvenance,
    SearchResultSetId,
    SearchResultSetProvenance,
    SearchResultSetV1,
    SearchSourceReference,
    SearchValidationError,
)

NOW = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)
REQUEST_ID = SearchRequestId("search-request:req-001")
REQUEST_FINGERPRINT = SearchFingerprint("sha256:" + "1" * 64)
PROVIDER = SearchProviderReference("provider:neutral-1")
INVOCATION = SearchInvocationId("search-invocation:inv-001")
OCCURRENCE = SearchOccurrence(NOW)


def freshness(
    constraint: FreshnessConstraint | None = None,
    publication_date: datetime | None = NOW - timedelta(hours=1),
    provider_reported_date: datetime | None = NOW - timedelta(hours=1),
) -> FreshnessFacts:
    return FreshnessFacts.from_observation(
        constraint or FreshnessConstraint(FreshnessKind.WINDOW, window_seconds=86400),
        publication_date=publication_date,
        provider_reported_date=provider_reported_date,
        search_occurrence=OCCURRENCE,
    )


def result(index: int = 1, **updates: object) -> NormalizedSearchResultV1:
    result_id = SearchResultId(f"search-result:result-{index}")
    source_url = f"https://example.com/item-{index}?tracking=preserved"
    provider_reference = ProviderResultReference(f"provider-result:item-{index}")
    values: dict[str, object] = {
        "result_id": result_id,
        "source_url": source_url,
        "canonical_url": f"https://provider.example/canonical-{index}",
        "title": f"Observed title {index}",
        "provider_snippet": "Provider-returned snippet only.",
        "source": SearchSourceReference("source:example.com"),
        "provider": PROVIDER,
        "provider_result_reference": provider_reference,
        "provider_position": index,
        "normalized_rank": index,
        "search_occurrence": OCCURRENCE,
        "publication_date": NOW - timedelta(hours=1),
        "publication_date_provenance": PublicationDateProvenance.PROVIDER_EXPLICIT,
        "provider_reported_date": NOW - timedelta(hours=1),
        "freshness": freshness(),
        "provenance": SearchResultProvenance(
            request_id=REQUEST_ID,
            request_fingerprint=REQUEST_FINGERPRINT,
            provider=PROVIDER,
            provider_invocation=INVOCATION,
            result_id=result_id,
            provider_result_reference=provider_reference,
            source_url=source_url,
            search_occurrence=OCCURRENCE,
            provider_position=index,
            correlation=CorrelationReference("correlation:turn-1"),
        ),
    }
    values.update(updates)
    return NormalizedSearchResultV1(**values)  # type: ignore[arg-type]


def result_set(
    results: tuple[NormalizedSearchResultV1, ...] | None = None,
    outcome: SearchOutcomeCode = SearchOutcomeCode.RESULTS,
    **updates: object,
) -> SearchResultSetV1:
    values: dict[str, object] = {
        "result_set_id": SearchResultSetId("search-result-set:set-001"),
        "request_id": REQUEST_ID,
        "request_fingerprint": REQUEST_FINGERPRINT,
        "provider": PROVIDER,
        "provider_invocation": INVOCATION,
        "outcome": outcome,
        "results": (result(),) if results is None else results,
        "search_occurrence": OCCURRENCE,
        "provenance": SearchResultSetProvenance(
            request_id=REQUEST_ID,
            request_fingerprint=REQUEST_FINGERPRINT,
            provider=PROVIDER,
            provider_invocation=INVOCATION,
            search_occurrence=OCCURRENCE,
            correlation=CorrelationReference("correlation:turn-1"),
        ),
    }
    values.update(updates)
    return SearchResultSetV1(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("identity", "value"),
    [
        (SearchResultId, "search-result:opaque-1"),
        (SearchResultSetId, "search-result-set:opaque-1"),
        (SearchSourceReference, "source:example.com"),
        (SearchProviderReference, "provider:neutral"),
        (ProviderResultReference, "provider-result:opaque"),
    ],
)
def test_result_identities_are_opaque_typed_and_not_urls_or_positions(identity, value) -> None:
    assert str(identity(value)) == value
    with pytest.raises(ValueError):
        identity("https://example.com/item")


def test_normalized_result_is_immutable_and_preserves_provider_facts() -> None:
    value = result(language="PT-br", content_type="Application/PDF", source_label="Example")
    assert value.provider_position == value.normalized_rank == 1
    assert value.source_domain == "example.com"
    assert value.language == "pt-br"
    assert value.content_type == "application/pdf"
    assert value.canonical_url == "https://provider.example/canonical-1"
    assert "tracking=preserved" in value.source_url
    with pytest.raises(FrozenInstanceError):
        value.title = "changed"  # type: ignore[misc]


def test_snippet_and_future_content_references_are_distinct() -> None:
    value = result(
        retrieved_content_reference=RetrievedContentReference("retrieved:future-1"),
        extracted_text_reference=ExtractedTextReference("extracted:future-1"),
        agent_summary_reference=AgentSummaryReference("agent-summary:future-1"),
    )
    assert value.provider_snippet == "Provider-returned snippet only."
    assert str(value.retrieved_content_reference) == "retrieved:future-1"
    assert str(value.extracted_text_reference) == "extracted:future-1"
    assert str(value.agent_summary_reference) == "agent-summary:future-1"
    assert not hasattr(value, "retrieved_content")
    assert not hasattr(value, "agent_summary")


@pytest.mark.parametrize("url", ["", "ftp://example.com/a", "https://localhost/a", "not a url"])
def test_url_validation_is_structural_and_fails_closed(url: str) -> None:
    with pytest.raises(SearchValidationError, match="URL"):
        result(source_url=url)


def test_provider_canonical_url_is_preserved_without_normalization_or_trust() -> None:
    supplied = "HTTPS://Provider.Example/item?utm_source=still-present"
    value = result(canonical_url=supplied)
    assert value.canonical_url == supplied
    assert "canonical_url_is_trusted" not in {item.name for item in fields(value)}


def test_publication_date_provenance_is_explicit_and_unknown_carries_no_date() -> None:
    unknown_freshness = freshness(publication_date=None, provider_reported_date=None)
    value = result(
        publication_date=None,
        provider_reported_date=None,
        publication_date_provenance=PublicationDateProvenance.UNKNOWN,
        freshness=unknown_freshness,
    )
    assert value.publication_date is None
    assert value.freshness.status is FreshnessStatus.UNKNOWN
    with pytest.raises(SearchValidationError, match="unknown publication"):
        replace(value, publication_date=NOW)


def test_provider_reported_date_is_not_implicitly_a_publication_date() -> None:
    reported = NOW - timedelta(hours=2)
    facts = freshness(publication_date=None, provider_reported_date=reported)
    value = result(
        publication_date=None,
        provider_reported_date=reported,
        publication_date_provenance=PublicationDateProvenance.UNKNOWN,
        freshness=facts,
    )
    assert value.provider_reported_date == reported
    assert value.publication_date is None
    assert value.freshness.status is FreshnessStatus.UNKNOWN


@pytest.mark.parametrize(
    ("constraint", "publication", "expected"),
    [
        (FreshnessConstraint(), None, FreshnessStatus.NOT_REQUESTED),
        (
            FreshnessConstraint(FreshnessKind.WINDOW, window_seconds=86400),
            NOW - timedelta(hours=2),
            FreshnessStatus.SATISFIED,
        ),
        (
            FreshnessConstraint(FreshnessKind.WINDOW, window_seconds=3600),
            NOW - timedelta(hours=2),
            FreshnessStatus.VIOLATED,
        ),
        (
            FreshnessConstraint(FreshnessKind.WINDOW, window_seconds=86400),
            None,
            FreshnessStatus.UNKNOWN,
        ),
    ],
)
def test_freshness_is_derived_from_evidence_without_filtering(
    constraint: FreshnessConstraint,
    publication: datetime | None,
    expected: FreshnessStatus,
) -> None:
    facts = freshness(constraint, publication, publication)
    assert facts.status is expected


def test_freshness_cannot_claim_satisfied_without_support() -> None:
    with pytest.raises(SearchValidationError, match="freshness status"):
        FreshnessFacts(
            FreshnessConstraint(FreshnessKind.WINDOW, window_seconds=86400),
            FreshnessStatus.SATISFIED,
            None,
            None,
            OCCURRENCE,
        )


def test_provenance_mismatch_is_rejected() -> None:
    base = result()
    with pytest.raises(SearchValidationError, match="correspond"):
        replace(base, source_url="https://different.example/item")
    with pytest.raises(SearchValidationError, match="correspond"):
        replace(base, provider_position=2)


def test_provider_metadata_is_namespaced_sorted_and_excluded_from_core_semantics() -> None:
    first = result(
        provider_metadata=(
            ProviderMetadataEntry("neutral", "score", 10),
            ProviderMetadataEntry("neutral", "engine-label", "alpha"),
        )
    )
    second = replace(first, provider_metadata=(ProviderMetadataEntry("other", "score", 99),))
    assert first.provider_metadata[0].key == "engine-label"
    assert first.semantic_fingerprint == second.semantic_fingerprint
    with pytest.raises(SearchValidationError, match="sensitive"):
        ProviderMetadataEntry("neutral", "api_token", "redacted")


def test_result_canonical_serialization_and_fingerprint_are_deterministic() -> None:
    first = result()
    payload = json.loads(first.canonical_serialization())
    assert payload["result"]["format_version"] == "normalized-search-result-v1"
    assert payload["semantic_fingerprint"].startswith("sha256:")
    assert first.canonical_serialization() == first.canonical_serialization()
    changed_occurrence = SearchOccurrence(NOW + timedelta(minutes=1))
    changed_provenance = replace(first.provenance, search_occurrence=changed_occurrence)
    changed_freshness = replace(first.freshness, search_occurrence=changed_occurrence)
    second = replace(
        first,
        search_occurrence=changed_occurrence,
        provenance=changed_provenance,
        freshness=changed_freshness,
    )
    assert first.semantic_fingerprint == second.semantic_fingerprint
    assert first.canonical_serialization() != second.canonical_serialization()


def test_results_result_set_preserves_order_and_distinct_ranks() -> None:
    value = result_set(results=(result(1), result(2)))
    assert value.outcome is SearchOutcomeCode.RESULTS
    assert [item.provider_position for item in value.results] == [1, 2]
    assert [item.normalized_rank for item in value.results] == [1, 2]


def test_no_results_is_valid_empty_observation_not_provider_failure() -> None:
    value = result_set(results=(), outcome=SearchOutcomeCode.NO_RESULTS)
    assert value.results == ()
    assert value.diagnostics == ()
    assert value.provenance.request_id == REQUEST_ID
    assert value.outcome.value not in {"provider_timeout", "provider_unavailable"}


@pytest.mark.parametrize(
    ("outcome", "items", "message"),
    [
        (SearchOutcomeCode.NO_RESULTS, (result(),), "NO_RESULTS"),
        (SearchOutcomeCode.RESULTS, (), "RESULTS"),
    ],
)
def test_result_set_outcome_and_structure_must_correspond(outcome, items, message) -> None:
    with pytest.raises(SearchValidationError, match=message):
        result_set(results=items, outcome=outcome)


def test_result_set_rejects_duplicate_id_position_and_invalid_normalized_rank() -> None:
    first = result(1)
    with pytest.raises(SearchValidationError, match="identities"):
        result_set(results=(first, replace(first, normalized_rank=2)))
    second = result(2)
    duplicate_position = replace(
        second,
        provider_position=1,
        provenance=replace(second.provenance, provider_position=1),
    )
    with pytest.raises(SearchValidationError, match="positions"):
        result_set(results=(first, duplicate_position))
    with pytest.raises(SearchValidationError, match="normalized ranks"):
        result_set(results=(replace(first, normalized_rank=2),))


def test_result_set_rejects_request_provider_invocation_and_provenance_mismatch() -> None:
    with pytest.raises(SearchValidationError, match="correspond"):
        result_set(request_id=SearchRequestId("search-request:other"))
    with pytest.raises(SearchValidationError, match="provenance mismatch"):
        result_set(
            results=(),
            outcome=SearchOutcomeCode.NO_RESULTS,
            provider=SearchProviderReference("provider:other"),
        )


def test_result_set_serialization_and_fingerprint_are_deterministic() -> None:
    value = result_set(results=(result(1), result(2)))
    payload = json.loads(value.canonical_serialization())
    assert payload["result_set"]["format_version"] == "search-result-set-v1"
    assert payload["result_set"]["outcome"] == "results"
    assert value.canonical_serialization() == value.canonical_serialization()


def test_result_contract_contains_no_retrieval_payload_agent_reasoning_or_raw_response() -> None:
    names = {item.name for item in fields(NormalizedSearchResultV1)}
    assert {
        "retrieved_content",
        "extracted_text",
        "agent_summary",
        "evidence",
        "raw_provider_response",
        "credentials",
        "reasoning",
    }.isdisjoint(names)
