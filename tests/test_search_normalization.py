from __future__ import annotations

import json
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime

import pytest

from synapse.search import (
    TRACKING_PARAMETER_NAMES_V1,
    TRACKING_PARAMETER_POLICY_V1,
    TRACKING_PARAMETER_PREFIXES_V1,
    URL_NORMALIZATION_RULES_V1,
    CorrelationReference,
    DeduplicatedSearchViewV1,
    DuplicateClassification,
    DuplicateGroup,
    FreshnessConstraint,
    FreshnessFacts,
    NormalizedSearchResultV1,
    ProviderResultReference,
    PublicationDateProvenance,
    RepresentativeSelectionRule,
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
    UrlComponentChange,
    UrlNormalizationError,
    UrlNormalizationWarning,
    build_deduplicated_view,
    normalize_search_url,
    semantic_fingerprint,
)

NOW = datetime(2026, 8, 12, 15, 0, tzinfo=UTC)
REQUEST_ID = SearchRequestId("search-request:normalization-1")
REQUEST_FINGERPRINT = SearchFingerprint("sha256:" + "2" * 64)
PROVIDER = SearchProviderReference("provider:neutral-1")
INVOCATION = SearchInvocationId("search-invocation:normalization-1")
OCCURRENCE = SearchOccurrence(NOW)


def result(
    index: int,
    source_url: str,
    *,
    canonical_url: str | None = None,
    provider: SearchProviderReference = PROVIDER,
) -> NormalizedSearchResultV1:
    identity = SearchResultId(f"search-result:normalization-{index}")
    provider_reference = ProviderResultReference(f"provider-result:normalization-{index}")
    provenance = SearchResultProvenance(
        request_id=REQUEST_ID,
        request_fingerprint=REQUEST_FINGERPRINT,
        provider=provider,
        provider_invocation=INVOCATION,
        result_id=identity,
        provider_result_reference=provider_reference,
        source_url=source_url,
        search_occurrence=OCCURRENCE,
        provider_position=index,
        correlation=CorrelationReference("correlation:normalization-1"),
    )
    facts = FreshnessFacts.from_observation(
        FreshnessConstraint(),
        publication_date=None,
        provider_reported_date=None,
        search_occurrence=OCCURRENCE,
    )
    return NormalizedSearchResultV1(
        result_id=identity,
        source_url=source_url,
        canonical_url=canonical_url,
        title=f"Result {index}",
        provider_snippet=None,
        source=SearchSourceReference(f"source:normalization-{index}"),
        provider=provider,
        provider_result_reference=provider_reference,
        provider_position=index,
        normalized_rank=index,
        search_occurrence=OCCURRENCE,
        freshness=facts,
        provenance=provenance,
        publication_date_provenance=PublicationDateProvenance.UNKNOWN,
    )


def result_set(*results: NormalizedSearchResultV1) -> SearchResultSetV1:
    provenance = SearchResultSetProvenance(
        request_id=REQUEST_ID,
        request_fingerprint=REQUEST_FINGERPRINT,
        provider=PROVIDER,
        provider_invocation=INVOCATION,
        search_occurrence=OCCURRENCE,
    )
    return SearchResultSetV1(
        result_set_id=SearchResultSetId("search-result-set:normalization-1"),
        request_id=REQUEST_ID,
        request_fingerprint=REQUEST_FINGERPRINT,
        provider=PROVIDER,
        provider_invocation=INVOCATION,
        outcome=SearchOutcomeCode.RESULTS,
        results=tuple(results),
        search_occurrence=OCCURRENCE,
        provenance=provenance,
    )


def test_http_https_case_default_ports_fragment_and_root_are_normalized() -> None:
    http = normalize_search_url("HTTP://Example.COM:80/#section")
    https = normalize_search_url("HTTPS://Example.COM:443")
    assert http.search_normalized_url == "http://example.com"
    assert https.search_normalized_url == "https://example.com"
    assert {
        UrlComponentChange.SCHEME_CASE,
        UrlComponentChange.HOST_CASE_OR_IDNA,
        UrlComponentChange.DEFAULT_PORT,
        UrlComponentChange.ROOT_PATH,
        UrlComponentChange.FRAGMENT,
    }.issubset(http.changed_components)


def test_query_order_tracking_policy_unknowns_and_repeated_values_are_explicit() -> None:
    value = normalize_search_url(
        "https://example.com/items?z=last&utm_source=newsletter&a=1&a=2&fbclid=x&gclid=y"
    )
    assert value.search_normalized_url == "https://example.com/items?a=1&a=2&z=last"
    assert TRACKING_PARAMETER_NAMES_V1 == frozenset({"fbclid", "gclid"})
    assert TRACKING_PARAMETER_PREFIXES_V1 == ("utm_",)
    assert value.tracking_policy_version == TRACKING_PARAMETER_POLICY_V1
    assert UrlComponentChange.TRACKING_PARAMETERS in value.changed_components
    assert UrlNormalizationWarning.QUERY_ORDER_NORMALIZED in value.warnings


def test_unknown_query_parameters_and_repeated_parameter_order_are_preserved() -> None:
    value = normalize_search_url("https://example.com/?b=2&feature=x&feature=y&a=1")
    assert value.search_normalized_url == "https://example.com?a=1&b=2&feature=x&feature=y"


def test_percent_encoding_only_decodes_unreserved_and_normalizes_hex_case() -> None:
    value = normalize_search_url("https://example.com/%7euser/%2f?q=%41%2f")
    assert value.search_normalized_url == "https://example.com/~user/%2F?q=A%2F"
    assert UrlComponentChange.PERCENT_ENCODING in value.changed_components


def test_idna_is_deterministic_and_non_root_trailing_slash_is_preserved() -> None:
    value = normalize_search_url("https://BÜCHER.example/docs/")
    assert value.hostname == "xn--bcher-kva.example"
    assert value.search_normalized_url.endswith("/docs/")
    assert UrlNormalizationWarning.NON_ROOT_TRAILING_SLASH_PRESERVED in value.warnings


@pytest.mark.parametrize(
    "url",
    [
        "",
        "not-a-url",
        "ftp://example.com/file",
        "file:///private/file",
        "javascript://example.com/code",
        "data://example.com/value",
        "https://user:password@example.com/private",
        "https://localhost/item",
        "https://example.com/%ZZ",
        "https://example.com/line\nbreak",
    ],
)
def test_malformed_unsupported_and_unsafe_urls_fail_closed_without_network(url: str) -> None:
    with pytest.raises(UrlNormalizationError):
        normalize_search_url(url)


def test_provider_canonical_url_remains_separate_and_unverified() -> None:
    value = normalize_search_url(
        "https://example.com/original?utm_source=x",
        provider_canonical_url="https://publisher.example/declared",
    )
    assert value.original_url == "https://example.com/original?utm_source=x"
    assert value.provider_canonical_url == "https://publisher.example/declared"
    assert value.search_normalized_url == "https://example.com/original"
    assert UrlNormalizationWarning.PROVIDER_CANONICAL_UNVERIFIED in value.warnings


def test_normalized_url_identity_is_deterministic_but_not_a_result_identity() -> None:
    first = normalize_search_url("https://EXAMPLE.com:443/?utm_medium=email")
    second = normalize_search_url("https://example.com")
    assert first.normalized_url_fingerprint == second.normalized_url_fingerprint
    assert first.rules_version == URL_NORMALIZATION_RULES_V1
    assert not isinstance(first.normalized_url_fingerprint, SearchResultId)


def test_exact_original_duplicate_builds_separate_group_and_preserves_source_set() -> None:
    first = result(1, "https://example.com/item")
    second = result(2, "https://example.com/item")
    source = result_set(first, second)
    before = source.canonical_serialization()
    view = build_deduplicated_view(source)
    assert view.duplicate_groups[0].classification is DuplicateClassification.EXACT_ORIGINAL_URL_DUPLICATE
    assert view.duplicate_groups[0].representative_result_id == first.result_id
    assert len(view.full_ranked_view) == 2
    assert len(view.deduplicated_ranked_view) == 1
    assert source.canonical_serialization() == before
    with pytest.raises(FrozenInstanceError):
        view.source_result_set_id = SearchResultSetId("search-result-set:changed")  # type: ignore[misc]


def test_normalized_duplicate_uses_rank_position_identity_selection_rule() -> None:
    first = result(1, "HTTPS://Example.com:443/item?utm_source=x#fragment")
    second = result(2, "https://example.com/item")
    view = build_deduplicated_view(result_set(first, second))
    group = view.duplicate_groups[0]
    assert group.classification is DuplicateClassification.NORMALIZED_URL_DUPLICATE
    assert group.representative_result_id == first.result_id
    assert group.provider_positions == (1, 2)
    assert len(group.provenance) == 2


def test_provider_canonical_duplicate_is_distinct_from_search_normalized_duplicate() -> None:
    first = result(
        1,
        "https://one.example/item-a",
        canonical_url="https://publisher.example/article",
    )
    second = result(
        2,
        "https://two.example/item-b",
        canonical_url="HTTPS://publisher.example:443/article#top",
    )
    view = build_deduplicated_view(result_set(first, second))
    assert view.duplicate_groups[0].classification is DuplicateClassification.PROVIDER_CANONICAL_DUPLICATE


def test_same_domain_is_annotated_but_never_deduplicated() -> None:
    first = result(1, "https://example.com/one")
    second = result(2, "https://example.com/two")
    view = build_deduplicated_view(result_set(first, second))
    assert view.comparisons[0].classification is DuplicateClassification.SAME_DOMAIN_ONLY
    assert view.duplicate_groups == ()
    assert len(view.deduplicated_ranked_view) == 2


def test_different_sources_are_unique_not_not_comparable() -> None:
    view = build_deduplicated_view(
        result_set(result(1, "https://one.example/a"), result(2, "https://two.example/b"))
    )
    assert view.comparisons[0].classification is DuplicateClassification.UNIQUE


def test_full_and_deduplicated_ranks_are_gapless_and_provider_positions_unchanged() -> None:
    source = result_set(
        result(1, "https://example.com/a?utm_source=x"),
        result(2, "https://example.com/a"),
        result(3, "https://other.example/c"),
    )
    view = build_deduplicated_view(source)
    assert [item.normalized_rank for item in view.full_ranked_view] == [1, 2, 3]
    assert [item.normalized_rank for item in view.deduplicated_ranked_view] == [1, 2]
    assert [item.provider_position for item in view.full_ranked_view] == [1, 2, 3]
    assert [item.provider_position for item in source.results] == [1, 2, 3]


def test_freshness_does_not_change_ranking() -> None:
    first = result(1, "https://example.com/one")
    second = result(2, "https://other.example/two")
    changed_freshness = replace(
        second.freshness,
        provider_reported_date=NOW,
    )
    changed = replace(second, freshness=changed_freshness, provider_reported_date=NOW)
    baseline = build_deduplicated_view(result_set(first, second))
    altered = build_deduplicated_view(result_set(first, changed))
    assert baseline.full_ranked_view == altered.full_ranked_view


def test_duplicate_group_provenance_model_does_not_embed_provider_in_url_identity() -> None:
    first = result(1, "https://example.com/item")
    second_provider = SearchProviderReference("provider:neutral-2")
    second = result(2, "https://example.com/item", provider=second_provider)
    assert first.provenance.provider != second.provenance.provider
    assert normalize_search_url(first.source_url).normalized_url_fingerprint == normalize_search_url(
        second.source_url
    ).normalized_url_fingerprint
    normalized = normalize_search_url(first.source_url)
    group = DuplicateGroup(
        group_fingerprint=semantic_fingerprint(
            {"members": (first.result_id, second.result_id), "reason": "cross-provider"}
        ),
        classification=DuplicateClassification.EXACT_ORIGINAL_URL_DUPLICATE,
        member_result_ids=(first.result_id, second.result_id),
        representative_result_id=first.result_id,
        representative_rule=RepresentativeSelectionRule.RANK_POSITION_ID_V1,
        provider_positions=(1, 2),
        search_normalized_urls=(
            normalized.search_normalized_url,
            normalized.search_normalized_url,
        ),
        provenance=(first.provenance, second.provenance),
    )
    assert {item.provider for item in group.provenance} == {PROVIDER, second_provider}


def test_projection_and_fingerprints_are_deterministic_and_canonical() -> None:
    source = result_set(
        result(1, "https://example.com/a?utm_campaign=x"),
        result(2, "https://example.com/a"),
    )
    first = build_deduplicated_view(source)
    second = build_deduplicated_view(source)
    assert isinstance(first, DeduplicatedSearchViewV1)
    assert first == second
    assert first.semantic_fingerprint == second.semantic_fingerprint
    payload = json.loads(first.canonical_serialization())
    assert payload["deduplicated_view"]["format_version"] == "search-dedup-view-v1"


def test_occurrence_metadata_does_not_change_projection_semantic_fingerprint() -> None:
    source = result_set(
        result(1, "https://example.com/a?utm_campaign=x"),
        result(2, "https://example.com/a"),
    )
    changed_occurrence = SearchOccurrence(NOW.replace(hour=16))
    changed_results = tuple(
        replace(
            item,
            search_occurrence=changed_occurrence,
            freshness=replace(item.freshness, search_occurrence=changed_occurrence),
            provenance=replace(item.provenance, search_occurrence=changed_occurrence),
        )
        for item in source.results
    )
    changed = replace(
        source,
        results=changed_results,
        search_occurrence=changed_occurrence,
        provenance=replace(source.provenance, search_occurrence=changed_occurrence),
    )
    first = build_deduplicated_view(source)
    second = build_deduplicated_view(changed)
    assert first.semantic_fingerprint == second.semantic_fingerprint
    assert first.canonical_serialization() != second.canonical_serialization()


def test_projection_has_no_relevance_trust_llm_or_freshness_boost_fields() -> None:
    names = set(DeduplicatedSearchViewV1.__dataclass_fields__)
    assert {
        "relevance",
        "trust_score",
        "source_reputation",
        "llm_score",
        "semantic_similarity",
        "freshness_boost",
        "agent_feedback",
    }.isdisjoint(names)
