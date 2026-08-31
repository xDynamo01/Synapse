from __future__ import annotations

import json
from dataclasses import fields, replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from synapse.search import (
    CorrelationReference,
    DomainConstraints,
    FreshnessConstraint,
    FreshnessKind,
    PolicyReference,
    ProviderTimeoutContract,
    RequesterReference,
    SafeSearchMode,
    SearchErrorCode,
    SearchInvocationId,
    SearchOccurrence,
    SearchProviderCapability,
    SearchProviderHealthStatus,
    SearchProviderInvocationV1,
    SearchProviderReference,
    SearchProviderResultStatus,
    SearchPurpose,
    SearchRequestId,
    SearchRequestOccurrence,
    SearchRequestV1,
    SearchValidationError,
    required_capabilities,
)
from synapse.search_adapters import (
    SearXNGAdapter,
    SearXNGAdapterConfig,
    SearXNGCategoryMapping,
    SearXNGTransportRequest,
    SearXNGTransportResponse,
)

NOW = datetime(2026, 8, 12, 18, 0, tzinfo=UTC)
PROVIDER = SearchProviderReference("provider:searxng-local")
FIXTURES = Path(__file__).parent / "fixtures" / "search"


def load_fixture(name: str) -> object:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def config(**updates: object) -> SearXNGAdapterConfig:
    values: dict[str, object] = {
        "provider": PROVIDER,
        "base_url": "http://searxng.invalid:8080",
        "category_mappings": (
            SearXNGCategoryMapping("news", "news"),
            SearXNGCategoryMapping("technical", "science"),
        ),
    }
    values.update(updates)
    return SearXNGAdapterConfig(**values)  # type: ignore[arg-type]


def request(**updates: object) -> SearchRequestV1:
    values: dict[str, object] = {
        "request_id": SearchRequestId("search-request:searxng-1"),
        "requester": RequesterReference("principal:owner"),
        "query": "provider neutral query",
        "purpose": SearchPurpose("technical.research"),
        "correlation": CorrelationReference("correlation:searxng-1"),
        "occurrence": SearchRequestOccurrence(NOW),
    }
    values.update(updates)
    return SearchRequestV1(**values)  # type: ignore[arg-type]


def invocation(
    search_request: SearchRequestV1 | None = None,
    *,
    provider: SearchProviderReference = PROVIDER,
) -> SearchProviderInvocationV1:
    value = search_request or request()
    return SearchProviderInvocationV1(
        invocation_id=SearchInvocationId("search-invocation:searxng-1"),
        request=value,
        request_id=value.request_id,
        request_fingerprint=value.semantic_fingerprint,
        provider=provider,
        required_capabilities=required_capabilities(value),
        correlation=value.correlation,
        causation=(),
        occurrence=SearchOccurrence(NOW),
        timeout=ProviderTimeoutContract(20),
        policy_reference=PolicyReference("policy:future-egress"),
    )


class FakeTransport:
    def __init__(self, payload: object, *, status_code: int = 200) -> None:
        self.payload = payload
        self.status_code = status_code
        self.requests: list[SearXNGTransportRequest] = []

    def exchange(self, request: SearXNGTransportRequest) -> SearXNGTransportResponse:
        self.requests.append(request)
        return SearXNGTransportResponse(self.status_code, self.payload, NOW)


def parameters(value: SearXNGTransportRequest) -> dict[str, str]:
    return dict(value.parameters)


def test_valid_config_is_typed_but_does_not_claim_reachability() -> None:
    value = config()
    adapter = SearXNGAdapter(value)
    assert value.base_url == "http://searxng.invalid:8080"
    assert adapter.health.status is SearchProviderHealthStatus.CONFIGURED
    assert adapter.health.reachable.value == "unknown"


@pytest.mark.parametrize(
    "base_url",
    [
        "",
        "ftp://example.com",
        "https://user:secret@example.com",
        "https://example.com/path",
        "https://example.com?query=x",
        "https://example.com/#fragment",
        "https://example.com:99999",
    ],
)
def test_invalid_base_url_is_rejected_without_dns_or_network(base_url: str) -> None:
    with pytest.raises(SearchValidationError, match="SearXNG"):
        config(base_url=base_url)


def test_query_language_categories_safe_search_limit_and_format_translation() -> None:
    value = request(
        language="pt-BR",
        categories=("technical", "news"),
        safe_search=SafeSearchMode.STRICT,
        result_limit=20,
    )
    translated = SearXNGAdapter(config()).translate_invocation(invocation(value))
    assert translated.method == "GET"
    assert translated.endpoint_path == "/search"
    assert parameters(translated) == {
        "q": "provider neutral query",
        "format": "json",
        "language": "pt-br",
        "categories": "news,science",
        "safesearch": "2",
        "limit": "20",
    }


def test_unknown_category_is_never_forwarded_by_fallback() -> None:
    value = request(categories=("unknown",))
    with pytest.raises(SearchValidationError, match="no explicit"):
        SearXNGAdapter(config()).translate_invocation(invocation(value))


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [(86400, "day"), (2592000, "month"), (31536000, "year")],
)
def test_exact_supported_freshness_windows_are_translated(seconds: int, expected: str) -> None:
    value = request(freshness=FreshnessConstraint(FreshnessKind.WINDOW, window_seconds=seconds))
    translated = SearXNGAdapter(config()).translate_invocation(invocation(value))
    assert parameters(translated)["time_range"] == expected


@pytest.mark.parametrize(
    "constraint",
    [
        FreshnessConstraint(FreshnessKind.WINDOW, window_seconds=3600),
        FreshnessConstraint(FreshnessKind.AFTER, after=NOW),
        FreshnessConstraint(FreshnessKind.BEFORE, before=NOW),
    ],
)
def test_unrepresentable_freshness_is_not_approximated(constraint: FreshnessConstraint) -> None:
    with pytest.raises(SearchValidationError, match="cannot be represented"):
        SearXNGAdapter(config()).translate_invocation(invocation(request(freshness=constraint)))


def test_domain_constraint_is_declared_unsupported_and_not_ignored() -> None:
    adapter = SearXNGAdapter(config())
    assert adapter.capabilities.support_for(SearchProviderCapability.DOMAIN_CONSTRAINTS).value == "unsupported"
    value = request(domains=DomainConstraints(include=("example.com",)))
    result = adapter.invoke(invocation(value))
    assert result.status is SearchProviderResultStatus.UNSUPPORTED_CAPABILITY


def test_normal_fixture_maps_results_snippets_dates_metadata_and_provider_identity() -> None:
    adapter = SearXNGAdapter(config())
    result = adapter.parse_response(invocation(), load_fixture("searxng_results.json"), NOW)
    assert result.status is SearchProviderResultStatus.RESULTS
    assert result.provider is PROVIDER
    assert result.result_set is not None and len(result.result_set.results) == 4
    first = result.result_set.results[0]
    assert first.provider_snippet == "Snippet returned by SearXNG."
    assert first.retrieved_content_reference is None
    assert first.publication_date == datetime(2026, 8, 12, 16, 30, tzinfo=UTC)
    assert first.provider_position == first.normalized_rank == 1
    metadata = {(item.namespace, item.key): item.value for item in first.provider_metadata}
    assert metadata[("searxng", "engines")] == "engine-a,engine-b"
    assert metadata[("searxng", "score")] == "1.25"
    assert all(item.provider is PROVIDER for item in result.result_set.results)


def test_invalid_or_absent_dates_remain_unknown_with_safe_diagnostic() -> None:
    result = SearXNGAdapter(config()).parse_response(
        invocation(), load_fixture("searxng_results.json"), NOW
    )
    assert result.result_set is not None
    assert result.result_set.results[2].publication_date is None
    assert result.result_set.results[3].publication_date is None
    assert len(result.result_set.diagnostics) == 1
    assert result.result_set.diagnostics[0].code is SearchErrorCode.PROVENANCE_INCOMPLETE


def test_url_normalization_dedup_and_ranking_use_search_v1_services() -> None:
    adapter = SearXNGAdapter(config())
    provider_result = adapter.parse_response(
        invocation(), load_fixture("searxng_results.json"), NOW
    )
    assert provider_result.result_set is not None
    view = adapter.normalized_projection(provider_result)
    first_normalization = next(
        item.normalization
        for item in view.normalizations
        if item.result_id == provider_result.result_set.results[0].result_id
    )
    assert first_normalization.original_url.startswith("HTTPS://")
    assert first_normalization.search_normalized_url == "https://example.com/article"
    assert len(view.duplicate_groups) == 1
    assert [item.normalized_rank for item in view.deduplicated_ranked_view] == [1, 2, 3]


def test_no_results_is_valid_and_distinct_from_malformed_payload() -> None:
    adapter = SearXNGAdapter(config())
    empty = adapter.parse_response(invocation(), load_fixture("searxng_no_results.json"), NOW)
    malformed = adapter.parse_response(invocation(), load_fixture("searxng_malformed_root.json"), NOW)
    assert empty.status is SearchProviderResultStatus.NO_RESULTS
    assert empty.result_set is not None and empty.result_set.results == ()
    assert malformed.status is SearchProviderResultStatus.MALFORMED_RESPONSE
    assert malformed.result_set is None


def test_malformed_entry_and_wrong_root_shape_are_fail_closed() -> None:
    adapter = SearXNGAdapter(config())
    entry = adapter.parse_response(invocation(), load_fixture("searxng_malformed_entry.json"), NOW)
    root = adapter.parse_response(invocation(), [], NOW)
    assert entry.status is SearchProviderResultStatus.MALFORMED_RESPONSE
    assert root.status is SearchProviderResultStatus.MALFORMED_RESPONSE


def test_invocation_correspondence_rejects_wrong_provider() -> None:
    with pytest.raises(SearchValidationError, match="provider identity mismatch"):
        SearXNGAdapter(config()).translate_invocation(
            invocation(provider=SearchProviderReference("provider:other"))
        )


def test_fake_transport_is_the_only_execution_boundary_and_receives_safe_request() -> None:
    transport = FakeTransport(load_fixture("searxng_no_results.json"))
    result = SearXNGAdapter(config(), transport).invoke(invocation())
    assert result.status is SearchProviderResultStatus.NO_RESULTS
    assert len(transport.requests) == 1
    assert not any(key.lower() in {"authorization", "api_key", "token"} for key, _ in transport.requests[0].parameters)


def test_without_transport_adapter_is_configured_but_operationally_unavailable() -> None:
    adapter = SearXNGAdapter(config())
    result = adapter.invoke(invocation())
    assert adapter.health.status is SearchProviderHealthStatus.CONFIGURED
    assert result.status is SearchProviderResultStatus.PROVIDER_UNAVAILABLE


def test_adapter_config_and_transport_are_not_search_domain_fields() -> None:
    invocation_fields = {item.name for item in fields(SearchProviderInvocationV1)}
    assert {"base_url", "endpoint_path", "searxng_category", "transport"}.isdisjoint(
        invocation_fields
    )
    assert replace(config(), endpoint_path="/search").provider is PROVIDER
